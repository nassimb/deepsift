#!/usr/bin/env python3
"""Download real MSL/Curiosity REMS + RAD products from the NASA Planetary Data System.

Sources (public, no authentication):
  REMS MODRDR (MSL-M-REMS-5-MODRDR-V1.0) — PDS Atmospheres Node, NMSU
      https://atmos.nmsu.edu/PDS/data/mslrem_1001/DATA/
  RAD RDR     (MSL-M-RAD-3-RDR-V1.0)     — PDS Planetary Plasma Interactions Node, UCLA
      https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/DATA/

Every original file is recorded in data/raw/manifest.json with URL, size and sha256 *of the
original bytes*. With --compact (default for split downloads):
  * REMS tables/labels are stored gzip-compressed (lossless; the adapter reads .gz).
  * RAD RDR files (~30 MB/sol after 2014, mostly histograms/PHA) are reduced to a derived record per
    observation — UTC, START_OBS_MARS, dose B/E, and the raw / zlib-full / zlib-decimated byte sizes
    measured on the original observation block — and the original is deleted. The manifest keeps the
    original sha256 so the derivation is verifiable by re-downloading.

Usage:
    uv run python scripts/fetch_nasa.py --sols 232-251
    uv run python scripts/fetch_nasa.py --split validation --split test
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SPLITS = ROOT / "data" / "splits" / "splits.json"

REMS_BASE = "https://atmos.nmsu.edu/PDS/data/mslrem_1001"
RAD_BASE = "https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0"
DECIMATION = 8
ZLIB_LEVEL = 6

_lock = threading.Lock()
_bucket_cache: dict[str, list[tuple[int, int, str]]] = {}


def buckets(client: httpx.Client, base: str) -> list[tuple[int, int, str]]:
    if base not in _bucket_cache:
        html = client.get(f"{base}/DATA/").text
        found = sorted({(int(a), int(b), f"SOL_{a}_{b}") for a, b in re.findall(r"SOL_(\d{5})_(\d{5})/", html)})
        _bucket_cache[base] = found
    return _bucket_cache[base]


def bucket_for(client: httpx.Client, base: str, sol: int) -> str:
    for lo, hi, name in buckets(client, base):
        if lo <= sol <= hi:
            return name
    raise ValueError(f"sol {sol} not in any PDS bucket of {base}")


def listing(client: httpx.Client, url: str) -> list[str]:
    for attempt in range(4):
        try:
            r = client.get(url)
            r.raise_for_status()
            return sorted(set(re.findall(r'href="([^"?/][^"?]*)"', r.text)))
        except httpx.HTTPError:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return []


def get_bytes(client: httpx.Client, url: str) -> bytes:
    for attempt in range(4):
        try:
            r = client.get(url)
            r.raise_for_status()
            return r.content
        except httpx.HTTPError as e:
            if attempt == 3:
                raise
            print(f"  retry {attempt + 1} {url}: {e}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def entry(path: Path, url: str, data: bytes, **extra) -> dict:
    return {"path": str(path.relative_to(ROOT)), "url": url, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), **extra}


def compact_rad(data: bytes, product: str) -> dict:
    text = data.decode("ascii", "replace")
    starts = [m.start() for m in re.finditer(r"^\[OBSERVATION: (\d+)\]", text, re.M)]
    obs = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[s:e]
        blob = block.encode()
        mars = re.search(r'START_OBS_MARS="(\d+) (\d\d):(\d\d):(\d\d)"', block)
        utc = re.search(r'START_OBS_UTC="(\d{4}-\d{3} \d\d:\d\d:\d\d)"', block)
        db = re.search(r"\[DOSIMETRY_TOTAL_DOSE_B: \d+\]\s+([-\d.eE+]+)", block)
        de = re.search(r"\[DOSIMETRY_TOTAL_DOSE_E: \d+\]\s+([-\d.eE+]+)", block)
        obs.append({
            "record": i, "start_obs_utc": utc.group(1) if utc else None,
            "start_obs_mars": " ".join(mars.groups()[:1]) + " " + ":".join(mars.groups()[1:]) if mars else None,
            "dose_b": float(db.group(1)) if db else None, "dose_e": float(de.group(1)) if de else None,
            "raw": len(blob), "full": len(zlib.compress(blob, ZLIB_LEVEL)),
            "compressed": len(zlib.compress(blob[: max(1, len(blob) // DECIMATION)], ZLIB_LEVEL)),
        })
    return {"format": "deepsift-rad-compact-v1", "product": product, "decimation": DECIMATION,
            "zlib_level": ZLIB_LEVEL, "observations": obs}


def fetch_rems(client, sol: int, compact: bool) -> list[dict]:
    d = f"{REMS_BASE}/DATA/{bucket_for(client, REMS_BASE, sol)}/SOL{sol:05d}/"
    names = [n for n in listing(client, d) if "RMD" in n and n.endswith((".TAB", ".LBL"))]
    if not names:
        raise FileNotFoundError(f"no REMS MODRDR product for sol {sol}")
    out = []
    for n in names:
        dest = RAW / "rems" / (n + (".gz" if compact else ""))
        if dest.exists() and dest.stat().st_size > 0:
            continue
        data = get_bytes(client, d + n)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(gzip.compress(data, 6) if compact else data)
        out.append(entry(dest, d + n, data, stored_as="gzip" if compact else "original"))
    return out


def fetch_rad(client, sol: int, compact: bool) -> list[dict]:
    d = f"{RAD_BASE}/DATA/{bucket_for(client, RAD_BASE, sol)}/"
    names = [n for n in listing(client, d) if re.match(rf"RAD_RDR_\d{{4}}_\d{{3}}_\d\d_\d\d_{sol:04d}_V\d\d\.TXT$", n)]
    if not names:
        raise FileNotFoundError(f"no RAD RDR product for sol {sol}")
    latest = max(n[-7:-4] for n in names)
    out = []
    for n in [n for n in names if n[-7:-4] == latest]:
        dest = RAW / "rad" / (n.replace(".TXT", ".compact.json.gz") if compact else n)
        if dest.exists() and dest.stat().st_size > 0:
            continue
        data = get_bytes(client, d + n)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if compact:
            dest.write_bytes(gzip.compress(json.dumps(compact_rad(data, n)).encode()))
        else:
            dest.write_bytes(data)
        out.append(entry(dest, d + n, data, stored_as="derived-compact" if compact else "original"))
    return out


def sols_from_split(names: list[str]) -> list[int]:
    spec = json.loads(SPLITS.read_text())["splits"]
    sols: set[int] = set()
    for name in names:
        for seg in spec[name]["segments"]:
            for key in ("warmup", "eval"):
                if seg.get(key):
                    sols.update(range(seg[key][0], seg[key][1] + 1))
    return sorted(sols)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sols", help="inclusive sol range, e.g. 232-251")
    ap.add_argument("--split", action="append", choices=["calibration", "validation", "test"])
    ap.add_argument("--compact", action=argparse.BooleanOptionalAction, default=None,
                    help="store REMS gzip + RAD derived records (default: on for --split, off for --sols)")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.split:
        sols = sols_from_split(args.split)
        compact = True if args.compact is None else args.compact
    else:
        lo, hi = (int(x) for x in (args.sols or "232-251").split("-"))
        sols = list(range(lo, hi + 1))
        compact = bool(args.compact)

    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    failures: list[str] = []
    jobs = [(sol, name, fn) for sol in sols for name, fn in (("REMS", fetch_rems), ("RAD", fetch_rad))]
    with httpx.Client(timeout=300, follow_redirects=True, headers={"User-Agent": "deepsift-research-prototype"}) as client:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(fn, client, sol, compact): (sol, name) for sol, name, fn in jobs}
            for fut in as_completed(futs):
                sol, name = futs[fut]
                try:
                    entries = fut.result()
                    with _lock:
                        for e in entries:
                            manifest["files"][e["path"]] = {**e, "sol": sol, "instrument": name}
                        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
                    print(f"sol {sol:4d} {name:4s} ok ({len(entries)} new)", flush=True)
                except Exception as e:  # noqa: BLE001 — one missing sol must not abort the run
                    failures.append(f"sol {sol} {name}: {e}")
                    print(f"sol {sol:4d} {name:4s} FAILED: {e}", file=sys.stderr, flush=True)

    manifest["fetched_at"] = datetime.now(timezone.utc).isoformat()
    manifest["sources"] = {"REMS": REMS_BASE, "RAD": RAD_BASE}
    manifest.setdefault("failures_by_run", []).append({"at": manifest["fetched_at"], "failures": failures})
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    print(f"{len(manifest['files'])} files in manifest, {len(failures)} failures this run")
    return 1 if failures and len(failures) == len(jobs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
