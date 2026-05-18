"""가먼트 프린터 Agent — dps-store API 풀링 → PDF 다운로드 → 출력."""

import logging
import os
import shutil
import threading
import time
from typing import Callable, Optional

import requests

import config
from api_client import GarmentApiClient
from auth import authenticate
from processor import process_file

logger = logging.getLogger(__name__)

# 백오프 설정
_BACKOFF_THRESHOLDS = [(3, 10), (6, 20), (10, 30)]


def _get_backoff_interval(empty_count: int, base_interval: float) -> float:
    """빈 응답 연속 횟수에 따라 풀링 간격 결정."""
    for threshold, interval in reversed(_BACKOFF_THRESHOLDS):
        if empty_count >= threshold:
            return interval
    return base_interval


def _download_pdf(url: str, dest_path: str) -> bool:
    """URL에서 PDF 다운로드."""
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        logger.error("PDF 다운로드 실패: %s", e)
        return False


def _make_filename(job: dict) -> str:
    """다운로드 파일명 생성."""
    order_number = job.get("orderNumber", "unknown")
    seqno = job.get("wepnpSeqno", "")
    ext = job.get("designFileType", "PDF").lower()
    return f"{order_number}_{seqno}_디자인.{ext}"


class AgentWorker:
    """풀링 루프를 백그라운드 스레드에서 실행."""

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._client: GarmentApiClient | None = None
        # 표준 콜백 셋 (g/l/m 통일) — 모두 Optional, 미지정 시 무시
        self.on_started: Optional[Callable[[], None]] = None
        self.on_stopped: Optional[Callable[[], None]] = None
        self.on_downloaded: Optional[Callable[[str], None]] = None
        self.on_done: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_auth_expired: Optional[Callable[[], None]] = None

    @property
    def running(self) -> bool:
        return self._running

    # 호환성을 위한 별칭 (이전 코드가 is_running을 참조)
    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        """Agent 시작 — API 키 없으면 Device Auth 자동 트리거."""
        if self._running:
            return
        if not config.API_KEY:
            if not config.API_TENANT:
                logger.error("스토어 ID(tenant) 미설정 — 설정 패널에서 입력 후 다시 시도하세요.")
                return
            logger.info("인증 시작 — tenant: %s", config.API_TENANT)
            threading.Thread(target=self._auth_and_start, daemon=True).start()
            return
        self._start_polling()

    def _auth_and_start(self):
        """브라우저 Device Auth → API 키 발급 → config.ini 저장 → 풀링 시작."""
        try:
            api_key = authenticate(config.API_BASE_URL, config.API_TENANT)
            config.save_value("api", "api_key", api_key)
            config.reload()
            logger.info("인증 완료 — 풀링 시작")
            self._start_polling()
        except SystemExit:
            return
        except Exception:
            logger.exception("인증 오류")

    def _start_polling(self):
        self._client = GarmentApiClient(config.API_BASE_URL, config.API_KEY)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Agent 풀링 시작 — 서버: %s", config.API_BASE_URL)
        _fire(self.on_started)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Agent 중지됨")
        _fire(self.on_stopped)

    def _loop(self):
        empty_count = 0
        base_interval = max(config.API_POLL_INTERVAL, 5)

        while self._running:
            try:
                data = self._client.get_pending_jobs()
                jobs = data.get("jobs", [])

                # 서버 지정 풀링 간격 반영
                server_interval = data.get("pollInterval")
                if server_interval and server_interval > 0:
                    base_interval = server_interval

                if not jobs:
                    empty_count += 1
                else:
                    empty_count = 0
                    for job in jobs:
                        if not self._running:
                            break
                        self._process_job(job)

            except requests.RequestException as e:
                logger.error("풀링 오류: %s", e)
                empty_count += 1

            interval = _get_backoff_interval(empty_count, base_interval)
            # 1초 단위로 체크하면서 대기 (빠른 중지 대응)
            waited = 0.0
            while waited < interval and self._running:
                time.sleep(1)
                waited += 1

    def _process_job(self, job: dict):
        job_id = job["id"]
        url = job["designFileUrl"]
        filename = _make_filename(job)
        download_path = os.path.join(config.DOWNLOAD_DIR, filename)

        logger.info("다운로드: %s", filename)

        if not _download_pdf(url, download_path):
            self._report_failed(job_id, "PDF 다운로드 실패")
            _fire(self.on_error, filename)
            return

        _fire(self.on_downloaded, filename)

        try:
            logger.info("출력 시작: %s", filename)
            process_file(download_path)
            self._report_printed(job_id)
            logger.info("출력 완료: %s", filename)
            _fire(self.on_done, filename)
        except Exception as e:
            logger.error("출력 실패: %s — %s", filename, e)
            self._report_failed(job_id, str(e))
            # 파일을 error 폴더로 이동
            error_dest = os.path.join(config.ERROR_DIR, filename)
            if os.path.exists(download_path):
                shutil.move(download_path, error_dest)
            _fire(self.on_error, filename)

    def _report_printed(self, job_id: str):
        try:
            self._client.mark_printed(job_id)
        except Exception as e:
            logger.error("출력 완료 보고 실패: %s", e)

    def _report_failed(self, job_id: str, reason: str):
        try:
            self._client.mark_failed(job_id, reason)
        except Exception as e:
            logger.error("출력 실패 보고 실패: %s", e)


def _fire(cb, *args):
    """콜백을 안전하게 호출 — 미지정이거나 예외면 무시."""
    if cb is None:
        return
    try:
        cb(*args)
    except Exception:
        logger.exception("콜백 예외 — 무시하고 계속")
