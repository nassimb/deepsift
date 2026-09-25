"""SYNTHETIC_GENERATOR_V2 contract tests (synthetic images only)."""

import numpy as np
import pytest

from deepsift.imaging import synthetic as v1
from deepsift.imaging import synthetic_v2 as v2


def _img(dark: bool):
    rng = np.random.default_rng(5)
    lo, hi = (5, 400) if dark else (600, 3200)
    return rng.uniform(lo, hi, (128, 160)).astype(np.float32)


@pytest.mark.parametrize("family", list(v2.FAMILIES))
@pytest.mark.parametrize("level", v2.LEVELS)
@pytest.mark.parametrize("dark", [False, True])
def test_v2_families_satisfy_their_contracts(family, level, dark):
    src = _img(dark)
    for seed in range(4):
        out, p, box = v2.perturb(src, family, level, seed)
        assert v2.check_contract(family, src, out, p, box) == [], (family, level, dark, seed)
        if v2.CONTRACTS[family]["kind"] == "VISUAL_NOVELTY":
            assert 0.0 <= p["amplitude_scale"] <= 1.0 and float(out.min()) >= v2.DN_LO and float(out.max()) <= v2.DN_HI


def test_near_duplicate_contract():
    for dark in (False, True):
        src = _img(dark)
        out, p = v2.near_duplicate(src, 3)
        assert v2.check_contract("NEAR_DUPLICATE", src, out, p, None) == []


def test_v1_visual_generator_violates_on_dark_images_documented():
    src = _img(True)
    viol = set()
    for seed in range(10):
        out, p, box = v1.perturb(src, "TEXTURE_CHANGE", "OBVIOUS", seed)
        viol.update(v2.check_contract("TEXTURE_CHANGE", src, out, p, box))
    assert "new_zero_pixels" in viol          # the Phase 3.1 cross-talk, reproduced
