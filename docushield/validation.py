"""Module 2 - Document validation rule engine (pure Python, no ML).

Every rule returns a Check with a status and a severity, so the officer sees
*which* rule fired and why. Severities:
  info     - context only
  warn     - worth a look, does not escalate the band on its own
  critical - strong evidence of forgery/invalidity (escalates the band)
  hard     - registry says revoked/lost or watchlist (escalates to RED)"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher

from docushield.registry_client import RegistryClient, RegistryUnavailable


@dataclass
class Check:
    id: str
    name: str
    status: str            # pass | warn | fail | skipped
    severity: str = "info"
    weight: float = 1.0
    detail: str = ""


@dataclass
class ValidationResult:
    checks: list = field(default_factory=list)
    pass_rate: float = 100.0
    registry: dict | None = None
    registry_state: str = "not_queried"   # ok | unreachable | not_queried


def _norm(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _names_equal(a, b) -> bool:
    return _norm(a) == _norm(b)


def run(ocr_res: dict, registry: RegistryClient | None, today: date | None = None, conf_floor: float = 60.0) -> ValidationResult:
    today = today or date.today()
    f, mrz = ocr_res["fields"], ocr_res["mrz"]
    conf = ocr_res["confidence"]
    checks: list[Check] = []

    # 1 ---- MRZ readable
    mrz_ok = bool(mrz and mrz["line1"].startswith("P<") and mrz["dob"] and mrz["expiry"] and mrz["doc_number"])
    checks.append(Check("mrz_readable", "MRZ readable & well-formed", "pass" if mrz_ok else "fail", "warn", 1,
                        "Both MRZ lines parsed." if mrz_ok else "MRZ could not be parsed - re-scan the page (glare/skew) or read manually."))

    # 2 ---- ICAO 9303 check digits
    if mrz_ok:
        bad = [k.replace("_", " ") for k, v in mrz["checks"].items() if not v]
        checks.append(Check("mrz_checksum", "ICAO 9303 MRZ check digits", "fail" if bad else "pass",
                            "critical" if bad else "info", 3,
                            ("Check digit failed for: " + ", ".join(bad) + ". The MRZ content was altered or the document is fabricated.") if bad
                            else "All 5 check digits (document no., DOB, expiry, personal no., composite) verify."))
    else:
        checks.append(Check("mrz_checksum", "ICAO 9303 MRZ check digits", "skipped", "info", 3, "MRZ unreadable."))

    # 3 ---- visual zone vs MRZ
    if mrz_ok:
        pairs = [("Surname", f["surname"], mrz["surname"], "surname", "text"),
                 ("Given names", f["given_names"], mrz["given_names"], "given_names", "text"),
                 ("Passport no.", f["doc_number"], mrz["doc_number"], "doc_number", "text"),
                 ("Date of birth", f["dob"], mrz["dob"], "dob", "date"),
                 ("Date of expiry", f["date_of_expiry"], mrz["expiry"], "date_of_expiry", "date"),
                 ("Sex", f["sex"], mrz["sex"], "sex", "text"),
                 ("Nationality", f["nationality"], mrz["nationality"], "nationality", "text")]
        mism, low_conf = [], []
        for label, vz, mz, key, kind in pairs:
            same = (vz == mz) if kind == "date" else _names_equal(vz, mz)
            if not same:
                (low_conf if conf.get(key, 100) < conf_floor else mism).append(f"{label}: printed '{vz}' vs MRZ '{mz}'")
        if mism:
            checks.append(Check("mrz_vz_mismatch", "MRZ matches printed (visual) zone", "fail", "critical", 3,
                                "Mismatch - " + "; ".join(mism) + ". One of the two zones was edited."))
        elif low_conf:
            checks.append(Check("mrz_vz_mismatch", "MRZ matches printed (visual) zone", "warn", "warn", 3,
                                "Low-confidence OCR differences (likely read errors): " + "; ".join(low_conf)))
        else:
            checks.append(Check("mrz_vz_mismatch", "MRZ matches printed (visual) zone", "pass", "info", 3,
                                "All 7 cross-checked fields agree."))
    else:
        checks.append(Check("mrz_vz_mismatch", "MRZ matches printed (visual) zone", "skipped", "info", 3, "MRZ unreadable."))

    # 4 ---- date logic
    dob = mrz["dob"] if mrz_ok else f["dob"]
    exp = mrz["expiry"] if mrz_ok else f["date_of_expiry"]
    iss = f["date_of_issue"]
    probs, warns = [], []
    if not (dob and exp and iss):
        probs.append("one or more dates unreadable")
    else:
        if dob >= today: probs.append("date of birth is in the future")
        elif (today - dob).days > 365 * 120: probs.append("holder would be over 120 years old")
        if iss >= exp: probs.append("issue date is not before expiry date")
        if iss > today: probs.append("issue date is in the future")
        if iss <= dob: probs.append("issued before the holder was born")
        if exp - iss > timedelta(days=3660): warns.append("validity longer than 10 years")
    if probs:
        checks.append(Check("date_logic", "Date plausibility", "fail", "critical", 2, "Impossible dates: " + "; ".join(probs) + "."))
    elif warns:
        checks.append(Check("date_logic", "Date plausibility", "warn", "warn", 2, "; ".join(warns).capitalize() + "."))
    else:
        checks.append(Check("date_logic", "Date plausibility", "pass", "info", 2, "DOB, issue and expiry dates are mutually consistent."))

    # 5 ---- expiry
    if exp:
        if exp < today:
            checks.append(Check("expired", "Document validity", "fail", "critical", 2, f"Document expired on {exp.isoformat()}."))
        elif exp < today + timedelta(days=183):
            checks.append(Check("expired", "Document validity", "warn", "warn", 2, f"Expires {exp.isoformat()} (<6 months validity remaining)."))
        else:
            checks.append(Check("expired", "Document validity", "pass", "info", 2, f"Valid until {exp.isoformat()}."))

    # 6 ---- ID number format
    dn = f["doc_number"] or ""
    ok_fmt = bool(re.fullmatch(r"[A-Z][0-9]{7}", dn))
    checks.append(Check("id_format", "Passport number format", "pass" if ok_fmt else "warn", "info" if ok_fmt else "warn", 1,
                        "Matches issuer pattern [A-Z]+7 digits." if ok_fmt else f"'{dn}' does not match the issuer's number pattern."))

    # 7 ---- registry (API only)
    res = ValidationResult(checks=checks)
    if registry is None:
        res.registry_state = "not_queried"
    else:
        docno = mrz["doc_number"] if mrz_ok and mrz["checks"]["document_number"] else dn
        payload = {"doc_number": docno, "surname": f["surname"], "given_names": f["given_names"],
                   "dob": f["dob"].isoformat() if f["dob"] else None,
                   "date_of_expiry": f["date_of_expiry"].isoformat() if f["date_of_expiry"] else None,
                   "nationality": f["nationality"], "sex": f["sex"]}
        try:
            r = registry.verify(payload)
            res.registry, res.registry_state = r, "ok"
        except RegistryUnavailable as e:
            res.registry_state = "unreachable"
            checks.append(Check("registry_lookup", "Registry lookup", "skipped", "warn", 2,
                                f"Registry unreachable ({e}). Verify manually against the national system."))
            r = None
        if r is not None:
            if not r["found"]:
                checks.append(Check("registry_not_found", "Registry lookup", "fail", "critical", 2,
                                    f"No document numbered '{docno}' exists in the registry."))
            else:
                checks.append(Check("registry_lookup", "Registry lookup", "pass", "info", 2, "Document number found in registry."))
                wrong = [k.replace("_", " ") for k, v in r["field_match"].items() if v is False]
                checks.append(Check("registry_mismatch", "Printed data matches registry", "fail" if wrong else "pass",
                                    "critical" if wrong else "info", 3,
                                    ("Printed value does not match the registry for: " + ", ".join(wrong) + ".") if wrong
                                    else "Name, DOB, expiry, sex and nationality all match the registry."))
                bad_status = r["status"] != "ACTIVE"
                checks.append(Check("registry_status", "Registry status", "fail" if bad_status else "pass",
                                    "hard" if bad_status else "info", 2,
                                    f"Registry status: {r['status']}." if bad_status else "Registry status: ACTIVE."))
                if r["watchlist_hit"]:
                    checks.append(Check("watchlist", "Watchlist screening", "fail", "hard", 1,
                                        f"Watchlist match (ref {r.get('watchlist_ref') or 'n/a'}). Follow the silent-alert SOP - do not "
                                        "confront the traveller; refer to the intelligence desk."))
                else:
                    checks.append(Check("watchlist", "Watchlist screening", "pass", "info", 1, "No watchlist match."))

    counted = [c for c in checks if c.status != "skipped"]
    total = sum(c.weight for c in counted) or 1.0
    got = sum(c.weight * (1.0 if c.status == "pass" else 0.5 if c.status == "warn" else 0.0) for c in counted)
    res.pass_rate = round(100.0 * got / total, 1)
    return res
