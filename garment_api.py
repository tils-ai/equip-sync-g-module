"""가먼트 API 직접 호출 : 1단계: 구조체 선언과 정렬 검증.

지금 출력 경로는 `우리 코드 → 벤더 CLI(exe) → 벤더 API(dll) → 드라이버` 다. 구조체를 채우는
주체가 CLI 라서 **CLI 세대가 곧 우리 세대**이고, 현장이 드라이버를 올릴 때마다 CLI 를 새로
받아야 한다. 그 CLI 는 공개 배포물이 아니다. 2026-09-22 현장 장애의 구조적 원인이었다.

구조체를 우리가 직접 선언하면 그 고리가 끊어진다. API 라이브러리는 드라이버·벤더 편집기가
현장 PC 에 이미 깔아 두므로 세대가 저절로 맞고, 우리가 들고 다닐 필요도 없어진다.

이 모듈은 그 전환의 **1단계**다. 실제 출력은 아직 하지 않는다. 구조체 배치가 라이브러리와
맞는지만 확인한다. 배치가 틀리면 값이 한 칸씩 밀린 채 인쇄되는데, 그건 출력이 실패하는 것보다
훨씬 비싼 사고다(옷을 버린다). 그래서 점검을 먼저 통과시키고 나서 다음 단계로 간다.

필드 순서·타입의 출처는 dps-store 문서 허브의 5.x 구조체 문서다. 폭이 고정된 타입만 쓴다 -
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

    **패딩 없는 배치(`_pack_ = 1`)다.** 벤더 편집기의 FFI 선언이 packed 구조체를 쓴다.
    기본 정렬로 두면 1바이트 항목 뒤 4바이트 항목 앞에 패딩이 끼어 그 뒤가 전부 밀리고,
    라이브러리는 엉뚱한 값을 읽어 범위 초과로 거부한다(현장에서 -1111 로 나타났다).
    """

    _pack_ = 1
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
    """legacy 계열 5.x 세대 인쇄 옵션. 이 세대에는 여기에도 `byWInkVer` 가 들어갔다.

    pro 와 마찬가지로 패딩 없는 배치다.
    """

    _pack_ = 1
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


# 기본 정렬(패딩 있음) 변형 : 어느 쪽이 맞는지 현장에서 한 번에 가리기 위해 함께 둔다.
AlignedProOption = type("AlignedProOption", (ctypes.Structure,), {"_fields_": list(ProOption._fields_)})
AlignedLegacyOption = type("AlignedLegacyOption", (ctypes.Structure,), {"_fields_": list(LegacyOption._fields_)})

# 계열별 배치 후보. packed 를 먼저 둔다(벤더 편집기 선언이 packed 다).
_LAYOUTS = {
    "pro": (("packed", ProOption), ("기본정렬", AlignedProOption)),
    "legacy": (("packed", LegacyOption), ("기본정렬", AlignedLegacyOption)),
}


def option_layouts(model: str) -> tuple:
    return _LAYOUTS.get(model, _LAYOUTS["pro"])


def option_type_for(api_dll: str, model: str) -> type:
    return option_layouts(model)[0][1]


ID = "id"
BOOLEAN = "bool"

# 설정 이름 → (구조체 필드, 변환). CLI 가 XML 로 넘기던 값과 같은 것을 구조체에 싣는다.
_FIELD_MAP = {
    "copies": ("uiCopies", ID),
    "platen_size": ("byPlatenSize", ID),
    "ink": ("byInk", ID),
    "resolution": ("byResolution", ID),
    "highlight": ("byHighlight", ID),
    "mask": ("byMask", ID),
    "ink_volume": ("byInkVolume", ID),
    "double_print": ("byDoublePrint", ID),
    "tolerance": ("byTolerance", ID),
    "min_white": ("byMinWhite", ID),
    "choke": ("byChoke", ID),
    "saturation": ("bySaturation", ID),
    "brightness": ("byBrightness", ID),
    "contrast": ("byContrast", ID),
    "cyan_balance": ("iCyanBalance", ID),
    "magenta_balance": ("iMagentaBalance", ID),
    "yellow_balance": ("iYellowBalance", ID),
    "black_balance": ("iBlackBalance", ID),
    "color_trans": ("colorTrans", ID),
    "machine_mode": ("byMachineMode", ID),
    "eco_mode": ("bEcoMode", BOOLEAN),
    "material_black": ("bMaterialBlack", BOOLEAN),
    "multiple": ("bMultiple", BOOLEAN),
    "trans_color": ("bTransColor", BOOLEAN),
    "pause": ("bPause", BOOLEAN),
    "uni_print": ("bUniDirection", BOOLEAN),
}

