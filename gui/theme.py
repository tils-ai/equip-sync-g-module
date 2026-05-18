"""색 토큰 + CustomTkinter 테마 매니저.

dps-store/docs/print/20260511-equipment-gui-spec.md §2 참조 — 3 레포가 동일 값을 복사 사용.
"""

from __future__ import annotations

import customtkinter as ctk

# ── 색 토큰 (light, dark) — CTk가 appearance_mode에 따라 자동 선택 ──
BG = ("#F5F5F7", "#1C1C1E")
SURFACE = ("#FFFFFF", "#2C2C2E")
SURFACE_2 = ("#F2F2F7", "#3A3A3C")
TEXT = ("#1F1F1F", "#E5E5E7")
TEXT_MUTED = ("#6E6E73", "#8E8A85")
ACCENT = ("#3B6EA5", "#7A9EB8")
SUCCESS = ("#34A853", "#8BC5A3")
DANGER = ("#E14B3D", "#D4897A")
WARNING = ("#E0A23A", "#E0BB6E")
NEUTRAL = ("#C7C7CC", "#5A5856")
LOG_BG = ("#F2F2F7", "#202022")
LOG_TEXT = ("#1F1F1F", "#D0CCC8")

CORNER = 8
PADDING = 12
GAP = 8


# ── 외관 모드 ──
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
