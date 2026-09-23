import configparser
import os
import sys


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
INI_PATH = os.path.join(BASE_DIR, "config.ini")


def _app_version() -> str:
    if getattr(sys, "frozen", False):
        return os.path.splitext(os.path.basename(sys.executable))[0]
    return "개발 실행(소스)"


APP_VERSION = _app_version()

_DEFAULT_INI = """\
[printer]
; ── 가먼트 디자인 프린터 ──
; Windows 설정 > 프린터에서 정확한 이름 확인. 여러 개 지정 시 콤마 구분.
; 비워두면 가먼트 자동 출력 비활성 (do_garment 가드).
garment_name =
; 가먼트 자동 출력 활성화 (true/false)
garment_enabled = true
; 출력 모드: cli (가먼트 CLI 경유, 기본) / direct (win32print 직접)
garment_mode = cli
; 다중 프린터 분배 방식: round_robin (작업마다 순차 회전) / single (항상 첫 번째만)
garment_dispatch = round_robin
; 출력 전송 방식: manual (다운로드 후 작업자가 GUI에서 클릭해 전송, 기본) / auto (받는 즉시 자동 전송)
garment_print_mode = manual

; ── 작업지시서 프린터 (A4 레이저/잉크젯 등) ──
; 비워두면 작업지시서 미출력 (work_order_enabled=false와 동일 효과)
work_order_name =
; 작업지시서 자동 출력 활성화 (true/false)
work_order_enabled = false

; (deprecated, 하위 호환) — 새 키 garment_name/garment_mode 사용
name =
mode = cli

[device]
; 장비 상태 폴링은 GTX CLI status 명령을 사용하며 LAN 연결 프린터 전용이다.
; USB 연결 운영에서는 출력이 정상이어도 연결 실패(-2701)가 반복될 수 있으므로 기본 OFF.
status_enabled = false
status_interval = 5

[garment_cli]
; 가먼트 CLI(legacy 계열) 경로 (비워두면 exe 폴더 → .source 폴더 순 탐색)
cli_legacy_path =
; 가먼트 CLI(pro 계열) 경로 (비워두면 exe 폴더 → .source 폴더 순 탐색)
; GTX 장비 계열: auto=Windows 드라이버명/프린터명으로 판정, pro=GTXpro 고정, legacy=GTX-4 고정
gtx_cli = auto
cli_pro_path =
; ── CLI 인자 ──
; 자동 중앙 정렬 (true=이미지/플래튼 기준 position 자동 계산, false=아래 position 값 사용)
auto_center = true
; 인쇄 위치 (8자리, 앞4=좌측여백, 뒤4=상단여백, 단위 0.1mm; auto_center=false일 때만 사용)
position = 00000000
; 인쇄 크기 (8자리, 앞4=너비, 뒤4=높이, 단위 0.1mm; 비워두면 magnification 사용; 설정 시 magnification 무시)
size =
; 배율 (4자리, 단위 0.1%, 1000=100%; size 미지정 시 사용; print 는 -S/-R 중 하나가 필수이므로 기본 1000)
magnification = 1000
; RGB(255,255,255) 해석: 0=투명, 1=화이트 잉크 (색있는 옷에서 흰 디자인 필요 시 1)
white_as = 0
; ── XML 요소 ──
; 인쇄 매수 (1~999)
copies = 1
; 머신 모드 (0=기본)
machine_mode = 0
; 해상도 (1=1200dpi x 1200dpi)
resolution = 1
; 플래튼 크기: 0=16x21, 1=16x18, 2=14x16(기본), 3=10x12, 4=7x8
platen_size = 2
; 플레이트 자동 맞춤(true): 이미지를 플레이트에 contain(축소만, 작으면 원본), 가로 중앙·세로 상단
auto_fit = true
; 성인 플레이트(기본) / 아동 플레이트(주문서 플레이트 교체 체크 시 자동 사용)
platen_adult = 2
platen_child = 3
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

[render]
; PDF → 이미지 변환 해상도 (높을수록 선명)
dpi = 300

[poppler]
; poppler 바이너리 경로 (비워두면 시스템 PATH 또는 번들)
; 작업지시서 PDF 를 프린터로 보낼 때만 쓴다. 디자인은 PNG 라 변환하지 않는다
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
; spec §11.5 통일 규칙 — 비워두면 %LOCALAPPDATA%\\equip-sync-g-module\\ 하위 기본 폴더 자동 사용
incoming =
processing =
done =
originals =
error =

[log]
; 로그 파일 경로 (비워두면 %LOCALAPPDATA%\\equip-sync-g-module\\logs\\watcher.log)
file =
level = INFO

[gui]
; system | light | dark
appearance = system
"""

