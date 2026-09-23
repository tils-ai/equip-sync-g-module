
import os
import shutil
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "vendor")
SOURCE = os.path.join(ROOT, ".source")
MANIFEST = os.path.join(VENDOR, ".dll_manifest")

EXE_MAP = {
    "cli_legacy.bin": "garment_cli_legacy.exe",
    "cli_pro.bin": "garment_cli_pro.exe",
}


def read_export_name(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("PE 파일이 아닙니다 (MZ 서명 없음)")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe : pe + 4] != b"PE\0\0":
        raise ValueError("PE 서명을 찾지 못했습니다")

    n_sections = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError(f"알 수 없는 optional header magic: {magic:#x}")
    data_dirs = opt + (112 if magic == 0x20B else 96)

    sections = []
    sec_off = opt + opt_size
    for i in range(n_sections):
        entry = sec_off + i * 40
        virtual_addr = struct.unpack_from("<I", data, entry + 12)[0]
        raw_size, raw_ptr = struct.unpack_from("<II", data, entry + 16)
        sections.append((virtual_addr, raw_size, raw_ptr))

    def to_offset(rva: int) -> int:
        for virtual_addr, raw_size, raw_ptr in sections:
            if virtual_addr <= rva < virtual_addr + raw_size:
                return raw_ptr + (rva - virtual_addr)
        raise ValueError(f"RVA {rva:#x} 가 어느 섹션에도 들어가지 않습니다")

    export_rva = struct.unpack_from("<I", data, data_dirs)[0]
    if export_rva == 0:
        raise ValueError("export 디렉터리가 없습니다 (DLL 이 아닌 것으로 보입니다)")

    name_rva = struct.unpack_from("<I", data, to_offset(export_rva) + 12)[0]
    start = to_offset(name_rva)
    end = data.index(b"\0", start)
    name = data[start:end].decode("ascii")

    if not name or os.path.basename(name) != name:
        raise ValueError(f"export 이름이 파일명으로 보이지 않습니다: {name!r}")
    return name


def _load_manifest_overrides() -> dict:
    overrides = {}
    if not os.path.isfile(MANIFEST):
        return overrides
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            alias, real = line.split("=", 1)
            overrides[alias.strip()] = real.strip()
    return overrides


def main() -> int:
    if not os.path.isdir(VENDOR):
        print(f"[restore_vendor] vendor 폴더 없음: {VENDOR}")
        return 1

    os.makedirs(SOURCE, exist_ok=True)
    overrides = _load_manifest_overrides()
    if overrides:
        print(f"[restore_vendor] 매니페스트 오버라이드 {len(overrides)}건 적용")

    restored = 0
    failed = []
    for fn in sorted(os.listdir(VENDOR)):
        src = os.path.join(VENDOR, fn)
        if not os.path.isfile(src) or fn.startswith("."):
            continue

        if fn in EXE_MAP:
            dst_name = EXE_MAP[fn]
        elif fn in overrides:
            dst_name = overrides[fn]
        elif fn.endswith(".lib"):
            try:
                dst_name = read_export_name(src)
            except ValueError as e:
                failed.append(f"{fn}: {e}")
                continue
        else:
            dst_name = fn

        shutil.copy2(src, os.path.join(SOURCE, dst_name))
        print(f"[restore_vendor] {fn} -> {dst_name}")
        restored += 1

    if failed:
        print("[restore_vendor] 실패: 아래 라이브러리의 원본 이름을 읽지 못했습니다.")
        for line in failed:
            print(f"  - {line}")
        print("  vendor/.dll_manifest 에 `<가명>=<원본 파일명>` 한 줄을 적으면 그 값을 씁니다.")
        return 2

    print(f"[restore_vendor] done: {restored} restored -> {SOURCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
