"""ICAO Doc 9303 TD3 (passport) MRZ: build, parse, checksum. Pure Python."""
from __future__ import annotations
import re
from datetime import date

_W = (7, 3, 1)


def char_value(c: str) -> int:
    if c.isdigit():
        return int(c)
    if c == "<":
        return 0
    if "A" <= c <= "Z":
        return ord(c) - 55
    raise ValueError(f"illegal MRZ char {c!r}")


def check_digit(field: str) -> int:
    return sum(char_value(c) * _W[i % 3] for i, c in enumerate(field)) % 10


def _pad(s: str, n: int) -> str:
    return (s + "<" * n)[:n]


def build_td3(surname: str, given: str, doc_no: str, nationality: str,
              dob: date, sex: str, expiry: date, personal_no: str = "",
              issuing: str | None = None) -> tuple[str, str]:
    issuing = issuing or nationality
    name = (surname.upper().replace(" ", "<").replace("-", "<") + "<<"
            + given.upper().replace(" ", "<").replace("-", "<"))
    l1 = _pad("P<" + issuing + name, 44)
    docf = _pad(doc_no.upper(), 9)
    dobf, expf = dob.strftime("%y%m%d"), expiry.strftime("%y%m%d")
    pers = _pad(personal_no.upper(), 14)
    l2 = (docf + str(check_digit(docf)) + nationality + dobf + str(check_digit(dobf))
          + sex + expf + str(check_digit(expf)) + pers + str(check_digit(pers)))
    composite = l2[0:10] + l2[13:20] + l2[21:43]
    l2 += str(check_digit(composite))
    assert len(l1) == 44 and len(l2) == 44
    return l1, l2


# OCR confusion tables (only applied at positions where the type is fixed)
_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2",
             "B": "8", "S": "5", "G": "6"}
_TO_ALPHA = {"0": "O", "1": "I", "2": "Z", "8": "B", "5": "S", "6": "G"}


def normalize_line(line: str, n: int = 44) -> str:
    """Clean raw OCR output of one MRZ line (case, spaces, length)."""
    line = re.sub(r"\s+", "", line.upper())
    line = re.sub(r"[^A-Z0-9<]", "<", line)
    return (line + "<" * n)[:n]


def correct_td3_line2(l2: str) -> str:
    """Position-aware OCR-confusion repair on fixed-type positions only
    (check digits, dates, composite -> digits; nationality -> letters).
    Never touches the doc-number / personal-number fields, so it cannot
    'repair' a tampered value into a valid one."""
    chars = list(l2)
    numeric_pos = [9] + list(range(13, 20)) + list(range(21, 28)) + [42, 43]
    for i in numeric_pos:
        chars[i] = _TO_DIGIT.get(chars[i], chars[i])
    for i in (10, 11, 12):
        chars[i] = _TO_ALPHA.get(chars[i], chars[i])
    return "".join(chars)


def _parse_date(s: str, kind: str, today: date | None = None) -> date | None:
    try:
        yy, mm, dd = int(s[:2]), int(s[2:4]), int(s[4:6])
        today = today or date.today()
        if kind == "dob":
            year = 2000 + yy if 2000 + yy <= today.year else 1900 + yy
        else:
            year = 2000 + yy
        return date(year, mm, dd)
    except (ValueError, TypeError):
        return None


def parse_td3(l1: str, l2: str, today: date | None = None) -> dict:
    l1, l2 = normalize_line(l1), correct_td3_line2(normalize_line(l2))
    surname, _, given = l1[5:].partition("<<")
    res = {
        "line1": l1, "line2": l2,
        "doc_type": l1[0], "issuing_country": l1[2:5],
        "surname": surname.replace("<", " ").strip(),
        "given_names": given.replace("<", " ").strip(),
        "doc_number": l2[0:9].replace("<", ""),
        "nationality": l2[10:13],
        "dob_raw": l2[13:19], "sex": l2[20],
        "expiry_raw": l2[21:27],
        "personal_number": l2[28:42].replace("<", ""),
        "dob": _parse_date(l2[13:19], "dob", today),
        "expiry": _parse_date(l2[21:27], "expiry", today),
    }

    def ok(field: str, digit: str) -> bool:
        try:
            return digit.isdigit() and check_digit(field) == int(digit)
        except ValueError:
            return False

    composite = l2[0:10] + l2[13:20] + l2[21:43]
    res["checks"] = {
        "document_number": ok(l2[0:9], l2[9]),
        "date_of_birth": ok(l2[13:19], l2[19]),
        "date_of_expiry": ok(l2[21:27], l2[27]),
        "personal_number": ok(l2[28:42], l2[42]) or set(l2[28:43]) <= {"<", "0"},
        "composite": ok(composite, l2[43]),
    }
    return res
