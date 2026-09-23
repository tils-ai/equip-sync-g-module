
from __future__ import annotations

import logging
import threading

import config

logger = logging.getLogger(__name__)


class GarmentDispatcher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index = 0

    def next_printer(self) -> str:
        names = list(config.GARMENT_PRINTER_NAMES or [])
        if not names:
            return config.GARMENT_PRINTER_NAME
        if config.GARMENT_DISPATCH == "single" or len(names) == 1:
            return names[0]
        with self._lock:
            name = names[self._index % len(names)]
            self._index = (self._index + 1) % len(names)
        logger.debug("dispatcher: 다음 프린터 → %s", name)
        return name

    def reset(self) -> None:
        with self._lock:
            self._index = 0


_default = GarmentDispatcher()


def next_printer() -> str:
    return _default.next_printer()


def reset() -> None:
    _default.reset()
