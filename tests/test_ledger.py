import os
from docushield.ledger import HashChainLedger


def test_chain_detects_tamper(tmp_path):
    p = str(tmp_path / "ledger.jsonl")
    led = HashChainLedger(p)
    led.record_screening("CP1", "K4829173", {"final": 10, "band": "GREEN"}, [])
    led.record_screening("CP1", "K4829173", {"final": 66, "band": "RED"}, ["watchlist"])
    ok, _, _ = led.verify()
    assert ok
    # tamper: rewrite an entry's risk_score without recomputing the hash
    lines = open(p).read().splitlines()
    import json
    e = json.loads(lines[0]); e["risk_score"] = 999
    lines[0] = json.dumps(e)
    open(p, "w").write("\n".join(lines) + "\n")
    led2 = HashChainLedger(p)
    ok2, bad_i, msg = led2.verify()
    assert not ok2 and bad_i == 0


def test_pseudonym_is_stable_and_not_reversible_trivially():
    from docushield.ledger import pseudonym
    a = pseudonym("K4829173")
    b = pseudonym("K4829173")
    c = pseudonym("L5530021")
    assert a == b and a != c and len(a) == 24
