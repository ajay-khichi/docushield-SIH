"""Seed the mock registry and build the demo sample pack (documents + selfies +
manifest). Everything is fabricated: names, numbers, faces, document art.

    python -m synth.generate            # writes samples/ and data/registry.db
"""
from __future__ import annotations
import json, os, random, sys
from datetime import date

import numpy as np
from PIL import Image, ImageFilter

from registry_service import db
from synth.faces import make_face, make_selfie
from synth.people import make_person
from synth.render import (render_document, save_scan, edit_field, edit_mrz_line, swap_photo, forger_save)
from docushield.mrz import build_td3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPOSTOR_SEED = 61

PERSONAS = {
    "holder":   dict(doc_number="K4829173", surname="Sharma", given_names="Aarav Kumar", dob=date(1991, 3, 14), sex="M",
                     issue_date=date(2022, 6, 20), expiry_date=date(2032, 6, 19), face_seed=11),
    "second":   dict(doc_number="L5530021", surname="Iyer", given_names="Meera", dob=date(1985, 11, 2), sex="F",
                     issue_date=date(2023, 2, 10), expiry_date=date(2033, 2, 9), face_seed=15),
    "revoked":  dict(doc_number="R1234567", surname="Khan", given_names="Omar Yusuf", dob=date(1979, 7, 25), sex="M",
                     issue_date=date(2021, 5, 4), expiry_date=date(2031, 5, 3), face_seed=12, status="REVOKED"),
    "watch":    dict(doc_number="W7654321", surname="Das", given_names="Nikhil", dob=date(1988, 1, 30), sex="M",
                     issue_date=date(2024, 3, 3), expiry_date=date(2034, 3, 2), face_seed=13,
                     watchlist=1, watchlist_note="WL-REF-0042"),
    "expired":  dict(doc_number="T2020202", surname="Nair", given_names="Kavya", dob=date(1970, 4, 9), sex="F",
                     issue_date=date(2015, 12, 1), expiry_date=date(2025, 11, 30), face_seed=16),
}
FORGED = dict(doc_number="F0000001", surname="Verma", given_names="Rohan", dob=date(1993, 9, 9), sex="M",
              issue_date=date(2025, 1, 15), expiry_date=date(2035, 1, 14), face_seed=14)   # NOT in registry


def _full(p: dict) -> dict:
    r = make_person(random.Random(0), p["face_seed"], p["doc_number"])
    r.update(p)
    return r


def seed_registry(n_random: int = 300) -> int:
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.init()
    r = random.Random(2026)
    reserved = {p["doc_number"] for p in PERSONAS.values()} | {FORGED["doc_number"]}
    made = 0
    while made < n_random:
        rec = make_person(r, face_seed=1000 + made)
        if rec["doc_number"] in reserved:
            continue
        db.upsert(rec); made += 1
    for p in PERSONAS.values():
        db.upsert(_full(p))
    return db.count()


