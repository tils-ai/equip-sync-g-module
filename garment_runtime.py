"""가먼트 API 라이브러리 선택 · 실행 폴더 구성 · 버전 계측.

임베드한 벤더 API 라이브러리는 특정 드라이버 세대에 맞춰 빌드돼 있다. 이 라이브러리는
얇은 껍데기라서, 실제 인쇄 데이터 생성은 **드라이버가 스풀 폴더에 깔아 둔 처리 모듈**이
한다. 그래서 현장 PC 가 드라이버를 올리면 임베드본이 그 모듈을 못 찾아 -1401
(드라이버 파일 없음)로 떨어진다. 우리가 임베드 버전을 따라 올리면 이번엔 드라이버를
안 올린 현장이 깨진다. 양쪽을 고정하면 반드시 한쪽이 진다.

해법은 **그 PC 에 설치된 같은 이름의 라이브러리를 쓰는 것**이다. 드라이버 패키지가
자기 세대에 맞는 라이브러리를 함께 깔아 두므로, 그걸 쓰면 세대가 저절로 맞는다.
임베드본은 설치본이 없는 PC 를 위한 폴백으로만 남는다.

선택한 라이브러리는 CLI exe 와 같은 폴더에 둬야 한다. Windows DLL 탐색은 exe 폴더가
최우선이라, cwd 나 PATH 를 건드리는 것보다 확실하다. 그래서 실행 폴더를 따로 만든다.

**벤더 원본 파일명을 코드에 박지 않는다.** 필요한 이름은 임베드된 파일 자신에게서 읽는다
(라이브러리 파일명은 복원된 파일명, 어느 exe 가 어느 라이브러리를 부르는지는 exe 안의
문자열, 제조사명은 버전 리소스). 레포가 공개라서 지켜야 하는 제약이고, 덕분에 벤더가
이름을 바꿔도 코드는 그대로다.
"""

import logging
import os
import re
import shutil
import struct

import config

logger = logging.getLogger(__name__)

# 설치본 탐색은 레지스트리·파일 walk 를 타므로 프로세스 생애 1회만 하고 재사용한다.
_installed_cache: dict[str, list[str]] = {}


# ------------------------------------------------------------------------------
# PE 버전 리소스 읽기 : 현장 조합(임베드/설치본/드라이버)을 버전으로 대조하기 위한 계측.
# ------------------------------------------------------------------------------

def file_version(path: str) -> str:
    """PE 파일의 FileVersion("4.0.0.12" 형식). 못 읽으면 빈 문자열.

    VS_FIXEDFILEINFO 시그니처(0xFEEF04BD)를 찾아 그 뒤 버전 워드를 읽는다. 리소스
    디렉터리를 정식으로 파싱하지 않는 대신 의존성이 없다(win32api 없이 동작).
    버전 리소스는 보통 파일 끝쪽 .rsrc 에 있으므로 꼬리부터 본다 : 드라이버 모듈이
    수십 MB 인 경우가 있어 통째로 읽지 않는다.
    """
    data = _read_version_region(path)
    idx = data.find(b"\xbd\x04\xef\xfe")
    if idx < 0 or idx + 24 > len(data):
        return ""
    try:
        ms_minor, ms_major, ls_build, ls_revision = struct.unpack_from("<HHHH", data, idx + 8)
    except struct.error:
        return ""
    return f"{ms_major}.{ms_minor}.{ls_revision}.{ls_build}"


_TAIL_BYTES = 4 << 20       # 꼬리 우선 탐색 크기
_WHOLE_FILE_LIMIT = 64 << 20  # 이보다 큰 파일은 통째로 읽지 않는다


