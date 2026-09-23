from docushield import risk


def test_clean_is_green():
    r = risk.compute(100, 0, 95, [])
    assert r.band == "GREEN"


def test_single_critical_escalates_to_amber_minimum():
    flags = [{"title": "x", "severity": "critical"}]
    r = risk.compute(95, 5, 95, flags)
    assert r.band != "GREEN"


def test_watchlist_hard_flag_forces_red():
    flags = [{"title": "watchlist", "severity": "hard"}]
    r = risk.compute(95, 5, 95, flags)
    assert r.band == "RED"


def test_no_face_score_renormalises_weights():
    r = risk.compute(100, 0, None, [])
    assert "face" not in r.weights_used
    assert abs(sum(r.weights_used.values()) - 1.0) < 1e-6
