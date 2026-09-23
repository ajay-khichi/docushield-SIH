"""Module 3 - Tampering detection (layered, explainable, no training data).

  1. ELA           - edited text fields re-compress differently from siblings
  2. Metadata      - editor signatures, stripped EXIF, modify-after-capture
  3. Font/stroke   - re-typed fields differ in glyph height / stroke width
  4. (stretch)     - CNN tamper classifier hook, disabled in this prototype

Each layer returns a 0..1 suspicion score + human-readable evidence. They are
combined with a noisy-OR so two weak, independent signals reinforce each other.
Known limits (surfaced in the UI): ELA is blind if the forger re-saves at the
same JPEG quality; photo swaps are NOT scored by ELA (too content-dependent) --
they are caught by the registry-photo comparison in the face module."""
from __future__ import annotations
import io
from dataclasses import dataclass, field
import cv2
import numpy as np
from PIL import Image

from docushield import config as C
from docushield.template import TEMPLATES, DEFAULT_TEMPLATE, CANVAS


@dataclass
class TamperResult:
    probability: float = 0.0                         # 0..100
    components: dict = field(default_factory=dict)   # name -> {score, applicable, detail}
    flagged_fields: list = field(default_factory=list)  # [{field, layer, reason}]
    ela_map: np.ndarray | None = None


def _scale_box(box, W, H):
    x, y, w, h = box
    sx, sy = W / CANVAS[0], H / CANVAS[1]
    return int(x * sx), int(y * sy), max(int(w * sx), 1), max(int(h * sy), 1)


# ----------------------------------------------------------------- 1. ELA
def ela_map(img: Image.Image, quality: int = C.ELA_QUALITY) -> np.ndarray:
    rgb = img.convert("RGB")
    buf = io.BytesIO(); rgb.save(buf, "JPEG", quality=quality); buf.seek(0)
    re_ = Image.open(buf).convert("RGB")
    d = np.abs(np.asarray(rgb).astype(np.int16) - np.asarray(re_).astype(np.int16))
    return d.max(axis=2).astype(np.float32)


def robust_z(values: np.ndarray) -> np.ndarray:
    med = np.median(values)
    mad = np.median(np.abs(values - med))
    scale = max(1.4826 * mad, 0.15 * abs(med), 0.05)
    return (values - med) / scale


def ela_layer(img: Image.Image, tpl: dict) -> tuple[dict, list, np.ndarray]:
    W, H = img.size
    e = ela_map(img)
    names = list(tpl["fields"])
    means = []
    for n in names:
        x, y, w, h = _scale_box(tpl["fields"][n]["box"], W, H)
        means.append(float(e[y:y + h, x:x + w].mean()))
    means = np.array(means)
    z = robust_z(means)
    med = float(np.median(means))
    flagged = []
    for n, m, zz in zip(names, means, z):
        if zz >= C.ELA_Z_FLAG and m >= 2 * med and m >= 0.6:
            flagged.append({"field": n, "layer": "ela",
                            "reason": f"Compression signature of '{tpl['fields'][n]['label'].title()}' differs sharply "
                                      f"from the other fields (ELA {m:.2f} vs typical {med:.2f}) - region likely edited after the original scan.",
                            "z": float(zz)})
    top = max((f["z"] for f in flagged), default=0.0)
    score = float(np.clip((top - C.ELA_Z_FLAG) / 4.0 + 0.5, 0, 1)) if flagged else 0.0
    detail = {"per_field_ela": {n: round(float(m), 3) for n, m in zip(names, means)},
              "typical": round(med, 3)}
    return {"score": score, "applicable": True, "detail": detail}, flagged, e


# ------------------------------------------------------------ 2. Metadata
_EXIF_SOFTWARE, _EXIF_DT, _EXIF_MAKE = 305, 306, 271
_EXIF_DT_ORIG = 36867