def _read_version_region(path: str) -> bytes:
    """버전 리소스가 있을 만한 구간을 읽는다 (꼬리 우선, 없으면 전체)."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > _TAIL_BYTES:
                f.seek(size - _TAIL_BYTES)
                tail = f.read(_TAIL_BYTES)
                if b"\xbd\x04\xef\xfe" in tail or size > _WHOLE_FILE_LIMIT:
                    return tail
                f.seek(0)
            return f.read()
    except OSError:
        return b""


def version_string(path: str, key: str) -> str:
    """PE 버전 리소스의 StringFileInfo 항목(CompanyName 등). 못 읽으면 빈 문자열.

    UTF-16 키 문자열을 찾고 그 뒤 첫 UTF-16 문자열을 값으로 읽는다.
    """
    data = _read_version_region(path)
    needle = key.encode("utf-16-le") + b"\x00\x00"
    idx = data.find(needle)
    if idx < 0:
        return ""
    cursor = idx + len(needle)
    # 값은 4바이트 정렬 뒤에 온다. 정렬 패딩(0x00)을 건너뛴 다음 UTF-16 런을 읽는다.
    while cursor + 1 < len(data) and data[cursor:cursor + 2] == b"\x00\x00":
        cursor += 2
    match = re.match(rb"(?:[\x20-\x7e]\x00)+", data[cursor:cursor + 512])
    if not match:
        return ""
    return match.group().decode("utf-16-le").strip()


def pe_machine_and_corflags(path: str) -> tuple:
    """(IMAGE_FILE_MACHINE, COR20 flags) : 관리 코드가 아니면 flags 는 None.

    AnyCPU .NET 실행파일은 machine 이 x86(0x14C)으로 찍히지만 64비트로 실행된다.
    그 구분에 필요한 CLR 헤더 플래그를 함께 돌려준다.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(0x400)
            if head[:2] != b"MZ":
                return (None, None)
            pe = struct.unpack_from("<I", head, 0x3C)[0]
            f.seek(pe)
            coff = f.read(24)
            if coff[:4] != b"PE\0\0":
                return (None, None)
            machine, n_sections = struct.unpack_from("<HH", coff, 4)
            opt_size = struct.unpack_from("<H", coff, 20)[0]
            opt = f.read(opt_size)
            magic = struct.unpack_from("<H", opt, 0)[0]
            data_dirs = 112 if magic == 0x20B else 96
            if opt_size < data_dirs + 15 * 8:
                return (machine, None)
            clr_rva = struct.unpack_from("<I", opt, data_dirs + 14 * 8)[0]
            if not clr_rva:
                return (machine, None)
            sections = f.read(n_sections * 40)
            for i in range(n_sections):
                va, raw_size, raw_ptr = struct.unpack_from("<III", sections, i * 40 + 12)
                if va <= clr_rva < va + raw_size:
                    f.seek(raw_ptr + (clr_rva - va))
                    return (machine, struct.unpack_from("<I", f.read(20), 16)[0])
    except (OSError, struct.error, IndexError):
        return (None, None)
    return (machine, None)


def major_version(path: str) -> str:
    """파일 버전의 첫 자리. 못 읽으면 빈 문자열.

    CLI 와 API 는 **같은 세대끼리만** 맞는다. 세대가 다르면 설정 구조가 어긋나 값이 엉뚱한
    자리로 들어간다(5.x 는 4.x 대비 White Ink Ver. 항목이 끼어들었다). 그 판정에 쓴다.
    """
    version = file_version(path)
    return version.split(".")[0] if version else ""


def describe_file(path: str) -> str:
    """로그·진단서용 한 줄 요약: `이름 v버전 (크기 bytes)`."""
    if not path or not os.path.isfile(path):
        return f"{path or '(경로 없음)'} : 없음"
    try:
        size = os.path.getsize(path)
    except OSError:
        size = -1
    version = file_version(path) or "버전 미상"
    return f"{os.path.basename(path)} v{version} ({size:,} bytes) : {path}"


# ------------------------------------------------------------------------------
# 임베드 자산에서 이름 알아내기 : 벤더 원본명을 코드에 남기지 않기 위한 우회.
# ------------------------------------------------------------------------------

def _sibling_dlls(exe: str) -> list[str]:
    folder = os.path.dirname(exe or "")
    if not folder or not os.path.isdir(folder):
        return []
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".dll"))
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names]


def api_dll_for(exe: str) -> str:
    """이 CLI exe 가 부르는 API 라이브러리의 경로 (같은 폴더에서 짝을 찾는다).

    CLI 는 관리 코드라 라이브러리를 import 테이블이 아니라 P/Invoke 문자열로 부른다.
    그 문자열이 exe 안에 그대로 들어 있으므로, 같은 폴더 .dll 이름 중 exe 바이트에
    등장하는 것을 짝으로 본다. 라이브러리가 하나뿐이면 그것을 쓴다.
    """
    dlls = _sibling_dlls(exe)
    if len(dlls) <= 1:
        return dlls[0] if dlls else ""
    try:
        with open(exe, "rb") as f:
            blob = f.read()
    except OSError:
        return ""
    for dll in dlls:
        name = os.path.basename(dll).encode("ascii", errors="ignore")
        if name and (name in blob or name.decode("ascii").encode("utf-16-le") in blob):
            return dll
    return ""


