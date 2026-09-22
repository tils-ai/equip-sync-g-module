"""가먼트 API 직접 호출 — 1단계: 구조체 선언과 정렬 검증.

지금 출력 경로는 `우리 코드 → 벤더 CLI(exe) → 벤더 API(dll) → 드라이버` 다. 구조체를 채우는
주체가 CLI 라서 **CLI 세대가 곧 우리 세대**이고, 현장이 드라이버를 올릴 때마다 CLI 를 새로
받아야 한다. 그 CLI 는 공개 배포물이 아니다. 2026-09-22 현장 장애의 구조적 원인이었다.

구조체를 우리가 직접 선언하면 그 고리가 끊어진다. API 라이브러리는 드라이버·벤더 편집기가
현장 PC 에 이미 깔아 두므로 세대가 저절로 맞고, 우리가 들고 다닐 필요도 없어진다.

이 모듈은 그 전환의 **1단계**다. 실제 출력은 아직 하지 않는다. 구조체 배치가 라이브러리와
맞는지만 확인한다. 배치가 틀리면 값이 한 칸씩 밀린 채 인쇄되는데, 그건 출력이 실패하는 것보다
훨씬 비싼 사고다(옷을 버린다). 그래서 점검을 먼저 통과시키고 나서 다음 단계로 간다.

필드 순서·타입의 출처는 dps-store 문서 허브의 5.x 구조체 문서다. 폭이 고정된 타입만 쓴다 —
개발 장비(macOS/Linux)에서도 오프셋이 같아야 표와 대조할 수 있기 때문이다.
"""

import ctypes
import datetime
import os
import platform

import config
import garment_runtime

MAX_PATH = 260
JOB_NAME_LEN = 128

BYTE = ctypes.c_ubyte
BOOL = ctypes.c_int32       # Windows BOOL = int
INT = ctypes.c_int32
UINT = ctypes.c_uint32
COLORREF = ctypes.c_uint32
LONG = ctypes.c_int32


class RECT(ctypes.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]


class ProOption(ctypes.Structure):
    """pro 계열 5.x 인쇄 옵션.

    4.x 대비 `byPrintMethod` · `byWInkVer` · `byQuality` · `bFastMode` 가 늘었다. 특히
    `byWInkVer` 가 `byInk` 와 `byResolution` **사이**에 끼어 그 뒤가 전부 밀린다.
    """

    _fields_ = [
        ("szFileName", ctypes.c_char * MAX_PATH),
        ("uiCopies", UINT),
        ("szJobName", ctypes.c_char * JOB_NAME_LEN),
        ("byPrintMethod", BYTE),
        ("byPlatenSize", BYTE),
        ("byInk", BYTE),
        ("byWInkVer", BYTE),
        ("byResolution", BYTE),
        ("bEcoMode", BOOL),
        ("byQuality", BYTE),
        ("byHighlight", BYTE),
        ("byMask", BYTE),
        ("byInkVolume", BYTE),
        ("byDoublePrint", BYTE),
        ("bFastMode", BOOL),
        ("bDivide", BOOL),
        ("byDivideSpan", BYTE),
        ("bPause", BOOL),
        ("byPauseSpan", BYTE),
        ("bMaterialBlack", BOOL),
        ("bMultiple", BOOL),
        ("bTransColor", BOOL),
        ("colorTrans", COLORREF),
        ("byTolerance", BYTE),
        ("byMinWhite", BYTE),
        ("byChoke", BYTE),
        ("bySaturation", BYTE),
        ("byBrightness", BYTE),
        ("byContrast", BYTE),
        ("iCyanBalance", INT),
        ("iMagentaBalance", INT),
        ("iYellowBalance", INT),
        ("iBlackBalance", INT),
        ("bUniDirection", BOOL),
        ("byTransLayer", BYTE),
        ("szTransFile", ctypes.c_char * MAX_PATH),
        ("uiReserved1", UINT),
        ("uiReserved2", UINT),
        ("uiReserved3", UINT),
        ("uiReserved4", UINT),
    ]


