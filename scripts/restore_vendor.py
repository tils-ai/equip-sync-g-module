"""빌드 직전, vendor/ 의 가명 자산을 임시 .source/ 로 복원한다.

- 레포(git)에는 벤더 원본 파일명을 텍스트로 남기지 않는다. 가명 바이너리(vendor/*.bin/*.lib)만 추적된다.
- CLI 실행파일은 코드가 찾는 '중립 이름'으로 복원한다(아래 EXE_MAP, git 평문 무방 — 제품 특정 불가).
- API 라이브러리는 실행파일이 내부에서 '원본 이름'으로 로드하므로 원본 이름으로 복원해야 한다.
  그 이름은 **라이브러리 자신이 PE export 디렉터리에 들고 있으므로 거기서 읽는다.**
  매핑 파일이나 CI secret 없이도 복원되고, 클론 직후 바로 빌드된다.

복원된 .source/ 는 PyInstaller `--add-data ".source;.source"` 로 단일 exe 에 임베드된다.

예전에는 미추적 매핑 파일(vendor/.dll_manifest)과 CI secret 으로만 원본 이름을 넣었다.
그러나 그 이름은 이미 커밋된 바이너리 안에 평문으로 들어 있어(`strings vendor/cli_legacy.lib`)
감춰진 적이 없었고, 새 개발자마다 매핑 파일을 따로 받아야 하는 비용만 남았다.
매니페스트는 **선택적 오버라이드**로만 남긴다 — 벤더가 export 이름과 다른 파일명을 요구하는
예외가 생겼을 때 쓴다.
"""

import os
import shutil
import struct
import sys

# Windows CI 기본 콘솔 인코딩(cp1252)에서 비ASCII 출력이 깨지지 않도록 UTF-8 강제.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "vendor")
SOURCE = os.path.join(ROOT, ".source")
MANIFEST = os.path.join(VENDOR, ".dll_manifest")

# 가명 → 중립 실행파일 이름 (코드 config 가 탐색하는 이름. 제품 특정 불가하므로 git 평문 OK)
EXE_MAP = {
    "cli_legacy.bin": "garment_cli_legacy.exe",
    "cli_pro.bin": "garment_cli_pro.exe",
}


def read_export_name(path: str) -> str:
    """PE export 디렉터리의 Name 필드에서 라이브러리 원본 파일명을 읽는다.

    DLL 은 자기 파일명을 export 디렉터리에 담고 있다. 벤더 실행파일이 그 이름으로
    LoadLibrary 를 호출하므로, 복원할 이름의 정답은 파일 자신에게 있다.

    형식이 예상과 다르면 ValueError 를 던진다. 조용히 틀린 이름으로 복원하면 현장에서
    '드라이버 파일 없음'(-1401)으로만 보여 원인을 찾는 데 오래 걸린다.
    """
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
    # 데이터 디렉터리는 optional header 뒤에 붙는다. PE32+ 쪽이 16바이트 더 길다.
    data_dirs = opt + (112 if magic == 0x20B else 96)

    # RVA → 파일 오프셋 변환에 섹션 테이블이 필요하다.
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

    # IMAGE_EXPORT_DIRECTORY 의 Name 필드는 구조체 시작에서 12바이트 지점이다.
    name_rva = struct.unpack_from("<I", data, to_offset(export_rva) + 12)[0]
    start = to_offset(name_rva)
    end = data.index(b"\0", start)
    name = data[start:end].decode("ascii")

    if not name or os.path.basename(name) != name:
        raise ValueError(f"export 이름이 파일명으로 보이지 않습니다: {name!r}")
    return name


def _load_manifest_overrides() -> dict:
    """가명 → 원본 이름 오버라이드. 파일이 없는 것이 정상이다.

    형식(라인별): `cli_legacy.lib=<원본 라이브러리 파일명>`
    """
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
            # 의존 런타임 DLL 등은 이름 그대로 복원
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