def _parse_dt(s):
    from datetime import datetime
    try:
        return datetime.strptime(str(s).strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def metadata_layer(raw: bytes | None) -> tuple[dict, list]:
    if raw is None:
        return {"score": 0.0, "applicable": False, "detail": {"note": "no original file bytes"}}, []
    try:
        im = Image.open(io.BytesIO(raw))
        ex = im.getexif()
        sub = ex.get_ifd(0x8769) if ex else {}
    except Exception as e:  # noqa
        return {"score": 0.0, "applicable": False, "detail": {"note": f"unreadable: {e}"}}, []
    flags, score, notes = [], 0.0, []
    sw = str(ex.get(_EXIF_SOFTWARE, "")).strip() if ex else ""
    if sw and any(sig in sw.lower() for sig in C.EDITOR_SIGNATURES):
        score = max(score, 0.9)
        flags.append({"field": "(file)", "layer": "metadata",
                      "reason": f"Image was last saved by editing software: '{sw}'."})
    if not ex or len(ex) == 0:
        score = max(score, 0.25)
        notes.append("EXIF absent")
        flags.append({"field": "(file)", "layer": "metadata",
                      "reason": "No capture metadata (EXIF) present - scanners/cameras normally embed it; "
                                "stripped metadata is a weak indicator of re-saving."})
    else:
        t_mod, t_orig = _parse_dt(ex.get(_EXIF_DT)), _parse_dt(sub.get(_EXIF_DT_ORIG))
        if t_mod and t_orig and (t_mod - t_orig).total_seconds() > 60:
            score = max(score, 0.6)
            flags.append({"field": "(file)", "layer": "metadata",
                          "reason": f"File was modified {(t_mod - t_orig)} after it was captured "
                                    f"(captured {t_orig}, modified {t_mod})."})
    return {"score": score, "applicable": True,
            "detail": {"software": sw or None, "make": str(ex.get(_EXIF_MAKE, "")) if ex else "",
                       "format": im.format, "notes": notes}}, flags


# ---------------------------------------------------- 3. Font / stroke check
def _glyph_stats(gray_roi: np.ndarray) -> dict | None:
    _, b = cv2.threshold(gray_roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, lab, st, _ = cv2.connectedComponentsWithStats(b, connectivity=8)
    hs = [st[i, cv2.CC_STAT_HEIGHT] for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 12]
    if len(hs) < 2:
        return None
    cap_h = float(np.percentile(hs, 85))
    cnts, _ = cv2.findContours(b, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perim = sum(cv2.arcLength(c, True) for c in cnts)
    stroke = 2.0 * float((b > 0).sum()) / max(perim, 1.0)
    cols = np.where(b.sum(0) > 0)[0]
    return {"cap_h": cap_h, "stroke": stroke, "extent": float(cols[-1] - cols[0] + 1)}


def font_layer(img: Image.Image, tpl: dict) -> tuple[dict, list]:
    W, H = img.size
    gray = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    stats = {}
    for n, f in tpl["fields"].items():
        x, y, w, h = _scale_box(f["box"], W, H)
        s = _glyph_stats(gray[y:y + h, x:x + w])
        if s:
            stats[n] = s
    flagged, worst = [], 0.0

    def compare(group: dict, keys=("cap_h", "stroke")):
        nonlocal worst
        if len(group) < 3:
            return
        meds = {k: float(np.median([g[k] for g in group.values()])) for k in keys}
        for name, g in group.items():
            dev = {k: abs(g[k] / meds[k] - 1.0) for k in keys}
            sev = max(dev.get("cap_h", 0) / C.FONT_HEIGHT_TOL, dev.get("stroke", 0) / C.FONT_STROKE_TOL)
            if sev >= 1.0:
                worst = max(worst, sev)
                what = "glyph height" if dev.get("cap_h", 0) / C.FONT_HEIGHT_TOL >= dev.get("stroke", 0) / C.FONT_STROKE_TOL else "stroke thickness"
                flagged.append({"field": name, "layer": "font",
                                "reason": f"Text in '{tpl['fields'][name]['label'].title()}' has different {what} than the rest of the page "
                                          f"({dev['cap_h']*100:.0f}% height / {dev['stroke']*100:.0f}% stroke deviation) - possible re-typed field."})
    compare(stats)
    # MRZ: the two lines must share font metrics
    mrz = []
    for (x, y, w, h) in tpl["mrz_lines"]:
        x, y, w, h = _scale_box((x, y, w, h), W, H)
        mrz.append(_glyph_stats(gray[y:y + h, x:x + w]))
    if all(mrz):
        d_h = abs(mrz[1]["cap_h"] / mrz[0]["cap_h"] - 1)
        d_e = abs(mrz[1]["extent"] / mrz[0]["extent"] - 1)
        if d_h > C.FONT_HEIGHT_TOL or d_e > 0.06:
            worst = max(worst, 1.5)
            flagged.append({"field": "mrz", "layer": "font",
                            "reason": f"The two MRZ lines use inconsistent glyph size/spacing (height {d_h*100:.0f}%, width {d_e*100:.0f}% apart) - "
                                      "machine-readable zone may have been re-typed."})
    score = float(np.clip(0.5 + 0.5 * (worst - 1.0), 0, 1)) if flagged else 0.0
    return {"score": score, "applicable": bool(stats),
            "detail": {k: {m: round(v, 2) for m, v in s.items()} for k, s in stats.items()}}, flagged


# --------------------------------------------------------------- combine
def analyse(img: Image.Image, raw_bytes: bytes | None = None, template: str = DEFAULT_TEMPLATE) -> TamperResult:
    tpl = TEMPLATES[template]
    ela_c, ela_f, emap = ela_layer(img, tpl)
    meta_c, meta_f = metadata_layer(raw_bytes)
    font_c, font_f = font_layer(img, tpl)
    comps = {"ela": ela_c, "metadata": meta_c, "font": font_c,
             "cnn": {"score": 0.0, "applicable": False,
                     "detail": {"note": "Stretch goal (ResNet fine-tuned on synthetic MIDV-2020 tampering) - not enabled in this prototype."}}}
    p_clean = 1.0
    for k, w in C.TAMPER_COMPONENT_WEIGHTS.items():
        p_clean *= 1.0 - w * comps[k]["score"]
    return TamperResult(probability=round(100 * (1 - p_clean), 1), components=comps,
                        flagged_fields=ela_f + font_f + meta_f, ela_map=emap)


# ------------------------------------------------------------- heatmap
def heatmap(img: Image.Image, res: TamperResult, template: str = DEFAULT_TEMPLATE) -> Image.Image:
    tpl = TEMPLATES[template]
    rgb = np.asarray(img.convert("RGB")).copy()
    e = res.ela_map if res.ela_map is not None else ela_map(img)
    e = cv2.GaussianBlur(e, (0, 0), 2.0)
    norm = np.clip(e / max(np.percentile(e, 99.7), 1.0), 0, 1)
    heat = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    heat = cv2.cvtColor(heat, cv2.COLOR_BGR2RGB)
    out = cv2.addWeighted(rgb, 0.45, heat, 0.55, 0)
    H, W = out.shape[:2]
    for f in res.flagged_fields:
        name = f["field"]
        if name in tpl["fields"]:
            x, y, w, h = _scale_box(tpl["fields"][name]["box"], W, H)
        elif name == "mrz":
            xs = [_scale_box(b, W, H) for b in tpl["mrz_lines"]]
            x, y = xs[0][0], xs[0][1]; w = xs[0][2]; h = xs[1][1] + xs[1][3] - xs[0][1]
        else:
            continue
        cv2.rectangle(out, (x - 4, y - 4), (x + w + 4, y + h + 4), (255, 40, 40), 3)
    return Image.fromarray(out)
