"""Phase 3 imaging invariants — SYNTHETIC TEST DATA only (no NASA products needed)."""

import numpy as np

from deepsift.evaluation.image_benchmark import allocate
from deepsift.imaging.acquisitions import group_acquisitions
from deepsift.imaging.features import hamming, phash, quality
from deepsift.imaging.pds3 import parse_label, read_image

LABEL = ('PDS_VERSION_ID = PDS3\r\nRECORD_BYTES = 16\r\nLABEL_RECORDS = 1\r\n^IMAGE = ("X.IMG",\r\n   3)\r\n'
         'ROVER_MOTION_COUNTER = (17,826,2,0)\r\nGROUP = COMPRESSION_PARMS\r\n  INST_CMPRS_NAME = "ICER"\r\n  INST_CMPRS_RATE = 3.0\r\n'
         'END_GROUP = COMPRESSION_PARMS\r\nOBJECT = IMAGE\r\n  LINES = 2\r\n  LINE_SAMPLES = 3\r\n  SAMPLE_TYPE = MSB_INTEGER\r\n'
         '  SAMPLE_BITS = 16\r\nEND_OBJECT = IMAGE\r\nEND\r\n')


def test_pds3_label_and_image_offset(tmp_path):
    L = parse_label(LABEL)
    assert L["^IMAGE"] == ["X.IMG", 3] and L["ROVER_MOTION_COUNTER"] == [17, 826, 2, 0]
    assert L["COMPRESSION_PARMS"]["INST_CMPRS_RATE"] == 3.0 and L["OBJECT:IMAGE"]["LINES"] == 2
    px = np.array([[1, 2, 3], [4095, 0, 7]], dtype=">i2")
    (tmp_path / "X.IMG").write_bytes(b"\xff" * 32 + px.tobytes())          # 2 header records of 16 bytes
    assert read_image(tmp_path / "X.IMG", L).tolist() == [[1, 2, 3], [4095, 0, 7]]


def _p(sclk, eye, tier, est=100.0):
    return {"sol": 412, "sclk_name": sclk, "sclk": float(sclk), "utc": "2013-10-03T11:04:39.557", "eye": eye, "tier": tier,
            "sequence_id": "trav00108", "site": 17, "drive": 826, "pose": 2, "frame_type": "STEREO",
            "instrument_azimuth_deg": 10.0, "instrument_elevation_deg": -20.0, "product_id": f"{eye}{tier}{sclk}",
            "estimated_downlink_bytes": est}


def test_stereo_pair_and_thumbnails_are_one_acquisition():
    acqs = group_acquisitions([_p(1, "L", "D"), _p(1, "R", "D"), _p(1, "L", "T"), _p(1, "R", "T"), _p(2, "L", "F")])
    assert len(acqs) == 2
    a = acqs[0]
    assert a["stereo"] and a["primary_tier"] == "D" and a["primary"]["eye"] == "L" and len(a["product_ids"]) == 4
    assert acqs[1]["acq_id"] == "MSL-NAV-0412-2" and not acqs[1]["stereo"]


def test_allocator_degrades_and_skips_unknown_costs():
    costs = [{"NONE": 0, "METADATA": 10, "THUMBNAIL": 50, "COMPRESSED": 200, "FULL": 1000},
             {"NONE": 0, "METADATA": 10, "THUMBNAIL": 50, "COMPRESSED": None, "FULL": 1000}]
    assert allocate(costs, [[(0, "FULL"), (1, "FULL")]], 1100) == ["FULL", "THUMBNAIL"]
    assert allocate(costs, [[(1, "FULL")]], 500) == ["NONE", "THUMBNAIL"]        # UNKNOWN compressed tier skipped
    # two passes: thumbnails first, then upgrades pay only the increment
    assert allocate(costs, [[(0, "THUMBNAIL"), (1, "THUMBNAIL")], [(0, "FULL")]], 1050) == ["FULL", "THUMBNAIL"]


def test_quality_states_are_engineering_only():
    rng = np.random.default_rng(0)
    clean = rng.uniform(800, 3000, (64, 64)).astype(np.float32)
    assert quality(clean, 0)["quality_state"] == "CLEAN"
    sat = clean.copy()
    sat[:40] = 4095
    assert quality(sat, 0)["quality_state"] == "BAD"
    miss = clean.copy()
    miss[:3] = 0
    assert quality(miss, 0)["quality_state"] == "SUSPECT"


def test_phash_stable_under_small_noise_and_different_for_other_scenes():
    rng = np.random.default_rng(1)
    base = np.kron(rng.uniform(500, 3500, (8, 8)), np.ones((32, 32))).astype(np.float32)
    noisy = base + rng.normal(0, 10, base.shape).astype(np.float32)
    other = np.kron(rng.uniform(500, 3500, (8, 8)), np.ones((32, 32))).astype(np.float32)
    assert hamming(phash(base), phash(noisy)) <= 4 < hamming(phash(base), phash(other))
