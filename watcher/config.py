import configparser
import os
import sys


def _base_dir():
    """exe 파일이 있는 폴더 (spec §11.5) — 운영자가 즉시 발견 가능한 위치."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
INI_PATH = os.path.join(BASE_DIR, "config.ini")

_DEFAULT_INI = """\
[printer]
; Windows 설정 > 프린터에서 정확한 이름 확인
; 여러 개 지정 시 콤마 구분 (첫 번째 실패 시 다음 프린터로 자동 폴백)
name = Brother GTX-4
; 출력 모드: direct (win32print 직접) / gtx4cmd (GTX4CMD.exe 경유)
mode = direct

[gtx4cmd]
; GTX4CMD.exe 경로 (비워두면 .source 폴더에서 탐색)
exe_path =
; ── CLI 인자 ──
; 자동 중앙 정렬 (true=이미지/플래튼 기준 position 자동 계산, false=아래 position 값 사용)
auto_center = true
; 인쇄 위치 (8자리, 앞4=좌측여백, 뒤4=상단여백, 단위 0.1mm; auto_center=false일 때만 사용)
position = 00000000
; 인쇄 크기 (8자리, 앞4=너비, 뒤4=높이, 단위 0.1mm; 비워두면 -S 미사용; 설정 시 magnification 무시)
size =
; 배율 (4자리, 단위 0.1%, 1000=100%; 비워두면 -R 미사용; -S와 동시 사용 불가)
magnification =
; RGB(255,255,255) 해석: 0=투명, 1=화이트 잉크 (색있는 옷에서 흰 디자인 필요 시 1)
white_as = 0
; ── XML 요소 ──
; 인쇄 매수 (1~999)
copies = 1
; 머신 모드 (0=GTX-422)
machine_mode = 0
; 해상도 (1=1200dpi x 1200dpi)
resolution = 1
; 플래튼 크기: 0=16x21, 1=16x18, 2=14x16, 3=10x12, 4=7x8
platen_size = 0
; 잉크 조합: 0=Color, 1=White, 2=Color+White, 3=Black
ink = 0
; Eco 모드 (ink=2일 때만): false/true
eco_mode = false
; 하이라이트 (ink=1 or 2일 때만, 1~9)
highlight = 5
; 마스크 (ink=1 or 2일 때만, 1~5)
mask = 1
; 컬러 잉크량 (ink=0일 때만, 1~10)
ink_volume = 5
; 더블 프린팅 (ink=0일 때만, 0~3)
double_print = 0
; 배경 검정 사용 (ink=2일 때만): false/true
material_black = false
; 멀티패스 (ink=0 or 2일 때만): false/true
multiple = false
; 투명색 사용 (ink=1 or 2일 때만): false/true
trans_color = false
; 투명 RGB 10진값 (trans_color=true일 때만)
color_trans = 0
; 톨러런스 (trans_color=true일 때만, 0~50)
tolerance = 0
; 최소 화이트 (ink=2일 때만, 1~6)
min_white = 1
; 초크 (ink=2일 때만, 0~10)
choke = 0
; W/C 일시정지 (ink=2일 때만): false/true
pause = false
; 채도 (0~40)
saturation = 0
; 명도 (0~40)
brightness = 0
; 대비 (0~40)
contrast = 0
; 컬러밸런스 Cyan (ink=0 or 2일 때만, -5~5)
cyan_balance = 0
; 컬러밸런스 Magenta (-5~5)
magenta_balance = 0
; 컬러밸런스 Yellow (-5~5)
yellow_balance = 0
; 컬러밸런스 Black (-5~5)
black_balance = 0
; 단방향 인쇄: false/true
uni_print = false

[folder]
; 비워두면 exe와 같은 폴더 기준으로 자동 생성
watch =
done =
error =

[render]
; PDF → 이미지 변환 해상도 (높을수록 선명)
dpi = 300

[poppler]
; poppler 바이너리 경로 (비워두면 시스템 PATH 또는 번들)
path =