# 아직 구조체 대응을 확정하지 못한 CLI 인자. 쓰이면 로그로 알린다.
UNMAPPED_ARGS = ("-W (흰색 해석)", "-R (상대 배율)")


def sample_option(option_type: type, overrides: dict = None) -> ctypes.Structure:
    """옵션 값 구성. 설정을 기본으로 깔고 호출자가 준 값으로 덮는다."""
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
    opt.bEcoMode = 1 if getattr(config, "ECO_MODE", False) else 0
    opt.bMaterialBlack = 1 if getattr(config, "MATERIAL_BLACK", False) else 0
    opt.bMultiple = 1 if getattr(config, "MULTIPLE", False) else 0
    opt.bTransColor = 1 if getattr(config, "TRANS_COLOR", False) else 0
    opt.bPause = 1 if getattr(config, "PAUSE", False) else 0
    opt.bUniDirection = 1 if getattr(config, "UNI_PRINT", False) else 0
    opt.colorTrans = int(getattr(config, "COLOR_TRANS", 0))
    if hasattr(opt, "byMachineMode"):
        opt.byMachineMode = int(getattr(config, "MACHINE_MODE", 0))
    opt.byTransLayer = int(getattr(config, "API_TRANS_LAYER", 1))
    if hasattr(opt, "byPrintMethod"):
        opt.byPrintMethod = 0  # 0 = 일반 가먼트 출력(DTG)
    if hasattr(opt, "byQuality"):
        opt.byQuality = 1  # 1 = Standard

    for key, value in (overrides or {}).items():
        mapped = _FIELD_MAP.get(key)
        if not mapped:
            continue
        name, kind = mapped
        if not hasattr(opt, name):
            continue  # 계열에 없는 필드(예: legacy 전용) 는 건너뛴다
        setattr(opt, name, (1 if value else 0) if kind is BOOLEAN else int(value))
    return opt


def field_layout(option_type: type) -> list:
    """(필드명, 오프셋, 크기) 목록 : 보고서에서 표와 대조하기 위한 것."""
    return [
        (name, getattr(option_type, name).offset, getattr(option_type, name).size)
        for name, _ in option_type._fields_
    ]


# 라이브러리가 우리 구조체보다 뒤까지 읽어도 프로세스가 죽지 않도록 넉넉히 잡는 버퍼 크기.
# 배치 후보(packed 739B / 기본정렬 756B)를 번갈아 시험하는 구조라, 작은 쪽을 넘겼을 때
# 라이브러리가 큰 쪽 기준으로 읽으면 할당 범위를 넘어 접근 위반이 난다. 그러면 GUI 까지
# 통째로 강제 종료된다(현장에서 실제로 그랬다). 항상 이 크기로 잡아 넘긴다.
OPTION_BUFFER = 4096


def _as_buffer(opt: ctypes.Structure):
    """옵션을 여유 있는 버퍼에 담아 돌려준다. 호출에는 이 버퍼의 주소를 넘긴다."""
    buf = ctypes.create_string_buffer(OPTION_BUFFER)
    ctypes.memmove(buf, ctypes.byref(opt), ctypes.sizeof(opt))
    return buf


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

    opt = None
    for label, layout in option_layouts(model):
        candidate = sample_option(layout)
        rc, err = call("CheckOption", ctypes.byref(_as_buffer(candidate)))
        if err:
            lines.append(f"  CheckOption({label}): {err}")
            continue
        verdict = "배치 일치" if rc == 0 else "불일치"
        lines.append(f"  CheckOption({label}, {ctypes.sizeof(layout)}B): {rc} ({verdict})")
        if rc == 0 and opt is None:
            opt = candidate
    opt = opt if opt is not None else sample_option(option_type)

    ink_color = INT(0)
    ink_white = INT(0)
    rc, err = call("CalcOption", ctypes.byref(_as_buffer(opt)),
                   ctypes.byref(ink_color), ctypes.byref(ink_white))
    if err:
        lines.append(f"  CalcOption : {err}")
    else:
        lines.append(f"  CalcOption : {rc} (color={ink_color.value}, white={ink_white.value})")

    return lines


SEND_LABEL = "PrintData"

SEND_VARIANTS = {
    0: "프린터, 데이터, 잡이름",
    1: "데이터, 프린터, 잡이름",
}