# ------------------------------------------------------------------------------
# 설치본 탐색 : 드라이버 패키지가 함께 깔아 둔 같은 이름의 라이브러리를 찾는다.
# ------------------------------------------------------------------------------

def spool_driver_dir() -> str:
    """Windows 프린터 드라이버 파일이 stage 되는 폴더."""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    return os.path.join(windir, "System32", "spool", "drivers", "x64", "3")


def driver_files(prefix: str, limit: int = 12) -> list[str]:
    """스풀 드라이버 폴더에서 `prefix` 로 시작하는 파일의 `이름 v버전` 목록.

    API 라이브러리가 로드하는 드라이버측 처리 모듈이 여기 있다. -1401 이 나면 이 목록이
    비어 있는지(설치 누락) 버전이 다른지(세대 불일치)가 바로 갈린다.
    """
    folder = spool_driver_dir()
    if not prefix or not os.path.isdir(folder):
        return []
    out = []
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().startswith(prefix.lower()))
    except OSError:
        return []
    for name in names[:limit]:
        full = os.path.join(folder, name)
        version = file_version(full)
        out.append(f"{name} v{version}" if version else name)
    return out


def driver_file_prefix(dll_path: str) -> str:
    """API 라이브러리 이름에서 드라이버측 파일들의 공통 접두사를 뽑는다.

    라이브러리는 `<계열>Api.dll` 꼴이고 드라이버측 파일도 같은 `<계열>` 로 시작한다.
    벤더 문자열을 코드에 박지 않고 접두사를 얻기 위한 변환이다.
    """
    base = os.path.basename(dll_path or "")
    stem = os.path.splitext(base)[0]
    return stem[:-3] if stem.lower().endswith("api") else stem


def _registry_roots(company: str) -> list[str]:
    """레지스트리에서 얻은 설치 폴더 후보. Windows 밖이면 빈 목록."""
    try:
        import winreg
    except ImportError:
        return []

    roots: list[str] = []
    vendor = (company or "").split()[0] if company else ""

    def _values(key):
        out = []
        try:
            count = winreg.QueryInfoKey(key)[1]
        except OSError:
            return out
        for i in range(count):
            try:
                _, value, kind = winreg.EnumValue(key, i)
            except OSError:
                continue
            if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(value, str):
                out.append(value)
        return out

    # ① 제조사 전용 키 : 벤더 도구가 설치 경로를 남기는 자리.
    if vendor:
        for hive, flag in ((winreg.HKEY_LOCAL_MACHINE, 0), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY)):
            try:
                with winreg.OpenKey(hive, f"SOFTWARE\\{vendor}", 0, winreg.KEY_READ | flag) as base:
                    sub_count = winreg.QueryInfoKey(base)[0]
                    for i in range(sub_count):
                        try:
                            name = winreg.EnumKey(base, i)
                            with winreg.OpenKey(base, name) as sub:
                                roots.extend(_values(sub))
                        except OSError:
                            continue
            except OSError:
                continue

    # ② 프로그램 추가/제거 : Publisher 가 같은 항목의 InstallLocation.
    uninstall = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
    for flag in (0, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninstall, 0, winreg.KEY_READ | flag) as base:
                for i in range(winreg.QueryInfoKey(base)[0]):
                    try:
                        with winreg.OpenKey(base, winreg.EnumKey(base, i)) as sub:
                            publisher = ""
                            location = ""
                            for value_name in ("Publisher", "InstallLocation"):
                                try:
                                    value, _ = winreg.QueryValueEx(sub, value_name)
                                except OSError:
                                    continue
                                if value_name == "Publisher":
                                    publisher = str(value)
                                else:
                                    location = str(value)
                            if location and vendor and vendor.lower() in publisher.lower():
                                roots.append(location)
                    except OSError:
                        continue
        except OSError:
            continue

    cleaned = []
    for root in roots:
        path = root.strip().strip('"')
        if os.path.isdir(path) and path not in cleaned:
            cleaned.append(path)
        elif os.path.isfile(path):
            folder = os.path.dirname(path)
            if folder not in cleaned:
                cleaned.append(folder)
    return cleaned


