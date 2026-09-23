
import logging
import threading
import time
from typing import Callable, Optional

import config
from garment_cli import read_printer_status

logger = logging.getLogger(__name__)


def _fire(cb, *args):
    if cb is None:
        return
    try:
        cb(*args)
    except Exception:
        logger.exception("장비 상태 콜백 예외 — 무시하고 계속")


class DeviceStatusPoller:

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self.latest: dict | None = None
        self._prev_error = False
        self.on_error: Optional[Callable[[dict], None]] = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self):
        if self._running:
            return
        if not config.DEVICE_STATUS_ENABLED or config.DEVICE_STATUS_INTERVAL <= 0:
            logger.info("장비 상태 폴링 비활성 (status_enabled/status_interval 설정)")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("장비 상태 폴링 시작 — %d초 간격", config.DEVICE_STATUS_INTERVAL)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self):
        while self._running:
            try:
                status = read_printer_status(config.GARMENT_PRINTER_NAME)
                self.latest = status
                self._check_error_edge(status)
            except Exception:
                logger.exception("장비 상태 폴링 예외 — 다음 주기에 재시도")
                self.latest = None

            interval = max(config.DEVICE_STATUS_INTERVAL, 1)
            waited = 0.0
            while waited < interval and self._running:
                time.sleep(1)
                waited += 1

    def _check_error_edge(self, status: dict | None):
        is_error = bool(status and status.get("error"))
        if is_error and not self._prev_error:
            _fire(self.on_error, status)
        self._prev_error = is_error
