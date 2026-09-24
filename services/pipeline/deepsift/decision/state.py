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
        if "stuck" in c.flags:
            quality.append("values stuck (identical consecutive samples)")
        if "dropout" in c.flags:
            quality.append(f"{c.missing_fraction:.0%} of samples missing")
        if "noise" in c.flags:
            quality.append(f"sample-to-sample noise {c.noise_ratio:.0f}x normal")
        if "dip" in c.flags:
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


# ---------------------------------------------------------------- ablation variants (Phase 2)
STATE_VARIANTS = ("full_context", "no_mission_objective", "minimal", "numeric_only")


def build_state_variant(event: ScientificEvent, mission_name: str, location: str, variant: str,
                        objective: dict | None = None) -> dict:
    """State sent to the engine for each ablation variant. Deterministic; never contains labels."""
    if variant == "no_mission_objective":
        return build_state(event, mission_name, location)
    if variant == "full_context":
        s = build_state(event, mission_name, location)
        if objective:
            s["mission_objective"] = {"name": objective.get("name"), "description": objective.get("description")}
        return s
    f = event.features
    if variant == "minimal":
        return {
            "instrument": event.instrument,
            "local_time": local_time_words(f.lmst_hour),
            "duration": duration_words(f.duration_s),
            "sensors_flagged": {
                name: [deviation_words(c.robust_z)] + [q for q in c.flags if q != "level"]
                for name, c in f.channels.items() if name in event.sensors
            },
        }
    if variant == "numeric_only":
        return {
            "instrument": event.instrument,
            "lmst_hour": round(f.lmst_hour, 3),
            "duration_s": round(f.duration_s, 1),
            "channels": {
                name: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in {
                    "mean": c.mean, "baseline": c.baseline, "robust_z": c.robust_z, "dip": c.dip,
                    "flat_fraction": c.flat_fraction, "missing_fraction": c.missing_fraction,
                    "noise_ratio": c.noise_ratio, "rarity": c.rarity}.items()}
                for name, c in f.channels.items()
            },
        }
    raise ValueError(f"unknown state variant {variant}")