class LegacyOption(ctypes.Structure):
    """legacy 계열 5.x 세대 인쇄 옵션. 이 세대에는 여기에도 `byWInkVer` 가 들어갔다."""

    _fields_ = [
        ("szFileName", ctypes.c_char * MAX_PATH),
        ("uiCopies", UINT),
        ("byMachineMode", BYTE),
        ("szJobName", ctypes.c_char * JOB_NAME_LEN),
        ("byPlatenSize", BYTE),
        ("byInk", BYTE),
        ("byWInkVer", BYTE),
        ("byResolution", BYTE),
        ("byHighlight", BYTE),
        ("byMask", BYTE),
        ("byInkVolume", BYTE),
        ("byDoublePrint", BYTE),
        ("bMaterialBlack", BOOL),
        ("bMultiple", BOOL),
        ("bTransColor", BOOL),
        ("colorTrans", COLORREF),
        ("byTolerance", BYTE),
        ("byMinWhite", BYTE),
        ("byChoke", BYTE),
        ("bPause", BOOL),
        ("bySaturation", BYTE),
        ("byBrightness", BYTE),
        ("byContrast", BYTE),
        ("iCyanBalance", INT),
        ("iMagentaBalance", INT),
        ("iYellowBalance", INT),
        ("bUniDirection", BOOL),
        ("uiReserved1", UINT),
        ("uiReserved2", UINT),
        ("byTransLayer", BYTE),
        ("szTransFile", ctypes.c_char * MAX_PATH),
        ("iBlackBalance", INT),
        ("bEcoMode", BOOL),
        ("bDivide", BOOL),
        ("byDivideSpan", BYTE),
        ("byPauseSpan", BYTE),
    ]


# 라이브러리 이름 접두사별 구조체. 접두사는 라이브러리 파일명에서 뽑는다(벤더명 미기재).
_OPTION_BY_PREFIX = {"pro": ProOption, "legacy": LegacyOption}


def option_type_for(api_dll: str, model: str) -> type:
    return _OPTION_BY_PREFIX.get(model, ProOption)


def sample_option(option_type: type, from_config: bool = True) -> ctypes.Structure:
    """점검용 옵션 값. 현장 설정을 그대로 실어야 현장과 같은 조건이 된다."""
    opt = option_type()
    opt.szFileName = b""
    opt.szJobName = b"selftest"
    opt.uiCopies = max(1, int(getattr(config, "COPIES", 1)))
    opt.byPlatenSize = int(getattr(config, "PLATEN_SIZE", 2))
    opt.byInk = int(getattr(config, "INK", 0))
    opt.byResolution = int(getattr(config, "RESOLUTION", 1))
    opt.byHighlight = int(getattr(config, "HIGHLIGHT", 5))
    opt.byMask = int(getattr(config, "MASK", 1))
    opt.byInkVolume = int(getattr(config, "INK_VOLUME", 5))
    opt.byDoublePrint = int(getattr(config, "DOUBLE_PRINT", 0))
    opt.byTolerance = int(getattr(config, "TOLERANCE", 0))
    opt.byMinWhite = int(getattr(config, "MIN_WHITE", 1))
    opt.byChoke = int(getattr(config, "CHOKE", 0))
    opt.bySaturation = int(getattr(config, "SATURATION", 0))
    opt.byBrightness = int(getattr(config, "BRIGHTNESS", 0))
    opt.byContrast = int(getattr(config, "CONTRAST", 0))
    opt.iCyanBalance = int(getattr(config, "CYAN_BALANCE", 0))
    opt.iMagentaBalance = int(getattr(config, "MAGENTA_BALANCE", 0))
    opt.iYellowBalance = int(getattr(config, "YELLOW_BALANCE", 0))
    opt.iBlackBalance = int(getattr(config, "BLACK_BALANCE", 0))
    if hasattr(opt, "byPrintMethod"):
        opt.byPrintMethod = 0  # 0 = 일반 가먼트 출력(DTG)
    if hasattr(opt, "byQuality"):
        opt.byQuality = 1  # 1 = Standard
    if not from_config:
        return opt
    return opt


def field_layout(option_type: type) -> list:
    """(필드명, 오프셋, 크기) 목록 — 보고서에서 표와 대조하기 위한 것."""
    return [
        (name, getattr(option_type, name).offset, getattr(option_type, name).size)
        for name, _ in option_type._fields_
    ]


