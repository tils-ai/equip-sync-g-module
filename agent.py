"""가먼트 프린터 Agent — dps-store API 풀링 → 디자인/작업지시서 두 종 출력."""

import logging
import os
import shutil
import threading
import time
from typing import Callable, Optional

import requests

import config
import dispatcher
from api_client import GarmentApiClient
from auth import authenticate
from processor import process_file
from work_order_builder import WorkOrderJob, build_work_order_pdf

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
    """다운로드 파일명 생성. dps-store getDesignFilename 규칙과 동일."""
    order_number = job.get("orderNumber", "unknown")
    seqno = job.get("wepnpSeqno", "")
    ext = job.get("designFileType", "PDF").lower()
    idx = int(job.get("itemIndex", 1))
    return f"{order_number}_{idx:02d}_{seqno}_디자인.{ext}"


def _is_image(path: str) -> bool:
    """작업지시서 미리보기로 쓸 수 있는 이미지 파일인지 (PNG/JPG)."""
    return os.path.splitext(path)[1].lower() in (".png", ".jpg", ".jpeg")


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
        # 카드 표시용 — 최근 풀링 응답 기준 잔여 잡 수 / 현재 잡 처리 중 여부
        self._pending_count = 0
        self._processing = False

    @property
    def running(self) -> bool:
        return self._running

    # 호환성을 위한 별칭 (이전 코드가 is_running을 참조)
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def pending_count(self) -> int:
        """가장 최근 풀링 응답에서 받은 잡 중 아직 처리 안 한 개수."""
        return self._pending_count

    @property
    def is_processing(self) -> bool:
        """현재 _process_job 실행 중 여부."""
        return self._processing

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
        HEARTBEAT_EVERY = 10  # 빈 폴링 N회마다 heartbeat 로그

        while self._running:
            try:
                # 클라이언트 capability 를 서버에 전달 — work_order_enabled=false 인 PC 가
                # workOrder 만 PENDING 인 큐를 받아 무한 스킵 루프 도는 문제 차단.
                data = self._client.get_pending_jobs(
                    garment_enabled=bool(config.GARMENT_ENABLED and config.GARMENT_PRINTER_NAME),
                    work_order_enabled=bool(config.WORK_ORDER_ENABLED and config.WORK_ORDER_PRINTER_NAME),
                )
                jobs = data.get("jobs", [])

                # 서버 지정 풀링 간격 반영
                server_interval = data.get("pollInterval")
                if server_interval and server_interval > 0:
                    base_interval = server_interval

                if not jobs:
                    self._pending_count = 0
                    if empty_count == 0:
                        logger.info("풀링 중 — 대기 큐 없음")
                    empty_count += 1
                    if empty_count % HEARTBEAT_EVERY == 0:
                        logger.info(
                            "풀링 중 — 대기 큐 없음 (연속 %d회, %d초 간격)",
                            empty_count, base_interval,
                        )
                else:
                    if empty_count > 0:
                        logger.info("풀링 — 잡 %d건 도착", len(jobs))
                    empty_count = 0
                    self._pending_count = len(jobs)
                    for job in jobs:
                        if not self._running:
                            break
                        # 단일 잡 처리 중 발생한 예외가 풀링 루프 전체를 죽이지 않도록 격리.
                        # 풀링 루프가 죽으면 이미 PRINTING 으로 마킹된 잡이 영원히 회수되지 않음.
                        self._processing = True
                        try:
                            self._process_job(job)
                        except Exception:
                            logger.exception(
                                "잡 처리 중 예외 — 다음 잡으로 진행 (job_id=%s)",
                                job.get("id"),
                            )
                        finally:
                            self._processing = False
                            self._pending_count = max(0, self._pending_count - 1)

            except requests.RequestException as e:
                logger.error("풀링 오류: %s", e)
                empty_count += 1
            except Exception:
                logger.exception("풀링 루프 예외 — 다음 주기에 재시도")
                empty_count += 1

            interval = _get_backoff_interval(empty_count, base_interval)
            # 1초 단위로 체크하면서 대기 (빠른 중지 대응)
            waited = 0.0
            while waited < interval and self._running:
                time.sleep(1)
                waited += 1

    def _process_job(self, job: dict):
        """큐 1건 처리 — 지시서 먼저, 가먼트 나중 (두 토글/pending 독립)."""
        job_id = job["id"]
        url = job["designFileUrl"]
        filename = _make_filename(job)
        download_path = os.path.join(config.DOWNLOAD_DIR, filename)

        garment_pending = bool(job.get("garmentPending", True))
        work_order_pending = bool(job.get("workOrderPending", False))

        # 클라이언트 토글로 거름 — 서버에서는 두 sub 모두 PENDING이지만 PC가 OFF면 건드리지 않는다.
        do_work_order = work_order_pending and config.WORK_ORDER_ENABLED and config.WORK_ORDER_PRINTER_NAME
        do_garment = garment_pending and config.GARMENT_ENABLED and config.GARMENT_PRINTER_NAME

        # 진단 가능성을 위해 풀링 응답의 sub status 와 토글 매칭을 항상 한 줄로 남긴다.
        # capability 분리가 안 된 구버전 서버와 페어링될 때 같은 잡이 무한 반복 풀링되는 케이스를
        # 사용자가 즉시 식별할 수 있게 함 (dps-store 20260520-garment-pull-capability-split 참조).
        logger.info(
            "잡 수신 id=%s file=%s garmentPending=%s workOrderPending=%s "
            "→ do_garment=%s do_work_order=%s",
            job_id, filename, garment_pending, work_order_pending, do_garment, do_work_order,
        )

        if not do_work_order and not do_garment:
            reason = self._skip_reason(garment_pending, work_order_pending)
            logger.info("스킵 (%s) id=%s file=%s", reason, job_id, filename)
            return

        # 디자인 파일 다운로드 — 양쪽 모두 PNG 미리보기/출력에 필요
        logger.info("다운로드: %s", filename)
        if not _download_pdf(url, download_path):
            # 다운로드 실패 시 활성화된 작업만 failed 보고
            if do_work_order:
                self._report_failed(job_id, "workOrder", "디자인 파일 다운로드 실패")
            if do_garment:
                self._report_failed(job_id, "garment", "디자인 파일 다운로드 실패")
            _fire(self.on_error, filename)
            return

        _fire(self.on_downloaded, filename)

        any_error = False

        # ── 가먼트 출력에 사용할 프린터를 미리 결정 ──
        # 워크오더에 같은 이름을 박아 "디자인이 어느 장비로 갔는지" 작업자가 알 수 있게 한다.
        garment_printer = dispatcher.next_printer() if do_garment else None

        # ── 1. 작업지시서 출력 (지시서 먼저) ──
        if do_work_order:
            try:
                logger.info("작업지시서 PDF 조립: %s", filename)
                wo_meta = job.get("workOrder") or {}
                idx = int(job.get("itemIndex", 1))
                wo_pdf = os.path.join(
                    config.DOWNLOAD_DIR,
                    f"{job.get('orderNumber','unknown')}_{idx:02d}_{job.get('wepnpSeqno','')}_지시서.pdf",
                )
                build_work_order_pdf(
                    WorkOrderJob(
                        order_number=job.get("orderNumber", ""),
                        product_name=job.get("productName", ""),
                        option_name=job.get("optionName"),
                        quantity=int(job.get("quantity", 1)),
                        wepnp_seqno=job.get("wepnpSeqno", ""),
                        tenant_name=wo_meta.get("tenantName", ""),
                        brand_name=wo_meta.get("brandName", ""),
                        printed_by=wo_meta.get("printedBy", ""),
                        work_url=wo_meta.get("workUrl", ""),
                        item_index=idx,
                        item_total=int(job.get("itemTotal", 1)),
                        preview_image_path=download_path if _is_image(download_path) else None,
                        design_filename=filename,
                        printer_name=garment_printer,
                    ),
                    wo_pdf,
                )
                from printer import print_pdf_general

                print_pdf_general(wo_pdf, config.WORK_ORDER_PRINTER_NAME)
                self._report_printed(job_id, "workOrder")
                logger.info("작업지시서 출력 완료: %s", filename)
            except Exception as e:
                any_error = True
                logger.exception("작업지시서 출력 실패: %s", filename)
                self._report_failed(job_id, "workOrder", str(e))

        # ── 2. 가먼트 디자인 출력 (가먼트 나중, quantity번 반복) ──
        if do_garment:
            qty = max(1, int(job.get("quantity", 1)))
            try:
                logger.info("가먼트 출력 시작: %s → %s (x%d)", filename, garment_printer, qty)
                for n in range(qty):
                    if not self._running:
                        raise RuntimeError("사용자 중지 요청")
                    logger.info("  [%d/%d]", n + 1, qty)
                    process_file(download_path, printer_name=garment_printer)
                    # process_file은 성공 시 done/으로 옮긴다 — 다음 회차 위해 복사본 복원 필요
                    if n + 1 < qty:
                        done_path = os.path.join(config.DONE_DIR, os.path.basename(download_path))
                        if os.path.exists(done_path):
                            shutil.copy(done_path, download_path)
                self._report_printed(job_id, "garment")
                logger.info("가먼트 출력 완료: %s", filename)
                _fire(self.on_done, filename)
            except Exception as e:
                any_error = True
                logger.exception("가먼트 출력 실패: %s", filename)
                self._report_failed(job_id, "garment", str(e))
                error_dest = os.path.join(config.ERROR_DIR, filename)
                if os.path.exists(download_path):
                    try:
                        shutil.move(download_path, error_dest)
                    except Exception:
                        pass

        if any_error:
            _fire(self.on_error, filename)

    def _skip_reason(self, garment_pending: bool, work_order_pending: bool) -> str:
        """스킵 메시지에 붙일 사유 한 줄. 운영자가 토글 vs 서버 응답 미스매치를 즉시 식별."""
        # 서버는 PENDING 인 sub 만 내려주는 것이 정상 (capability 가드 적용 후).
        # 그럼에도 둘 다 처리 못 한다는 건 토글 OFF + sub PENDING 의 미스매치.
        g_off = not (config.GARMENT_ENABLED and config.GARMENT_PRINTER_NAME)
        w_off = not (config.WORK_ORDER_ENABLED and config.WORK_ORDER_PRINTER_NAME)
        if garment_pending and g_off and work_order_pending and w_off:
            return "양쪽 토글 OFF — 다른 PC 처리 대기"
        if garment_pending and g_off and not work_order_pending:
            return "garmentPending 인데 가먼트 토글 OFF"
        if work_order_pending and w_off and not garment_pending:
            return "workOrderPending 인데 지시서 토글 OFF — 서버 capability 가드 미적용 의심"
        if not garment_pending and not work_order_pending:
            return "양쪽 sub 모두 PENDING 아님 — 다른 PC 가 이미 선점"
        return "스킵 사유 불명 (g=%s/w=%s)" % (garment_pending, work_order_pending)

    def _report_printed(self, job_id: str, target: str):
        try:
            self._client.mark_printed(job_id, target)
        except Exception as e:
            logger.error("출력 완료 보고 실패 (%s): %s", target, e)

    def _report_failed(self, job_id: str, target: str, reason: str):
        try:
            self._client.mark_failed(job_id, target, reason)
        except Exception as e:
            logger.error("출력 실패 보고 실패 (%s): %s", target, e)


def _fire(cb, *args):
    """콜백을 안전하게 호출 — 미지정이거나 예외면 무시."""
    if cb is None:
        return
    try:
        cb(*args)
    except Exception:
        logger.exception("콜백 예외 — 무시하고 계속")
