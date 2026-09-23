
import ctypes
import datetime
import os
import platform
import time

import config
import garment_runtime

MAX_PATH = 260
JOB_NAME_LEN = 128

BYTE = ctypes.c_ubyte
BOOL = ctypes.c_int32
INT = ctypes.c_int32
UINT = ctypes.c_uint32
COLORREF = ctypes.c_uint32
LONG = ctypes.c_int32


class SIZE(ctypes.Structure):

    _fields_ = [("cx", LONG), ("cy", LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]


class ProOption(ctypes.Structure):

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


AlignedProOption = type("AlignedProOption", (ctypes.Structure,), {"_fields_": list(ProOption._fields_)})
AlignedLegacyOption = type("AlignedLegacyOption", (ctypes.Structure,), {"_fields_": list(LegacyOption._fields_)})

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

UNMAPPED_ARGS = ("-W (흰색 해석)", "-R (상대 배율)")


def sample_option(option_type: type, overrides: dict = None) -> ctypes.Structure:
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
        opt.byPrintMethod = 0
    if hasattr(opt, "byQuality"):
        opt.byQuality = 1

    for key, value in (overrides or {}).items():
        mapped = _FIELD_MAP.get(key)
        if not mapped:
            continue
        name, kind = mapped
        if not hasattr(opt, name):
            continue
        setattr(opt, name, (1 if value else 0) if kind is BOOLEAN else int(value))
    return opt


def field_layout(option_type: type) -> list:
    return [
        (name, getattr(option_type, name).offset, getattr(option_type, name).size)
        for name, _ in option_type._fields_
    ]


OPTION_BUFFER = 4096


def _as_buffer(opt: ctypes.Structure):
    buf = ctypes.create_string_buffer(OPTION_BUFFER)
    ctypes.memmove(buf, ctypes.byref(opt), ctypes.sizeof(opt))
    return buf


def _load(api_dll: str):
    folder = os.path.dirname(os.path.abspath(api_dll))
    if hasattr(os, "add_dll_directory") and os.path.isdir(folder):
        os.add_dll_directory(folder)
    loader = getattr(ctypes, "WinDLL", ctypes.CDLL)
    return loader(api_dll)


def probe(api_dll: str, model: str = "pro") -> list:
    lines = []
    prefix = garment_runtime.driver_file_prefix(api_dll)
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
        except Exception as e:
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


PRINTFILE_VARIANTS = {
    2: "프린터, 옵션*, RECT*, 이미지, 0",
    0: "이미지, 옵션*, RECT*, 잡이름, 0",
    1: "이미지, 옵션*, RECT(값), 잡이름, 0",
    3: "OpenPrinter 후 = variant 0",
    4: "이미지, 옵션*, RECT*, 잡이름, 1",
}


OPTION_JSON_FIELDS = (
    "szFileName", "uiCopies", "szJobName", "byPrintMethod", "byPlatenSize", "byInk",
    "byResolution", "bEcoMode", "byQuality", "byInkVolume", "byDoublePrint", "byHighlight",
    "byMask", "bFastMode", "bDivide", "byDivideSpan", "bPause", "byPauseSpan",
    "bMaterialBlack", "bMultiple", "bTransColor", "colorTrans", "byTolerance", "byMinWhite",
    "byChoke", "bySaturation", "byBrightness", "byContrast", "iCyanBalance", "iMagentaBalance",
    "iYellowBalance", "iBlackBalance", "bUniDirection", "byTransLayer",
)

BAND_HEIGHT = 300

TRANSPARENT_KEY_RGB = (255, 0, 255)
TRANSPARENT_KEY_COLORREF = 255 + 0 * 256 + 255 * 65536


def option_json(opt: ctypes.Structure) -> str:
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


def rgba_probe(png_path: str, printer_name: str, api_dll: str = "", model: str = "pro",
               overrides: dict = None) -> list:
    lines = _Trace()
    exe = config.PRO_CLI_EXE if model == "pro" else config.LEGACY_CLI_EXE
    api_dll = api_dll or _pick_api(exe)
    prefix = garment_runtime.driver_file_prefix(api_dll)
    option_type = option_type_for(api_dll, model)
    opt = sample_option(option_type, overrides)
    lines.append(f"  라이브러리 : {garment_runtime.describe_file(api_dll)}")
    try:
        from PIL import Image

        lib = _load(api_dll)
        opener = getattr(lib, f"{prefix}OpenPrinter")
        opener.restype = ctypes.c_int32
        process = getattr(lib, f"{prefix}ProcessImage_RGBA")
        process.restype = ctypes.c_int32
        closer = getattr(lib, f"{prefix}ClosePrinter")
        closer.restype = ctypes.c_int32
    except (ImportError, OSError, AttributeError) as e:
        lines.append(f"  준비 실패: {e}")
        lines.close()
        return list(lines)

    handle = ctypes.c_void_p()
    rc = opener(ctypes.byref(handle), ctypes.c_wchar_p(printer_name), ctypes.byref(_as_buffer(opt)))
    lines.append(f"  open: {rc}")
    if rc != 0:
        lines.close()
        return list(lines)

    with Image.open(png_path) as img:
        band = img.convert("RGBA").crop((0, 0, min(img.width, 512), min(img.height, 8)))
    w, h = band.size
    raw = band.tobytes()
    buf = ctypes.create_string_buffer(raw, len(raw))
    I = ctypes.c_int32
    lines.append(f"  시험 밴드  : {w}x{h}")

    shapes = []
    for conv in (0, 1, 2):
        shapes.append((f"w,h,buf,y=0,conv={conv}", (I(w), I(h), buf, I(0), I(conv))))
        shapes.append((f"핸들,w,h,buf,y=0,conv={conv}", (handle, I(w), I(h), buf, I(0), I(conv))))
    shapes += [
        ("w,h,buf,y=0", (I(w), I(h), buf, I(0))),
        ("w,h,buf", (I(w), I(h), buf)),
        ("buf,w,h,y=0,conv=0", (buf, I(w), I(h), I(0), I(0))),
        ("h,w,buf,y=0,conv=0 (가로세로 바꿈)", (I(h), I(w), buf, I(0), I(0))),
        ("w,h,buf,stride,y=0,conv=0", (I(w), I(h), buf, I(w * 4), I(0), I(0))),
        ("핸들,w,h,buf,stride,y=0,conv=0", (handle, I(w), I(h), buf, I(w * 4), I(0), I(0))),
        ("w,h,stride,buf,y=0,conv=0", (I(w), I(h), I(w * 4), buf, I(0), I(0))),
        ("w,h,buf,y=0,conv=0,0", (I(w), I(h), buf, I(0), I(0), I(0))),
    ]
    for label, args in shapes:
        try:
            code = process(*args)
        except Exception as e:
            lines.append(f"  {label}: 호출 실패 {e}")
            continue
        lines.append(f"  {label}: {code}")
        if code == 0:
            lines.append("  → 이 모양이 통합니다")
            break

    lines.append(f"  close: {closer(handle)}")
    lines.close()
    return list(lines)


def printer_jobs(printer_name: str) -> str:
    if not printer_name:
        return "(프린터 미지정)"
    try:
        import win32print
    except ImportError:
        return "(win32print 없음)"
    jobs = None
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            try:
                jobs = win32print.EnumJobs(handle, 0, 99, 1)
            except Exception:
                jobs = win32print.EnumJobs(handle, 0, 99, 0)
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        return f"(조회 실패: {e})"
    if not jobs:
        return "작업 없음"
    out = []
    for job in jobs[:5]:
        try:
            out.append(
                f"#{job.get('JobId')} {job.get('pDocument') or '(이름없음)'} "
                f"상태={job.get('Status')} {job.get('Size', 0):,}B"
            )
        except Exception:
            out.append(str(job)[:80])
    return f"{len(jobs)}건 : " + " | ".join(out)


def rgba_print(png_path: str, out_path: str, printer_name: str, api_dll: str = "",
               model: str = "pro", overrides: dict = None, white_convert: int = 0,
               position: str = "", size: str = "") -> tuple:
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
    opt.szFileName = b""
    opt.szJobName = os.path.basename(png_path).encode("utf-8", "ignore")[:JOB_NAME_LEN - 1]

    pos_x10, pos_y10 = _parse_pos(position or getattr(config, "POSITION", "00000000"))
    size_w10, size_h10 = _parse_pos(size or getattr(config, "SIZE", "") or "00000000")
    started = time.time()
    lines.append(f"  라이브러리 : {garment_runtime.describe_file(api_dll)}")
    lines.append(f"  경로       : RGBA (알파 보존)")
    lines.append(f"  프린터     : {printer_name}")
    jobs_before = printer_jobs(printer_name)
    lines.append(f"  큐(호출 전): {jobs_before}")
    lines.append(
        "  옵션       : "
        + ", ".join(
            f"{name}={getattr(opt, name)}"
            for name in ("uiCopies", "byPrintMethod", "byPlatenSize", "byInk", "byWInkVer",
                         "byResolution", "byQuality", "byInkVolume", "byTransLayer", "bTransColor")
            if hasattr(opt, name)
        )
    )
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

    handle = ctypes.c_void_p()
    try:
        opener = getattr(lib, f"{prefix}OpenPrinter")
        opener.restype = ctypes.c_int32
    except AttributeError:
        lines.append("  OpenPrinter 함수가 없습니다.")
        lines.close()
        return None, list(lines)

    optbuf = _as_buffer(opt)
    opener.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_wchar_p, ctypes.c_void_p]
    try:
        rc = opener(ctypes.byref(handle), ctypes.c_wchar_p(printer_name), ctypes.cast(optbuf, ctypes.c_void_p))
    except Exception as e:
        lines.append(f"  open 호출 실패: {e}")
        lines.close()
        return None, list(lines)
    lines.append(f"  open       : {rc} (핸들={handle.value}) {time.time()-started:.1f}초")
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

    jobs_after = jobs_before
    rc = 0
    try:
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

        def _shapes(width, rows, buf, y):
            return (
                ("핸들, w, h, 버퍼, y, 변환",
                 lambda: process(handle, ctypes.c_int32(width), ctypes.c_int32(rows), buf,
                                 ctypes.c_int32(y), ctypes.c_int32(white_convert))),
                ("w, h, 버퍼, y, 변환",
                 lambda: process(ctypes.c_int32(width), ctypes.c_int32(rows), buf,
                                 ctypes.c_int32(y), ctypes.c_int32(white_convert))),
                ("핸들, w, h, 버퍼, y",
                 lambda: process(handle, ctypes.c_int32(width), ctypes.c_int32(rows), buf,
                                 ctypes.c_int32(y))),
                ("w, h, 버퍼, y",
                 lambda: process(ctypes.c_int32(width), ctypes.c_int32(rows), buf,
                                 ctypes.c_int32(y))),
            )

        process.argtypes = [
            ctypes.c_void_p, SIZE, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int32, ctypes.c_int32,
        ]
        for band_top in range(0, canvas_h, BAND_HEIGHT):
            rows = min(BAND_HEIGHT, canvas_h - band_top)
            chunk = raw[band_top * stride:(band_top + rows) * stride]
            buf = ctypes.create_string_buffer(chunk, len(chunk))
            rc = process(handle, SIZE(canvas_w, rows),
                         ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
                         ctypes.c_int32(band_top), ctypes.c_int32(white_convert))
            if band_top == 0 or band_top + BAND_HEIGHT >= canvas_h:
                ink = sum(1 for v in chunk[3::4] if v)
                lines.append(
                    f"  밴드 y={band_top:<5} {rows}행 {len(chunk):,}B "
                    f"잉크픽셀 {ink:,} rc={rc}"
                )
            if rc != 0:
                lines.append(f"  픽셀 전달(y={band_top}): {rc}")
                break
        else:
            total_ink = sum(1 for v in raw[3::4] if v)
            lines.append(
                f"  픽셀 전달  : 전 밴드 완료, 잉크 나갈 픽셀 총 {total_ink:,} "
                f"({time.time()-started:.1f}초)"
            )
    except Exception as e:
        lines.append(f"  이미지 전달 실패: {e}")
        rc = None

    try:
        closer = getattr(lib, f"{prefix}ClosePrinter")
        closer.restype = ctypes.c_int32
        crc = closer(handle)
        if crc != 0:
            lines.append(f"  close(핸들): {crc}, 인자 없이 재시도")
            crc = closer()
        lines.append(f"  close      : {crc} ({time.time()-started:.1f}초)")
        jobs_after = printer_jobs(printer_name)
        lines.append(f"  큐(호출 후): {jobs_after}")
        if rc == 0 and crc != 0:
            rc = crc
    except Exception as e:
        lines.append(f"  close 실패: {e}")

    size = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
    delivered = jobs_after != jobs_before and "조회 실패" not in jobs_after
    if rc == 0 and not delivered:
        lines.append("  ⚠ 큐에 작업이 늘지 않았습니다. 장비로 나가지 않은 것으로 봅니다.")
        lines.append("  → 실패로 보고합니다. 호출자가 기존 경로로 내려가 출력은 나갑니다.")
        lines.close()
        return -9999, list(lines)
    if rc == 0:
        lines.append("DIRECT_SENT")
        lines.append(f"  전송 완료  : 닫는 순간 장비로 나갔습니다 (남은 파일 {size:,} bytes 는 껍데기)")
    else:
        lines.append(f"  생성 결과  : {size:,} bytes")
    lines.close()
    return rc, list(lines)


