"""Mars Science Laboratory / Curiosity adapter — REMS MODRDR + RAD RDR from the PDS.

REMS MODRDR (MSL-M-REMS-5-MODRDR-V1.0): fixed-length ASCII records (372 bytes), ~1 Hz bursts.
    Column layout from the PDS format file MODRDR6.FMT (40 columns).
    UTC is derived per product from the label's SPACECRAFT_CLOCK_START_COUNT ↔ START_TIME pair.
RAD RDR (MSL-M-RAD-3-RDR-V1.0): one ASCII file per sol, one [OBSERVATION: NN] block per
    integration (~15–30 min). We use the dosimetry total-dose rates B and E (µGy/h).

Source-of-truth rule: if the requested sols are not in data/raw (download cache), the adapter
falls back to data/fixtures (real PDS bytes, labelled LOCAL_NASA_SAMPLE). It never substitutes
synthetic data; if neither exists it raises.
"""

from __future__ import annotations

import gzip
import re
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import polars as pl

from deepsift.adapters.base import ChannelSpec, LoadedMission, MissionAdapter, MissionMetadata
from deepsift.core.config import DATA_DIR
from deepsift.core.models import DataSource

REMS_COLUMNS = [
    "TIMESTAMP", "LMST", "LTST", "HORIZONTAL_WIND_SPEED", "VERTICAL_WIND_SPEED", "WIND_DIRECTION",
    "WS_CONFIDENCE_LEVEL", "BRIGHTNESS_TEMP", "BRIGHTNESS_TEMP_LONG_TERM_UNCERTAINTY",
    "BRIGHTNESS_TEMP_SHORT_TERM_UNCERTAINTY", "GTS_CONFIDENCE_LEVEL", "BOOM1_LOCAL_AIR_TEMP",
    "ATS_BOOM1_CONFIDENCE_LEVEL", "BOOM2_LOCAL_AIR_TEMP", "ATS_BOOM2_CONFIDENCE_LEVEL", "AMBIENT_TEMP",
    "AMBIENT_TEMP_CONFIDENCE_LEVEL", "UV_A", "UV_B", "UV_C", "UV_ABC", "UV_D", "UV_E", "UV_A_UNCERTAINTY",
    "UV_B_UNCERTAINTY", "UV_C_UNCERTAINTY", "UV_ABC_UNCERTAINTY", "UV_D_UNCERTAINTY", "UV_E_UNCERTAINTY",
    "UVS_CONFIDENCE_LEVEL", "LOCAL_RELATIVE_HUMIDITY", "HS_TEMP", "LOCAL_RELATIVE_HUMIDITY_UNCERTAINTY",
    "VOLUME_MIXING_RATIO", "VOLUME_MIXING_RATIO_UNCERTAINTY", "HS_CONFIDENCE_LEVEL", "PS_CONFIGURATION",
    "PRESSURE", "PRESSURE_UNCERTAINTY", "PS_CONFIDENCE_LEVEL",
]
MISSING = -999.0

# channel name -> PDS column
REMS_CHANNELS = {
    "pressure": "PRESSURE",
    "air_temp": "AMBIENT_TEMP",
    "ground_temp": "BRIGHTNESS_TEMP",
    "uv_abc": "UV_ABC",
    "rel_humidity": "LOCAL_RELATIVE_HUMIDITY",
}

CHANNELS = [
    ChannelSpec("pressure", "REMS", "Pa", 0.25, (300, 1300), description="REMS PS atmospheric pressure"),
    ChannelSpec("air_temp", "REMS", "K", 0.5, (120, 320), description="REMS ATS ambient air temperature"),
    ChannelSpec("ground_temp", "REMS", "K", 0.5, (120, 320), description="REMS GTS ground brightness temperature"),
    ChannelSpec("uv_abc", "REMS", "W/m²", 0.05, (0, 60), description="REMS UVS integrated UV-ABC flux"),
    ChannelSpec("rel_humidity", "REMS", "%", 0.3, (0, 100), description="REMS HS local relative humidity"),
    ChannelSpec("dose_b", "RAD", "µGy/h", 0.08, (0, 1000), diurnal=False, description="RAD total dose rate, detector B"),
    ChannelSpec("dose_e", "RAD", "µGy/h", 0.08, (0, 1000), diurnal=False, description="RAD total dose rate, detector E"),
]

LMST_RE = re.compile(r"(\d{5})M(\d\d):(\d\d):(\d\d(?:\.\d+)?)")


