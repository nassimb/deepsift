"""M3 — group PDS products into IMAGE ACQUISITIONS (the Phase 3 experimental unit).

An acquisition = every product sharing one capture instant: same sol and same spacecraft clock in the file name.
A stereo pair (left + right) and each eye's rover thumbnail therefore form ONE acquisition, never four observations.
Primary tier (the product used for image features): full > subframe > mono-downsampled > downsampled, left eye first.
Stable id: MSL-NAV-<sol:04d>-<sclk>.
"""

from __future__ import annotations

from collections import defaultdict

PRIMARY_ORDER = ["F", "S", "M", "D"]


def group_acquisitions(products: list[dict]) -> list[dict]:
    by = defaultdict(list)
    for p in products:
        by[(p["sol"], p["sclk_name"])].append(p)
    acqs = []
    for (sol, sclk), ps in sorted(by.items()):
        primaries = [p for p in ps if p["tier"] != "T"]
        thumbs = [p for p in ps if p["tier"] == "T"]
        if not primaries:
            continue                                   # thumbnail-only instants are kept out (none expected; counted)
        eyes = sorted({p["eye"] for p in primaries})
        pick = sorted(primaries, key=lambda p: (PRIMARY_ORDER.index(p["tier"]) if p["tier"] in PRIMARY_ORDER else 9, p["eye"] != "L"))[0]
        thumb = next((t for t in sorted(thumbs, key=lambda t: t["eye"] != pick["eye"])), None)
        acqs.append({
            "acq_id": f"MSL-NAV-{sol:04d}-{sclk}", "sol": sol, "sclk": min(p["sclk"] or sclk for p in ps), "utc": min(str(p["utc"]) for p in ps),
            "sequence_id": pick["sequence_id"], "site": pick["site"], "drive": pick["drive"], "pose": pick["pose"],
            "eyes": eyes, "stereo": eyes == ["L", "R"], "primary_tier": pick["tier"], "frame_type": pick["frame_type"],
            "azimuth_deg": pick["instrument_azimuth_deg"], "elevation_deg": pick["instrument_elevation_deg"],
            "primary": pick, "primaries": primaries, "thumbnail": thumb, "thumbnails": thumbs,
            "product_ids": sorted(p["product_id"] for p in ps),
        })
    return acqs


def grouping_stats(products: list[dict], acqs: list[dict]) -> dict:
    tiers = defaultdict(int)
    for a in acqs:
        tiers[a["primary_tier"]] += 1
    return {"products": len(products), "acquisitions": len(acqs), "stereo_acquisitions": sum(a["stereo"] for a in acqs),
            "mono_acquisitions": sum(not a["stereo"] for a in acqs), "primary_tier_counts": dict(tiers),
            "acquisitions_with_thumbnail": sum(1 for a in acqs if a["thumbnail"]),
            "products_per_acquisition_mean": len(products) / max(1, len(acqs))}