[api]
; dps-store 테넌트명 (인증 시 자동 설정)
tenant =
; API 키 (Device Auth로 발급, 자동 설정)
api_key =
; dps-store 서버 URL
base_url = https://store.dpl.shop
; 풀링 간격 (초)
poll_interval = 5

[download]
; PDF 다운로드 폴더 (비워두면 incoming/과 통합)
dir =

[paths]
; spec §11.5 통일 규칙 — 비워두면 %LOCALAPPDATA%\equip-sync-b-module\ 하위 기본 폴더 자동 사용
incoming =
processing =
done =
originals =
error =

[log]
; 로그 파일 경로 (비워두면 %LOCALAPPDATA%\equip-sync-b-module\logs\watcher.log)
file =
level = INFO

[gui]
; system | light | dark
appearance = system
"""

# config.ini가 없으면 기본값으로 생성
if not os.path.exists(INI_PATH):
    with open(INI_PATH, "w", encoding="utf-8") as f:
        f.write(_DEFAULT_INI)

_ini = configparser.ConfigParser()
_ini.read(INI_PATH, encoding="utf-8")

def _parse_printer_names(raw: str) -> list[str]:
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return names or ["Brother GTX-4"]


# --- printer ---
PRINTER_NAMES = _parse_printer_names(_ini.get("printer", "name", fallback="Brother GTX-4"))
PRINTER_NAME = PRINTER_NAMES[0]  # 하위호환: 단일 참조 시 첫 번째 프린터
PRINTER_MODE = _ini.get("printer", "mode", fallback="direct")

# --- gtx4cmd ---
def _load_gtx4cmd() -> dict:
    """GTX4CMD 파라미터를 dict로 로드. 누락/파싱 오류 시 기본값."""
    def _i(key, default):
        try:
            return _ini.getint("gtx4cmd", key, fallback=default)
        except ValueError:
            return default

    def _b(key, default):
        try:
            return _ini.getboolean("gtx4cmd", key, fallback=default)
        except ValueError:
            return default

    def _s(key, default=""):
        return _ini.get("gtx4cmd", key, fallback=default).strip()

    return {
        # CLI
        "AUTO_CENTER": _b("auto_center", True),
        "POSITION": _s("position", "00000000") or "00000000",
        "SIZE": _s("size"),
        "MAGNIFICATION": _s("magnification"),
        "WHITE_AS": _i("white_as", 0),
        # XML
        "COPIES": _i("copies", 1),
        "MACHINE_MODE": _i("machine_mode", 0),
        "RESOLUTION": _i("resolution", 1),
        "PLATEN_SIZE": _i("platen_size", 0),
        "INK": _i("ink", 0),
        "ECO_MODE": _b("eco_mode", False),
        "HIGHLIGHT": _i("highlight", 5),
        "MASK": _i("mask", 1),
        "INK_VOLUME": _i("ink_volume", 5),
        "DOUBLE_PRINT": _i("double_print", 0),
        "MATERIAL_BLACK": _b("material_black", False),
        "MULTIPLE": _b("multiple", False),
        "TRANS_COLOR": _b("trans_color", False),
        "COLOR_TRANS": _i("color_trans", 0),
        "TOLERANCE": _i("tolerance", 0),
        "MIN_WHITE": _i("min_white", 1),
        "CHOKE": _i("choke", 0),
        "PAUSE": _b("pause", False),
        "SATURATION": _i("saturation", 0),
        "BRIGHTNESS": _i("brightness", 0),
        "CONTRAST": _i("contrast", 0),
        "CYAN_BALANCE": _i("cyan_balance", 0),
        "MAGENTA_BALANCE": _i("magenta_balance", 0),
        "YELLOW_BALANCE": _i("yellow_balance", 0),
        "BLACK_BALANCE": _i("black_balance", 0),
        "UNI_PRINT": _b("uni_print", False),
    }


_gtx = _load_gtx4cmd()
AUTO_CENTER = _gtx["AUTO_CENTER"]
POSITION = _gtx["POSITION"]
SIZE = _gtx["SIZE"]
MAGNIFICATION = _gtx["MAGNIFICATION"]
WHITE_AS = _gtx["WHITE_AS"]
COPIES = _gtx["COPIES"]
MACHINE_MODE = _gtx["MACHINE_MODE"]
RESOLUTION = _gtx["RESOLUTION"]
PLATEN_SIZE = _gtx["PLATEN_SIZE"]
INK = _gtx["INK"]
ECO_MODE = _gtx["ECO_MODE"]
HIGHLIGHT = _gtx["HIGHLIGHT"]
MASK = _gtx["MASK"]
INK_VOLUME = _gtx["INK_VOLUME"]
DOUBLE_PRINT = _gtx["DOUBLE_PRINT"]
MATERIAL_BLACK = _gtx["MATERIAL_BLACK"]
MULTIPLE = _gtx["MULTIPLE"]
TRANS_COLOR = _gtx["TRANS_COLOR"]
COLOR_TRANS = _gtx["COLOR_TRANS"]
TOLERANCE = _gtx["TOLERANCE"]
MIN_WHITE = _gtx["MIN_WHITE"]
CHOKE = _gtx["CHOKE"]
PAUSE = _gtx["PAUSE"]
SATURATION = _gtx["SATURATION"]
BRIGHTNESS = _gtx["BRIGHTNESS"]
CONTRAST = _gtx["CONTRAST"]
CYAN_BALANCE = _gtx["CYAN_BALANCE"]
MAGENTA_BALANCE = _gtx["MAGENTA_BALANCE"]
YELLOW_BALANCE = _gtx["YELLOW_BALANCE"]
BLACK_BALANCE = _gtx["BLACK_BALANCE"]
UNI_PRINT = _gtx["UNI_PRINT"]

# GUI 파라미터 패널에서 사용하는 GTX4CMD 파라미터 키 목록 (저장 시 순서 보존)
GTX4CMD_KEYS = [
    "auto_center", "position", "size", "magnification", "white_as",
    "copies", "machine_mode", "resolution", "platen_size", "ink",
    "eco_mode", "highlight", "mask", "ink_volume", "double_print",
    "material_black", "multiple", "trans_color", "color_trans", "tolerance",
    "min_white", "choke", "pause",
    "saturation", "brightness", "contrast",
    "cyan_balance", "magenta_balance", "yellow_balance", "black_balance",
    "uni_print",
]

# 플래튼 크기 (0.1mm 단위, 너비 x 높이) — 인치 → 25.4mm 환산
PLATEN_DIMS = {
    0: (4064, 5334),  # 16x21 inches
    1: (4064, 4572),  # 16x18 inches
    2: (3556, 4064),  # 14x16 inches
    3: (2540, 3048),  # 10x12 inches
    4: (1778, 2032),  # 7x8 inches
}

# --- gtx4cmd exe 경로 ---
def _resolve_gtx4cmd():
    explicit = _ini.get("gtx4cmd", "exe_path", fallback="")
    if explicit and os.path.isfile(explicit):
        return explicit
    # exe와 같은 폴더 (배포 시 기본)
    same_dir = os.path.join(BASE_DIR, "GTX4CMD.exe")
    if os.path.isfile(same_dir):
        return same_dir
    # .source 폴더 (개발 시)
    source = os.path.join(BASE_DIR, ".source", "GTX4CMD.exe")
    if os.path.isfile(source):
        return source
    return ""

GTX4CMD_EXE = _resolve_gtx4cmd()

# --- folder (spec §11.5 — incoming/processing/done/done/originals/error/logs 통일) ---
def _path_fallback(paths_key: str, legacy_section: str, legacy_key: str, default_sub: str) -> str:
    val = _ini.get("paths", paths_key, fallback="").strip()
    if not val:
        val = _ini.get(legacy_section, legacy_key, fallback="").strip()
    return val or os.path.join(BASE_DIR, default_sub)


WATCH_DIR = _path_fallback("incoming", "folder", "watch", "incoming")
PROCESSING_DIR = _ini.get("paths", "processing", fallback="").strip() or os.path.join(BASE_DIR, "processing")
DONE_DIR = _path_fallback("done", "folder", "done", "done")
ORIGINALS_DIR = _ini.get("paths", "originals", fallback="").strip() or os.path.join(DONE_DIR, "originals")
ERROR_DIR = _path_fallback("error", "folder", "error", "error")
LOG_FILE = _ini.get("log", "file", fallback="").strip() or os.path.join(BASE_DIR, "logs", "watcher.log")
LOG_LEVEL = _ini.get("log", "level", fallback="INFO").strip().upper()

# --- render ---
RENDER_DPI = _ini.getint("render", "dpi", fallback=300)

# --- poppler ---
def _resolve_poppler():
    explicit = _ini.get("poppler", "path", fallback="")
    if explicit:
        return explicit
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "poppler")
        if os.path.isdir(bundled):
            return bundled
    return None

POPPLER_PATH = _resolve_poppler()

# --- api ---
API_TENANT = _ini.get("api", "tenant", fallback="")
API_KEY = _ini.get("api", "api_key", fallback="")
API_BASE_URL = _ini.get("api", "base_url", fallback="https://store.dpl.shop")
API_POLL_INTERVAL = _ini.getint("api", "poll_interval", fallback=5)

# --- download (legacy — 명시되지 않으면 incoming과 통합) ---
DOWNLOAD_DIR = _ini.get("download", "dir", fallback="").strip() or WATCH_DIR

# 파일 안정성 확인 파라미터
FILE_STABLE_CHECK_INTERVAL = 1.0
FILE_STABLE_CHECK_COUNT = 2

# 폴더 자동 생성 (spec §11.5 6종 + DOWNLOAD_DIR 호환)
for _d in (WATCH_DIR, PROCESSING_DIR, DONE_DIR, ORIGINALS_DIR, ERROR_DIR, DOWNLOAD_DIR, os.path.dirname(LOG_FILE)):
    if _d:
        os.makedirs(_d, exist_ok=True)


def save_value(section: str, key: str, value: str):
    """config.ini에 값을 저장한다."""
    _ini.set(section, key, value)
    with open(INI_PATH, "w", encoding="utf-8") as f:
        _ini.write(f)


def get_appearance() -> str:
    p = configparser.ConfigParser()
    p.read(INI_PATH, encoding="utf-8")
    value = p.get("gui", "appearance", fallback="system").strip().lower()
    return value if value in {"system", "light", "dark"} else "system"


def set_appearance(value: str) -> None:
    value = (value or "system").strip().lower()
    if value not in {"system", "light", "dark"}:
        value = "system"
    p = configparser.ConfigParser()
    p.read(INI_PATH, encoding="utf-8")
    if not p.has_section("gui"):
        p.add_section("gui")
    p.set("gui", "appearance", value)
    with open(INI_PATH, "w", encoding="utf-8") as f:
        p.write(f)


def reload():
    """config.ini를 다시 읽어서 모듈 변수를 갱신한다."""
    global PRINTER_NAME, PRINTER_NAMES, PRINTER_MODE, GTX4CMD_EXE
    global AUTO_CENTER, POSITION, SIZE, MAGNIFICATION, WHITE_AS
    global COPIES, MACHINE_MODE, RESOLUTION, PLATEN_SIZE, INK
    global ECO_MODE, HIGHLIGHT, MASK, INK_VOLUME, DOUBLE_PRINT
    global MATERIAL_BLACK, MULTIPLE, TRANS_COLOR, COLOR_TRANS, TOLERANCE
    global MIN_WHITE, CHOKE, PAUSE
    global SATURATION, BRIGHTNESS, CONTRAST
    global CYAN_BALANCE, MAGENTA_BALANCE, YELLOW_BALANCE, BLACK_BALANCE, UNI_PRINT
    global WATCH_DIR, PROCESSING_DIR, DONE_DIR, ORIGINALS_DIR, ERROR_DIR
    global RENDER_DPI, POPPLER_PATH, LOG_FILE, LOG_LEVEL
    global API_TENANT, API_KEY, API_BASE_URL, API_POLL_INTERVAL, DOWNLOAD_DIR

    _ini.read(INI_PATH, encoding="utf-8")

    PRINTER_NAMES = _parse_printer_names(_ini.get("printer", "name", fallback="Brother GTX-4"))
    PRINTER_NAME = PRINTER_NAMES[0]
    PRINTER_MODE = _ini.get("printer", "mode", fallback="direct")
    GTX4CMD_EXE = _resolve_gtx4cmd()

    g = _load_gtx4cmd()
    AUTO_CENTER = g["AUTO_CENTER"]
    POSITION = g["POSITION"]; SIZE = g["SIZE"]; MAGNIFICATION = g["MAGNIFICATION"]; WHITE_AS = g["WHITE_AS"]
    COPIES = g["COPIES"]; MACHINE_MODE = g["MACHINE_MODE"]; RESOLUTION = g["RESOLUTION"]
    PLATEN_SIZE = g["PLATEN_SIZE"]; INK = g["INK"]
    ECO_MODE = g["ECO_MODE"]; HIGHLIGHT = g["HIGHLIGHT"]; MASK = g["MASK"]
    INK_VOLUME = g["INK_VOLUME"]; DOUBLE_PRINT = g["DOUBLE_PRINT"]
    MATERIAL_BLACK = g["MATERIAL_BLACK"]; MULTIPLE = g["MULTIPLE"]
    TRANS_COLOR = g["TRANS_COLOR"]; COLOR_TRANS = g["COLOR_TRANS"]; TOLERANCE = g["TOLERANCE"]
    MIN_WHITE = g["MIN_WHITE"]; CHOKE = g["CHOKE"]; PAUSE = g["PAUSE"]
    SATURATION = g["SATURATION"]; BRIGHTNESS = g["BRIGHTNESS"]; CONTRAST = g["CONTRAST"]
    CYAN_BALANCE = g["CYAN_BALANCE"]; MAGENTA_BALANCE = g["MAGENTA_BALANCE"]
    YELLOW_BALANCE = g["YELLOW_BALANCE"]; BLACK_BALANCE = g["BLACK_BALANCE"]
    UNI_PRINT = g["UNI_PRINT"]
    WATCH_DIR = _path_fallback("incoming", "folder", "watch", "incoming")
    PROCESSING_DIR = _ini.get("paths", "processing", fallback="").strip() or os.path.join(BASE_DIR, "processing")
    DONE_DIR = _path_fallback("done", "folder", "done", "done")
    ORIGINALS_DIR = _ini.get("paths", "originals", fallback="").strip() or os.path.join(DONE_DIR, "originals")
    ERROR_DIR = _path_fallback("error", "folder", "error", "error")
    LOG_FILE = _ini.get("log", "file", fallback="").strip() or os.path.join(BASE_DIR, "logs", "watcher.log")
    LOG_LEVEL = _ini.get("log", "level", fallback="INFO").strip().upper()
    RENDER_DPI = _ini.getint("render", "dpi", fallback=300)
    POPPLER_PATH = _resolve_poppler()

    API_TENANT = _ini.get("api", "tenant", fallback="")
    API_KEY = _ini.get("api", "api_key", fallback="")
    API_BASE_URL = _ini.get("api", "base_url", fallback="https://store.dpl.shop")
    API_POLL_INTERVAL = _ini.getint("api", "poll_interval", fallback=5)
    DOWNLOAD_DIR = _ini.get("download", "dir", fallback="").strip() or WATCH_DIR

    for _d in (WATCH_DIR, PROCESSING_DIR, DONE_DIR, ORIGINALS_DIR, ERROR_DIR, DOWNLOAD_DIR, os.path.dirname(LOG_FILE)):
        if _d:
            os.makedirs(_d, exist_ok=True)