def _find_in_tree(root: str, filename: str, max_dirs: int = 4000) -> list[str]:
    """`root` 아래에서 `filename` 을 찾는다. 방문 폴더 수에 상한을 둔다."""
    found = []
    visited = 0
    for current, dirs, files in os.walk(root):
        visited += 1
        if visited > max_dirs:
            logger.debug("설치본 탐색 상한 도달: %s", root)
            break
        for name in files:
            if name.lower() == filename.lower():
                found.append(os.path.join(current, name))
        # 언어 리소스·캐시처럼 뻔히 없는 가지는 들어가지 않는다.
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("locales", "cache", "logs")]
    return found


def installed_api_dlls(embedded_dll: str) -> list[str]:
    """이 PC 에 설치된, 임베드본과 같은 이름의 API 라이브러리 경로 목록.

    임베드본 자신은 제외한다. 결과는 프로세스 생애 동안 캐시한다.
    """
    if not embedded_dll:
        return []
    cached = _installed_cache.get(embedded_dll)
    if cached is not None:
        return cached

    filename = os.path.basename(embedded_dll)
    company = version_string(embedded_dll, "CompanyName")
    found: list[str] = []

    # 드라이버가 스풀 폴더에 직접 깔아 두는 경우.
    direct = os.path.join(spool_driver_dir(), filename)
    if os.path.isfile(direct):
        found.append(direct)

    for root in _registry_roots(company):
        for hit in _find_in_tree(root, filename):
            if hit not in found:
                found.append(hit)

    embedded_real = os.path.normcase(os.path.abspath(embedded_dll))
    found = [p for p in found if os.path.normcase(os.path.abspath(p)) != embedded_real]

    _installed_cache[embedded_dll] = found
    if found:
        logger.info("설치된 가먼트 API 라이브러리 %d개 발견", len(found))
        for path in found:
            logger.info("  %s", describe_file(path))
    return found


# ------------------------------------------------------------------------------
# 실행 폴더 구성 : 고른 라이브러리를 CLI exe 옆에 둔다.
# ------------------------------------------------------------------------------

def version_summary(exe: str, api_dll: str) -> str:
    """로그·진단서용 버전 3종 요약 : CLI · 사용 중인 API · 드라이버측 파일.

    이 세 값의 조합이 현장에서 되고 안 되고를 가른다. 지금까지는 아무 데도 안 남아
    매번 추리해야 했다. 파일 IO 가 있으므로 조합당 1회만 계산하고 캐시한다.
    """
    key = f"{exe}|{api_dll}"
    cached = _summary_cache.get(key)
    if cached is not None:
        return cached

    embedded = api_dll_for(exe)
    used = api_dll or embedded
    source = "설치본" if api_dll else "임베드"
    parts = [
        f"CLI={os.path.basename(exe)} v{file_version(exe) or '?'}",
        f"API={os.path.basename(used)} v{file_version(used) or '?'} ({source})",
    ]
    driver = driver_files(driver_file_prefix(embedded or used))
    parts.append("드라이버 파일=" + (", ".join(driver) if driver else "(스풀 폴더에 없음)"))
    summary = " · ".join(parts)
    _summary_cache[key] = summary
    return summary


_summary_cache: dict[str, str] = {}


def _copy_if_changed(src: str, dst: str) -> None:
    try:
        if os.path.isfile(dst):
            s, d = os.stat(src), os.stat(dst)
            if s.st_size == d.st_size and int(s.st_mtime) == int(d.st_mtime):
                return
    except OSError:
        pass
    shutil.copy2(src, dst)


def prepare(exe: str, api_dll: str) -> str:
    """`api_dll` 을 쓰는 실행 폴더를 만들고 그 안의 CLI exe 경로를 반환.

    exe 와 라이브러리를 한 폴더에 복사한다. 실패하면 원래 exe 경로를 그대로 돌려줘
    임베드본으로 동작하게 둔다(출력이 멈추는 것보다 낫다).
    """
    if not api_dll:
        return exe
    embedded_dll = api_dll_for(exe)
    tag = file_version(api_dll).replace(".", "_") or "unknown"
    folder = os.path.join(
        config.GARMENT_RUNTIME_DIR,
        f"{os.path.splitext(os.path.basename(exe))[0]}-{tag}",
    )
    try:
        os.makedirs(folder, exist_ok=True)
        target_exe = os.path.join(folder, os.path.basename(exe))
        _copy_if_changed(exe, target_exe)
        _copy_if_changed(api_dll, os.path.join(folder, os.path.basename(embedded_dll or api_dll)))
        return target_exe
    except OSError as e:
        logger.warning("가먼트 실행 폴더 구성 실패(%s) : 임베드본으로 진행", e)
        return exe
