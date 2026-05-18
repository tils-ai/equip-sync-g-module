import logging
import os
import time
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import config
from processor import process_file

logger = logging.getLogger(__name__)


class PDFFileHandler(FileSystemEventHandler):
    """감시 폴더에 PDF 파일이 생성되면 처리한다."""

    def __init__(self):
        super().__init__()
        self._processing = set()
        self._lock = threading.Lock()

    def _handle_file(self, file_path: str):
        ext = os.path.splitext(file_path)[1].lower()
        if ext != ".pdf":
            return

        with self._lock:
            if file_path in self._processing:
                return
            self._processing.add(file_path)

        logger.info("파일 감지: %s", os.path.basename(file_path))
        t = threading.Thread(target=self._wait_and_process, args=(file_path,), daemon=True)
        t.start()

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file(event.src_path)

    def on_moved(self, event):
        """Windows에서 파일 복사 시 임시파일 → 최종파일로 rename되는 경우 처리."""
        if event.is_directory:
            return
        self._handle_file(event.dest_path)

    def _wait_and_process(self, file_path: str):
        try:
            if not self._wait_for_stable(file_path):
                logger.warning("파일 안정화 실패 (타임아웃 또는 삭제): %s", os.path.basename(file_path))
                return
            process_file(file_path)
        except Exception:
            logger.exception("파일 처리 중 예외: %s", os.path.basename(file_path))
        finally:
            with self._lock:
                self._processing.discard(file_path)

    @staticmethod
    def _wait_for_stable(file_path: str, timeout: float = 30.0) -> bool:
        """파일 크기가 안정될 때까지 대기."""
        interval = config.FILE_STABLE_CHECK_INTERVAL
        required = config.FILE_STABLE_CHECK_COUNT
        stable = 0
        prev_size = -1
        elapsed = 0.0
        not_found_count = 0

        while elapsed < timeout:
            if not os.path.exists(file_path):
                not_found_count += 1
                if not_found_count > 5:
                    return False
                time.sleep(interval)
                elapsed += interval
                continue

            not_found_count = 0
            size = os.path.getsize(file_path)
            if size == prev_size and size > 0:
                stable += 1
                if stable >= required:
                    return True
            else:
                stable = 0
            prev_size = size
            time.sleep(interval)
            elapsed += interval
        return False


def start_watching():
    """폴더 감시 시작, Observer 반환."""
    os.makedirs(config.INCOMING_DIR, exist_ok=True)
    observer = Observer()
    observer.schedule(PDFFileHandler(), config.INCOMING_DIR, recursive=False)
    observer.start()
    logger.info("폴더 감시 시작: %s", config.INCOMING_DIR)
    return observer
