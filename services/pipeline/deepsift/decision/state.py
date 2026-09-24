"""Deterministic construction of the compact event state sent to a decision engine.

TypeSafe documents that Jev is weak at arithmetic and at reading raw numbers, so every
numeric feature is paired with a qualitative descriptor computed here, in code. Raw sensor rows
are never sent — only the aggregated event.
"""

from __future__ import annotations

from deepsift.core.models import ScientificEvent


def deviation_words(z: float) -> str:
    a = abs(z)
    direction = "above" if z > 0 else "below"
    if a < 2:
        return "within normal variability"
    if a < 4:
        return f"moderately {direction} normal"
    if a < 8:
        return f"strongly {direction} normal"
    return f"extremely far {direction} normal"


def rarity_words(r: float) -> str:
    if r >= 0.99:
        return "rarer than 99% of earlier observations"
    if r >= 0.95:
        return "rarer than 95% of earlier observations"
    if r >= 0.8:
        return "uncommon"
    return "common"


def duration_words(s: float) -> str:
    if s < 120:
        return f"brief ({s:.0f} s)"
    if s < 3600:
        return f"minutes-long ({s / 60:.0f} min)"
    return f"hours-long ({s / 3600:.1f} h)"


def local_time_words(h: float) -> str:
    part = "night" if h < 6 or h >= 19 else "morning" if h < 11 else "midday" if h < 14 else "afternoon"
    return f"{int(h):02d}:{int((h % 1) * 60):02d} local mean solar time ({part})"


def build_state(event: ScientificEvent, mission_name: str, location: str) -> dict:
    f = event.features
    channels = {}
    for name, c in f.channels.items():
        d = {
            "measured": f"{c.mean:.2f} {c.unit} (range {c.min:.2f}–{c.max:.2f})" if c.mean is not None else "no samples received",
            "usual_for_this_local_time": f"{c.baseline:.2f} {c.unit}" if c.baseline is not None else "unknown",
            "deviation": f"{c.robust_z:+.1f} sigma — {deviation_words(c.robust_z)}",
            "rarity": rarity_words(c.rarity),
        }
        quality = []
        if c.flat_fraction >= 0.95:
            quality.append("values stuck (identical consecutive samples)")
        if c.missing_fraction >= 0.5:
            quality.append(f"{c.missing_fraction:.0%} of samples missing")
        if c.noise_ratio >= 4:
            quality.append(f"sample-to-sample noise {c.noise_ratio:.0f}x normal")
        if name == "pressure" and c.dip >= 0.75:
            quality.append(f"short pressure drop of {c.dip:.2f} Pa below the running median")
        if quality:
            d["notes"] = quality
        channels[name] = d
    return {
        "mission": mission_name,
        "location": location,
        "instrument": event.instrument,
        "local_time": local_time_words(f.lmst_hour),
        "duration": duration_words(f.duration_s),
        "sensors_flagged": event.sensors,
        "number_of_sensors_flagged": len(event.sensors),
        "other_instrument_also_anomalous": "yes" if f.cross_instrument_coincidence else "no",
        "similar_to_earlier_events": "no" if f.novelty > 0.5 else "yes",
        "detection_reasons": f.trigger_reasons[:6],
        "channels": channels,
    }
