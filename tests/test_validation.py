from datetime import date
from docushield import validation


def _ocr(dob="1991-03-14", expiry="2032-06-19", surname="SHARMA"):
    from docushield.mrz import build_td3, parse_td3
    l1, l2 = build_td3("Sharma", "Aarav Kumar", "K4829173", "UTO", date.fromisoformat(dob), "M", date.fromisoformat(expiry))
    mrz = parse_td3(l1, l2)
    return {
        "fields": {"doc_number": "K4829173", "nationality": "UTO", "surname": surname, "given_names": "AARAV KUMAR",
                  "dob": date.fromisoformat(dob), "sex": "M", "date_of_issue": date(2022, 6, 20),
                  "date_of_expiry": date.fromisoformat(expiry)},
        "confidence": {k: 95.0 for k in ["doc_number", "nationality", "surname", "given_names", "dob", "sex", "date_of_issue", "date_of_expiry"]},
        "mrz": mrz,
    }


def test_clean_document_passes_everything():
    res = validation.run(_ocr(), registry=None)
    assert res.pass_rate > 90
    assert all(c.status != "fail" for c in res.checks)


def test_vz_mrz_mismatch_is_critical():
    res = validation.run(_ocr(surname="SHARNA"), registry=None)
    fail = [c for c in res.checks if c.id == "mrz_vz_mismatch"]
    assert fail and fail[0].status == "fail" and fail[0].severity == "critical"


def test_expired_document_flagged():
    res = validation.run(_ocr(expiry="2020-01-01"), registry=None)
    exp = [c for c in res.checks if c.id == "expired"]
    assert exp and exp[0].status == "fail"


def test_impossible_dates_flagged():
    # issue date after expiry date is impossible regardless of MRZ 2-digit-year pivoting
    ocr = _ocr()
    ocr["fields"]["date_of_issue"] = date(2033, 1, 1)
    res = validation.run(ocr, registry=None)
    dl = [c for c in res.checks if c.id == "date_logic"]
    assert dl and dl[0].status == "fail"
