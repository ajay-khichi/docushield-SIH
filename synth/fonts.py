"""Cross-platform font lookup (Linux / Windows / macOS) with safe fallback."""
from PIL import ImageFont
import os

_CANDIDATES = {
    "mono": ["DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
             "C:/Windows/Fonts/consola.ttf", "/System/Library/Fonts/Menlo.ttc", "cour.ttf"],
    "sans_bold": ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Helvetica.ttc", "arialbd.ttf"],
    "sans": ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "arial.ttf"],
    "serif_bold": ["DejaVuSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
                   "C:/Windows/Fonts/timesbd.ttf", "/System/Library/Fonts/Times.ttc", "timesbd.ttf"],
}

def get_font(kind: str, size: int):
    for cand in _CANDIDATES[kind]:
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default(size)
