#!/usr/bin/env python3
"""Presentation-only Navcam previews for the public Mission Control (held-out traverses, sols 950–979).

    uv run python scripts/build_navcam_previews.py

For every acquisition in apps/web/data/mission-control.json, renders the actual NASA PDS products named by the frozen
product IDs:
  * primary (full-quality tier, each eye)  → 160 px max-side grayscale JPEG
  * rover thumbnail product (T tier, each eye) → 64 px grayscale JPEG (native size)
Deterministic derivation: native DN (PDS3 reader) → linear stretch between the 0.5th and 99.5th DN percentiles → 8-bit →
PIL LANCZOS downscale (never upscaled) → JPEG (fixed quality, optimize, baseline). No enhancement, no generated content,
no interpretation. Each source .IMG is verified against the SHA-256 in data/manifests/navcam_test.json first.

Outputs apps/web/public/navcam/SOLnnnnn/<product_id>.jpg and apps/web/public/navcam/provenance.json. These previews are
NOT scientific artifacts: no experiment, metric or retained set uses them.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import PIL
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.imaging.pds3 import parse_label, read_image  # noqa: E402

OUT = ROOT / "apps" / "web" / "public" / "navcam"
PARAMS = {"stretch_percentiles": [0.5, 99.5], "primary_max_px": 160, "thumbnail_max_px": 64, "jpeg_quality": {"primary": 70, "thumbnail": 85},
          "resample": "LANCZOS", "jpeg": "baseline, optimize=True, grayscale"}


def render(img_path: Path, lbl_path: Path, max_px: int, quality: int, dst: Path) -> tuple[int, int]:
    dn = read_image(img_path, parse_label(lbl_path.read_text(encoding="latin-1"))).astype(np.float64)
    lo, hi = np.percentile(dn, PARAMS["stretch_percentiles"])
    if hi <= lo:
        lo, hi = float(dn.min()), float(dn.max()) or 1.0
    u8 = np.clip((dn - lo) / (hi - lo) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    im = Image.fromarray(u8)
    s = min(1.0, max_px / max(im.size))
    if s < 1.0:
        im = im.resize((max(1, round(im.size[0] * s)), max(1, round(im.size[1] * s))), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, format="JPEG", quality=quality, optimize=True, progressive=False)
    return im.size


def main() -> int:
    mc = json.loads((ROOT / "apps/web/data/mission-control.json").read_text())
    prods = {p["product_id"]: p for p in json.loads((ROOT / "data/manifests/navcam_test.json").read_text())["products"]}
    entries, total = [], 0
    for tr in mc["traverses"]:
        for f in tr["frames"]:
            for role, ids, max_px in (("primary", f["primary"], PARAMS["primary_max_px"]), ("thumbnail", f["thumbnails"], PARAMS["thumbnail_max_px"])):
                for pid in ids:
                    p = prods[pid]
                    img, lbl = ROOT / p["path_img"], ROOT / p["path_lbl"]
                    assert hashlib.sha256(img.read_bytes()).hexdigest() == p["sha256_img"], f"source changed: {pid}"
                    dst = OUT / f"SOL{p['sol']:05d}" / f"{pid}.jpg"
                    w, h = render(img, lbl, max_px, PARAMS["jpeg_quality"][role], dst)
                    total += dst.stat().st_size
                    entries.append({"product_id": pid, "acq_id": f["acq_id"], "sol": p["sol"], "eye": p["eye"], "tier": p["tier"], "role": role,
                                    "source_url_img": p["url_img"], "source_sha256_img": p["sha256_img"], "source_size": [p["line_samples"], p["lines"]],
                                    "preview": f"/navcam/SOL{p['sol']:05d}/{pid}.jpg", "preview_size": [w, h],
                                    "preview_sha256": hashlib.sha256(dst.read_bytes()).hexdigest()})
    (OUT / "provenance.json").write_text(json.dumps({
        "label": "NASA PDS OBSERVATION previews — presentation only, not used by any experiment or metric",
        "credit": "NASA/JPL-Caltech · Mars Science Laboratory Navcam raw EDR (PDS Imaging Node, MSLNAV_0XXX)",
        "licence_note": "NASA/PDS data are not covered by the DEEPSIFT Apache-2.0 code licence; see NOTICE",
        "display_note": ("Display preview: contrast-stretched for visualization (per-image 0.5–99.5th DN percentile linear stretch); "
                         "previews are not photometrically comparable across observations. Display resolution reflects the downlink "
                         "representation shown in the replay, not a judgement of scientific importance."),
        "derivation": PARAMS, "software": {"pillow": PIL.__version__, "numpy": np.__version__, "reader": "deepsift.imaging.pds3.read_image"},
        "source_manifest": "data/manifests/navcam_test.json", "count": len(entries), "entries": entries}, indent=1))
    print(f"{len(entries)} previews · {total / 1e6:.1f} MB → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
