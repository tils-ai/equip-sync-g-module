import logging
import os
import sys

import config
import fonts

# GUI 모듈 import 전에 폰트를 프로세스에 등록
fonts.register()


def setup_logging() -> None:
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
        fh = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        # 파일 핸들러 실패해도 콘솔/큐 핸들러는 살아남도록 무시
        pass

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)


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
    return 0 if rc == 0 else 1


from gui import WatcherApp


def main():
    setup_logging()
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