if not os.path.exists(INI_PATH):
    with open(INI_PATH, "w", encoding="utf-8") as f:
        f.write(_DEFAULT_INI)

_ini = configparser.ConfigParser()
_ini.read(INI_PATH, encoding="utf-8")

def _parse_printer_names(raw: str) -> list[str]:
    return [n.strip() for n in raw.split(",") if n.strip()]


GARMENT_PRINTER_NAMES = _parse_printer_names(
    _ini.get("printer", "garment_name", fallback=_ini.get("printer", "name", fallback=""))
)
GARMENT_PRINTER_NAME = GARMENT_PRINTER_NAMES[0] if GARMENT_PRINTER_NAMES else ""
GARMENT_ENABLED = _ini.getboolean("printer", "garment_enabled", fallback=True)
GARMENT_MODE = _ini.get("printer", "garment_mode", fallback=_ini.get("printer", "mode", fallback="cli"))
GARMENT_DISPATCH = _ini.get("printer", "garment_dispatch", fallback="round_robin").strip().lower()
if GARMENT_DISPATCH not in ("round_robin", "single"):
    GARMENT_DISPATCH = "round_robin"
GARMENT_PRINT_MODE = _ini.get("printer", "garment_print_mode", fallback="manual").strip().lower()
if GARMENT_PRINT_MODE not in ("manual", "auto"):
    GARMENT_PRINT_MODE = "manual"
GARMENT_AUTO_DELETE = _ini.getboolean("printer", "garment_auto_delete", fallback=False)

WORK_ORDER_PRINTER_NAME = _ini.get("printer", "work_order_name", fallback="").strip()
WORK_ORDER_ENABLED = _ini.getboolean("printer", "work_order_enabled", fallback=False)

PRINTER_NAMES = GARMENT_PRINTER_NAMES
PRINTER_NAME = GARMENT_PRINTER_NAME
PRINTER_MODE = GARMENT_MODE