def _prepare_image(png_path: str, opt: ctypes.Structure, lines) -> str:
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
            if has_dpi and not has_alpha:
                lines.append(f"  이미지 보정: 불필요 (dpi={img.info.get('dpi')}, 알파={has_alpha})")
                return png_path
            prepared = img.convert("RGBA") if has_alpha else img.convert("RGB")
            if has_alpha:
                alpha = prepared.getchannel("A")
                rgb = prepared.convert("RGB")
                key = Image.new("RGB", prepared.size, TRANSPARENT_KEY_RGB)
                mask = alpha.point(lambda v: 255 if v == 0 else 0)
                rgb.paste(key, mask=mask)
                prepared = rgb
                opt.bTransColor = 1
                opt.colorTrans = TRANSPARENT_KEY_COLORREF
                opt.byTolerance = 0
                lines.append(
                    f"  투명색 지정: 완전 투명 픽셀을 RGB{TRANSPARENT_KEY_RGB} 로 칠하고 "
                    f"colorTrans={TRANSPARENT_KEY_COLORREF} 로 지정"
                )
            out = os.path.join(os.path.dirname(os.path.abspath(png_path)), "prepared.png")
            prepared.save(out, dpi=(dpi, dpi))
    except (OSError, ValueError) as e:
        lines.append(f"  이미지 보정 실패: {e} (원본 그대로 사용)")
        return png_path

    lines.append(f"  이미지 보정: dpi={dpi} 기입")
    return out