def _load(api_dll: str):
    """API 라이브러리 로드. 같은 폴더의 의존 모듈도 찾도록 탐색 경로를 더해 준다."""
    folder = os.path.dirname(os.path.abspath(api_dll))
    if hasattr(os, "add_dll_directory") and os.path.isdir(folder):
        os.add_dll_directory(folder)
    loader = getattr(ctypes, "WinDLL", ctypes.CDLL)
    return loader(api_dll)


def probe(api_dll: str, model: str = "pro") -> list:
    """라이브러리를 열어 구조체 배치를 점검하고 결과 줄 목록을 돌려준다.

    핵심은 CheckOption 이다. 0 이면 배치가 맞는 것이고, -11xx 가 나오면 **그 코드가 가리키는
    필드 언저리에서 밀렸다**는 뜻이라 어디를 고쳐야 할지까지 나온다.
    """
    lines = []
    prefix = garment_runtime.driver_file_prefix(api_dll)  # 예: 함수 접두사
    option_type = option_type_for(api_dll, model)
    lines.append(f"  라이브러리 : {garment_runtime.describe_file(api_dll)}")
    lines.append(f"  함수 접두사 : {prefix}")
    lines.append(f"  구조체     : {option_type.__name__} / sizeof={ctypes.sizeof(option_type)} bytes")

    try:
        lib = _load(api_dll)
    except OSError as e:
        lines.append(f"  로드 실패   : {e}")
        return lines

    def call(name, *args):
        try:
            fn = getattr(lib, f"{prefix}{name}")
        except AttributeError:
            return None, "함수 없음"
        try:
            return fn(*args), None
        except Exception as e:  # 호출 규약·인자 불일치
            return None, f"호출 실패: {e}"

    rc, err = call("GetCustom")
    lines.append(f"  GetCustom  : {err or rc}")

    opt = sample_option(option_type)
    rc, err = call("CheckOption", ctypes.byref(opt))
    if err:
        lines.append(f"  CheckOption: {err}")
    else:
        verdict = "정렬 일치로 판단" if rc == 0 else "배치 불일치 의심 — 아래 오프셋 표 확인"
        lines.append(f"  CheckOption: {rc} ({verdict})")

    ink_color = INT(0)
    ink_white = INT(0)
    rc, err = call("CalcOption", ctypes.byref(opt), ctypes.byref(ink_color), ctypes.byref(ink_white))
    if err:
        lines.append(f"  CalcOption : {err}")
    else:
        lines.append(f"  CalcOption : {rc} (color={ink_color.value}, white={ink_white.value})")

    return lines


