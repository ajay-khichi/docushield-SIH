from datetime import date
from PIL import Image
from docushield import tamper
from synth.render import render_document, save_scan, edit_field, forger_save
from synth.faces import make_face

REC = dict(doc_number="K4829173", surname="Sharma", given_names="Aarav Kumar", nationality="UTO", sex="M",
          dob=date(1991, 3, 14), issue_date=date(2022, 6, 20), expiry_date=date(2032, 6, 19))


def _doc(path):
    img = render_document(REC, make_face(11), seed=3)
    save_scan(img, path)
    im = Image.open(path); im.load()
    return im, open(path, "rb").read()


def test_genuine_document_scores_clean(tmp_path):
    img, raw = _doc(str(tmp_path / "g.jpg"))
    r = tamper.analyse(img, raw)
    assert r.probability < 20
    assert r.flagged_fields == []


def test_edited_field_is_flagged(tmp_path):
    img, raw = _doc(str(tmp_path / "g.jpg"))
    edited = edit_field(img, "dob", "14 MAR 1981")
    p = str(tmp_path / "t.jpg")
    forger_save(edited, p, quality=95, software="Adobe Photoshop 25.0")
    im2 = Image.open(p); im2.load()
    r = tamper.analyse(im2, open(p, "rb").read())
    assert r.probability >= 60
    assert any(f["field"] == "dob" for f in r.flagged_fields)
