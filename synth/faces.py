"""Procedural synthetic faces. Every face is fabricated from a seed -- there is
no real person behind any image, which keeps the whole prototype DPDP-clean."""
from __future__ import annotations
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SKIN = [(255, 224, 189), (241, 194, 125), (224, 172, 105), (198, 134, 66), (141, 85, 36), (98, 60, 30)]
HAIR = [(20, 15, 10), (60, 40, 20), (110, 70, 30), (170, 130, 60), (200, 200, 200), (120, 30, 20)]
EYE = [(40, 30, 20), (60, 90, 50), (50, 80, 140), (90, 60, 30)]
BG = [(200, 215, 235), (225, 225, 225), (215, 235, 215), (240, 225, 205)]


def make_face(seed: int, size=(240, 300)) -> Image.Image:
    r = random.Random(seed)
    W, H = size
    img = Image.new("RGB", size, r.choice(BG))
    d = ImageDraw.Draw(img)
    skin, hair, eye = r.choice(SKIN), r.choice(HAIR), r.choice(EYE)
    fw, fh = r.randint(int(W * .50), int(W * .64)), r.randint(int(H * .52), int(H * .64))
    cx, cy = W // 2, int(H * .48)
    style = r.choice(["short", "long", "bald", "cap", "bun"])
    if style in ("long", "bun"):
        d.ellipse([cx - fw // 2 - 22, cy - fh // 2 - 26, cx + fw // 2 + 22, cy + fh // 2 + 70], fill=hair)
    # shoulders
    d.rounded_rectangle([cx - 95, H - 62, cx + 95, H + 40], 30, fill=r.choice([(40, 60, 100), (90, 40, 50), (50, 90, 70), (70, 70, 80)]))
    d.rectangle([cx - 22, cy + fh // 2 - 10, cx + 22, H - 55], fill=tuple(int(c * .92) for c in skin))
    d.ellipse([cx - fw // 2, cy - fh // 2, cx + fw // 2, cy + fh // 2], fill=skin)
    if style == "short":
        d.pieslice([cx - fw // 2 - 4, cy - fh // 2 - 8, cx + fw // 2 + 4, cy + fh // 4], 180, 360, fill=hair)
    elif style == "cap":
        d.pieslice([cx - fw // 2 - 6, cy - fh // 2 - 14, cx + fw // 2 + 6, cy + fh // 5], 180, 360, fill=hair)
        d.rectangle([cx - fw // 2 - 14, cy - fh // 4, cx + fw // 2 + 14, cy - fh // 4 + 10], fill=hair)
    elif style == "bun":
        d.ellipse([cx - 22, cy - fh // 2 - 44, cx + 22, cy - fh // 2 - 4], fill=hair)
        d.pieslice([cx - fw // 2 - 2, cy - fh // 2 - 6, cx + fw // 2 + 2, cy + fh // 5], 180, 360, fill=hair)
    elif style == "long":
        d.pieslice([cx - fw // 2 - 4, cy - fh // 2 - 8, cx + fw // 2 + 4, cy + fh // 5], 180, 360, fill=hair)
    ex = r.randint(int(fw * .20), int(fw * .27)); ey = cy - r.randint(0, 14)
    er = r.randint(7, 12)
    for s in (-1, 1):
        x = cx + s * ex
        d.ellipse([x - er - 5, ey - er // 2 - 3, x + er + 5, ey + er // 2 + 3], fill=(250, 250, 250))
        d.ellipse([x - er // 2, ey - er // 2, x + er // 2, ey + er // 2], fill=eye)
        d.line([x - er - 8, ey - er - 7, x + er + 8, ey - er - 7 + r.randint(-4, 4)], fill=hair, width=r.randint(3, 6))
    d.line([cx, ey + 6, cx + r.randint(-6, 6), cy + fh // 6], fill=tuple(int(c * .7) for c in skin), width=3)
    my = cy + fh // 3; mw = r.randint(int(fw * .16), int(fw * .27))
    d.arc([cx - mw, my - 10, cx + mw, my + 14 + r.randint(0, 8)], 20, 160, fill=(150, 60, 60), width=4)
    if r.random() < .3:
        for s in (-1, 1):
            d.ellipse([cx + s * ex - er - 14, ey - er - 10, cx + s * ex + er + 14, ey + er + 10], outline=(30, 30, 30), width=3)
    if r.random() < .3 and style != "bun":
        d.pieslice([cx - fw // 3, my - 16, cx + fw // 3, my + fh // 3], 0, 180, fill=hair)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def make_selfie(seed: int, size=(240, 300), rng_seed: int = 0) -> Image.Image:
    """A 'live capture' of the same synthetic person: different lighting,
    slight rotation / shift, sensor noise, mild blur."""
    r = random.Random(rng_seed or seed * 7919 + 13)
    img = make_face(seed, size).rotate(r.uniform(-4, 4), resample=Image.BICUBIC, fillcolor=(210, 210, 210))
    a = np.asarray(img).astype(np.float32)
    a = a * r.uniform(0.85, 1.12) + r.uniform(-14, 14)
    a += np.random.default_rng(rng_seed or seed).normal(0, 4.5, a.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    dx, dy = r.randint(-8, 8), r.randint(-8, 8)
    canvas = Image.new("RGB", size, (210, 210, 210)); canvas.paste(img, (dx, dy))
    return canvas.filter(ImageFilter.GaussianBlur(0.8))
