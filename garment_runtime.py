
import logging
import os
import re
import shutil
import struct

import config

logger = logging.getLogger(__name__)

_installed_cache: dict[str, list[str]] = {}


def file_version(path: str) -> str:
    data = _read_version_region(path)
    idx = data.find(b"\xbd\x04\xef\xfe")
    if idx < 0 or idx + 24 > len(data):
        return ""
    try:
        ms_minor, ms_major, ls_build, ls_revision = struct.unpack_from("<HHHH", data, idx + 8)
    except struct.error:
        return ""
    return f"{ms_major}.{ms_minor}.{ls_revision}.{ls_build}"


_TAIL_BYTES = 4 << 20
_WHOLE_FILE_LIMIT = 64 << 20


def _read_version_region(path: str) -> bytes:
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
    data = _read_version_region(path)
    needle = key.encode("utf-16-le") + b"\x00\x00"
    idx = data.find(needle)
    if idx < 0:
        return ""
    cursor = idx + len(needle)
    while cursor + 1 < len(data) and data[cursor:cursor + 2] == b"\x00\x00":
        cursor += 2
    match = re.match(rb"(?:[\x20-\x7e]\x00)+", data[cursor:cursor + 512])
    if not match:
        return ""
    return match.group().decode("utf-16-le").strip()


def pe_machine_and_corflags(path: str) -> tuple:
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
    version = file_version(path)
    return version.split(".")[0] if version else ""


def describe_file(path: str) -> str:
    if not path or not os.path.isfile(path):
        return f"{path or '(경로 없음)'} : 없음"
    try:
        size = os.path.getsize(path)
    except OSError:
        size = -1
    version = file_version(path) or "버전 미상"
    return f"{os.path.basename(path)} v{version} ({size:,} bytes) : {path}"


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


def spool_driver_dir() -> str:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    return os.path.join(windir, "System32", "spool", "drivers", "x64", "3")


def driver_files(prefix: str, limit: int = 12) -> list[str]:
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
    base = os.path.basename(dll_path or "")
    stem = os.path.splitext(base)[0]
    return stem[:-3] if stem.lower().endswith("api") else stem


def _registry_roots(company: str) -> list[str]:
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
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("locales", "cache", "logs")]
    return found


def installed_api_dlls(embedded_dll: str) -> list[str]:
    if not embedded_dll:
        return []
    cached = _installed_cache.get(embedded_dll)
    if cached is not None:
        return cached

    filename = os.path.basename(embedded_dll)
    company = version_string(embedded_dll, "CompanyName")
    found: list[str] = []

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


def version_summary(exe: str, api_dll: str) -> str:
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
