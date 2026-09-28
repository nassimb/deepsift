"""Public Phase 3 Mission Control: frozen release data only, exact frozen results, no API / localhost dependency."""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from deepsift.evaluation import traverse as T

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2"
MCJ = ROOT / "apps/web/data/mission-control.json"
WEB = ROOT / "apps/web"
SOURCES = [WEB / "app/mission-control/page.tsx", WEB / "components/mission/MissionControl.tsx", WEB / "lib/missionControl.ts"]


@pytest.fixture(scope="module")
def mc():
    return json.loads(MCJ.read_text())


@pytest.fixture(scope="module")
def frozen():
    return json.loads((RUN / "results.json").read_text())


def test_headline_and_operating_points_match_frozen_final_test(mc, frozen):
    p = frozen["primary"]
    assert mc["primary"]["result"] == p["RESULT"] == "PASS"
    for k in ("bytes_fraction", "coverage_5m", "max_distance_to_kept_m_worst", "stereo_broken"):
        assert mc["primary"][k] == p["metrics"][k]
    S = frozen["traverse"]["summary"]
    assert mc["operating_points"]["send_all"]["bytes_fraction"] == S["1.0|SEND_ALL"]["bytes_fraction"]
    for f in ("0.5", "0.25", "0.125"):
        for k, v in mc["operating_points"][f].items():
            assert v == S[f"{f}|METADATA_POSITION"][k], (f, k)
    assert mc["operating_points"]["0.25"]["bytes_fraction"] == p["metrics"]["bytes_fraction"]


def test_retained_frame_sets_match_frozen_selection(mc, frozen):
    obs = [json.loads(x) for x in (RUN / "observations.jsonl").read_text().splitlines()]
    idx = {o["id"]: i for i, o in enumerate(obs)}
    E = np.load(RUN / "embeddings.npy")
    rows = {(r["sequence"], r["fraction"], r["method"]): r for r in frozen["traverse"]["rows"]}
    assert len(mc["traverses"]) == frozen["traverse"]["sequences"]
    for tr in mc["traverses"]:
        ids = [f["acq_id"] for f in tr["frames"]]
        xy = np.array([[obs[idx[a]]["location_context"]["landing_x"], obs[idx[a]]["location_context"]["landing_y"]] for a in ids])
        em = E[[idx[a] for a in ids]]
        for f, pol in tr["policies"].items():
            assert pol["kept"] == T.select("METADATA_POSITION", xy, em, float(f)), (tr["sequence"], f)
            st = rows[(tr["sequence"], float(f), "METADATA_POSITION")]
            assert pol["metrics"]["frames_retained"] == st["frames_retained"] == len(pol["kept"])
            assert pol["metrics"]["max_distance_to_kept_m"] == st["max_distance_to_kept_m"]
            assert pol["metrics"]["coverage_5m"] == st["position_coverage"]
            assert abs(max(d for _, d in pol["nearest"]) - st["max_distance_to_kept_m"]) < 1e-3


def test_frames_are_in_frozen_time_order_within_each_traverse(mc):
    for tr in mc["traverses"]:
        t = [datetime.fromisoformat(f["utc"]).replace(tzinfo=timezone.utc).timestamp() for f in tr["frames"]]
        assert t == sorted(t) and tr["frames"][0]["t_s"] == 0


def test_stereo_pairs_never_split_in_primary_policy(mc):
    for tr in mc["traverses"]:
        for j in tr["policies"]["0.25"]["kept"]:
            f = tr["frames"][j]
            if f["stereo"]:
                assert f["full_bytes"] and f["full_bytes"] > 0
                eyes = sorted(p[:2] for p in f["primary"])
                assert eyes == ["NL", "NR"], f["acq_id"]
                assert sorted(p[:2] for p in f["thumbnails"]) == ["NL", "NR"]
        assert tr["policies"]["0.25"]["metrics"]["stereo_broken"] == 0


def test_public_mission_control_has_no_api_or_localhost_dependency(mc):
    for p in SOURCES:
        src = p.read_text()
        assert "@/lib/api" not in src and "fetch(" not in src, p
        assert not re.search(r"localhost|127\.0\.0\.1|:8787|NEXT_PUBLIC_DEEPSIFT_API", src), p
    blob = MCJ.read_text()
    assert "localhost" not in blob and ":8787" not in blob
    urls = set(re.findall(r"https?://[^\"/]+", blob))
    assert urls <= {"https://planetarydata.jpl.nasa.gov"}, urls


def test_rendered_mission_control_contains_no_localhost():
    html = WEB / ".next/server/app/mission-control.html"
    if not html.exists():
        pytest.skip("web app not built")
    text = html.read_text()
    assert "localhost" not in text and ":8787" not in text
    assert "HISTORICAL REPLAY" in text and "LIVE NASA FEED" not in text.upper().replace("NEVER A LIVE NASA FEED", "")


def test_data_built_only_from_frozen_final_run(mc):
    assert mc["source"]["run"] == "artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2"
    counts = defaultdict(int)
    for tr in mc["traverses"]:
        counts["frames"] += tr["frames_count"]
    ds = json.loads((RUN / "dataset_report.json").read_text())
    assert counts["frames"] == ds["traverse_frames"]