def _load_cli_params() -> dict:
    def _i(key, default):
        try:
            return _ini.getint("garment_cli", key, fallback=default)
        except ValueError:
            return default

    def _b(key, default):
        try:
            return _ini.getboolean("garment_cli", key, fallback=default)
        except ValueError:
            return default

    def _s(key, default=""):
        return _ini.get("garment_cli", key, fallback=default).strip()

    _size = _s("size")
    _mag = _s("magnification")
    if not _size and not _mag:
        _mag = "1000"

    return {
        "GTX_CLI": _s("gtx_cli", "auto").lower(),
        "AUTO_CENTER": _b("auto_center", True),
        "POSITION": _s("position", "00000000") or "00000000",
        "SIZE": _size,
        "MAGNIFICATION": _mag,
        "WHITE_AS": _i("white_as", 0),
        "COPIES": _i("copies", 1),
        "MACHINE_MODE": _i("machine_mode", 0),
        "RESOLUTION": _i("resolution", 1),
        "PLATEN_SIZE": _i("platen_size", 2),
        "AUTO_FIT": _b("auto_fit", True),
        "PLATEN_ADULT": _i("platen_adult", 2),
        "PLATEN_CHILD": _i("platen_child", 3),
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


_gtx = _load_cli_params()
GTX_CLI = _gtx["GTX_CLI"] if _gtx["GTX_CLI"] in ("auto", "pro", "legacy") else "auto"
AUTO_CENTER = _gtx["AUTO_CENTER"]
POSITION = _gtx["POSITION"]
SIZE = _gtx["SIZE"]
MAGNIFICATION = _gtx["MAGNIFICATION"]
WHITE_AS = _gtx["WHITE_AS"]
COPIES = _gtx["COPIES"]
MACHINE_MODE = _gtx["MACHINE_MODE"]
RESOLUTION = _gtx["RESOLUTION"]
PLATEN_SIZE = _gtx["PLATEN_SIZE"]
AUTO_FIT = _gtx["AUTO_FIT"]
PLATEN_ADULT = _gtx["PLATEN_ADULT"]
PLATEN_CHILD = _gtx["PLATEN_CHILD"]
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

CLI_PARAM_KEYS = [
    "gtx_cli", "auto_center", "position", "size", "magnification", "white_as",
    "copies", "machine_mode", "resolution", "platen_size", "ink",
    "eco_mode", "highlight", "mask", "ink_volume", "double_print",
    "material_black", "multiple", "trans_color", "color_trans", "tolerance",
    "min_white", "choke", "pause",
    "saturation", "brightness", "contrast",
    "cyan_balance", "magenta_balance", "yellow_balance", "black_balance",
    "uni_print",
]

PLATEN_DIMS = {
    0: (4064, 5334),
    1: (4064, 4572),
    2: (3556, 4064),
    3: (2540, 3048),
    4: (1778, 2032),
}

def _resolve_cmd_exe(exe_name: str, ini_key: str) -> str:
    explicit = _ini.get("garment_cli", ini_key, fallback="")
    if explicit and os.path.isfile(explicit):
        return explicit
    bases = [BASE_DIR]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and meipass not in bases:
        bases.append(meipass)
    for base in bases:
        for sub in (exe_name, os.path.join(".source", exe_name)):
            cand = os.path.join(base, sub)
            if os.path.isfile(cand):
                return cand
    return ""


def _resolve_legacy_cli():
    return _resolve_cmd_exe("garment_cli_legacy.exe", "cli_legacy_path")


def _resolve_pro_cli():
    return _resolve_cmd_exe("garment_cli_pro.exe", "cli_pro_path")


LEGACY_CLI_EXE = _resolve_legacy_cli()
PRO_CLI_EXE = _resolve_pro_cli()
ACTIVE_CMD_STATE = os.path.join(BASE_DIR, ".active_garment_cmd")


def _resolve_api_dll_mode() -> str:
    value = _ini.get("garment_cli", "api_dll", fallback="auto").strip()
    return value or "auto"


def _resolve_backend() -> str:
    return "cli"


GARMENT_BACKEND = _resolve_backend()
try:
    API_RECT_DPI = _ini.getint("garment_cli", "api_rect_dpi", fallback=600)
except ValueError:
    API_RECT_DPI = 600
API_IMAGE_PATH = _ini.get("garment_cli", "api_image_path", fallback="rgba").strip().lower()
try:
    API_TRANS_LAYER = _ini.getint("garment_cli", "api_trans_layer", fallback=1)
except ValueError:
    API_TRANS_LAYER = 1

GARMENT_API_DLL = _resolve_api_dll_mode()
GARMENT_RUNTIME_DIR = os.path.join(BASE_DIR, "garment-runtime")
ACTIVE_API_STATE = os.path.join(BASE_DIR, ".active_garment_api")
ACTIVE_PRINTFILE_STATE = os.path.join(BASE_DIR, ".active_garment_printfile")
ACTIVE_SEND_STATE = os.path.join(BASE_DIR, ".active_garment_send")

def _path_fallback(paths_key: str, legacy_section: str, legacy_key: str, default_sub: str) -> str:
    val = _ini.get("paths", paths_key, fallback="").strip()
    if not val:
        val = _ini.get(legacy_section, legacy_key, fallback="").strip()
    return val or os.path.join(BASE_DIR, default_sub)


INCOMING_DIR = _path_fallback("incoming", "folder", "watch", "incoming")
PROCESSING_DIR = _ini.get("paths", "processing", fallback="").strip() or os.path.join(BASE_DIR, "processing")
DONE_DIR = _path_fallback("done", "folder", "done", "done")
ORIGINALS_DIR = _ini.get("paths", "originals", fallback="").strip() or os.path.join(DONE_DIR, "originals")
ERROR_DIR = _path_fallback("error", "folder", "error", "error")
LOG_FILE = _ini.get("log", "file", fallback="").strip() or os.path.join(BASE_DIR, "logs", "watcher.log")
LOG_LEVEL = _ini.get("log", "level", fallback="INFO").strip().upper()

RENDER_DPI = _ini.getint("render", "dpi", fallback=300)

POPPLER_SOURCE = ""


def _resolve_poppler():
    global POPPLER_SOURCE
    explicit = _ini.get("poppler", "path", fallback="")
    if explicit:
        POPPLER_SOURCE = "config.ini"
        return explicit
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "poppler")
        if os.path.isdir(bundled):
            POPPLER_SOURCE = "번들"
            return bundled
    POPPLER_SOURCE = "시스템 PATH"
    return None

