"""Fabricated identity generator. Names are random combinations of common
given/family names; numbers and faces are fabricated. No real person."""
from __future__ import annotations
import random
from datetime import date, timedelta

FIRST = ["Aarav", "Priya", "Rohan", "Meera", "Kabir", "Ananya", "Vihaan", "Ishita", "Arjun", "Diya", "Neel", "Sanya",
         "Aditya", "Kavya", "Yash", "Tara", "Dev", "Riya", "Nikhil", "Pooja", "Samir", "Leela", "Omar", "Zoya"]
LAST = ["Sharma", "Verma", "Iyer", "Khan", "Patel", "Reddy", "Nair", "Singh", "Gupta", "Das", "Menon", "Joshi",
        "Rao", "Mehta", "Bose", "Kulkarni", "Thakur", "Pillai", "Chopra", "Sethi"]
PLACES = ["NORTHVALE", "EASTHAVEN", "LAKEMONT", "STONEBRIDGE", "RIVERTON", "HIGHFIELD"]


def make_person(r: random.Random, face_seed: int, doc_number: str | None = None, **over) -> dict:
    today = date(2026, 9, 1)
    dob = date(1955, 1, 1) + timedelta(days=r.randint(0, 20000))
    issue = today - timedelta(days=r.randint(60, 2800))
    rec = {
        "doc_number": doc_number or (r.choice("KLMNPRTW") + "".join(str(r.randint(0, 9)) for _ in range(7))),
        "surname": r.choice(LAST), "given_names": r.choice(FIRST) + (" " + r.choice(FIRST) if r.random() < .6 else ""),
        "dob": dob, "sex": r.choice("MF"), "nationality": "UTO", "place_of_birth": r.choice(PLACES),
        "issue_date": issue, "expiry_date": issue + timedelta(days=3652),
        "status": "ACTIVE", "watchlist": 0, "watchlist_note": "", "face_seed": face_seed,
    }
    rec.update(over)
    return rec