def make_arxp(png_path: str, out_path: str, api_dll: str = "", model: str = "pro",
              position: str = "", size: str = "", overrides: dict = None,
              variant: int = 0, printer_name: str = "") -> tuple:
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
        fixed, note = _autofix(check, option_type, overrides, file_name, job_name)
        if fixed is None:
            lines.append("  → 통과하는 값을 찾지 못했습니다. 생성을 중단합니다(밀린 값으로 만들면 안 됨).")
            return rc, lines
        opt = fixed
        lines.append(f"  자동 보정  : {note} (원래 값으로는 rc={rc})")
        lines.append("  → 이 보정은 임시 조치다. 같은 보정이 반복되면 설정 기본값을 고쳐야 한다.")

    left, top = _parse_pos(position or getattr(config, "POSITION", "00000000"))
    width, height = _parse_pos(size or getattr(config, "SIZE", "") or "00000000")
    dpi = int(getattr(config, "API_RECT_DPI", 1200) or 1200)
    to_dots = lambda v: int(round(v * dpi / 254.0))  # noqa: E731
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
    embedded = garment_runtime.api_dll_for(exe)
    installed = garment_runtime.installed_api_dlls(embedded)
    return installed[0] if installed else embedded


def _parse_pos(value: str) -> tuple:
    text = (value or "").strip() or "00000000"
    try:
        return int(text[:4]), int(text[4:8])
    except ValueError:
        return 0, 0


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
