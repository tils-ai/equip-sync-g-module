
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

PRETENDARD = "Pretendard"
FALLBACK = "Malgun Gothic"


def _resource_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "fonts"
    return Path(__file__).resolve().parent / "assets" / "fonts"


def bundled_font_path(bold: bool = False) -> Path | None:
    font_dir = _resource_dir()
    bold_path = font_dir / "Pretendard-Bold.ttf"
    regular_path = font_dir / "Pretendard-Regular.ttf"
    if bold and bold_path.exists():
        return bold_path
    if regular_path.exists():
        return regular_path
    return bold_path if bold_path.exists() else None


_cached_family: str | None = None


def register() -> str:
    global _cached_family
    if _cached_family is not None:
        return _cached_family

    font_dir = _resource_dir()
    regular = font_dir / "Pretendard-Regular.ttf"
    bold = font_dir / "Pretendard-Bold.ttf"

    if not regular.exists():
        logger.warning("번들 Pretendard 누락 (%s) → '%s'로 폴백", regular, FALLBACK)
        _cached_family = FALLBACK
        return _cached_family

    if sys.platform == "win32":
        try:
            import ctypes

            FR_PRIVATE = 0x10
            ctypes.windll.gdi32.AddFontResourceExW(str(regular), FR_PRIVATE, 0)
            if bold.exists():
                ctypes.windll.gdi32.AddFontResourceExW(str(bold), FR_PRIVATE, 0)
            _cached_family = PRETENDARD
        except Exception:
            logger.exception("Pretendard 등록 실패 (Windows GDI) → '%s'로 폴백", FALLBACK)
            _cached_family = FALLBACK
    elif sys.platform == "darwin":
        try:
            from CoreText import (  # type: ignore[import-not-found]
                CTFontManagerRegisterFontsForURL,
                kCTFontManagerScopeProcess,
            )
            from Foundation import NSURL  # type: ignore[import-not-found]

            for path in [regular, bold]:
                if path.exists():
                    url = NSURL.fileURLWithPath_(str(path))
                    CTFontManagerRegisterFontsForURL(url, kCTFontManagerScopeProcess, None)
            _cached_family = PRETENDARD
        except Exception:
            logger.exception("Pretendard 등록 실패 (CoreText) → '%s'로 폴백", FALLBACK)
            _cached_family = FALLBACK
    else:
        logger.warning("지원하지 않는 OS (%s) → '%s'로 폴백", sys.platform, FALLBACK)
        _cached_family = FALLBACK

    return _cached_family


def family() -> str:
    return _cached_family or FALLBACK