def _open_text(path: Path) -> bytes:
    return gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()


def _label_value(label: str, key: str) -> str:
    m = re.search(rf"^\s*{key}\s*=\s*\"?([^\"\r\n]+)\"?", label, re.M)
    if not m:
        raise ValueError(f"{key} not in label")
    return m.group(1).strip()


def parse_rems_product(tab_bytes: bytes, label: str, product: str, sol: int) -> tuple[pl.DataFrame, list[bytes]]:
    """Parse one REMS MODRDR table. Returns (wide frame, raw record lines)."""
    sclk0 = float(_label_value(label, "SPACECRAFT_CLOCK_START_COUNT"))
    utc0 = datetime.fromisoformat(_label_value(label, "START_TIME")).replace(tzinfo=timezone.utc)
    lines = [ln for ln in tab_bytes.splitlines(keepends=True) if ln.strip()]
    rows = []
    for ln in lines:
        parts = [p.strip().strip('"').strip() for p in ln.decode("ascii", "replace").split(",")]
        rows.append(parts)
    wide = pl.DataFrame(rows, schema=REMS_COLUMNS, orient="row")
    lm = wide["LMST"].str.extract_groups(LMST_RE.pattern)
    wide = wide.with_columns(
        pl.col("TIMESTAMP").cast(pl.Float64).alias("sclk"),
        lm.struct.field("1").cast(pl.Int32).alias("sol"),
        (
            lm.struct.field("2").cast(pl.Float64) * 3600
            + lm.struct.field("3").cast(pl.Float64) * 60
            + lm.struct.field("4").cast(pl.Float64)
        ).alias("lmst_s"),
        pl.lit(product).alias("product"),
        pl.int_range(pl.len(), dtype=pl.Int64).alias("row_in_product"),
    )
    wide = wide.with_columns(
        (pl.lit(utc0) + pl.duration(microseconds=((pl.col("sclk") - sclk0) * 1e6).cast(pl.Int64))).alias("t")
    )
    return wide, lines


def parse_rad_product(txt: bytes, product: str) -> pl.DataFrame:
    """Parse the per-observation header and total-dose elements of one RAD RDR file."""
    text = txt.decode("ascii", "replace")
    starts = [m.start() for m in re.finditer(r"^\[OBSERVATION: (\d+)\]", text, re.M)]
    out = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[s:e]
        mars = re.search(r'START_OBS_MARS="(\d+) (\d\d):(\d\d):(\d\d)"', block)
        utc = re.search(r'START_OBS_UTC="(\d{4})-(\d{3}) (\d\d):(\d\d):(\d\d)"', block)
        dose_b = re.search(r"\[DOSIMETRY_TOTAL_DOSE_B: \d+\]\s+([-\d.eE+]+)", block)
        dose_e = re.search(r"\[DOSIMETRY_TOTAL_DOSE_E: \d+\]\s+([-\d.eE+]+)", block)
        if not (mars and utc):
            continue
        y, doy, hh, mm, ss = (int(x) for x in utc.groups())
        t = datetime(y, 1, 1, hh, mm, ss, tzinfo=timezone.utc) + timedelta(days=doy - 1)
        out.append(
            {
                "record": i,
                "t": t,
                "sol": int(mars.group(1)),
                "lmst_s": int(mars.group(2)) * 3600 + int(mars.group(3)) * 60 + int(mars.group(4)),
                "dose_b": float(dose_b.group(1)) if dose_b else None,
                "dose_e": float(dose_e.group(1)) if dose_e else None,
                "bytes": len(block.encode()),
                "raw": block.encode(),
                "product": product,
            }
        )
    return pl.DataFrame(out, schema_overrides={"t": pl.Datetime("us", "UTC"), "lmst_s": pl.Float64})


