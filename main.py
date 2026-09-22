import logging
import os
import sys

import config
import fonts

# GUI 모듈 import 전에 폰트를 프로세스에 등록
fonts.register()


def setup_logging(to_file: bool = True) -> None:
    """루트 로거 설정 — config.LOG_LEVEL/LOG_FILE 반영.

    이 호출이 누락되면 root logger 가 기본 WARNING 레벨이라 agent/processor 의
    logger.info(...) 가 모두 버려져 GUI 로그 박스에 아무것도 안 뜬다.
    """
    level_name = (config.LOG_LEVEL or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # 재진입 방지 — 핸들러 중복 부착 회피
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_dir = os.path.dirname(config.LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    try:
        if not to_file:
            raise RuntimeError("자식 모드 — 파일 핸들러 생략")
        fh = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        # 파일 핸들러 실패해도 콘솔/큐 핸들러는 살아남도록 무시
        pass

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)


def _hard_exit(code: int) -> None:
    """정리 단계를 건너뛰고 즉시 끝낸다.

    벤더 라이브러리를 부른 프로세스는 일을 마치고도 종료되지 않고 매달리는 경우가 있다.
    현장에서 인쇄 데이터를 5MB 만들어 놓고도 자식이 안 죽어, 부모가 180초를 기다린 뒤
    실패로 보고 다음 모양으로 넘어갔다. 결과를 이미 남겼으므로 미련 없이 끊는다.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def run_api_selftest() -> int:
    """`--api-selftest` — API 직접 호출 전환의 1단계(구조체 정렬) 점검만 하고 끝낸다.

    GUI 를 띄우지 않는다. 현장 PC 에서 cmd 한 줄로 실행해 보고서만 받아오기 위한 통로다.
    인쇄는 하지 않으므로 장비·옷에 영향이 없다.
    """
    import garment_api

    path = garment_api.self_test_report()
    print(f"점검 보고서: {path}")  # 콘솔에서 실행했을 때만 보인다
    logging.getLogger(__name__).info("API 점검 보고서: %s", path)
    return 0


def run_api_makearxp(png_path: str, out_path: str = "", opt_json: str = "",
                     position: str = "", size: str = "", model: str = "pro",
                     variant: int = 0, printer: str = "") -> int:
    """`--api-makearxp <png> [출력경로]` — 2단계 시험. 인쇄 데이터만 만들어 본다.

    장비로 보내는 단계는 타지 않는다. 다만 마지막 인자의 의미가 미확정이라,
    **첫 실행은 장비 전원을 끄거나 USB 를 뽑고** 하는 것을 전제한다.
    """
    import garment_api

    if not os.path.isfile(png_path):
        print(f"입력 PNG 를 찾을 수 없습니다: {png_path}")
        return 2
    out_path = out_path or os.path.splitext(png_path)[0] + "-direct.arxp"
    overrides = {}
    if opt_json:
        import json

        try:
            overrides = json.loads(opt_json)
        except ValueError:
            print(f"옵션 JSON 해석 실패: {opt_json}")
            return 2
    rc, lines = garment_api.make_arxp(
        png_path, out_path, model=model, position=position, size=size,
        overrides=overrides, variant=variant, printer_name=printer,
    )
    log = logging.getLogger(__name__)
    for line in lines:
        print(line)
        log.info("%s", line)
    # 부모가 결과를 읽는 약속된 줄. 자식이 죽으면 이 줄이 없다 → 부모가 크래시로 판정한다.
    print(f"RC={rc}")
    log.info("직접 호출 생성 반환 코드: %s", rc)
    _hard_exit(0 if rc == 0 else 1)


from gui import WatcherApp


def main():
    # 자식 모드는 watcher.log 를 건드리지 않는다. 부모와 같은 파일에 동시에 쓰면 부모가 남긴
    # 줄이 사라진다(현장에서 전송 단계 로그가 통째로 비었다). 자식의 기록은 진단서로 남는다.
    child_mode = any(a.startswith("--api-") for a in sys.argv)
    setup_logging(to_file=not child_mode)
    logging.getLogger(__name__).info(
        "=== 실행 빌드: %s · 출력 경로: %s ===", config.APP_VERSION, config.GARMENT_BACKEND
    )
    if "--api-selftest" in sys.argv:
        raise SystemExit(run_api_selftest())
    if "--api-probe" in sys.argv:
        import garment_api

        log = logging.getLogger(__name__)
        for line in garment_api.probe_option():
            print(line)
            log.info("%s", line)
        raise SystemExit(0)
    if "--api-send" in sys.argv:
        import garment_api

        i = sys.argv.index("--api-send")
        rest = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
        if len(rest) < 2:
            print("사용법: --api-send <데이터> <프린터> [--variant N] [--model pro]")
            raise SystemExit(2)

        def _sflag(name: str) -> str:
            return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else ""

        try:
            import ctypes

            ctypes.windll.kernel32.SetErrorMode(0x0002 | 0x0001 | 0x8000)
        except (AttributeError, OSError):
            pass
        rc, lines = garment_api.send(
            rest[0], rest[1], model=_sflag("--model") or "pro",
            variant=int(_sflag("--variant") or 0),
        )
        for line in lines:
            print(line)
        print(f"RC={rc}")
        _hard_exit(0 if rc == 0 else 1)
    if "--api-makearxp" in sys.argv:
        i = sys.argv.index("--api-makearxp")
        rest = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
        if not rest:
            print("사용법: --api-makearxp <입력.png> [출력.arxp] [--opt <json>] [--position P] [--size S]")
            raise SystemExit(2)

        def _flag(name: str) -> str:
            return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else ""

        raise SystemExit(run_api_makearxp(
            rest[0], rest[1] if len(rest) > 1 else "",
            opt_json=_flag("--opt"), position=_flag("--position"),
            size=_flag("--size"), model=_flag("--model") or "pro",
            variant=int(_flag("--variant") or 0), printer=_flag("--printer"),
        ))
    app = WatcherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
