import logging
import os
import sys

import config
import fonts

fonts.register()


def setup_logging(to_file: bool = True) -> None:
    level_name = (config.LOG_LEVEL or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

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
            raise RuntimeError("자식 모드 : 파일 핸들러 생략")
        fh = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)


def _hard_exit(code: int) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def run_api_selftest() -> int:
    import garment_api

    path = garment_api.self_test_report()
    print(f"점검 보고서: {path}")
    logging.getLogger(__name__).info("API 점검 보고서: %s", path)
    return 0


def run_api_makearxp(png_path: str, out_path: str = "", opt_json: str = "",
                     position: str = "", size: str = "", model: str = "pro",
                     variant: int = 0, printer: str = "") -> int:
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
    print(f"RC={rc}")
    log.info("직접 호출 생성 반환 코드: %s", rc)
    _hard_exit(0 if rc == 0 else 1)


from gui import WatcherApp


def main():
    child_mode = any(a.startswith("--api-") for a in sys.argv)
    if child_mode:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
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
    if "--api-rgba-probe" in sys.argv:
        import garment_api

        i = sys.argv.index("--api-rgba-probe")
        rest = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
        if len(rest) < 2:
            print("사용법: --api-rgba-probe <png> <프린터>")
            raise SystemExit(2)
        try:
            import ctypes

            ctypes.windll.kernel32.SetErrorMode(0x0002 | 0x0001 | 0x8000)
        except (AttributeError, OSError):
            pass
        for line in garment_api.rgba_probe(rest[0], rest[1]):
            print(line)
        _hard_exit(0)
    if "--api-rgba" in sys.argv:
        import garment_api

        i = sys.argv.index("--api-rgba")
        rest = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
        if len(rest) < 3:
            print("사용법: --api-rgba <png> <출력> <프린터> [--opt <json>] [--model pro]")
            raise SystemExit(2)

        def _rflag(name: str) -> str:
            return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else ""

        try:
            import ctypes

            ctypes.windll.kernel32.SetErrorMode(0x0002 | 0x0001 | 0x8000)
        except (AttributeError, OSError):
            pass
        import json as _json

        overrides = _json.loads(_rflag("--opt") or "{}")
        rc, lines = garment_api.rgba_print(
            rest[0], rest[1], rest[2], model=_rflag("--model") or "pro", overrides=overrides,
            position=_rflag("--position"), size=_rflag("--size"),
        )
        for line in lines:
            print(line)
        print(f"RC={rc}")
        _hard_exit(0 if rc == 0 else 1)
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
