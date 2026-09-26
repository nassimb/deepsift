#!/usr/bin/env python3
"""Open Graph / Twitter preview (1200×630 PNG) for the public site, drawn from apps/web/data/release.json only.

    uv run python scripts/make_social_preview.py

Writes apps/web/app/opengraph-image.png, twitter-image.png and their .alt.txt files (Next.js metadata file conventions).
No NASA logo or insignia; plain text and numbers from the frozen held-out result.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import matplotlib
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "web" / "app"
FONTS = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
BG, INK, INK2, INK3, ACC, LINE = "#07080a", "#e4e7ea", "#a3abb4", "#6b747e", "#6da7ec", "#272c33"


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def main() -> int:
    r = json.loads((ROOT / "apps" / "web" / "data" / "release.json").read_text())
    h = r["headline"]
    kpis = [(f"{h['bytes_fraction'] * 100:.1f}%", "full-quality bytes"), (f"{h['coverage_5m'] * 100:.0f}%", "5 m spatial coverage"),
            (f"{h['max_distance_to_kept_m_worst']:.2f} m", "max nearest-kept distance"), (str(h["stereo_broken"]), "broken stereo pairs")]
    im = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, 1200, 60):
        d.line([(x, 0), (x, 630)], fill="#0e1014")
    for y in range(0, 630, 60):
        d.line([(0, y), (1200, y)], fill="#0e1014")
    mono, monob, sans = "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf", "DejaVuSans.ttf"
    d.text((70, 62), "D E E P S I F T", font=font(monob, 30), fill=INK)
    d.text((70, 112), "Autonomous downlink research", font=font(sans, 44), fill=INK)
    d.text((70, 170), "Curiosity Navcam · held-out test · sols 950–979", font=font(mono, 24), fill=ACC)
    d.text((70, 206), "Scheduler V3 + rover-position sampling · 1/4 of traverse frames kept at full quality", font=font(sans, 20), fill=INK2)
    x0, y0, w = 70, 290, 265
    for i, (v, k) in enumerate(kpis):
        x = x0 + i * w
        d.rectangle([x, y0, x + w - 16, y0 + 170], outline=LINE, width=2)
        d.text((x + 20, y0 + 28), v, font=font(mono, 50), fill=INK)
        d.text((x + 20, y0 + 110), k, font=font(sans, 17), fill=INK2)
    d.text((70, 510), f"Pre-registered criterion: {h['result']} · {r['test_dataset']['traverse_sequences_ge_10_frames']} traverses, "
                      f"{r['test_dataset']['traverse_frames']} archived frames", font=font(mono, 18), fill=INK3)
    d.text((70, 545), "Retrospective replay of archived NASA PDS data · independent research prototype · not NASA-affiliated",
           font=font(sans, 16), fill=INK3)
    out = APP / "opengraph-image.png"
    im.save(out, optimize=True)
    shutil.copy(out, APP / "twitter-image.png")
    alt = (f"DEEPSIFT held-out test on Curiosity Navcam sols 950–979: {kpis[0][0]} of full-quality bytes, {kpis[1][0]} 5 m spatial coverage, "
           f"{kpis[2][0]} maximum distance to a kept frame, {kpis[3][0]} broken stereo pairs.")
    for n in ("opengraph-image.alt.txt", "twitter-image.alt.txt"):
        (APP / n).write_text(alt)
    print("→", out.relative_to(ROOT), out.stat().st_size // 1024, "kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
