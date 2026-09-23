from datetime import date
from docushield import ocr
from synth.render import render_document, save_scan
from synth.faces import make_face

REC = dict(doc_number="K4829173", surname="Sharma", given_names="Aarav Kumar", nationality="UTO", sex="M",
          dob=date(1991, 3, 14), issue_date=date(2022, 6, 20), expiry_date=date(2032, 6, 19))


def test_extracts_correct_fields_and_valid_mrz(tmp_path):
    img = render_document(REC, make_face(11), seed=3)
    p = str(tmp_path / "g.jpg")
    save_scan(img, p)
    from PIL import Image
    r = ocr.extract(Image.open(p))
    assert r["fields"]["doc_number"] == "K4829173"
    assert r["fields"]["surname"] == "SHARMA"
    assert r["fields"]["dob"] == date(1991, 3, 14)
    assert all(r["mrz"]["checks"].values())