def make_arxp(png_path: str, out_path: str, api_dll: str = "", model: str = "pro",
              position: str = "", size: str = "") -> tuple:
    """2단계 시험 — 라이브러리를 직접 불러 PNG 에서 인쇄 데이터를 만든다.

    `PrintFile(입력경로, 옵션, RECT, 잡이름, BOOL)` 한 번으로 되는지 확인하는 것이 목적이다.
    출력 파일 경로는 옵션의 `szFileName` 에 실어 보낸다 — CLI 의 `-A` 에 해당한다.

    ⚠ **아직 미검증 경로다.** 마지막 BOOL 인자의 의미를 벤더 자료 없이 확정하지 못했다.
    장비로 바로 보내는 뜻일 가능성을 배제할 수 없으므로, **첫 실행은 장비 전원을 끄거나 USB 를
    뽑은 상태에서** 한다. 그 상태면 최악이라도 오류 코드만 돌아온다.

    반환: (rc, 설명 줄 목록)
    """
    lines = []
    exe = config.PRO_CLI_EXE if model == "pro" else config.LEGACY_CLI_EXE
    api_dll = api_dll or _pick_api(exe)
    if not api_dll:
        return None, ["API 라이브러리를 찾지 못했습니다."]

    prefix = garment_runtime.driver_file_prefix(api_dll)
    option_type = option_type_for(api_dll, model)
    opt = sample_option(option_type)
    opt.szFileName = os.path.abspath(out_path).encode("utf-8", "ignore")[:MAX_PATH - 1]
    opt.szJobName = b"direct-call test"

    lines.append(f"  라이브러리 : {garment_runtime.describe_file(api_dll)}")
    lines.append(f"  입력 PNG   : {png_path}")
    lines.append(f"  출력 대상  : {out_path}")

    try:
        lib = _load(api_dll)
    except OSError as e:
        return None, lines + [f"  로드 실패   : {e}"]

    # 배치가 틀린 채 진행하면 값이 밀린 데이터가 만들어진다. 반드시 먼저 막는다.
    try:
        rc = getattr(lib, f"{prefix}CheckOption")(ctypes.byref(opt))
    except Exception as e:
        return None, lines + [f"  CheckOption 호출 실패: {e}"]
    lines.append(f"  CheckOption: {rc}")
    if rc != 0:
        lines.append("  → 배치 불일치. 생성을 중단합니다(밀린 값으로 만들면 안 됨).")
        return rc, lines

    left, top = _parse_pos(position or getattr(config, "POSITION", "00000000"))
    width, height = _parse_pos(size or getattr(config, "SIZE", "") or "00000000")
    rect = RECT(left, top, left + width, top + height)
    lines.append(f"  RECT       : ({rect.left}, {rect.top}, {rect.right}, {rect.bottom}) 0.1mm")

    try:
        fn = getattr(lib, f"{prefix}PrintFile")
        fn.restype = ctypes.c_int32
        rc = fn(ctypes.c_wchar_p(os.path.abspath(png_path)), ctypes.byref(opt),
                rect, ctypes.c_wchar_p("direct-call test"), ctypes.c_int32(0))
    except Exception as e:
        return None, lines + [f"  PrintFile 호출 실패: {e}"]

    lines.append(f"  PrintFile  : {rc}")
    if os.path.isfile(out_path):
        lines.append(f"  생성 결과  : {os.path.getsize(out_path):,} bytes")
    else:
        lines.append("  생성 결과  : 파일 없음")
    return rc, lines


def _pick_api(exe: str) -> str:
    """이 시험에 쓸 라이브러리 — 설치본이 있으면 그것, 없으면 임베드본."""
    embedded = garment_runtime.api_dll_for(exe)
    installed = garment_runtime.installed_api_dlls(embedded)
    return installed[0] if installed else embedded


def _parse_pos(value: str) -> tuple:
    """8자리 문자열(앞4=가로, 뒤4=세로, 0.1mm)을 정수 쌍으로."""
    text = (value or "").strip() or "00000000"
    try:
        return int(text[:4]), int(text[4:8])
    except ValueError:
        return 0, 0


def self_test_report() -> str:
    """임베드본·설치본 모두를 점검한 보고서를 파일로 남기고 경로를 돌려준다."""
    now = datetime.datetime.now()
    log_dir = os.path.dirname(config.LOG_FILE) or os.path.join(config.BASE_DIR, "logs")
    diag_dir = os.path.join(log_dir, "diagnostics")
    os.makedirs(diag_dir, exist_ok=True)
    path = os.path.join(diag_dir, f"api-selftest-{now.strftime('%Y%m%d-%H%M%S')}.txt")

    L = ["=" * 70, "가먼트 API 직접 호출 점검 (1단계: 구조체 정렬)",
         f"시각   : {now.strftime('%Y-%m-%d %H:%M:%S')}",
         f"플랫폼 : {platform.system()} {platform.machine()} / Python {platform.python_version()}",
         "=" * 70, ""]

    for label, exe, model in (("pro 계열", config.PRO_CLI_EXE, "pro"),
                              ("legacy 계열", config.LEGACY_CLI_EXE, "legacy")):
        L.append(f"[{label}]")
        if not exe or not os.path.isfile(exe):
            L.append("  CLI 없음 — 건너뜀")
            L.append("")
            continue
        embedded = garment_runtime.api_dll_for(exe)
        candidates = ([embedded] if embedded else []) + garment_runtime.installed_api_dlls(embedded)
        for api_dll in candidates:
            L.extend(probe(api_dll, model))
            L.append("")

    L.append("[구조체 오프셋]")
    for label, option_type in (("pro", ProOption), ("legacy", LegacyOption)):
        L.append(f"  -- {label} ({ctypes.sizeof(option_type)} bytes) --")
        for name, offset, size in field_layout(option_type):
            L.append(f"    {offset:>5}  {size:>4}  {name}")
        L.append("")

    L.append("=" * 70)
    L.append("끝")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path
