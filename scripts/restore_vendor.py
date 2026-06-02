"""빌드 직전, vendor/ 의 가명 자산을 임시 .source/ 로 복원한다.

- 레포(git)에는 벤더 원본 파일명을 남기지 않는다. 가명 바이너리(vendor/*.bin/*.lib)만 추적된다.
- CLI 실행파일은 코드가 찾는 '중립 이름'으로 복원한다(아래 EXE_MAP, git 평문 무방 — 제품 특정 불가).
- API 라이브러리는 실행파일이 내부에서 '원본 이름'으로 로드하므로 원본 이름으로 복원해야 한다.
  원본 라이브러리 이름은 git 에 두지 않고, 미추적 매핑 파일(vendor/.dll_manifest) 또는
  CI secret 으로 주입한다. (a 안: GitHub Actions secret + 로컬 미추적 파일)

복원된 .source/ 는 PyInstaller `--add-data ".source;.source"` 로 단일 exe 에 임베드된다.
"""

import os
import shutil
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


def _load_dll_map() -> dict:
    """가명 → 원본 라이브러리 이름 매핑. 미추적 manifest(또는 CI 가 secret 으로 써둔 파일)에서 읽는다.

    형식(라인별): `cli_legacy.lib=<원본 라이브러리 파일명>`
    """
    mapping = {}
    if not os.path.isfile(MANIFEST):
        return mapping
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            alias, real = line.split("=", 1)
            mapping[alias.strip()] = real.strip()
    return mapping


def main() -> int:
    if not os.path.isdir(VENDOR):
        print(f"[restore_vendor] vendor 폴더 없음: {VENDOR}")
        return 1

    os.makedirs(SOURCE, exist_ok=True)
    dll_map = _load_dll_map()

    restored = 0
    missing_dll_alias = []
    for fn in sorted(os.listdir(VENDOR)):
        src = os.path.join(VENDOR, fn)
        if not os.path.isfile(src) or fn.startswith("."):
            continue
        if fn in EXE_MAP:
            dst_name = EXE_MAP[fn]
        elif fn.endswith(".lib"):
            dst_name = dll_map.get(fn)
            if not dst_name:
                missing_dll_alias.append(fn)
                continue
        else:
            # 의존 런타임 DLL 등은 이름 그대로 복원
            dst_name = fn
        shutil.copy2(src, os.path.join(SOURCE, dst_name))
        print(f"[restore_vendor] {fn} -> {dst_name}")
        restored += 1

    if missing_dll_alias:
        print(
            "[restore_vendor] 경고: 다음 라이브러리의 원본 이름 매핑이 없습니다 "
            f"(vendor/.dll_manifest 또는 CI secret 확인): {missing_dll_alias}"
        )
        return 2

    print(f"[restore_vendor] done: {restored} restored -> {SOURCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
