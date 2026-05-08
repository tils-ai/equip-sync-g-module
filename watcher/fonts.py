"""Pretendard 폰트 로더 — 패키지된 .otf를 프로세스에 등록 후 family명을 반환.

PyInstaller 동결 빌드: sys._MEIPASS/assets/fonts 에서 로드 (--add-data로 번들).
개발 모드: 이 파일과 같은 디렉토리의 assets/fonts/ 에서 로드.
실패 시 OS 기본 한글 폰트(Malgun Gothic)로 폴백.
"""

from __future__ import annotations

import sys
from pathlib import Path

PRETENDARD = "Pretendard"
FALLBACK = "Malgun Gothic"


def _resource_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "fonts"
    return Path(__file__).resolve().parent / "assets" / "fonts"


_cached_family: str | None = None


def register() -> str:
    """앱 시작 시 1회 호출. 이후 호출은 캐시된 값 반환."""
    global _cached_family
    if _cached_family is not None:
        return _cached_family

    font_dir = _resource_dir()
    regular = font_dir / "Pretendard-Regular.otf"
    bold = font_dir / "Pretendard-Bold.otf"

    if not regular.exists():
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
            _cached_family = FALLBACK
    else:
        _cached_family = FALLBACK

    return _cached_family


def family() -> str:
    """캐시된 family명 반환 (register 미호출 시 fallback)."""
    return _cached_family or FALLBACK
