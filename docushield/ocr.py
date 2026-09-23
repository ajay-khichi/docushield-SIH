"""Module 1 - OCR extraction.

Template-anchored: for a known document layout we OCR each field box
separately (much more accurate than whole-page OCR, and it lets later modules
reason per-field). Engine is pluggable: Tesseract by default, PaddleOCR if
installed and DOCUSHIELD_OCR=paddle."""
from __future__ import annotations
import os, re
os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # tesseract is faster when we parallelise per-field instead
from datetime import date
import cv2
import numpy as np
from PIL import Image

from docushield.template import TEMPLATES, DEFAULT_TEMPLATE, CANVAS
from docushield.mrz import parse_td3, normalize_line

MONTHS = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
WL = {
    "alpha": "ABCDEFGHIJKLMNOPQRSTUVWXYZ -",
    "docno": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "date": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
    "sex": "MFX",
    "mrz": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<",
}


def _tesseract_cmd():
    import pytesseract
    cmd = os.getenv("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract


def tesseract_available() -> bool:
    try:
        _tesseract_cmd().get_tesseract_version()
        return True
    except Exception:
        return False


def _prep(crop: np.ndarray, target_h: int = 90) -> np.ndarray:
    g = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
    s = target_h / max(g.shape[0], 1)
    g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.copyMakeBorder(b, 14, 14, 14, 14, cv2.BORDER_CONSTANT, value=255)


def _read(crop: np.ndarray, whitelist: str, psm: int = 7, target_h: int = 90) -> tuple[str, float]:
    pt = _tesseract_cmd()
    img = _prep(crop, target_h)
    cfg = f'--oem 3 --psm {psm} -c "tessedit_char_whitelist={whitelist}" -c preserve_interword_spaces=1'
    data = pt.image_to_data(img, config=cfg, output_type=pt.Output.DICT)
    words = [(w, float(c)) for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) >= 0]
    text = " ".join(w for w, _ in words)
    conf = float(np.mean([c for _, c in words])) if words else 0.0
    return text.strip(), conf


MRZ_SCALES = (64, 80, 100, 120)


def read_mrz_line(crop: np.ndarray, idx: int) -> tuple[str, float]:
    """OCR one MRZ line at several scales and keep the best candidate.
    Selection is by structural validity (length 44, checksum passes for line 2),
    i.e. it chooses between OCR *reads of the same printed text*; it can never
    turn a genuinely tampered (checksum-failing) MRZ into a passing one."""
    best, best_key = ("", 0.0), (-1, -1)
    for th in MRZ_SCALES:
        txt, conf = _read(crop, WL["mrz"], target_h=th)
        norm = normalize_line(txt)
        raw_len = len(re.sub(r"\s+", "", txt))
        if idx == 1:
            passed = sum(parse_td3("P" + "<" * 43, norm)["checks"].values())
            key = (passed, int(raw_len == 44))
        else:
            key = (int(norm.startswith("P<")), raw_len)
        if key > best_key:
            best, best_key = (re.sub(r"\s+", "", txt), conf), key
    return best


def parse_vz_date(txt: str) -> date | None:
    m = re.search(r"(\d{1,2})\s*([A-Z0-9]{3})\s*(\d{4})", txt.upper())
    if not m:
        return None
    dd, mon, yy = m.groups()
    mon = mon.replace("0", "O").replace("1", "I")
    if mon not in MONTHS:
        return None
    try:
        return date(int(yy), MONTHS[mon], int(dd))
    except ValueError:
        return None


def box_scaled(box, sx, sy):
    x, y, w, h = box
    return int(x * sx), int(y * sy), int(w * sx), int(h * sy)


def extract(img: Image.Image, template: str = DEFAULT_TEMPLATE) -> dict:
    """Returns {'fields': {...}, 'confidence': {...}, 'mrz': parsed|None, 'raw_mrz': [...]}"""
    tpl = TEMPLATES[template]
    arr = np.asarray(img.convert("RGB"))
    H, W = arr.shape[:2]
    sx, sy = W / CANVAS[0], H / CANVAS[1]
    fields, conf, raw = {}, {}, {}
    from concurrent.futures import ThreadPoolExecutor

    def job_field(item):
        name, f = item
        x, y, w, h = box_scaled(f["box"], sx, sy)
        return name, f["kind"], _read(arr[y:y + h, x:x + w], WL[f["kind"]])

    def job_mrz(item):
        idx, box = item
        x, y, w, h = box_scaled(box, sx, sy)
        return read_mrz_line(arr[y:y + h, x:x + w], idx)

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_futs = list(ex.map(job_field, tpl["fields"].items()))
        m_futs = list(ex.map(job_mrz, enumerate(tpl["mrz_lines"])))
    for name, kind, (txt, c) in f_futs:
        raw[name], conf[name] = txt, c
        if kind == "date":
            fields[name] = parse_vz_date(txt)
        elif kind == "alpha":
            fields[name] = re.sub(r"\s+", " ", txt).strip()
        elif kind == "docno":
            fields[name] = re.sub(r"\s+", "", txt)
        else:
            fields[name] = txt.strip()
    mrz_raw = [t for t, _ in m_futs]
    mrz_conf = [c for _, c in m_futs]
    mrz = parse_td3(mrz_raw[0], mrz_raw[1]) if len(mrz_raw) == 2 else None
    return {"fields": fields, "raw_fields": raw, "confidence": conf,
            "mrz": mrz, "raw_mrz": mrz_raw, "mrz_confidence": float(np.mean(mrz_conf)) if mrz_conf else 0.0}
