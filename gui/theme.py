
from __future__ import annotations

import customtkinter as ctk

BG = ("#F4F5F7", "#16181D")
SURFACE = ("#FFFFFF", "#21242B")
SURFACE_2 = ("#F1F3F6", "#2A2E37")
SURFACE_3 = ("#E7EAF0", "#333845")
BORDER = ("#E2E5EB", "#3A3F4B")

TEXT = ("#171A1F", "#ECEEF2")
TEXT_SUB = ("#444A54", "#B6BCC6")
TEXT_MUTED = ("#6B717C", "#8A909C")
TEXT_ON_ACCENT = ("#FFFFFF", "#0E1116")

ACCENT = ("#2D6CDF", "#5A8DF0")
ACCENT_HOVER = ("#1F58C0", "#7AA4F4")
ACCENT_SOFT = ("#E8F0FE", "#1E2A44")
NEUTRAL_BTN = ("#E7EAF0", "#333845")
NEUTRAL_HOVER = ("#DADFE8", "#3D4350")
NEUTRAL = ("#C7CCD4", "#5A606C")
ACCENT_ALT = ("#6D4AFF", "#9B82FF")
ACCENT_ALT_HOVER = ("#5A37E0", "#B29DFF")

IDLE = ("#6B717C", "#8A909C")
IDLE_SOFT = ("#EEF0F4", "#262A33")
PROGRESS = ("#2D6CDF", "#5A8DF0")
PROGRESS_SOFT = ("#E8F0FE", "#1E2A44")
SUCCESS = ("#1E9E54", "#3FBE75")
SUCCESS_SOFT = ("#E4F6EC", "#16301F")
WARNING = ("#C77700", "#F0A93C")
WARNING_SOFT = ("#FFF3DD", "#332100")
DANGER = ("#D62E2E", "#FF5C5C")
DANGER_SOFT = ("#FCE6E6", "#3A1414")

LOG_BG = ("#F1F3F6", "#1A1C21")
LOG_TEXT = ("#1F2329", "#CFD3DA")

FONT_CAPTION = 12
FONT_BODY = 14
FONT_BODY_LG = 16
FONT_TITLE = 20
FONT_METRIC = 34
FONT_DEVICE = 18

SP_1 = 4
SP_2 = 8
SP_3 = 12
SP_4 = 16
SP_6 = 24
SP_8 = 32
PADDING = 12
GAP = 8

CORNER_SM = 8
CORNER_MD = 12
CORNER_LG = 16
CORNER = CORNER_MD
BORDER_W = 1
TOUCH_MIN = 48
TOUCH_LG = 56


VALID = ("system", "light", "dark")
APPEARANCE_LABELS = {"system": "시스템", "light": "라이트", "dark": "다크"}
APPEARANCE_REVERSE = {v: k for k, v in APPEARANCE_LABELS.items()}


def _normalize(value: str) -> str:
    v = (value or "system").strip().lower()
    return v if v in VALID else "system"


def apply(appearance: str) -> str:
    norm = _normalize(appearance)
    ctk.set_appearance_mode(norm.capitalize())
    return norm
