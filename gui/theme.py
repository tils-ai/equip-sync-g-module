"""색 / 타이포 / 스페이싱 토큰 + CustomTkinter 테마 매니저.

dps-store/docs/print/20260611-garment-client-gui-design.md 의 토큰 제안 반영.
모든 색은 (light, dark) 튜플 — CTk 가 appearance_mode 에 따라 자동 선택.
현장(공장·매장) 운영툴 기준: 큰 터치 타깃·높은 시인성·명확한 상태 신호.
"""

from __future__ import annotations

import customtkinter as ctk

# ── 표면 (배경→카드→내부패널→hover 4단 + 윤곽) ──
BG = ("#F4F5F7", "#16181D")        # 앱 최하단 배경
SURFACE = ("#FFFFFF", "#21242B")   # 카드/패널 기본
SURFACE_2 = ("#F1F3F6", "#2A2E37")  # 카드 내부(썸네일/로그/입력)
SURFACE_3 = ("#E7EAF0", "#333845")  # hover/선택/강조 패널
BORDER = ("#E2E5EB", "#3A3F4B")     # 카드/패널 1px 윤곽

# ── 텍스트 ──
TEXT = ("#171A1F", "#ECEEF2")
TEXT_SUB = ("#444A54", "#B6BCC6")       # 본문 보조
TEXT_MUTED = ("#6B717C", "#8A909C")     # 캡션/라벨
TEXT_ON_ACCENT = ("#FFFFFF", "#0E1116")  # 액센트 버튼 위 글자

# ── 주/보조 액션 ──
ACCENT = ("#2D6CDF", "#5A8DF0")        # 주 액션(출력)
ACCENT_HOVER = ("#1F58C0", "#7AA4F4")
ACCENT_SOFT = ("#E8F0FE", "#1E2A44")   # 정보/진행 틴트 배경
NEUTRAL_BTN = ("#E7EAF0", "#333845")   # 보조 버튼(폴더/설정) 배경
NEUTRAL_HOVER = ("#DADFE8", "#3D4350")
NEUTRAL = ("#C7CCD4", "#5A606C")       # 비활성 점/중립 윤곽 (하위호환 유지)
ACCENT_ALT = ("#6D4AFF", "#9B82FF")    # 보조 강조(컬러옷 White+Color 출력 버튼)
ACCENT_ALT_HOVER = ("#5A37E0", "#B29DFF")

# ── 상태: SOLID(전경: 텍스트·점·테두리) + SOFT(배경 tint) ──
IDLE = ("#6B717C", "#8A909C")          # 대기/미시작 = 중립 회색
IDLE_SOFT = ("#EEF0F4", "#262A33")
PROGRESS = ("#2D6CDF", "#5A8DF0")      # 진행/전송중 = 파랑
PROGRESS_SOFT = ("#E8F0FE", "#1E2A44")
SUCCESS = ("#1E9E54", "#3FBE75")       # 완료/성공 = 초록
SUCCESS_SOFT = ("#E4F6EC", "#16301F")
WARNING = ("#C77700", "#F0A93C")       # 주의 = 주황
WARNING_SOFT = ("#FFF3DD", "#332100")
DANGER = ("#D62E2E", "#FF5C5C")        # 에러/실패 = 빨강
DANGER_SOFT = ("#FCE6E6", "#3A1414")

# ── 로그 ──
LOG_BG = ("#F1F3F6", "#1A1C21")
LOG_TEXT = ("#1F2329", "#CFD3DA")

# ── 타이포 스케일 (현장 가독성 위해 전반 상향) ──
FONT_CAPTION = 12   # 카드 라벨/배지/캡션
FONT_BODY = 14      # 기본 본문
FONT_BODY_LG = 16   # 강조 본문/상품명
FONT_TITLE = 20     # 섹션 제목
FONT_METRIC = 34    # 현황 카드 숫자
FONT_DEVICE = 18    # 장비 상태 텍스트

# ── 스페이싱 (4·8 배수) ──
SP_1 = 4
SP_2 = 8
SP_3 = 12
SP_4 = 16
SP_6 = 24
SP_8 = 32
PADDING = 12  # 하위호환
GAP = 8       # 하위호환

# ── 라운드 / 윤곽 / 터치 ──
CORNER_SM = 8    # 칩/배지/작은 버튼
CORNER_MD = 12   # 카드/패널
CORNER_LG = 16   # 메인 컨테이너/모달
CORNER = CORNER_MD  # 하위호환 (기존 theme.CORNER)
BORDER_W = 1
TOUCH_MIN = 48   # 터치 타깃 최소 높이(주 액션)
TOUCH_LG = 56    # 핵심 액션(출력 버튼)


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