POPPLER_PATH = _resolve_poppler()

API_TENANT = _ini.get("api", "tenant", fallback="")
API_KEY = _ini.get("api", "api_key", fallback="")
API_BASE_URL = _ini.get("api", "base_url", fallback="https://store.dpl.shop")
API_POLL_INTERVAL = _ini.getint("api", "poll_interval", fallback=5)

DEVICE_STATUS_ENABLED = _ini.getboolean("device", "status_enabled", fallback=False)
DEVICE_STATUS_INTERVAL = _ini.getint("device", "status_interval", fallback=5)

DOWNLOAD_DIR = _ini.get("download", "dir", fallback="").strip() or INCOMING_DIR

FILE_STABLE_CHECK_INTERVAL = 1.0
FILE_STABLE_CHECK_COUNT = 2

for _d in (INCOMING_DIR, PROCESSING_DIR, DONE_DIR, ORIGINALS_DIR, ERROR_DIR, DOWNLOAD_DIR, os.path.dirname(LOG_FILE)):
    if _d:
        os.makedirs(_d, exist_ok=True)


def save_value(section: str, key: str, value: str):
    if not _ini.has_section(section):
        _ini.add_section(section)
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
    global PRINTER_NAME, PRINTER_NAMES, PRINTER_MODE, LEGACY_CLI_EXE, PRO_CLI_EXE
    global GARMENT_API_DLL, GARMENT_BACKEND
    global GARMENT_PRINTER_NAME, GARMENT_PRINTER_NAMES, GARMENT_ENABLED, GARMENT_MODE
    global GARMENT_DISPATCH, GARMENT_PRINT_MODE, GARMENT_AUTO_DELETE
    global WORK_ORDER_PRINTER_NAME, WORK_ORDER_ENABLED
    global GTX_CLI, AUTO_CENTER, POSITION, SIZE, MAGNIFICATION, WHITE_AS
    global COPIES, MACHINE_MODE, RESOLUTION, PLATEN_SIZE, INK
    global AUTO_FIT, PLATEN_ADULT, PLATEN_CHILD
    global ECO_MODE, HIGHLIGHT, MASK, INK_VOLUME, DOUBLE_PRINT
    global MATERIAL_BLACK, MULTIPLE, TRANS_COLOR, COLOR_TRANS, TOLERANCE
    global MIN_WHITE, CHOKE, PAUSE
    global SATURATION, BRIGHTNESS, CONTRAST
    global CYAN_BALANCE, MAGENTA_BALANCE, YELLOW_BALANCE, BLACK_BALANCE, UNI_PRINT
    global INCOMING_DIR, PROCESSING_DIR, DONE_DIR, ORIGINALS_DIR, ERROR_DIR
    global RENDER_DPI, POPPLER_PATH, LOG_FILE, LOG_LEVEL
    global API_TENANT, API_KEY, API_BASE_URL, API_POLL_INTERVAL, DOWNLOAD_DIR
    global DEVICE_STATUS_ENABLED, DEVICE_STATUS_INTERVAL

    _ini.read(INI_PATH, encoding="utf-8")

    GARMENT_PRINTER_NAMES = _parse_printer_names(
        _ini.get("printer", "garment_name", fallback=_ini.get("printer", "name", fallback=""))
    )
    GARMENT_PRINTER_NAME = GARMENT_PRINTER_NAMES[0] if GARMENT_PRINTER_NAMES else ""
    GARMENT_ENABLED = _ini.getboolean("printer", "garment_enabled", fallback=True)
    GARMENT_MODE = _ini.get(
        "printer", "garment_mode", fallback=_ini.get("printer", "mode", fallback="cli")
    )
    GARMENT_DISPATCH = _ini.get("printer", "garment_dispatch", fallback="round_robin").strip().lower()
    if GARMENT_DISPATCH not in ("round_robin", "single"):
        GARMENT_DISPATCH = "round_robin"
    GARMENT_PRINT_MODE = _ini.get("printer", "garment_print_mode", fallback="manual").strip().lower()
    if GARMENT_PRINT_MODE not in ("manual", "auto"):
        GARMENT_PRINT_MODE = "manual"
    GARMENT_AUTO_DELETE = _ini.getboolean("printer", "garment_auto_delete", fallback=False)
    WORK_ORDER_PRINTER_NAME = _ini.get("printer", "work_order_name", fallback="").strip()
    WORK_ORDER_ENABLED = _ini.getboolean("printer", "work_order_enabled", fallback=False)
    PRINTER_NAMES = GARMENT_PRINTER_NAMES
    PRINTER_NAME = GARMENT_PRINTER_NAME
    PRINTER_MODE = GARMENT_MODE
    LEGACY_CLI_EXE = _resolve_legacy_cli()
    PRO_CLI_EXE = _resolve_pro_cli()
    GARMENT_API_DLL = _resolve_api_dll_mode()
    GARMENT_BACKEND = _resolve_backend()

    g = _load_cli_params()
    GTX_CLI = g["GTX_CLI"] if g["GTX_CLI"] in ("auto", "pro", "legacy") else "auto"
    AUTO_CENTER = g["AUTO_CENTER"]
    POSITION = g["POSITION"]; SIZE = g["SIZE"]; MAGNIFICATION = g["MAGNIFICATION"]; WHITE_AS = g["WHITE_AS"]
    COPIES = g["COPIES"]; MACHINE_MODE = g["MACHINE_MODE"]; RESOLUTION = g["RESOLUTION"]
    PLATEN_SIZE = g["PLATEN_SIZE"]; INK = g["INK"]
    AUTO_FIT = g["AUTO_FIT"]; PLATEN_ADULT = g["PLATEN_ADULT"]; PLATEN_CHILD = g["PLATEN_CHILD"]
    ECO_MODE = g["ECO_MODE"]; HIGHLIGHT = g["HIGHLIGHT"]; MASK = g["MASK"]
    INK_VOLUME = g["INK_VOLUME"]; DOUBLE_PRINT = g["DOUBLE_PRINT"]
    MATERIAL_BLACK = g["MATERIAL_BLACK"]; MULTIPLE = g["MULTIPLE"]
    TRANS_COLOR = g["TRANS_COLOR"]; COLOR_TRANS = g["COLOR_TRANS"]; TOLERANCE = g["TOLERANCE"]
    MIN_WHITE = g["MIN_WHITE"]; CHOKE = g["CHOKE"]; PAUSE = g["PAUSE"]
    SATURATION = g["SATURATION"]; BRIGHTNESS = g["BRIGHTNESS"]; CONTRAST = g["CONTRAST"]
    CYAN_BALANCE = g["CYAN_BALANCE"]; MAGENTA_BALANCE = g["MAGENTA_BALANCE"]
    YELLOW_BALANCE = g["YELLOW_BALANCE"]; BLACK_BALANCE = g["BLACK_BALANCE"]
    UNI_PRINT = g["UNI_PRINT"]
    INCOMING_DIR = _path_fallback("incoming", "folder", "watch", "incoming")
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
    DEVICE_STATUS_ENABLED = _ini.getboolean("device", "status_enabled", fallback=False)
    DEVICE_STATUS_INTERVAL = _ini.getint("device", "status_interval", fallback=5)
    DOWNLOAD_DIR = _ini.get("download", "dir", fallback="").strip() or INCOMING_DIR

    for _d in (INCOMING_DIR, PROCESSING_DIR, DONE_DIR, ORIGINALS_DIR, ERROR_DIR, DOWNLOAD_DIR, os.path.dirname(LOG_FILE)):
        if _d:
            os.makedirs(_d, exist_ok=True)
