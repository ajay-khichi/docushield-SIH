"""Module 4 - Face verification.

Backends
  deepface : ArcFace via DeepFace (pretrained; `pip install deepface`, downloads
             weights on first use). This is the production-intent backend.
  demo     : lightweight OpenCV matcher (blurred colour-thumbnail cosine) so the prototype
             runs offline / on any laptop and works on the *synthetic* avatar
             faces. It is NOT a biometric-grade matcher and is labelled as such
             in every result.
Output is always a 0-100 similarity score + which backend produced it."""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np
from PIL import Image

from docushield import config as C
from docushield.template import TEMPLATES, DEFAULT_TEMPLATE, CANVAS


@dataclass
class FaceResult:
    score: float
    backend: str
    note: str = ""


def crop_photo(doc_img: Image.Image, template: str = DEFAULT_TEMPLATE) -> Image.Image:
    W, H = doc_img.size
    x, y, w, h = TEMPLATES[template]["photo"]
    sx, sy = W / CANVAS[0], H / CANVAS[1]
    return doc_img.crop((int(x * sx), int(y * sy), int((x + w) * sx), int((y + h) * sy)))


# ------------------------------------------------------------- demo matcher
def _thumb(img: Image.Image) -> np.ndarray:
    """Heavily blurred 12x15 colour thumbnail - tolerant to the small shifts,
    rotations and lighting changes between a live capture and a printed photo."""
    a = np.asarray(img.convert("RGB").resize((96, 120))).astype(np.float32)
    a = cv2.GaussianBlur(a, (0, 0), 6.0)
    return cv2.resize(a, (12, 15), interpolation=cv2.INTER_AREA).ravel()


def _cos(a, b):
    a, b = a - a.mean(), b - b.mean()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


# Calibrated on 80 synthetic identities x (2 same-person selfies + 2 impostors):
# AUC 0.998; same-person p5 = 0.955, impostor p95 = 0.934 (see tests/test_face.py)
DEMO_LO, DEMO_HI = 0.90, 0.99


def demo_similarity(a: Image.Image, b: Image.Image) -> float:
    s = _cos(_thumb(a), _thumb(b))
    return float(np.clip((s - DEMO_LO) / (DEMO_HI - DEMO_LO), 0, 1) * 100)


# ----------------------------------------------------------------- deepface
def _deepface_available() -> bool:
    try:
        import deepface  # noqa: F401
        return True
    except Exception:
        return False


def _deepface_similarity(a: Image.Image, b: Image.Image) -> float:
    from deepface import DeepFace
    r = DeepFace.verify(np.asarray(a.convert("RGB"))[:, :, ::-1], np.asarray(b.convert("RGB"))[:, :, ::-1],
                        model_name="ArcFace", detector_backend="opencv",
                        distance_metric="cosine", enforce_detection=False)
    return float(np.clip(1 - r["distance"] / (2 * r["threshold"]), 0, 1) * 100)


def active_backend() -> str:
    if C.FACE_BACKEND == "demo":
        return "demo"
    if C.FACE_BACKEND in ("auto", "deepface") and _deepface_available():
        return "deepface"
    return "demo"


def compare(a: Image.Image, b: Image.Image) -> FaceResult:
    be = active_backend()
    if be == "deepface":
        try:
            return FaceResult(round(_deepface_similarity(a, b), 1), "deepface/ArcFace")
        except Exception as e:  # noqa - fall back, never crash the checkpoint
            return FaceResult(round(demo_similarity(a, b), 1), "demo",
                              f"DeepFace failed ({type(e).__name__}); used demo matcher.")
    return FaceResult(round(demo_similarity(a, b), 1), "demo",
                      "Demo matcher (not biometric-grade) - install deepface for ArcFace biometric matching.")
