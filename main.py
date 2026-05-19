import logging
import os

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


from gui import WatcherApp


def main():
    setup_logging()
    app = WatcherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
