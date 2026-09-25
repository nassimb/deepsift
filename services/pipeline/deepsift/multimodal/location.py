"""M4 — PLACES location join (MSL localization bundle, PDS Imaging Node `msl_places`).

Exact join on the label's ROVER_MOTION_COUNTER (site, drive, pose) against localized_interp.csv ROVER rows; fallback
(site, drive) with the nearest pose; then the SITE row. The match type is recorded — positions are per rover stop, and
their uncertainty is defined by the PLACES SIS (not re-estimated here).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from deepsift.core.config import DATA_DIR

URL = "https://planetarydata.jpl.nasa.gov/img/data/msl/msl_places/data_localizations/localized_interp.csv"
LOCAL = DATA_DIR / "raw" / "places" / "localized_interp.csv"
FIELDS = ("landing_x", "landing_y", "landing_z", "planetocentric_latitude", "longitude", "elevation", "yaw")


def fetch() -> dict:
    if not LOCAL.exists():
        LOCAL.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(URL, timeout=300, follow_redirects=True)
        r.raise_for_status()
        LOCAL.write_bytes(r.content)
    data = LOCAL.read_bytes()
    rec = {"url": URL, "path": str(LOCAL), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
           "checked_at": datetime.now(timezone.utc).isoformat()}
    (LOCAL.parent / "manifest.json").write_text(json.dumps(rec, indent=1))
    return rec


class Places:
    def __init__(self, path: Path = LOCAL):
        rows = list(csv.DictReader(io.StringIO(path.read_text())))
        self.rover, self.site = {}, {}
        for r in rows:
            try:
                s, d, p = int(r["site"]), int(r["drive"]), int(r["pose"])
            except (ValueError, KeyError):
                continue
            vals = {k: float(r[k]) for k in FIELDS if r.get(k) not in (None, "")}
            if r["frame"].strip().upper() == "SITE":
                self.site[s] = vals
            else:
                self.rover[(s, d, p)] = vals
        self.by_sd: dict = {}
        for (s, d, p), v in self.rover.items():
            self.by_sd.setdefault((s, d), []).append((p, v))

    def locate(self, site, drive, pose) -> dict:
        if (site, drive, pose) in self.rover:
            return {**self.rover[(site, drive, pose)], "match": "exact_site_drive_pose"}
        if (site, drive) in self.by_sd:
            p, v = min(self.by_sd[(site, drive)], key=lambda x: abs(x[0] - (pose or 0)))
            return {**v, "match": f"site_drive_nearest_pose({p})"}
        if site in self.site:
            return {**self.site[site], "match": "site_origin_only"}
        return {"match": "none"}
