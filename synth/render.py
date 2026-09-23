"""Render a fully synthetic 'UTO' mock passport page, save it like a scanner
would (JPEG + EXIF), and simulate forger edits for the tamper-class samples."""
from __future__ import annotations
import io, random
from datetime import date, datetime
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from docushield.mrz import build_td3
from docushield.template import TEMPLATES, DEFAULT_TEMPLATE, CANVAS
from synth.fonts import get_font

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def fmt_date(d: date) -> str:
    return f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}"


def _paper(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    W, H = CANVAS
    base = np.zeros((H, W, 3), np.float32)
    base[:] = (236, 240, 247)
    yy, xx = np.mgrid[0:H, 0:W]
    wave = 5 * np.sin((xx + yy) / 14.0) + 3 * np.sin((xx - yy) / 23.0)
    base += wave[..., None]
    base += rng.normal(0, 2.2, base.shape)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def render_document(rec: dict, face: Image.Image, seed: int = 0) -> Image.Image:
    tpl = TEMPLATES[DEFAULT_TEMPLATE]
    img = _paper(seed)
    d = ImageDraw.Draw(img)
    W, H = CANVAS
    d.rectangle([0, 0, W - 1, H - 1], outline=(30, 40, 70), width=8)
    d.rectangle([8, 8, W - 9, 112], fill=(30, 50, 100))
    d.text((40, 22), "REPUBLIC OF UTOPIA", font=get_font("sans_bold", 40), fill=(255, 255, 255))
    d.text((40, 72), "MOCK PASSPORT  |  SYNTHETIC SPECIMEN - NOT A REAL DOCUMENT", font=get_font("sans", 20), fill=(210, 220, 245))
    d.text((760, 40), "P   UTO", font=get_font("sans_bold", 34), fill=(255, 255, 255))
    px, py, pw, ph = tpl["photo"]
    img.paste(face.resize((pw, ph)), (px, py))
    d.rectangle([px - 1, py - 1, px + pw, py + ph], outline=(30, 40, 70), width=2)
    values = {
        "doc_number": rec["doc_number"], "nationality": rec["nationality"],
        "surname": rec["surname"].upper(), "given_names": rec["given_names"].upper(),
        "dob": fmt_date(rec["dob"]), "sex": rec["sex"],
        "date_of_issue": fmt_date(rec["issue_date"]), "date_of_expiry": fmt_date(rec["expiry_date"]),
    }
    for name, f in tpl["fields"].items():
        x, y, w, h = f["box"]
        d.text((x, y - 24), f["label"], font=get_font("sans", 15), fill=(90, 100, 120))
        d.text((x + 4, y + 2), values[name], font=get_font("sans_bold", 30), fill=(15, 20, 35))
    # MRZ band
    d.rectangle([12, 556, W - 13, 684], fill=(255, 255, 255))
    l1, l2 = build_td3(rec["surname"], rec["given_names"], rec["doc_number"], rec["nationality"],
                       rec["dob"], rec["sex"], rec["expiry_date"], rec.get("personal_number", ""))
    for (x, y, w, h), line in zip(tpl["mrz_lines"], (l1, l2)):
        d.text((x, y), line, font=get_font("mono", 34), fill=(10, 10, 10))
    return img


def save_scan(img: Image.Image, path: str, quality: int = 80, software: str | None = None,
              with_exif: bool = True, when: datetime | None = None) -> str:
    """Save as JPEG the way a checkpoint document scanner would."""
    kw = {"quality": quality}
    if with_exif:
        ex = Image.Exif()
        ex[271] = "SynthScan Corp"; ex[272] = "PassportReader-X1"
        t = (when or datetime(2026, 9, 1, 10, 30, 0)).strftime("%Y:%m:%d %H:%M:%S")
        ex[306] = t
        ex.get_ifd(0x8769)[36867] = t
        if software:
            ex[305] = software
        kw["exif"] = ex
    img.save(path, "JPEG", **kw)
    return path


# ---------------- forger simulations (operate on a decoded scan) ----------------
def _patch_color(img: Image.Image, box) -> tuple:
    x, y, w, h = box
    a = np.asarray(img.crop((x - 12, y - 6, x - 2, y + h + 6))).reshape(-1, 3)
    return tuple(int(v) for v in np.median(a, axis=0))


def edit_field(img: Image.Image, field: str, new_text: str, font_kind="sans_bold", size=30) -> Image.Image:
    img = img.copy(); d = ImageDraw.Draw(img)
    x, y, w, h = TEMPLATES[DEFAULT_TEMPLATE]["fields"][field]["box"]
    d.rectangle([x, y, x + w, y + h], fill=_patch_color(img, (x, y, w, h)))
    d.text((x + 4, y + 2 + (30 - size) // 2), new_text, font=get_font(font_kind, size), fill=(15, 20, 35))
    return img


def edit_mrz_line(img: Image.Image, idx: int, new_text: str) -> Image.Image:
    img = img.copy(); d = ImageDraw.Draw(img)
    x, y, w, h = TEMPLATES[DEFAULT_TEMPLATE]["mrz_lines"][idx]
    d.rectangle([x, y, x + w, y + h], fill=(255, 255, 255))
    d.text((x, y), new_text, font=get_font("mono", 34), fill=(10, 10, 10))
    return img


def swap_photo(img: Image.Image, new_face: Image.Image) -> Image.Image:
    img = img.copy()
    px, py, pw, ph = TEMPLATES[DEFAULT_TEMPLATE]["photo"]
    img.paste(new_face.resize((pw, ph)), (px, py))
    return img


def forger_save(img: Image.Image, path: str, quality=95, software: str | None = None, strip_exif=False) -> str:
    """Forger re-saves the edited image. Sloppy forger leaves an editor tag;
    careful one strips metadata entirely."""
    if strip_exif:
        img.save(path, "JPEG", quality=quality)
    else:
        save_scan(img, path, quality=quality, software=software, when=datetime(2026, 9, 3, 22, 14, 0))
    return path
