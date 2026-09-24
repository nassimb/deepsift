#!/usr/bin/env python3
"""Build data/ground_truth/documented_events.json from primary sources.

Reproducible: the Forbush-decrease catalogue is parsed programmatically from the arXiv version of
Guo et al. (2018); the source PDFs are downloaded to data/processed/lit/ (git-ignored) and their
sha256 is recorded. Hand-entered events carry verbatim quotes from their sources.

Severity is a DEEPSIFT evaluation convention fixed BEFORE any Phase-2 evaluation was run
(see docs/ground-truth.md). It is not a scientific ranking.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
LIT = ROOT / "data" / "processed" / "lit"
OUT = ROOT / "data" / "ground_truth" / "documented_events.json"

SOURCES = {
    "guo2018": {
        "url": "https://arxiv.org/pdf/1712.06885v1",
        "citation": "Guo, J., Lillis, R., Wimmer-Schweingruber, R. F., et al. (2018). Measurements of Forbush decreases at Mars: "
                    "both by MSL on ground and by MAVEN in orbit. Astronomy & Astrophysics, 611, A79. doi:10.1051/0004-6361/201732087 "
                    "(arXiv:1712.06885v1, Appendix table).",
        "source_type": "peer_reviewed_paper",
    },
    "lowe2025": {
        "url": "https://arxiv.org/pdf/2502.02469v1",
        "citation": "Löwe, J. L., Khaksarighiri, S., Wimmer-Schweingruber, R. F., Hassler, D. M., Ehresmann, B., Guo, J., et al. "
                    "(2025). Nowcasting Solar Energetic Particle Events for Mars Missions. Manuscript submitted to Space Weather "
                    "(arXiv:2502.02469v1), Tables 1-3.",
        "source_type": "mission_team_publication",
    },
    "hassler2014": {
        "url": "https://www.science.org/doi/10.1126/science.1244797",
        "citation": "Hassler, D. M., Zeitlin, C., Wimmer-Schweingruber, R. F., et al. (2014). Mars' Surface Radiation Environment "
                    "Measured with the Mars Science Laboratory's Curiosity Rover. Science, 343(6169), 1244797. doi:10.1126/science.1244797",
        "source_type": "peer_reviewed_paper",
    },
    "viudez2019": {
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6750032/",
        "citation": "Viúdez-Moreiras, D., Newman, C. E., de la Torre, M., et al. (2019). Effects of the MY34/2018 Global Dust Storm "
                    "as Measured by MSL REMS in Gale Crater. Journal of Geophysical Research: Planets, 124(7), 1899-1912. "
                    "doi:10.1029/2019JE005985",
        "source_type": "peer_reviewed_paper",
    },
}

# Guo et al. (2018) Table 1: uncertainty of the manual identification procedure
GUO_DELTA_ONSET_DAYS = 0.68
GUO_DELTA_NADIR_DAYS = 0.55

# Mars sol ↔ UTC for sol-resolution sources: linear relation fitted on REMS records
# (sol length 88,775.244 s; anchor from the MODRDR product of sol 242, LMST 00:00 ≈ 2013-04-11T05:30Z).
# Accuracy of this conversion is minutes — far below the sol resolution of the sources that use it.
SOL_SECONDS = 88775.244
SOL_ANCHOR = (242, datetime(2013, 4, 11, 5, 30, tzinfo=timezone.utc))


def sol_to_utc(sol: float) -> datetime:
    return SOL_ANCHOR[1] + timedelta(seconds=(sol - SOL_ANCHOR[0]) * SOL_SECONDS)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_text(key: str) -> tuple[str, str]:
    LIT.mkdir(parents=True, exist_ok=True)
    pdf = LIT / f"{key}.pdf"
    if not pdf.exists():
        pdf.write_bytes(httpx.get(SOURCES[key]["url"], follow_redirects=True, timeout=120,
                                  headers={"User-Agent": "deepsift-research"}).content)
    import pypdf

    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(str(pdf)).pages)
    return text, hashlib.sha256(pdf.read_bytes()).hexdigest()


def fd_severity(drop_pct: float) -> str:
    # fixed a priori: Guo et al. give δdrop = 1.38 % for the manual procedure; hourly RAD dose-rate scatter is a few %
    if drop_pct >= 5.0:
        return "high"
    if drop_pct >= 3.0:
        return "medium"
    return "low"


def guo_events(text: str) -> list[dict]:
    row = re.compile(r"^(\d{1,3}) (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (\d+) (\d+) ([\d.]+) (.*)$", re.M)
    out = []
    for m in row.finditer(text):
        num, onset, nadir, d0, d1, drop, maven = m.groups()
        t0 = datetime.strptime(onset, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        t1 = datetime.strptime(nadir, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        out.append({
            "event_id": f"FD-GUO2018-{int(num):03d}",
            "event_type": "radiation",
            "event_subtype": "forbush_decrease",
            "start_time": iso(t0),
            "end_time": iso(t1),
            "time_uncertainty": {"start_days": GUO_DELTA_ONSET_DAYS, "end_days": GUO_DELTA_NADIR_DAYS,
                                 "basis": "Guo et al. (2018) Table 1, uncertainty of the manual identification procedure"},
            "confidence_in_time_bounds": "documented_uncertainty",
            "affected_instruments": ["RAD"],
            "severity": fd_severity(float(drop)),
            "magnitude": {"dose_rate_drop_percent": float(drop), "dose_rate_at_onset_uGy_per_day": int(d0),
                          "dose_rate_at_nadir_uGy_per_day": int(d1)},
            "source": "guo2018",
            "source_type": SOURCES["guo2018"]["source_type"],
            "citation": SOURCES["guo2018"]["citation"],
            "notes": f"Catalogue row {num}; interval = onset → nadir (the decrease phase). MAVEN columns: {maven.strip()}.",
        })
    return out


LOWE_SURFACE_SEPS = [
    # (date as printed in Löwe et al. Table 3 'Martian surface', shelter duration from Table 1 where given)
    ("2013-04-10", "00d 05h:33m"), ("2013-10-10", "00d 11h:15m"), ("2014-01-05", None), ("2014-09-02", "01d 14h:17m"),
    ("2014-09-10", None), ("2017-09-10", None), ("2021-10-28", None), ("2022-02-15", None), ("2022-03-14", None),
    ("2023-03-12", None), ("2024-05-20", None), ("2024-07-22", None), ("2024-07-26", None), ("2024-08-04", None),
    ("2024-09-02", None), ("2024-10-05", None),
]


def lowe_events(text: str) -> list[dict]:
    out = []
    for date, shelter in LOWE_SURFACE_SEPS:
        if date not in text:
            raise RuntimeError(f"{date} not found in Löwe et al. text — source changed?")
        d = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        out.append({
            "event_id": f"SEP-LOWE2025-{date}",
            "event_type": "radiation",
            "event_subtype": "solar_energetic_particle_event",
            "start_time": iso(d),
            "end_time": iso(d + timedelta(days=2)),
            "time_uncertainty": {"start_days": 1.0, "end_days": 1.0,
                                 "basis": "source gives a calendar date only; the window [date, date+2 d] is a DEEPSIFT bounding convention"},
            "confidence_in_time_bounds": "NEEDS_VERIFICATION",
            "affected_instruments": ["RAD"],
            "severity": "high",
            "magnitude": {"dose_E_shelter_duration_above_25pct": shelter} if shelter else {},
            "source": "lowe2025",
            "source_type": SOURCES["lowe2025"]["source_type"],
            "citation": SOURCES["lowe2025"]["citation"],
            "notes": "Listed under 'MARTIAN SURFACE' SEP events measured by MSL/RAD. Date semantics are not defined in the text "
                     "('The timestamps in the first column refer to the SEP events'). Use only with tolerant matching. "
                     "Manuscript was submitted, not yet peer reviewed, at the time of retrieval.",
        })
    return out


def sol242_event() -> dict:
    return {
        "event_id": "SEP-2013-04-SOL242",
        "event_type": "radiation",
        "event_subtype": "solar_energetic_particle_event",
        "start_time": "2013-04-11T00:00:00Z",
        "end_time": "2013-04-12T23:59:59Z",
        "time_uncertainty": {"start_days": 1.0, "end_days": 1.0, "basis": "day-resolution statements in the source; see verification record"},
        "confidence_in_time_bounds": "NEEDS_VERIFICATION",
        "affected_instruments": ["RAD"],
        "severity": "high",
        "magnitude": {"dose_enhancement_over_gcr": "~30% (Hassler et al. 2014)", "sep_dose_uGy": 50},
        "source": "hassler2014",
        "source_type": SOURCES["hassler2014"]["source_type"],
        "citation": SOURCES["hassler2014"]["citation"],
        "split_note": "In the CALIBRATION split, which was inspected during v0.1 development. Reported only as a development event.",
        "verification": {
            "old_bounds": {"start_time": "2013-04-11T06:00:00Z", "end_time": "2013-04-12T12:00:00Z",
                           "origin": "v0.1 data/labels/documented_events.yaml — set by the maintainers from the PDS RDR dose record"},
            "new_bounds": {"start_time": "2013-04-11T00:00:00Z", "end_time": "2013-04-12T23:59:59Z"},
            "statements_found": [
                {"source": "hassler2014", "where": "main text and Fig. 1 caption",
                 "quote": "RAD observed a dose rate enhancement from one hard SEP event on sol 242 (12 to 13 April 2013)"},
                {"source": "hassler2014", "where": "Materials and Methods",
                 "quote": "The dose rate time series associated with the SEP event enhancement seen on 11 to 12 April 2013 resulting from an M-class flare on the Sun"},
                {"source": "lowe2025", "where": "Tables 1-3", "quote": "2013-04-10 (Martian surface SEP event)"},
                {"source": "PDS MSL-M-RAD-3-RDR-V1.0", "where": "RAD_RDR_2013_101_*_0242 (DEEPSIFT reading)",
                 "quote": "dose B 9.13 µGy/h at 2013-04-11T06:01Z, 10.73 at 12:09Z, peak 12.13 at 14:12Z, back to ~9.2 by 2013-04-12T04:32Z"},
            ],
            "reason": "The primary peer-reviewed source is internally inconsistent (12-13 April vs 11-12 April); the mission-team "
                      "preprint lists 2013-04-10. Sol 242 spans ≈2013-04-11T05:30Z → 2013-04-12T06:10Z by the REMS clock relation, "
                      "which is consistent only with the 11-12 April statement. New bounds = the 11-12 April statement at day "
                      "resolution. Sub-day timing is NOT established by an independent source; status stays NEEDS_VERIFICATION. "
                      "The old bounds were derived by looking at the same RDR data they are evaluated on.",
        },
        "notes": "Development event only.",
    }


def dust_storm_events() -> list[dict]:
    phases = [
        ("GDS-MY34-ONSET", "Storm reaches Gale (start of the onset phase at Gale)", 2075, 2085, "high"),
        ("GDS-MY34-PEAK", "Peak at Gale / highly dusty phase (sols 2085-2100)", 2085, 2101, "high"),
    ]
    out = []
    for eid, quote, s0, s1, sev in phases:
        out.append({
            "event_id": eid,
            "event_type": "atmospheric",
            "event_subtype": "global_dust_storm_phase",
            "start_time": iso(sol_to_utc(s0)),
            "end_time": iso(sol_to_utc(s1)),
            "start_sol": s0, "end_sol": s1,
            "time_uncertainty": {"start_days": 1.03, "end_days": 1.03, "basis": "source gives sol numbers (1 sol = 1.0275 d)"},
            "confidence_in_time_bounds": "sol_resolution",
            "affected_instruments": ["REMS"],
            "affected_channels": ["uv_abc", "pressure", "air_temp", "ground_temp"],
            "severity": sev,
            "magnitude": {"peak_opacity": 8.5, "surface_uv_decrease": "~95%", "semidiurnal_tide_amplitude_Pa": 40},
            "source": "viudez2019",
            "source_type": SOURCES["viudez2019"]["source_type"],
            "citation": SOURCES["viudez2019"]["citation"],
            "notes": f"Phase marker as stated by the source: \"{quote}\". Gradual multi-sol event; a detector with a 7-sol trailing "
                     "baseline adapts during the event, so only the onset is expected to be detectable as a departure.",
        })
    return out


def main() -> None:
    guo_text, guo_sha = fetch_text("guo2018")
    lowe_text, lowe_sha = fetch_text("lowe2025")
    events = guo_events(guo_text)
    if len(events) != 121:
        raise RuntimeError(f"expected 121 FD rows, parsed {len(events)}")
    events += lowe_events(lowe_text) + [sol242_event()] + dust_storm_events()
    doc = {
        "schema": "deepsift-ground-truth-v1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sources": {k: {**v, **({"sha256": guo_sha} if k == "guo2018" else {"sha256": lowe_sha} if k == "lowe2025" else {})}
                    for k, v in SOURCES.items()},
        "coverage": {
            "guo2018": {"start": "2014-10-17T00:00:00Z", "end": "2016-09-28T23:59:59Z", "instrument": "RAD",
                        "completeness": "FD list from two independent manual identifications merged; small FDs may be missing"},
            "lowe2025": {"start": "2012-08-06T00:00:00Z", "end": "2024-10-31T23:59:59Z", "instrument": "RAD",
                         "completeness": "surface SEP events detected by RAD (16)"},
        },
        "severity_convention": {
            "note": "Fixed before Phase-2 evaluation. Not a scientific ranking.",
            "forbush_decrease": "high if drop ≥ 5 %, medium if 3–5 %, low if < 3 %",
            "solar_energetic_particle_event": "high",
            "global_dust_storm_phase": "high",
        },
        "events": events,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    by = {}
    for e in events:
        by[e["source"]] = by.get(e["source"], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(events)} events {by}")


if __name__ == "__main__":
    main()
