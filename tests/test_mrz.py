from datetime import date
from docushield.mrz import build_td3, parse_td3, check_digit


def test_icao_reference_example():
    # Official ICAO Doc 9303 worked example
    assert check_digit("L898902C3") == 6
    assert check_digit("740812") == 2
    assert check_digit("120415") == 9


def test_build_and_parse_roundtrip():
    l1, l2 = build_td3("Sharma", "Aarav Kumar", "K4829173", "UTO", date(1991, 3, 14), "M", date(2032, 6, 19))
    p = parse_td3(l1, l2)
    assert p["surname"] == "SHARMA"
    assert p["given_names"] == "AARAV KUMAR"
    assert p["dob"] == date(1991, 3, 14)
    assert p["expiry"] == date(2032, 6, 19)
    assert all(p["checks"].values())


def test_tampered_checksum_fails():
    l1, l2 = build_td3("Sharma", "Aarav Kumar", "K4829173", "UTO", date(1991, 3, 14), "M", date(2032, 6, 19))
    bad = l2[:14] + "9" + l2[15:]     # change a DOB digit, leave check digit stale
    p = parse_td3(l1, bad)
    assert p["checks"]["date_of_birth"] is False
    assert p["checks"]["composite"] is False


def test_ocr_confusion_repair_is_type_scoped():
    l1, l2 = build_td3("Sharma", "Aarav Kumar", "K4829173", "UTO", date(1991, 3, 14), "M", date(2032, 6, 19))
    noisy = l2.replace("UTO", "UT0")     # OCR read O as 0 in nationality (alpha field)
    p = parse_td3(l1, noisy)
    assert p["nationality"] == "UTO"
    assert all(p["checks"].values())
