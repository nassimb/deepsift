#!/usr/bin/env python3
"""Download real MSL/Curiosity REMS + RAD products from the NASA Planetary Data System.

Sources (public, no authentication):
  REMS MODRDR (MSL-M-REMS-5-MODRDR-V1.0) — PDS Atmospheres Node, NMSU
      https://atmos.nmsu.edu/PDS/data/mslrem_1001/DATA/
  RAD RDR     (MSL-M-RAD-3-RDR-V1.0)     — PDS Planetary Plasma Interactions Node, UCLA
      https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/DATA/

Every file is recorded in data/raw/manifest.json with its source URL, size and sha256 so that
a benchmark run can state exactly which bytes it was computed from.

Usage:
    uv run python scripts/fetch_nasa.py --sols 232-251
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

REMS_BASE = "https://atmos.nmsu.edu/PDS/data/mslrem_1001"
RAD_BASE = "https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0"

# PDS volume sub-directory ranges (identical boundaries on both nodes for the early mission).
SOL_BUCKETS = [(0, 89), (90, 179), (180, 269), (270, 359), (360, 449), (450, 583), (584, 707), (708, 804)]


def bucket(sol: int, rad: bool) -> str:
    for lo, hi in SOL_BUCKETS:
        if lo <= sol <= hi:
            # REMS starts its first bucket at sol 1, RAD at sol 0.
            lo = 1 if (lo == 0 and not rad) else lo
            return f"SOL_{lo:05d}_{hi:05d}"
    raise ValueError(f"sol {sol} outside supported range (extend SOL_BUCKETS)")


def listing(client: httpx.Client, url: str) -> list[str]:
    r = client.get(url)
    r.raise_for_status()
    return sorted(set(re.findall(r'href="([^"?/][^"?]*)"', r.text)))


def download(client: httpx.Client, url: str, dest: Path, retries: int = 3) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        data = dest.read_bytes()
    else:
        for attempt in range(retries):
            try:
                r = client.get(url)
                r.raise_for_status()
                data = r.content
                dest.write_bytes(data)
                break
            except httpx.HTTPError as e:
                if attempt == retries - 1:
                    raise
                print(f"  retry {attempt + 1} for {url}: {e}", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
    return {
        "path": str(dest.relative_to(ROOT)),
        "url": url,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def fetch_rems(client: httpx.Client, sol: int) -> list[dict]:
    d = f"{REMS_BASE}/DATA/{bucket(sol, rad=False)}/SOL{sol:05d}/"
    names = [n for n in listing(client, d) if "RMD" in n and n.endswith((".TAB", ".LBL"))]
    if not names:
        raise FileNotFoundError(f"no REMS MODRDR product for sol {sol}")
    return [download(client, d + n, RAW / "rems" / n) for n in names]


def fetch_rad(client: httpx.Client, sol: int) -> list[dict]:
    d = f"{RAD_BASE}/DATA/{bucket(sol, rad=True)}/"
    names = [n for n in listing(client, d) if re.match(rf"RAD_RDR_\d{{4}}_\d{{3}}_\d\d_\d\d_{sol:04d}_V\d\d\.(TXT|LBL)$", n)]
    if not names:
        raise FileNotFoundError(f"no RAD RDR product for sol {sol}")
    # Keep only the highest product version for each sol.
    latest = max(n[-7:-4] for n in names)
    return [download(client, d + n, RAW / "rad" / n) for n in names if n[-7:-4] == latest]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sols", default="232-251", help="inclusive sol range, e.g. 232-251")
    args = ap.parse_args()
    lo, hi = (int(x) for x in args.sols.split("-"))

    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    failures: list[str] = []
    with httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "deepsift-research-prototype"}) as client:
        for sol in range(lo, hi + 1):
            for name, fn in (("REMS", fetch_rems), ("RAD", fetch_rad)):
                try:
                    for entry in fn(client, sol):
                        manifest["files"][entry["path"]] = {**entry, "sol": sol, "instrument": name}
                    print(f"sol {sol:4d} {name:4s} ok")
                except Exception as e:  # noqa: BLE001 — one missing sol must not abort the run
                    failures.append(f"sol {sol} {name}: {e}")
                    print(f"sol {sol:4d} {name:4s} FAILED: {e}", file=sys.stderr)

    manifest["fetched_at"] = datetime.now(timezone.utc).isoformat()
    manifest["sources"] = {"REMS": REMS_BASE, "RAD": RAD_BASE}
    manifest["failures"] = failures
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"{len(manifest['files'])} files in manifest, {len(failures)} failures")
    return 1 if failures and len(failures) == 2 * (hi - lo + 1) else 0


if __name__ == "__main__":
    raise SystemExit(main())