def _degrade(img: Image.Image) -> Image.Image:
    a = np.asarray(img.filter(ImageFilter.GaussianBlur(0.7))).astype(np.float32)
    a += np.random.default_rng(3).normal(0, 3.0, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def build_samples(out: str | None = None) -> list[dict]:
    out = out or os.path.join(ROOT, "samples")
    os.makedirs(out, exist_ok=True)
    manifest: list[dict] = []

    def add(key, title, story, expected, doc_path, selfie_seed, expect_flags=()):
        sp = os.path.join(out, f"{key}_selfie.png")
        make_selfie(selfie_seed, rng_seed=selfie_seed * 31 + len(manifest)).save(sp)
        manifest.append({"id": key, "title": title, "story": story, "expected_band": expected,
                         "document": os.path.basename(doc_path), "selfie": os.path.basename(sp),
                         "expect_flags": list(expect_flags)})

    def genuine(persona, seed):
        rec = _full(persona)
        return render_document(rec, make_face(persona["face_seed"]), seed=seed), rec

    def scan(img, key, **kw):
        p = os.path.join(out, f"{key}.jpg"); save_scan(img, p, **kw); return p

    def decoded(path):
        im = Image.open(path); im.load(); return im

    # 01 genuine
    img, rec = genuine(PERSONAS["holder"], 1)
    p = scan(img, "01_genuine_clear")
    add("01_genuine_clear", "Genuine document, genuine bearer", "Untouched scan; bearer matches photo and registry.",
        ["GREEN"], p, 11)
    # 02 genuine, low-quality scan
    img2, _ = genuine(PERSONAS["second"], 2)
    p = scan(_degrade(img2), "02_genuine_lowquality", quality=68)
    add("02_genuine_lowquality", "Genuine, poor-quality scan", "Blurry, noisy, heavily compressed - must NOT be flagged.",
        ["GREEN"], p, 15)
    holder_scan = decoded(scan(genuine(PERSONAS["holder"], 1)[0], "_tmp_holder"))
    os.remove(os.path.join(out, "_tmp_holder.jpg"))
    # 03 DOB edited (sloppy forger: different save quality, Photoshop tag)
    t = edit_field(holder_scan, "dob", "14 MAR 1981")
    p = forger_save(t, os.path.join(out, "03_dob_edited_ela.jpg"), 95, "Adobe Photoshop 25.0")
    add("03_dob_edited_ela", "Date of birth altered (sloppy forger)",
        "DOB changed on the printed page only; saved with an editor at a different JPEG quality.",
        ["RED", "AMBER"], p, 11, ["ela", "metadata", "mrz_vz_mismatch", "registry_mismatch"])
    # 04 expiry extended in VIZ + MRZ, check digit not recomputed (careful forger)
    l1, l2 = build_td3("Sharma", "Aarav Kumar", "K4829173", "UTO", date(1991, 3, 14), "M", date(2032, 6, 19))
    forged_l2 = l2[:21] + "350619" + l2[27:]                    # new expiry, stale check digit
    t = edit_field(holder_scan, "date_of_expiry", "19 JUN 2035")
    t = edit_mrz_line(t, 1, forged_l2)
    p = forger_save(t, os.path.join(out, "04_expiry_extended_mrz.jpg"), 80, strip_exif=True)
    add("04_expiry_extended_mrz", "Expiry extended, MRZ edited too (careful forger)",
        "Same font, same JPEG quality, metadata stripped: image forensics see little - the MRZ checksum and registry expose it.",
        ["RED", "AMBER"], p, 11, ["mrz_checksum", "registry_mismatch"])
    # 05 surname re-typed in slightly different size
    t = edit_field(holder_scan, "surname", "SHARNA", size=27)
    p = forger_save(t, os.path.join(out, "05_surname_retyped.jpg"), 80, strip_exif=True)
    add("05_surname_retyped", "Surname re-typed (font mismatch)", "Name altered by a forger using a slightly different type size.",
        ["RED", "AMBER"], p, 11, ["font", "mrz_vz_mismatch"])
    # 06 photo swap (impostor's face pasted; registry photo still shows real holder)
    t = swap_photo(holder_scan, make_face(IMPOSTOR_SEED))
    p = forger_save(t, os.path.join(out, "06_photo_swapped.jpg"), 80, strip_exif=True)
    add("06_photo_swapped", "Photo swapped - impostor holds the document",
        "Impostor's photo pasted in. Live face matches the printed photo (!), but the printed photo no longer matches the registry.",
        ["AMBER", "RED"], p, IMPOSTOR_SEED, ["registry_photo_mismatch"])
    # 07 impersonation: real document, wrong person
    img, _ = genuine(PERSONAS["holder"], 1)
    p = scan(img, "07_impersonation")
    add("07_impersonation", "Genuine document, different bearer", "Untouched genuine document presented by someone else.",
        ["AMBER", "RED"], p, IMPOSTOR_SEED, ["face_mismatch"])
    # 08 revoked
    img, _ = genuine(PERSONAS["revoked"], 8)
    p = scan(img, "08_revoked_document")
    add("08_revoked_document", "Genuine-looking but REVOKED document", "Physically perfect; registry says it was revoked.",
        ["RED"], p, 12, ["registry_status"])
    # 09 watchlist
    img, _ = genuine(PERSONAS["watch"], 9)
    p = scan(img, "09_watchlist_hit")
    add("09_watchlist_hit", "Watchlist hit (silent alert)", "Document is fine; registry returns a watchlist reference. Officer follows SOP, no confrontation.",
        ["RED"], p, 13, ["watchlist"])
    # 10 wholly forged, checksums valid, not in registry
    rec = _full(FORGED)
    img = render_document(rec, make_face(FORGED["face_seed"]), seed=10)
    p = scan(img, "10_forged_not_in_registry")
    add("10_forged_not_in_registry", "Fabricated document - number not in registry",
        "Internally consistent (valid checksums) but no such document exists.", ["AMBER", "RED"], p, 14, ["registry_not_found"])
    # 11 expired
    img, _ = genuine(PERSONAS["expired"], 11)
    p = scan(img, "11_expired_document")
    add("11_expired_document", "Expired document", "Genuine but expired.", ["AMBER", "RED"], p, 16, ["expired"])

    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest


if __name__ == "__main__":
    n = seed_registry()
    m = build_samples()
    print(f"registry seeded with {n} synthetic records; {len(m)} demo scenarios written to samples/")
