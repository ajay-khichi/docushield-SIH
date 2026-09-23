"""Registry lookup logic, shared by:
  - the HTTP API (registry_service/app.py)          - used by Docker/local multi-service setup
  - the in-process LocalRegistryClient               - used by single-process free hosting

Keeping the logic here means both transports return byte-for-byte identical
results; only how a caller reaches this code differs."""
from __future__ import annotations
from registry_service import db


def verify_payload(payload: dict) -> dict:
    row = db.get(str(payload.get("doc_number") or "").strip().upper())
    if not row:
        return {"found": False}

    def eq(a, b):
        return None if a is None else (str(a).strip().upper() == str(b).strip().upper())

    match = {"surname": eq(payload.get("surname"), row["surname"]),
             "given_names": eq(payload.get("given_names"), row["given_names"]),
             "dob": eq(payload.get("dob"), row["dob"]),
             "date_of_expiry": eq(payload.get("date_of_expiry"), row["expiry_date"]),
             "nationality": eq(payload.get("nationality"), row["nationality"]),
             "sex": eq(payload.get("sex"), row["sex"])}
    return {"found": True, "status": row["status"], "field_match": match,
            "watchlist_hit": bool(row["watchlist"]), "watchlist_ref": row["watchlist_note"] or None}


def get_photo_row(doc_number: str):
    return db.get(doc_number.strip().upper())