def send(data_path: str, printer_name: str, api_dll: str = "", model: str = "pro",
         job_name: str = "", variant: int = 0) -> tuple:
    """3단계 : 만들어 둔 인쇄 데이터를 장비로 보낸다. CLI 의 `send -A … -P …` 에 해당한다.

    문자열 세 개만 넘기는 함수라 구조체 배치와 무관하다. 즉 세대가 달라도 이 호출만은
    안전하다. 인자 순서(프린터, 데이터, 잡 이름)는 벤더 편집기의 호출 형태를 따랐다.
    """
    lines = _Trace()
    exe = config.PRO_CLI_EXE if model == "pro" else config.LEGACY_CLI_EXE
    api_dll = api_dll or _pick_api(exe)
    if not api_dll:
        lines.append("API 라이브러리를 찾지 못했습니다.")
        lines.close()
        return None, list(lines)
    if not os.path.isfile(data_path):
        lines.append(f"인쇄 데이터가 없습니다: {data_path}")
        lines.close()
        return None, list(lines)

    prefix = garment_runtime.driver_file_prefix(api_dll)
    lines.append(f"  전송 대상  : {printer_name}")
    lines.append(f"  데이터     : {data_path} ({os.path.getsize(data_path):,} bytes)")
    try:
        lib = _load(api_dll)
    except OSError as e:
        lines.append(f"  로드 실패   : {e}")
        lines.close()
        return None, list(lines)

    lines.append(f"  전송 모양  : variant {variant} : {SEND_VARIANTS.get(variant, '?')}")
    data = ctypes.c_wchar_p(os.path.abspath(data_path))
    target = ctypes.c_wchar_p(printer_name)
    job = ctypes.c_wchar_p(job_name or os.path.basename(data_path))
    try:
        fn = getattr(lib, f"{prefix}PrintData")
        fn.restype = ctypes.c_int32
        rc = fn(data, target, job) if variant == 1 else fn(target, data, job)
    except Exception as e:
        lines.append(f"  PrintData 호출 실패: {e}")
        lines.close()
        return None, list(lines)
    lines.append(f"  PrintData  : {rc}")
    lines.close()
    return rc, list(lines)


