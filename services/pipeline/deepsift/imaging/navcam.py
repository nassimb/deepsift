"""ImageMissionAdapter + the MSL Navcam implementation (raw EDR, PDS Imaging Node).

Mission-specific knowledge (URLs, file naming, label fields) lives here; everything downstream uses the normalized
product record. A Perseverance adapter would implement the same interface.

Downlink byte accounting (declared; see docs/phase3-report.md § Byte accounting):
    estimated_downlink_bytes = LINES × LINE_SAMPLES × INST_CMPRS_RATE / 8
using the label's COMPRESSION_PARMS group (the compression actually applied onboard). For LOCO (lossless) the rate is
the measured bits/pixel; for ICER the rate is the byte budget the encoder stops at, so the estimate is an upper
bound. Packet/CCSDS framing and the label itself are not included. If any field is missing → None (UNKNOWN).
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from deepsift.core.config import DATA_DIR
from deepsift.imaging.pds3 import parse_label

NAV_BASE = "https://planetarydata.jpl.nasa.gov/img/data/msl/MSLNAV_0XXX"
RAW_ROOT = DATA_DIR / "raw" / "navcam"
NAME = re.compile(r"^N([LR])([AB])_(\d{9})EDR_([A-Z])(\d{3})(\d{4})([A-Z]{4}\d{5})M\d\.IMG$")
TIERS = {"F": "full", "D": "downsampled", "S": "subframe", "M": "mono_downsampled", "T": "thumbnail"}


@dataclass(frozen=True)
class ProductRef:
    sol: int
    name: str            # IMG file name
    url_img: str
    url_lbl: str
    listed_size: str


class ImageMissionAdapter(ABC):
    """Interface for any mission camera archive."""

    mission: str
    instrument: str

    @abstractmethod
    def discover_products(self, sols: list[int]) -> list[ProductRef]: ...

    @abstractmethod
    def fetch_metadata(self, ref: ProductRef) -> str: ...

    @abstractmethod
    def fetch_product(self, ref: ProductRef) -> tuple[Path, Path]: ...

    @abstractmethod
    def normalize_metadata(self, ref: ProductRef, label_text: str) -> dict: ...

    @abstractmethod
    def link_to_mission_time(self, record: dict) -> dict: ...


class CuriosityNavcamAdapter(ImageMissionAdapter):
    mission, instrument = "MSL", "NAVCAM"
    ROW = re.compile(r'indexcolname"><a href="([^"]+)">[^<]+</a></td><td class="indexcollastmod">[^<]*</td><td class="indexcolsize">\s*([^<]+)<')

    def __init__(self, root: Path = RAW_ROOT, client: httpx.Client | None = None):
        self.root = root
        self.client = client or httpx.Client(timeout=120, follow_redirects=True)

    def _get(self, url: str) -> bytes:
        """GET with polite backoff: the archive rate-limits (HTTP 429); Retry-After is honoured."""
        import time

        last = None
        for attempt in range(12):
            try:
                r = self.client.get(url)
                if r.status_code in (429, 502, 503, 504):
                    wait = float(r.headers.get("retry-after", 0) or 0) or min(60.0, 2.0 * 2 ** attempt)
                    time.sleep(wait)
                    last = f"HTTP {r.status_code}"
                    continue
                r.raise_for_status()
                return r.content
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(min(60.0, 2.0 * 2 ** attempt))
        raise RuntimeError(f"GET failed: {url}: {last}")

    def discover_products(self, sols: list[int]) -> list[ProductRef]:
        out = []
        for sol in sols:
            d = f"{NAV_BASE}/DATA/SOL{sol:05d}/"
            r = self.client.get(d)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            for name, size in self.ROW.findall(r.text):
                if name.endswith(".IMG") and NAME.match(name):
                    out.append(ProductRef(sol, name, d + name, d + name[:-4] + ".LBL", size.strip()))
        return out

    def local_paths(self, ref: ProductRef) -> tuple[Path, Path]:
        base = self.root / "MSLNAV_0XXX" / "DATA" / f"SOL{ref.sol:05d}"     # original archive structure
        return base / ref.name, base / (ref.name[:-4] + ".LBL")

    def fetch_metadata(self, ref: ProductRef) -> str:
        _, lbl = self.local_paths(ref)
        return lbl.read_text(encoding="latin-1") if lbl.exists() else self._get(ref.url_lbl).decode("latin-1")

    def fetch_product(self, ref: ProductRef) -> tuple[Path, Path]:
        img, lbl = self.local_paths(ref)
        img.parent.mkdir(parents=True, exist_ok=True)
        for url, dest in ((ref.url_lbl, lbl), (ref.url_img, img)):
            if not dest.exists() or dest.stat().st_size == 0:
                data = self._get(url)
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(data)
                tmp.replace(dest)
        return img, lbl

    def normalize_metadata(self, ref: ProductRef, label_text: str) -> dict:
        L = parse_label(label_text)
        m = NAME.match(ref.name)
        eye, string, sclk_name, tier, site_n, drive_n, seq = m.groups()
        obj = L.get("OBJECT:IMAGE", {})
        c = L.get("COMPRESSION_PARMS", {})
        rmc = L.get("ROVER_MOTION_COUNTER") or []
        geo = L.get("ROVER_DERIVED_GEOMETRY_PARMS", {})
        lines, samples = obj.get("LINES"), obj.get("LINE_SAMPLES")
        rate = c.get("INST_CMPRS_RATE")
        est = (int(lines) * int(samples) * float(rate) / 8) if all(isinstance(x, (int, float)) for x in (lines, samples, rate)) else None
        return {
            "product_id": L.get("PRODUCT_ID"), "sol": ref.sol, "planet_day_number": L.get("PLANET_DAY_NUMBER"),
            "utc": L.get("START_TIME"), "sclk": float(L.get("SPACECRAFT_CLOCK_START_COUNT")) if L.get("SPACECRAFT_CLOCK_START_COUNT") else None,
            "sclk_name": int(sclk_name), "eye": eye, "string": string, "instrument_id": L.get("INSTRUMENT_ID"),
            "site": rmc[0] if len(rmc) > 0 else int(site_n), "drive": rmc[1] if len(rmc) > 1 else int(drive_n),
            "pose": rmc[2] if len(rmc) > 2 else None, "rover_motion_counter": rmc,
            "sequence_id": L.get("SEQUENCE_ID") or seq.lower(), "tier": tier, "tier_name": TIERS.get(tier, tier),
            "frame_type": L.get("FRAME_TYPE"), "lines": lines, "line_samples": samples, "sample_bits": obj.get("SAMPLE_BITS"),
            "sample_type": obj.get("SAMPLE_TYPE"), "compression": c.get("INST_CMPRS_NAME"), "compression_rate_bpp": rate,
            "compression_ratio": c.get("INST_CMPRS_RATIO"), "error_pixels": c.get("ERROR_PIXELS"),
            "estimated_downlink_bytes": est, "instrument_azimuth_deg": geo.get("INSTRUMENT_AZIMUTH"),
            "instrument_elevation_deg": geo.get("INSTRUMENT_ELEVATION"), "solar_elevation_deg": geo.get("SOLAR_ELEVATION"),
            "exposure_ms": L.get("EXPOSURE_DURATION"), "url_img": ref.url_img, "url_lbl": ref.url_lbl,
        }

    def link_to_mission_time(self, record: dict) -> dict:
        t = datetime.fromisoformat(str(record["utc"]).replace("Z", "")).replace(tzinfo=timezone.utc)
        return {"utc": t, "sol": record["sol"], "sclk": record["sclk"]}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