class CuriosityAdapter(MissionAdapter):
    id = "msl_curiosity"

    def __init__(self, raw_dir: Path | None = None, fixture_dir: Path | None = None, window_s: int = 300,
                 decimation: int = 8, zlib_level: int = 6):
        self.raw_dir = raw_dir or DATA_DIR / "raw"
        self.fixture_dir = fixture_dir or DATA_DIR / "fixtures" / "msl_curiosity"
        self.window_s = window_s
        self.decimation = decimation
        self.zlib_level = zlib_level
        self._products: list[tuple[str, Path, Path | None, int]] = []  # (instrument, data, label, sol)
        self._source = DataSource.NASA_PDS
        self._loaded: LoadedMission | None = None

    # ---------------------------------------------------------------- discovery
    @staticmethod
    def _scan(root: Path) -> list[tuple[str, Path, Path | None, int]]:
        found = []
        for p in sorted((root / "rems").glob("RME_*RMD*.TAB*")):
            sol = int(re.search(r"RMD(\d{4})", p.name).group(1))
            lbl = next(iter(sorted((root / "rems").glob(p.name.split(".")[0] + ".LBL*"))), None)
            found.append(("REMS", p, lbl, sol))
        for p in sorted((root / "rad").glob("RAD_RDR_*.TXT*")):
            sol = int(re.search(r"_(\d{4})_V\d\d", p.name).group(1))
            found.append(("RAD", p, None, sol))
        return found

    def load(self, sols: list[int] | None = None) -> None:
        products = self._scan(self.raw_dir)
        source = DataSource.NASA_PDS
        if not products:
            products = self._scan(self.fixture_dir)
            source = DataSource.LOCAL_NASA_SAMPLE
        if sols is not None:
            products = [p for p in products if p[3] in set(sols)]
        if not products:
            raise FileNotFoundError(
                "No Curiosity products found in data/raw or data/fixtures. Run `uv run python scripts/fetch_nasa.py`."
            )
        self._products, self._source, self._loaded = products, source, None

    # ---------------------------------------------------------------- metadata
    def metadata(self) -> MissionMetadata:
        return MissionMetadata(
            id=self.id,
            name="Mars Science Laboratory",
            short_name="MSL / CURIOSITY",
            target="Mars — Gale Crater",
            instruments={
                "REMS": "Rover Environmental Monitoring Station (MSL-M-REMS-5-MODRDR-V1.0)",
                "RAD": "Radiation Assessment Detector (MSL-M-RAD-3-RDR-V1.0)",
            },
            channels=CHANNELS,
            sol_length_s=88775.244,
            location="Gale Crater, Mars (4.59°S, 137.44°E landing site)",
            data_citations=[
                "Gómez-Elvira, J. (2013). MSL Mars Rover Environmental Monitoring Station RDR Data V1.0, "
                "MSL-M-REMS-5-MODRDR-V1.0, NASA Planetary Data System (Atmospheres Node).",
                "Hassler, D. M. et al. MSL RAD Reduced Data Record V1.0, MSL-M-RAD-3-RDR-V1.0, "
                "NASA Planetary Data System (PPI Node).",
            ],
            data_source=self._source,
            sols=sorted({p[3] for p in self._products}),
            products=[p[1].name for p in self._products],
        )

    @staticmethod
    def _rad_local_time(samples: pl.DataFrame) -> pl.DataFrame:
        """RAD RDR `START_OBS_MARS` is not a per-observation local time in these products (consecutive
        observations differ by ~1 s while START_OBS_UTC advances ~1 h), so RAD sol/LMST are derived from
        START_OBS_UTC with a linear UTC → mission-sol fit on the REMS records (which carry both)."""
        rems = samples.filter((pl.col("instrument") == "REMS") & (pl.col("channel") == "pressure"))
        rad = samples.filter(pl.col("instrument") == "RAD")
        if rems.height < 100 or rad.is_empty():
            return samples
        x = rems["t"].dt.epoch("ms").to_numpy() / 1000.0
        y = rems["sol"].to_numpy() + rems["lmst_s"].to_numpy() / 86400.0
        slope, icpt = np.polyfit(x - x.mean(), y, 1)
        solf = pl.lit(icpt) + pl.lit(slope) * (pl.col("t").dt.epoch("ms").cast(pl.Float64) / 1000.0 - x.mean())
        rad = rad.with_columns(solf.alias("_solf")).with_columns(
            pl.col("_solf").floor().cast(pl.Int32).alias("sol"),
            ((pl.col("_solf") - pl.col("_solf").floor()) * 86400.0).alias("lmst_s"),
        ).drop("_solf")
        return pl.concat([samples.filter(pl.col("instrument") != "RAD"), rad.select(samples.columns)])

    def window_key(self, instrument: str) -> pl.Expr:
        if instrument == "RAD":  # one RAD observation = one integration window
            return pl.concat_str([pl.col("product"), pl.lit(":"), pl.col("record").cast(pl.Utf8)])
        # LMST-aligned windows never straddle local midnight and line up across sols
        return pl.concat_str([
            pl.col("sol").cast(pl.Utf8), pl.lit(":"), (pl.col("lmst_s") // self.window_s).cast(pl.Int64).cast(pl.Utf8)
        ])

    # ---------------------------------------------------------------- normalize
    def normalize(self) -> LoadedMission:
        if self._loaded is not None:
            return self._loaded
        if not self._products:
            self.load()
        sample_frames, record_frames, byte_rows = [], [], []

        for instrument, path, label_path, sol in self._products:
            product = path.name.replace(".gz", "")
            raw = _open_text(path)
            if instrument == "REMS":
                if label_path is None:
                    raise FileNotFoundError(f"missing label for {product}")
                label = _open_text(label_path).decode("ascii", "replace")
                wide, lines = parse_rems_product(raw, label, product, sol)
                wide = wide.with_columns(self.window_key("REMS").alias("window"))
                # measured byte costs per window, on the original records
                win = wide["window"].to_list()
                groups: dict[str, list[int]] = {}
                for i, w in enumerate(win):
                    groups.setdefault(w, []).append(i)
                for w, idx in groups.items():
                    blob = b"".join(lines[i] for i in idx)
                    dec = b"".join(lines[i] for i in idx[:: self.decimation])
                    byte_rows.append({
                        "instrument": "REMS", "window": w, "raw": len(blob),
                        "full": len(zlib.compress(blob, self.zlib_level)),
                        "compressed": len(zlib.compress(dec, self.zlib_level)),
                        "row_start": idx[0], "row_end": idx[-1], "product": product,
                    })
                wide = wide.with_columns(pl.col("row_in_product").alias("record"))
                record_frames.append(wide.select(
                    pl.lit("REMS").alias("instrument"), "product", "record", "t",
                    pl.lit(len(lines[0]) if lines else 0, dtype=pl.Int64).alias("bytes"),
                ))
                for ch, col in REMS_CHANNELS.items():
                    sample_frames.append(
                        wide.select(
                            "t", "sol", "lmst_s", pl.lit("REMS").alias("instrument"), pl.lit(ch).alias("channel"),
                            pl.col(col).cast(pl.Float64, strict=False).alias("value"), "record", "product",
                        ).filter(pl.col("value").is_not_null() & (pl.col("value") != MISSING))
                    )
            else:
                obs = parse_rad_product(raw, product)
                if obs.is_empty():
                    continue
                for row in obs.iter_rows(named=True):
                    blob = row["raw"]
                    byte_rows.append({
                        "instrument": "RAD", "window": f"{product}:{row['record']}", "raw": len(blob),
                        "full": len(zlib.compress(blob, self.zlib_level)),
                        # RAD blocks are mostly histograms; the lossy product keeps counters + dose only
                        "compressed": len(zlib.compress(blob[: max(1, len(blob) // self.decimation)], self.zlib_level)),
                        "row_start": row["record"], "row_end": row["record"], "product": product,
                    })
                record_frames.append(obs.select(pl.lit("RAD").alias("instrument"), "product", "record", "t", "bytes"))
                for ch in ("dose_b", "dose_e"):
                    sample_frames.append(
                        obs.select(
                            "t", pl.col("sol").cast(pl.Int32), "lmst_s", pl.lit("RAD").alias("instrument"),
                            pl.lit(ch).alias("channel"), pl.col(ch).cast(pl.Float64).alias("value"),
                            pl.col("record").cast(pl.Int64), "product",
                        ).filter(pl.col("value").is_not_null())
                    )

        samples = pl.concat(sample_frames, how="vertical_relaxed")
        samples = self._rad_local_time(samples)
        samples = samples.sort("instrument", "channel", "t")
        records = pl.concat(record_frames, how="vertical_relaxed")
        window_bytes = pl.DataFrame(byte_rows)
        md = self.metadata()
        self._loaded = LoadedMission(samples=samples, records=records, window_bytes=window_bytes, metadata=md)
        return self._loaded


def sclk_sanity(samples: pl.DataFrame) -> float:
    """Fraction of REMS samples whose UTC ordering matches LMST ordering (should be ~1.0)."""
    r = samples.filter(pl.col("instrument") == "REMS", pl.col("channel") == "pressure").sort("t")
    key = (r["sol"].to_numpy() * 86400.0 + r["lmst_s"].to_numpy())
    return float(np.mean(np.diff(key) >= -1)) if len(key) > 1 else 1.0
