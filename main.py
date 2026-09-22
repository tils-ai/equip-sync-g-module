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


from gui import WatcherApp


def main():
    setup_logging()
    if "--api-selftest" in sys.argv:
        raise SystemExit(run_api_selftest())
    app = WatcherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