class _Trace(list):
    """줄을 모으면서 동시에 파일로 흘려 쓴다.

    벤더 라이브러리가 프로세스를 죽이면 버퍼에 남은 표준 출력은 사라진다. 어디까지 갔는지
    남기려면 한 줄마다 파일에 밀어 넣어야 한다. 이 파일이 직접 호출 경로의 진단서다.
    """

    def __init__(self):
        super().__init__()
        self.path = ""
        try:
            log_dir = os.path.dirname(config.LOG_FILE) or os.path.join(config.BASE_DIR, "logs")
            diag = os.path.join(log_dir, "diagnostics")
            os.makedirs(diag, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            self.path = os.path.join(diag, f"api-direct-{stamp}.txt")
            self._fh = open(self.path, "w", encoding="utf-8")
            self._write(f"가먼트 API 직접 호출 기록 : {stamp}")
            self._write(f"실행 빌드: {getattr(config, 'APP_VERSION', '?')}")
        except OSError:
            self._fh = None

    def _write(self, line: str) -> None:
        if self._fh:
            try:
                self._fh.write(line + "\n")
                self._fh.flush()
                os.fsync(self._fh.fileno())
            except OSError:
                pass

    def append(self, line):
        super().append(line)
        self._write(str(line))

    def close(self):
        if self._fh:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


# PrintFile 호출 모양 후보. 벤더 자료 없이 확정하지 못해, 자식 프로세스에서 하나씩 시험한다.
# 모양이 틀리면 스택이 깨져 프로세스가 즉사한다(0xC0000409). 그래서 반드시 자식에서만 돈다.
# 2026-09-22 현장에서 **모양 2 가 통했다**(PrintFile=0, 5MB 생성). 첫 인자는 이미지가 아니라
# 프린터명이고 이미지는 네 번째다. 기본 순서를 그 모양부터로 바꾼다.
PRINTFILE_VARIANTS = {
    2: "프린터, 옵션*, RECT*, 이미지, 0",
    0: "이미지, 옵션*, RECT*, 잡이름, 0",
    1: "이미지, 옵션*, RECT(값), 잡이름, 0",
    3: "OpenPrinter 후 = variant 0",
    4: "이미지, 옵션*, RECT*, 잡이름, 1",
}


# 벤더 편집기가 쓰는 경로. PrintFile 은 파일을 라이브러리가 직접 읽어 알파를 버리지만,
# 이 경로는 우리가 픽셀을 알파째 밀어 넣는다. 투명 배경을 살리려면 이쪽이어야 한다.
#   open(프린터, 옵션JSON) -> processImageRGBA(w, h, RGBA, y, 흰색변환) -> close()
# 옵션을 JSON 으로 넘기므로 구조체 배치(packed) 문제도 함께 비껴간다.
OPTION_JSON_FIELDS = (
    "szFileName", "uiCopies", "szJobName", "byPrintMethod", "byPlatenSize", "byInk",
    "byResolution", "bEcoMode", "byQuality", "byInkVolume", "byDoublePrint", "byHighlight",
    "byMask", "bFastMode", "bDivide", "byDivideSpan", "bPause", "byPauseSpan",
    "bMaterialBlack", "bMultiple", "bTransColor", "colorTrans", "byTolerance", "byMinWhite",
    "byChoke", "bySaturation", "byBrightness", "byContrast", "iCyanBalance", "iMagentaBalance",
    "iYellowBalance", "iBlackBalance", "bUniDirection", "byTransLayer",
)

BAND_HEIGHT = 300  # 편집기와 같은 밴드 높이


def option_json(opt: ctypes.Structure) -> str:
    """구조체 값을 편집기가 쓰는 JSON 형태로 옮긴다."""
    import json

    data = {}
    for name in OPTION_JSON_FIELDS:
        if not hasattr(opt, name):
            continue
        value = getattr(opt, name)
        data[name] = value.decode("utf-8", "replace") if isinstance(value, bytes) else int(value)
    data["szTransFile"] = ""
    data["uiReserved1"] = 0
    data["uiReserved2"] = 0
    data["uiReserved3"] = 0
    data["uiReserved4"] = 0
    return json.dumps(data)


def rgba_print(png_path: str, out_path: str, printer_name: str, api_dll: str = "",
               model: str = "pro", overrides: dict = None, white_convert: int = 0,
               position: str = "", size: str = "") -> tuple:
    """알파를 살려 출력한다. 우리가 픽셀을 직접 넘기는 경로."""
    lines = _Trace()
    exe = config.PRO_CLI_EXE if model == "pro" else config.LEGACY_CLI_EXE
    api_dll = api_dll or _pick_api(exe)
    if not api_dll:
        lines.append("API 라이브러리를 찾지 못했습니다.")
        lines.close()
        return None, list(lines)
    prefix = garment_runtime.driver_file_prefix(api_dll)
    option_type = option_type_for(api_dll, model)
    opt = sample_option(option_type, overrides)
    opt.szFileName = os.path.abspath(out_path).encode("utf-8", "ignore")[:MAX_PATH - 1]
    opt.szJobName = b"direct-call"

    pos_x10, pos_y10 = _parse_pos(position or getattr(config, "POSITION", "00000000"))
    size_w10, size_h10 = _parse_pos(size or getattr(config, "SIZE", "") or "00000000")
    lines.append(f"  라이브러리 : {garment_runtime.describe_file(api_dll)}")
    lines.append(f"  경로       : RGBA (알파 보존)")
    try:
        from PIL import Image
    except ImportError:
        lines.append("  PIL 이 없어 RGBA 경로를 쓸 수 없습니다.")
        lines.close()
        return None, list(lines)
    try:
        lib = _load(api_dll)
    except OSError as e:
        lines.append(f"  로드 실패   : {e}")
        lines.close()
        return None, list(lines)

    # 이 계열에는 JSON 입구(OpenPrinterJson)가 없다. 5.0.0.19 에도 없었다. 구조체를 받는
    # OpenPrinter 를 쓴다. 인자 순서는 확정되지 않아 후보를 차례로 시도한다 : 틀리면 오류
    # 코드가 돌아오거나 프로세스가 죽는데, 이 함수는 자식에서만 돌므로 앱은 살아 있는다.
    handle = ctypes.c_void_p()
    try:
        opener = getattr(lib, f"{prefix}OpenPrinter")
        opener.restype = ctypes.c_int32
    except AttributeError:
        lines.append("  OpenPrinter 함수가 없습니다.")
        lines.close()
        return None, list(lines)

    optbuf = _as_buffer(opt)
    shapes = (
        ("핸들*, 프린터, 옵션*", lambda: opener(ctypes.byref(handle),
                                            ctypes.c_wchar_p(printer_name),
                                            ctypes.byref(optbuf))),
        ("프린터, 옵션*, 핸들*", lambda: opener(ctypes.c_wchar_p(printer_name),
                                            ctypes.byref(optbuf),
                                            ctypes.byref(handle))),
        ("핸들*, 프린터", lambda: opener(ctypes.byref(handle),
                                     ctypes.c_wchar_p(printer_name))),
    )
    rc = None
    for label, call in shapes:
        try:
            rc = call()
        except Exception as e:
            lines.append(f"  open({label}) 호출 실패: {e}")
            continue
        lines.append(f"  open({label}): {rc}")
        if rc == 0:
            break
    if rc != 0:
        lines.append("  → 프린터를 열지 못했습니다.")
        lines.close()
        return rc, list(lines)
    if rc < 0:
        lines.close()
        return rc, list(lines)

    try:
        process = getattr(lib, f"{prefix}ProcessImage_RGBA")
    except AttributeError:
        try:
            process = getattr(lib, f"{prefix}ProcessImageRGBA")
        except AttributeError:
            lines.append("  ProcessImage_RGBA 함수가 없습니다.")
            lines.close()
            return None, list(lines)
    process.restype = ctypes.c_int32

    rc = 0
    try:
        # 이 경로에는 RECT 가 없다. 크기와 위치는 **픽셀 자체**가 정한다. 그래서 장비 좌표계
        # 해상도(600dpi)로 키운 뒤, 플래튼 폭만큼의 캔버스에 지정 위치로 붙여 넘긴다.
        # 원본 300dpi 를 그대로 넣으면 좌표계가 절반이라 또 반으로 찍힌다.
        dots_dpi = int(getattr(config, "API_RECT_DPI", 600) or 600)
        to_dots = lambda v: int(round(v * dots_dpi / 254.0))  # noqa: E731
        plate_w10, plate_h10 = getattr(config, "PLATEN_DIMS", {}).get(
            int(opt.byPlatenSize), (3556, 4064)
        )
        target_w, target_h = to_dots(size_w10), to_dots(size_h10)
        left, top0 = to_dots(pos_x10), to_dots(pos_y10)
        canvas_w, canvas_h = to_dots(plate_w10), to_dots(plate_h10)

        with Image.open(png_path) as img:
            art = img.convert("RGBA")
        if (target_w, target_h) != art.size and target_w > 0 and target_h > 0:
            art = art.resize((target_w, target_h), Image.LANCZOS)
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        canvas.paste(art, (left, top0))
        lines.append(
            f"  이미지     : 원본 -> {target_w}x{target_h} 도트, "
            f"플래튼 캔버스 {canvas_w}x{canvas_h} @{dots_dpi}dpi, 위치 ({left}, {top0})"
        )

        raw = canvas.tobytes()
        stride = canvas_w * 4
        lines.append(f"  밴드       : {BAND_HEIGHT}행씩 {-(-canvas_h // BAND_HEIGHT)}회")
        for band_top in range(0, canvas_h, BAND_HEIGHT):
            rows = min(BAND_HEIGHT, canvas_h - band_top)
            chunk = raw[band_top * stride:(band_top + rows) * stride]
            buf = ctypes.create_string_buffer(chunk, len(chunk))
            rc = process(ctypes.c_int32(canvas_w), ctypes.c_int32(rows), buf,
                         ctypes.c_int32(band_top), ctypes.c_int32(white_convert))
            if rc != 0:
                lines.append(f"  processImageRGBA(y={band_top}): {rc}")
                break
    except Exception as e:
        lines.append(f"  이미지 전달 실패: {e}")
        rc = None

    try:
        closer = getattr(lib, f"{prefix}ClosePrinter")
        closer.restype = ctypes.c_int32
        crc = closer()
        lines.append(f"  close      : {crc}")
        if rc == 0 and crc != 0:
            rc = crc
    except Exception as e:
        lines.append(f"  close 실패: {e}")

    if os.path.isfile(out_path):
        lines.append(f"  생성 결과  : {os.path.getsize(out_path):,} bytes")
    elif rc == 0:
        # 이 경로는 프린터를 열어 픽셀을 밀어 넣는다. 파일이 없다는 것은 장비로 바로 나갔다는
        # 뜻이다. 뒤이어 전송까지 하면 같은 옷에 두 번 찍힌다. 호출자에게 알린다.
        lines.append("DIRECT_SENT")
        lines.append("  생성 결과  : 파일 없음 : 장비로 직접 나갔습니다. 별도 전송은 건너뜁니다.")
    else:
        lines.append("  생성 결과  : 파일 없음")
    lines.close()
    return rc, list(lines)


def _prepare_image(png_path: str, opt: ctypes.Structure, lines) -> str:
    """라이브러리에 넘기기 전 이미지를 다듬는다. 원본은 건드리지 않는다.

    **알파는 어떤 경우에도 건드리지 않는다.** 한때 컬러 전용일 때 흰색으로 눕히는 길을 뒀는데
    잘못된 발상이었다. 같은 디자인이 유색 옷으로 가면 그 알파 영역에 흰 밑판이 깔려 사각형이
    통째로 찍힌다. 옷 색에 따라 디자인이 다르게 취급되면 안 된다. 알파는 알파다.

    DPI 는 없을 때만 박는다. 크기는 RECT 가 정하므로 지금은 영향이 없지만, 값이 비어 있는
    것보다는 명시된 편이 낫다. 픽셀은 바뀌지 않는다.
    """
    try:
        from PIL import Image
    except ImportError:
        lines.append("  이미지 보정: PIL 없음, 원본 그대로 사용")
        return png_path

    dpi = int(getattr(config, "RENDER_DPI", 300) or 300)
    try:
        with Image.open(png_path) as img:
            has_dpi = bool(img.info.get("dpi"))
            has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
            flatten = False  # 알파는 어떤 경우에도 눕히지 않는다
            if has_dpi and not flatten:
                lines.append(f"  이미지 보정: 불필요 (dpi={img.info.get('dpi')}, 알파={has_alpha})")
                return png_path
            prepared = img.convert("RGBA") if has_alpha else img.convert("RGB")
            if flatten:
                canvas = Image.new("RGB", prepared.size, (255, 255, 255))
                canvas.paste(prepared, mask=prepared.split()[-1])
                prepared = canvas
            out = os.path.join(os.path.dirname(os.path.abspath(png_path)), "prepared.png")
            prepared.save(out, dpi=(dpi, dpi))
    except (OSError, ValueError) as e:
        lines.append(f"  이미지 보정 실패: {e} (원본 그대로 사용)")
        return png_path

    lines.append(
        f"  이미지 보정: dpi={dpi} 기입 (알파 보존)"
        + (", 설정에 따라 알파를 흰색으로 눕힘" if flatten else "")
    )
    return out


def make_arxp(png_path: str, out_path: str, api_dll: str = "", model: str = "pro",
              position: str = "", size: str = "", overrides: dict = None,
              variant: int = 0, printer_name: str = "") -> tuple:
    """2단계 시험 : 라이브러리를 직접 불러 PNG 에서 인쇄 데이터를 만든다.

    `PrintFile(입력경로, 옵션, RECT, 잡이름, BOOL)` 한 번으로 되는지 확인하는 것이 목적이다.
    출력 파일 경로는 옵션의 `szFileName` 에 실어 보낸다 : CLI 의 `-A` 에 해당한다.

    ⚠ **아직 미검증 경로다.** 마지막 BOOL 인자의 의미를 벤더 자료 없이 확정하지 못했다.
    장비로 바로 보내는 뜻일 가능성을 배제할 수 없으므로, **첫 실행은 장비 전원을 끄거나 USB 를
    뽑은 상태에서** 한다. 그 상태면 최악이라도 오류 코드만 돌아온다.

    반환: (rc, 설명 줄 목록)
    """
    lines = _Trace()
    exe = config.PRO_CLI_EXE if model == "pro" else config.LEGACY_CLI_EXE
    api_dll = api_dll or _pick_api(exe)
    if not api_dll:
        lines.append("API 라이브러리를 찾지 못했습니다.")
        lines.close()
        return None, list(lines)

    prefix = garment_runtime.driver_file_prefix(api_dll)
    file_name = os.path.abspath(out_path).encode("utf-8", "ignore")[:MAX_PATH - 1]
    job_name = b"direct-call test"

    lines.append(f"  라이브러리 : {garment_runtime.describe_file(api_dll)}")
    lines.append(f"  입력 PNG   : {png_path}")
    lines.append(f"  출력 대상  : {out_path}")

    try:
        lib = _load(api_dll)
    except OSError as e:
        return None, lines + [f"  로드 실패   : {e}"]

    # 배치가 틀린 채 진행하면 값이 밀린 데이터가 만들어진다. 반드시 먼저 막는다.
    # 배치 후보(packed / 기본정렬)를 차례로 검사해 통과하는 쪽을 쓴다.
    try:
        check = getattr(lib, f"{prefix}CheckOption")
        check.restype = ctypes.c_int32
    except AttributeError as e:
        return None, lines + [f"  CheckOption 없음: {e}"]

    opt = None
    rc = None
    for label, option_type in option_layouts(model):
        candidate = sample_option(option_type, overrides)
        candidate.szFileName = file_name
        candidate.szJobName = job_name
        buf = _as_buffer(candidate)
        try:
            code = check(ctypes.byref(buf))
        except Exception as e:
            return None, lines + [f"  CheckOption 호출 실패({label}): {e}"]
        lines.append(f"  CheckOption({label}, {ctypes.sizeof(option_type)}B): {code}")
        if code == 0:
            opt, rc = candidate, 0
            lines.append(f"  → 배치 확정: {label}")
            break
        if opt is None:
            opt, rc, option_type_used = candidate, code, option_type
    if rc != 0:
        option_type = option_type_used
        # 어느 항목이 걸렸는지 라이브러리에 직접 물어 통과값을 찾는다. 세대가 바뀌면 항목의
        # 유효 범위·의미도 같이 바뀌는데(5.x 는 항목이 넷 늘었다), 그때마다 현장을 한 번 더
        # 왕복시키는 대신 여기서 맞춘다. 무엇을 바꿨는지는 반드시 남긴다.
        fixed, note = _autofix(check, option_type, overrides, file_name, job_name)
        if fixed is None:
            lines.append("  → 통과하는 값을 찾지 못했습니다. 생성을 중단합니다(밀린 값으로 만들면 안 됨).")
            return rc, lines
        opt = fixed
        lines.append(f"  자동 보정  : {note} (원래 값으로는 rc={rc})")
        lines.append("  → 이 보정은 임시 조치다. 같은 보정이 반복되면 설정 기본값을 고쳐야 한다.")

    left, top = _parse_pos(position or getattr(config, "POSITION", "00000000"))
    width, height = _parse_pos(size or getattr(config, "SIZE", "") or "00000000")
    # RECT 는 0.1mm 가 아니라 **장비 도트** 단위다. CLI 의 -S/-L 은 0.1mm 였으므로 환산한다.
    # 그대로 넘겼더니 현장에서 355.6mm 짜리가 75mm(21%)로 찍혔다 : 3556 을 도트로 읽은 값이다.
    dpi = int(getattr(config, "API_RECT_DPI", 1200) or 1200)
    to_dots = lambda v: int(round(v * dpi / 254.0))  # noqa: E731 (254 = 1 inch in 0.1mm)
    rect = RECT(to_dots(left), to_dots(top), to_dots(left + width), to_dots(top + height))
    lines.append(
        f"  배치       : ({left}, {top}) {width}x{height} (0.1mm)"
        f" -> RECT ({rect.left}, {rect.top}, {rect.right}, {rect.bottom}) @{dpi}dpi"
    )

    lines.append(f"  투명 처리  : byTransLayer={opt.byTransLayer}")
    png_path = _prepare_image(png_path, opt, lines)
    lines.append(f"  호출 모양  : variant {variant} : {PRINTFILE_VARIANTS.get(variant, '?')}")
    try:
        fn = getattr(lib, f"{prefix}PrintFile")
        fn.restype = ctypes.c_int32
        image = ctypes.c_wchar_p(os.path.abspath(png_path))
        job = ctypes.c_wchar_p("direct-call")
        buf = _as_buffer(opt)

        if variant == 3:
            # 프린터를 먼저 연 뒤 호출한다. 벤더 편집기도 출력 전에 항상 연다.
            handle = ctypes.c_void_p()
            try:
                opener = getattr(lib, f"{prefix}OpenPrinter")
                opener.restype = ctypes.c_int32
                orc = opener(ctypes.byref(handle), ctypes.c_wchar_p(printer_name or ""))
                lines.append(f"  OpenPrinter: {orc}")
            except AttributeError:
                lines.append("  OpenPrinter: 함수 없음")

        if variant == 1:
            rc = fn(image, ctypes.byref(buf), rect, job, ctypes.c_int32(0))
        elif variant == 2:
            rc = fn(ctypes.c_wchar_p(printer_name or ""), ctypes.byref(buf),
                    ctypes.byref(rect), image, ctypes.c_int32(0))
        elif variant == 4:
            rc = fn(image, ctypes.byref(buf), ctypes.byref(rect), job, ctypes.c_int32(1))
        else:
            rc = fn(image, ctypes.byref(buf), ctypes.byref(rect), job, ctypes.c_int32(0))
    except Exception as e:
        lines.append(f"  PrintFile 호출 실패: {e}")
        lines.close()
        return None, list(lines)

    lines.append(f"  PrintFile  : {rc}")
    if os.path.isfile(out_path):
        lines.append(f"  생성 결과  : {os.path.getsize(out_path):,} bytes")
    else:
        lines.append("  생성 결과  : 파일 없음")
    lines.close()
    return rc, list(lines)


def _autofix(check, option_type: type, overrides: dict, file_name: bytes, job_name: bytes):
    """CheckOption 을 통과하는 값을 한 항목씩 바꿔 가며 찾는다.

    반환: (옵션, 무엇을 바꿨는지) : 못 찾으면 (None, "").
    """
    for name, values in _PROBE_CANDIDATES:
        if not hasattr(option_type, name):
            continue
        for value in values:
            candidate = sample_option(option_type, overrides)
            candidate.szFileName = file_name
            candidate.szJobName = job_name
            original = getattr(candidate, name)
            if original == value:
                continue
            setattr(candidate, name, value)
            try:
                if check(ctypes.byref(_as_buffer(candidate))) == 0:
                    return candidate, f"{name} {original} → {value}"
            except Exception:
                return None, ""
    return None, ""


def _pick_api(exe: str) -> str:
    """이 시험에 쓸 라이브러리 : 설치본이 있으면 그것, 없으면 임베드본."""
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


# 후보값 : CheckOption 이 거부할 때 한 항목씩 바꿔 가며 통과 조합을 찾는다.
_PROBE_CANDIDATES = (
    ("byDoublePrint", (0, 1, 2, 3)),
    ("byQuality", (0, 1, 2, 3, 4)),
    ("byWInkVer", (0, 1)),
    ("byPrintMethod", (0, 1, 2)),
    ("byInkVolume", (1, 5, 10)),
    ("byResolution", (0, 1, 2)),
    ("byHighlight", (1, 5, 9)),
    ("byMask", (1, 3, 5)),
    ("byMinWhite", (1, 3, 6)),
    ("byInk", (0, 1, 2)),
    ("byPlatenSize", (0, 2, 3)),
    ("uiCopies", (1,)),
)


def probe_option(api_dll: str = "", model: str = "pro") -> list:
    """CheckOption 이 거부할 때, 어느 항목 때문인지 한 항목씩 바꿔 가며 찾는다.

    코드 번호만 보고 추측하면 왕복이 길어진다. 라이브러리에 직접 물어보는 편이 빠르다.
    호출은 전부 메모리 안에서 끝나므로 장비·옷에 영향이 없다.
    """
    lines = []
    exe = config.PRO_CLI_EXE if model == "pro" else config.LEGACY_CLI_EXE
    api_dll = api_dll or _pick_api(exe)
    if not api_dll:
        return ["API 라이브러리를 찾지 못했습니다."]
    prefix = garment_runtime.driver_file_prefix(api_dll)
    option_type = option_type_for(api_dll, model)
    lines.append(f"  라이브러리 : {garment_runtime.describe_file(api_dll)}")

    try:
        lib = _load(api_dll)
        check = getattr(lib, f"{prefix}CheckOption")
        check.restype = ctypes.c_int32
    except (OSError, AttributeError) as e:
        return lines + [f"  준비 실패   : {e}"]

    def rc_for(changes: dict) -> int:
        opt = sample_option(option_type)
        for key, val in changes.items():
            if hasattr(opt, key):
                setattr(opt, key, val)
        try:
            return check(ctypes.byref(_as_buffer(opt)))
        except Exception:
            return None

    base = rc_for({})
    lines.append(f"  기준 설정  : CheckOption={base}")
    if base == 0:
        lines.append("  → 현재 설정 그대로 통과합니다.")
        return lines

    lines.append("  -- 한 항목씩 바꿔 보기 (통과=0) --")
    passing = []
    for name, values in _PROBE_CANDIDATES:
        if not hasattr(option_type, name):
            continue
        results = []
        for value in values:
            rc = rc_for({name: value})
            results.append(f"{value}→{rc}")
            if rc == 0:
                passing.append((name, value))
        lines.append(f"    {name:<16} {', '.join(results)}")

    if passing:
        lines.append("  -- 통과시키는 값 --")
        for name, value in passing:
            lines.append(f"    {name} = {value}")
        return lines

    lines.append("  -- 한 항목으로는 안 됨. 5.x 신설 항목 조합 탐색 --")
    found = None
    for method in (0, 1, 2):
        for wink in (0, 1):
            for quality in (0, 1, 2, 3, 4):
                for double in (0, 1):
                    rc = rc_for({"byPrintMethod": method, "byWInkVer": wink,
                                 "byQuality": quality, "byDoublePrint": double})
                    if rc == 0:
                        found = (method, wink, quality, double)
                        break
                if found:
                    break
            if found:
                break
        if found:
            break
    if found:
        lines.append(
            f"    통과: byPrintMethod={found[0]}, byWInkVer={found[1]}, "
            f"byQuality={found[2]}, byDoublePrint={found[3]}"
        )
    else:
        lines.append("    통과 조합 없음 : 구조체 배치를 다시 봐야 합니다.")
    return lines


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
            L.append("  CLI 없음 : 건너뜀")
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
