"""가먼트 프린터 Agent — dps-store API 풀링 → 디자인/작업지시서 두 종 출력.

작업자 수동 전송 워크플로우 (20260609-garment-worker-gated-print):
  - 다운로드 단계(폴링 스레드, 자동): 디자인을 로컬에 받고 mark_downloaded → READY 큐 적재.
  - 출력 단계(프린터별 워커 스레드): 작업자 GUI 클릭(manual) 또는 자동(auto)으로 장비 전송 + 지시서 출력.
    프린터 1대면 1건씩 순차, 여러 대면 프린터당 1건씩(워커=프린터 수만큼 동시).
"""

import json
import logging
import os
import queue
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

import config
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


# 다운로드 청크 — 대용량 디자인 PNG 에서 8KB 는 syscall 오버헤드가 커서 1MB 로 읽는다
_DOWNLOAD_CHUNK = 1024 * 1024
_DOWNLOAD_RETRIES = 1  # 첫 시도 실패 시 1회 즉시 재시도 (다음 폴링까지 기다리지 않게)


def _download_file(url: str, dest_path: str, timeout: int = 60, label: str = "") -> bool:
    """URL에서 파일 다운로드 (디자인 파일 · 작업지시서 썸네일 공용).

    소요 시간·크기·처리율을 남긴다 — 현장에서 "다운로드가 느리다"를 진단하려면
    네트워크가 느린 것인지 큐 대기가 긴 것인지 구분할 수 있어야 한다.
    """
    name = label or os.path.basename(dest_path)
    for attempt in range(_DOWNLOAD_RETRIES + 1):
        started = time.monotonic()
        size = 0
        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=_DOWNLOAD_CHUNK):
                    if chunk:
                        f.write(chunk)
                        size += len(chunk)
            elapsed = max(time.monotonic() - started, 0.001)
            logger.info(
                "다운로드 완료: %s — %.1fMB, %.1f초 (%.1fMB/s)",
                name, size / 1048576, elapsed, size / 1048576 / elapsed,
            )
            return True
        except Exception as e:
            elapsed = time.monotonic() - started
            if attempt < _DOWNLOAD_RETRIES:
                logger.warning(
                    "다운로드 실패 — 즉시 재시도 (%s, %.1f초 경과): %s", name, elapsed, e
                )
                continue
            logger.error("다운로드 실패 (%s, %.1f초 경과): %s", name, elapsed, e)
            return False
    return False


def _make_filename(job: dict) -> str:
    """다운로드 파일명 생성. dps-store getDesignFilename 규칙과 동일."""
    order_number = job.get("orderNumber", "unknown")
    seqno = job.get("wepnpSeqno", "")
    ext = job.get("designFileType", "PDF").lower()
    idx = int(job.get("itemIndex", 1))
    return f"{order_number}_{idx:02d}_{seqno}_디자인.{ext}"


def _download_thumbnails(job: dict) -> list[str]:
    """작업지시서에 실을 썸네일(에디터 미리보기) 내려받기.

    인쇄 면 수만큼 내려온다. 지시서 부가 정보라 실패해도 출력은 계속한다 — 받은 것만 싣는다.
    """
    urls = [u for u in ((job.get("workOrder") or {}).get("thumbnailUrls") or []) if u]
    if not urls:
        return []

    order_number = job.get("orderNumber", "unknown")
    seqno = job.get("wepnpSeqno", "")
    idx = int(job.get("itemIndex", 1))
    paths: list[str] = []
    for n, url in enumerate(urls, 1):
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            ext = ".png"
        dest = os.path.join(
            config.DOWNLOAD_DIR, f"{order_number}_{idx:02d}_{seqno}_썸네일{n}{ext}"
        )
        if _download_file(url, dest, timeout=20, label=f"썸네일{n}"):
            paths.append(dest)
        else:
            logger.warning("썸네일 다운로드 실패 — 해당 장은 지시서에서 생략: %s", url)
    return paths


def _is_image(path: str) -> bool:
    """작업지시서 미리보기로 쓸 수 있는 이미지 파일인지 (PNG/JPG)."""
    return os.path.splitext(path)[1].lower() in (".png", ".jpg", ".jpeg")


# ─────────────────────────────────────────────────────────────────────────
# READY 스토어 — 다운로드 완료 후 작업자 출력 대기 큐 (로컬 영속화로 크래시 복구)
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class ReadyItem:
    """출력 큐 1건 — 다운로드 완료 후 작업자 전송 대상.

    do_garment / do_work_order 는 아직 전송하지 않은 sub 를 나타낸다.
    sub 가 전송완료(SENT)되면 False 로 내려가고, 둘 다 False 면 status="done".
    status: "ready"(대기) | "failed"(실패, 재시도 가능) | "done"(완료/이력).
    """

    job: dict
    download_path: str
    do_garment: bool
    do_work_order: bool
    status: str = "ready"
    error_reason: str = ""

    @property
    def id(self) -> str:
        return self.job.get("id", "")

    @property
    def filename(self) -> str:
        return _make_filename(self.job)


def _ready_store_path() -> str:
    return os.path.join(config.DOWNLOAD_DIR, "ready.json")


def _load_ready_store() -> list[ReadyItem]:
    """ready.json 복원 — 다운로드 파일이 실제로 남아 있는 항목만."""
    path = _ready_store_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error("ready.json 로드 실패: %s", e)
        return []

    items: list[ReadyItem] = []
    for r in raw if isinstance(raw, list) else []:
        it = ReadyItem(
            job=r.get("job", {}) or {},
            download_path=r.get("download_path", ""),
            do_garment=bool(r.get("do_garment", False)),
            do_work_order=bool(r.get("do_work_order", False)),
            status=r.get("status", "ready") or "ready",
            error_reason=r.get("error_reason", "") or "",
        )
        if not it.id:
            continue
        # done 은 이력이라 원본 파일이 없어도 유지(완료 탭). ready/failed 는 출력 원본이
        # 있어야 재시도 가능하므로 파일 존재를 확인.
        if it.status == "done" or (it.download_path and os.path.exists(it.download_path)):
            items.append(it)
        else:
            logger.warning("ready.json 항목 스킵 (출력 원본 없음): %s [%s]", it.id, it.status)
    return items


# 완료(done) 이력 보관 상한 — 그 이상은 오래된 것부터 버림(메모리/파일 비대 방지).
_DONE_KEEP = 30


def _save_ready_store(items: list[ReadyItem]) -> None:
    """ready.json 원자적 저장. done 항목은 최근 _DONE_KEEP 개만 보관."""
    path = _ready_store_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        done = [it for it in items if it.status == "done"]
        if len(done) > _DONE_KEEP:
            drop = set(id(it) for it in done[: len(done) - _DONE_KEEP])
            items = [it for it in items if id(it) not in drop]
        data = [
            {
                "job": it.job,
                "download_path": it.download_path,
                "do_garment": it.do_garment,
                "do_work_order": it.do_work_order,
                "status": it.status,
                "error_reason": it.error_reason,
            }
            for it in items
        ]
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        logger.error("ready.json 저장 실패: %s", e)


class AgentWorker:
    """풀링(다운로드) 루프 + 프린터별 출력 워커를 백그라운드 스레드에서 실행."""

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._client: GarmentApiClient | None = None
        # 표준 콜백 셋 (g/l/m 통일) — 모두 Optional, 미지정 시 무시
        self.on_started: Optional[Callable[[], None]] = None
        self.on_stopped: Optional[Callable[[], None]] = None
        self.on_downloaded: Optional[Callable[[str], None]] = None
        # 작업자 수동 전송 워크플로우 콜백
        self.on_ready: Optional[Callable[[ReadyItem], None]] = None  # READY 적재(그리드 추가)
        self.on_printing: Optional[Callable[[str, str], None]] = None  # (item_id, printer) 전송 시작
        self.on_item_done: Optional[Callable[[str], None]] = None  # 전송완료(완료 탭으로 이동)
        self.on_item_failed: Optional[Callable[[str, str], None]] = None  # (item_id, reason) 실패(실패 탭)
        self.on_item_removed: Optional[Callable[[str], None]] = None  # 그리드에서 제거(이력 정리 등)
        self.on_done: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_auth_expired: Optional[Callable[[], None]] = None
        # 카드 표시용 — 최근 풀링 응답 기준 잔여 잡 수 / 현재 잡 처리 중 여부
        self._pending_count = 0
        self._processing = False
        # READY 스토어 + 출력 큐
        self._ready_lock = threading.Lock()
        self._ready: dict[str, ReadyItem] = {}
        self._enqueued: set[str] = set()  # 출력 큐 투입/처리 중 — 중복 방지
        # 큐 항목 = (item_id, ink override). ink=None 이면 config.INK 사용.
        self._print_queue: "queue.Queue[tuple[str, Optional[int]]]" = queue.Queue()
        self._print_threads: list[threading.Thread] = []
        # 출력 워커 세대 토큰 — 증가 시 이전 세대 워커는 자연 종료. 설정 변경 시 워커 재생성에 사용.
        self._worker_gen = 0

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
        """현재 다운로드 처리 중 여부."""
        return self._processing

    @property
    def ready_count(self) -> int:
        """출력 대기(READY) 항목 수."""
        with self._ready_lock:
            return len(self._ready)

    def ready_snapshot(self) -> list[ReadyItem]:
        """현재 READY 항목 목록 복사본 (GUI 재구성용)."""
        with self._ready_lock:
            return list(self._ready.values())

    def status_counts(self) -> dict[str, int]:
        """출력 큐를 상태별로 집계 — 현황 카드/그리드 탭과 동일 기준.

        전송 큐에 투입된(=전송 중) ready 항목은 printing 으로 분류.
        """
        with self._ready_lock:
            c = {"ready": 0, "printing": 0, "failed": 0, "done": 0}
            for it in self._ready.values():
                if it.status == "ready" and it.id in self._enqueued:
                    c["printing"] += 1
                elif it.status in c:
                    c[it.status] += 1
            return c

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

    def _printer_pool(self) -> list[Optional[str]]:
        """출력 워커가 바인딩할 프린터 목록. 프린터당 워커 1개(=프린터별 직렬, 여러 대면 동시).

        - 프린터 미설정: [None] 1개 (가먼트 출력은 스킵, 작업지시서만 처리하는 PC 등).
        - single 분배: 첫 프린터 1개.
        - round_robin: 설정된 프린터 전부.
        """
        names = list(config.GARMENT_PRINTER_NAMES or [])
        if not names:
            return [config.GARMENT_PRINTER_NAME or None]
        if config.GARMENT_DISPATCH == "single":
            return [names[0]]
        return names

    def _spawn_print_workers(self) -> int:
        """현재 config 기준으로 출력 워커를 (재)생성. 세대 토큰을 올려 이전 세대 워커는 자연 종료시킨다.

        프린터 이름이 워커 시작 시점에 인자로 고정되므로, 설정에서 프린터를 바꾸면 이 메서드로
        새 프린터 풀에 맞춰 워커를 다시 띄워야 즉시 반영된다.
        """
        self._worker_gen += 1
        gen = self._worker_gen
        # 프린터별 1개 (프린터 수만큼 동시 전송)
        self._print_threads = []
        for printer_name in self._printer_pool():
            t = threading.Thread(target=self._print_loop, args=(printer_name, gen), daemon=True)
            t.start()
            self._print_threads.append(t)
        return len(self._print_threads)

    def restart_print_workers(self) -> None:
        """설정 변경(프린터 등)을 즉시 반영 — 폴링 루프는 유지한 채 출력 워커만 재생성."""
        if not self._running:
            return
        n = self._spawn_print_workers()
        logger.info("출력 워커 재시작(설정 반영) — 워커 %d", n)

    def _start_polling(self):
        self._client = GarmentApiClient(config.API_BASE_URL, config.API_KEY)
        self._running = True

        # 출력 워커 — 프린터별 1개 (프린터 수만큼 동시 전송)
        self._spawn_print_workers()

        # 크래시 복구 — ready.json 복원 → 그리드 재구성. auto 모드면 곧바로 출력 큐 투입.
        self._restore_ready_store()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(
            "Agent 풀링 시작 — 서버: %s, 출력 모드: %s, 워커: %d",
            config.API_BASE_URL, config.GARMENT_PRINT_MODE, len(self._print_threads),
        )
        _fire(self.on_started)

    def _restore_ready_store(self):
        """재시작 시 ready.json 복원."""
        restored = _load_ready_store()
        if not restored:
            return
        with self._ready_lock:
            for it in restored:
                self._ready[it.id] = it
        n_ready = sum(1 for it in restored if it.status == "ready")
        n_failed = sum(1 for it in restored if it.status == "failed")
        n_done = sum(1 for it in restored if it.status == "done")
        logger.info("스토어 복원 — 대기 %d · 실패 %d · 완료 %d", n_ready, n_failed, n_done)
        for it in restored:
            # 카드는 자신의 status 에 맞는 탭에 추가됨(add_item 이 item.status 참조).
            _fire(self.on_ready, it)
            if it.status == "ready" and config.GARMENT_PRINT_MODE == "auto":
                self.print_ready(it.id)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        # 출력 워커는 daemon + 큐 timeout 으로 자연 종료
        self._print_threads = []
        logger.info("Agent 중지됨")
        _fire(self.on_stopped)

    # ── 풀링(다운로드) 루프 ──────────────────────────────────────────────

    #: hasMore 무한 신뢰 방지 — 서버가 계속 "남았다"고만 답하는 상황에서도 폴링이 폭주하지 않게
    _MAX_FAST_POLLS = 30

    def _loop(self):
        empty_count = 0
        fast_polls = 0
        base_interval = max(config.API_POLL_INTERVAL, 5)
        HEARTBEAT_EVERY = 10  # 빈 폴링 N회마다 heartbeat 로그

        while self._running:
            try:
                data = self._client.get_pending_jobs(
                    garment_enabled=bool(config.GARMENT_ENABLED and config.GARMENT_PRINTER_NAME),
                    work_order_enabled=bool(config.WORK_ORDER_ENABLED and config.WORK_ORDER_PRINTER_NAME),
                )
                jobs = data.get("jobs", [])
                has_more = bool(data.get("hasMore"))

                server_interval = data.get("pollInterval")
                if server_interval and server_interval > 0:
                    base_interval = server_interval

                if not jobs and has_more and fast_polls < self._MAX_FAST_POLLS:
                    # 서버에 처리할 큐는 있는데 이번엔 못 받은 상태(동시성 1 제한 등).
                    # 이걸 "할 일 없음"으로 세면 백오프가 30초까지 벌어져 다음 건이 그만큼 늦는다.
                    self._pending_count = 0
                    empty_count = 0
                    fast_polls += 1
                    if fast_polls == 1:
                        logger.info("풀링 — 대기 큐 있음(hasMore), 백오프 없이 재시도")
                elif not jobs:
                    self._pending_count = 0
                    if empty_count == 0:
                        logger.info("풀링 중 — 대기 큐 없음")
                    empty_count += 1
                    fast_polls = 0
                    if empty_count % HEARTBEAT_EVERY == 0:
                        logger.info(
                            "풀링 중 — 대기 큐 없음 (연속 %d회, %d초 간격)",
                            empty_count, base_interval,
                        )
                else:
                    if empty_count > 0:
                        logger.info("풀링 — 잡 %d건 도착", len(jobs))
                    empty_count = 0
                    fast_polls = 0
                    self._pending_count = len(jobs)
                    for job in jobs:
                        if not self._running:
                            break
                        self._processing = True
                        try:
                            self._download_job(job)
                        except Exception:
                            logger.exception(
                                "다운로드 처리 중 예외 — 다음 잡으로 진행 (job_id=%s)",
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
            waited = 0.0
            while waited < interval and self._running:
                time.sleep(1)
                waited += 1

    def _download_job(self, job: dict):
        """다운로드 단계 — 디자인 다운로드 + READY 적재 + mark_downloaded. 장비 전송 안 함."""
        job_id = job["id"]
        url = job["designFileUrl"]
        filename = _make_filename(job)
        download_path = os.path.join(config.DOWNLOAD_DIR, filename)

        garment_pending = bool(job.get("garmentPending", True))
        work_order_pending = bool(job.get("workOrderPending", False))

        # 클라이언트 토글로 거름 — 서버에서는 PENDING 이어도 PC 토글 OFF면 건드리지 않는다.
        do_work_order = work_order_pending and config.WORK_ORDER_ENABLED and config.WORK_ORDER_PRINTER_NAME
        do_garment = garment_pending and config.GARMENT_ENABLED and config.GARMENT_PRINTER_NAME

        logger.info(
            "잡 수신 id=%s file=%s garmentPending=%s workOrderPending=%s → do_garment=%s do_work_order=%s",
            job_id, filename, garment_pending, work_order_pending, do_garment, do_work_order,
        )

        if not do_work_order and not do_garment:
            reason = self._skip_reason(garment_pending, work_order_pending)
            logger.info("스킵 (%s) id=%s file=%s", reason, job_id, filename)
            return

        # 디자인 파일 다운로드 — 그리드 썸네일/출력에 필요
        logger.info("다운로드: %s", filename)
        if not _download_file(url, download_path):
            if do_work_order:
                self._report_failed(job_id, "workOrder", "디자인 파일 다운로드 실패")
            if do_garment:
                self._report_failed(job_id, "garment", "디자인 파일 다운로드 실패")
            _fire(self.on_error, filename)
            return

        _fire(self.on_downloaded, filename)

        # 작업지시서용 썸네일 — job 에 심어두면 ready.json 으로 함께 영속화된다
        if do_work_order:
            job["thumbnailPaths"] = _download_thumbnails(job)

        # READY 적재 + 서버에 다운로드 완료 보고 (DOWNLOADING → READY)
        item = ReadyItem(
            job=job,
            download_path=download_path,
            do_garment=bool(do_garment),
            do_work_order=bool(do_work_order),
        )
        with self._ready_lock:
            self._ready[job_id] = item
            self._persist_locked()
        if do_garment:
            self._report_downloaded(job_id, "garment")
        if do_work_order:
            self._report_downloaded(job_id, "workOrder")
        logger.info("READY 적재: %s (mode=%s)", filename, config.GARMENT_PRINT_MODE)
        _fire(self.on_ready, item)

        # auto 모드면 곧바로 출력 큐 투입 (기존 동작과 동일)
        if config.GARMENT_PRINT_MODE == "auto":
            self.print_ready(job_id)

    # ── 출력 단계 ────────────────────────────────────────────────────────

    def print_ready(self, item_id: str, ink: Optional[int] = None) -> bool:
        """READY 항목을 출력 큐에 투입 (GUI 클릭 또는 auto). 중복 투입 방지.

        ink: 잉크 모드 (0=Color/흰옷, 2=Color+White/컬러옷). None 이면 config.INK.
        반환: 투입 성공 여부(이미 큐/처리 중이거나 없는 항목이면 False).
        """
        with self._ready_lock:
            item = self._ready.get(item_id)
            if item is None or item.status == "done":
                return False
            if item_id in self._enqueued:
                return False
            # 재시도 시 실패 표식 초기화 — 대기 상태로 되돌려 전송 시도.
            item.status = "ready"
            item.error_reason = ""
            self._enqueued.add(item_id)
            self._persist_locked()
        self._print_queue.put((item_id, ink))
        return True

    def delete_ready(self, item_id: str) -> tuple[bool, str]:
        """READY 항목을 큐에서 삭제 (GUI 삭제 버튼).

        중복되거나 잘못 만들어진 디자인을 걷어낸다. 전에는 없애려면 출력 버튼을 눌러
        흘려보내야 했고, 그때마다 작업지시서가 같이 인쇄돼 용지가 낭비됐다.

        서버 삭제가 성공해야 로컬에서도 지운다. 로컬만 지우면 다음 풀링에서 같은 건이
        다시 내려온다. 404 는 서버에 이미 없다는 뜻이므로 성공으로 본다.

        **복구는 없다.** 잘못 지웠으면 관리자 주문 관리의 재출력으로 다시 넣는다.
        반환: (성공 여부, 사용자에게 보여줄 사유)
        """
        with self._ready_lock:
            item = self._ready.get(item_id)
            if item is None:
                return False, "이미 없는 항목입니다."
            # 장비로 보내는 중에 지우면 전송 결과를 반영할 대상이 사라진다
            if item_id in self._enqueued:
                return False, "전송 중인 항목은 삭제할 수 없습니다."
            label = item.filename
            paths = [item.download_path, *(item.job.get("thumbnailPaths") or [])]

        if self._client is None:
            return False, "서버에 연결되어 있지 않습니다."

        try:
            self._client.delete_job(item_id)
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status != 404:
                logger.error("큐 삭제 실패 — 서버 오류 (%s): %s", label, e)
                return False, f"서버 삭제 실패: {e}"
            logger.info("큐 삭제 — 서버에 이미 없음, 로컬만 정리: %s", label)

        with self._ready_lock:
            self._ready.pop(item_id, None)
            self._persist_locked()
        for path in paths:
            self._cleanup_source(path)

        logger.info("큐 삭제됨: %s (id=%s)", label, item_id)
        _fire(self.on_item_removed, item_id)
        return True, ""

    def _print_loop(self, printer_name: Optional[str], gen: int):
        """프린터 1대에 바인딩된 출력 워커 — 큐에서 항목을 받아 1건씩 순차 전송.

        gen: 워커 세대. self._worker_gen 과 달라지면(설정 변경으로 워커 재생성됨) 이 워커는 종료한다.
        """
        while self._running and gen == self._worker_gen:
            try:
                item_id, ink = self._print_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                with self._ready_lock:
                    item = self._ready.get(item_id)
                if item is None:
                    continue
                self._print_item(item, printer_name, ink)
            except Exception:
                logger.exception("출력 워커 예외 (item_id=%s)", item_id)
            finally:
                with self._ready_lock:
                    self._enqueued.discard(item_id)
                self._print_queue.task_done()

    def _print_item(self, item: ReadyItem, printer_name: Optional[str], ink: Optional[int] = None):
        """READY 1건 전송 — 지시서 먼저, 가먼트 나중. 성공한 sub 는 SENT 처리하고 제거.

        ink: 잉크 모드 (0=Color/흰옷, 2=Color+White/컬러옷). None 이면 config.INK.
        실패한 sub 는 서버가 READY 유지(작업자 재클릭)하므로 항목을 스토어에 남긴다.
        """
        job = item.job
        job_id = item.id
        filename = item.filename
        download_path = item.download_path

        _fire(self.on_printing, job_id, printer_name or "")
        any_error = False

        # ── 1. 작업지시서 출력 (지시서 먼저) ──
        if item.do_work_order:
            try:
                logger.info("작업지시서 PDF 조립: %s", filename)
                wo_meta = job.get("workOrder") or {}
                idx = int(job.get("itemIndex", 1))
                wo_pdf = os.path.join(
                    config.DOWNLOAD_DIR,
                    f"{job.get('orderNumber', 'unknown')}_{idx:02d}_{job.get('wepnpSeqno', '')}_지시서.pdf",
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
                        thumbnail_paths=[
                            p for p in (job.get("thumbnailPaths") or []) if os.path.exists(p)
                        ],
                        design_filename=filename,
                        printer_name=printer_name,
                    ),
                    wo_pdf,
                )
                from printer import print_pdf_general

                print_pdf_general(wo_pdf, config.WORK_ORDER_PRINTER_NAME)
                self._report_printed(job_id, "workOrder")
                with self._ready_lock:
                    item.do_work_order = False
                    self._persist_locked()
                logger.info("작업지시서 출력 완료: %s", filename)
            except Exception as e:
                any_error = True
                logger.exception("작업지시서 출력 실패: %s", filename)
                self._report_failed(job_id, "workOrder", str(e))

        # ── 2. 가먼트 디자인 출력 (가먼트 나중, quantity번 반복) ──
        # process_file 은 받은 파일을 done/error 로 옮긴다. 재시도·재시작에 대비해
        # 원본(download_path)은 보존하고, 실명 복사본을 만들어 그걸 출력에 넘긴다.
        # 복사본 basename 이 실명이라 done/error 폴더에도 실제 파일명이 남는다.
        garment_err: Optional[str] = None
        if item.do_garment and printer_name:
            qty = max(1, int(job.get("quantity", 1)))
            needs_plate_change = bool(job.get("needsPlateChange", False))
            try:
                logger.info(
                    "가먼트 출력 시작: %s → %s (x%d)%s",
                    filename, printer_name, qty,
                    " [아동 플레이트]" if needs_plate_change else "",
                )
                for n in range(qty):
                    if not self._running:
                        raise RuntimeError("사용자 중지 요청")
                    logger.info("  [%d/%d]", n + 1, qty)
                    self._print_one_copy(download_path, filename, printer_name, needs_plate_change, ink)
                self._report_printed(job_id, "garment")
                with self._ready_lock:
                    item.do_garment = False
                    self._persist_locked()
                logger.info("가먼트 출력 완료: %s", filename)
                _fire(self.on_done, filename)
            except Exception as e:
                any_error = True
                garment_err = str(e)
                logger.exception("가먼트 출력 실패: %s", filename)
                self._report_failed(job_id, "garment", str(e))
        elif item.do_garment and not printer_name:
            any_error = True
            garment_err = "가먼트 프린터 미설정"
            logger.error("가먼트 처리 대상이나 프린터 미설정: %s", filename)
            self._report_failed(job_id, "garment", garment_err)

        # 완료/실패 상태 확정. 남은 sub 가 없으면 done(완료 탭), 실패가 있으면 failed(실패 탭).
        with self._ready_lock:
            remaining = item.do_garment or item.do_work_order
            if not remaining:
                item.status = "done"
                item.error_reason = ""
                # 완료 원본은 더 쓰지 않으므로 정리 (그리드 카드는 placeholder 썸네일).
                self._cleanup_source(item.download_path)
            elif any_error:
                item.status = "failed"
                item.error_reason = garment_err or "전송 실패"
            self._persist_locked()
            evicted = self._evict_old_done_locked() if not remaining else []
        if not remaining:
            _fire(self.on_item_done, job_id)
        elif any_error:
            _fire(self.on_item_failed, job_id, item.error_reason)
        for ev in evicted:
            _fire(self.on_item_removed, ev)
        if any_error:
            _fire(self.on_error, filename)

    def _print_one_copy(self, source: str, filename: str, printer_name: str, needs_plate_change: bool, ink: Optional[int] = None):
        """원본을 건드리지 않도록 실명 복사본을 만들어 출력. process_file 이 복사본을 done/error 로 이동."""
        work_dir = tempfile.mkdtemp(prefix="garment_")
        work_copy = os.path.join(work_dir, filename)
        try:
            shutil.copy(source, work_copy)
            process_file(work_copy, printer_name=printer_name, needs_plate_change=needs_plate_change, ink=ink)
        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    @staticmethod
    def _cleanup_source(path: str):
        """완료된 출력 원본 삭제 — 실패 시 무시."""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            logger.debug("출력 원본 정리 실패: %s", path, exc_info=True)

    def _evict_old_done_locked(self) -> list[str]:
        """_ready_lock 보유 상태 — done 이 상한을 넘으면 오래된 것부터 제거하고 제거 id 반환."""
        done_ids = [iid for iid, it in self._ready.items() if it.status == "done"]
        if len(done_ids) <= _DONE_KEEP:
            return []
        drop = done_ids[: len(done_ids) - _DONE_KEEP]
        for iid in drop:
            self._ready.pop(iid, None)
        return drop

    def _persist_locked(self):
        """_ready_lock 보유 상태에서 호출 — ready.json 저장."""
        _save_ready_store(list(self._ready.values()))

    def _skip_reason(self, garment_pending: bool, work_order_pending: bool) -> str:
        """스킵 메시지에 붙일 사유 한 줄. 운영자가 토글 vs 서버 응답 미스매치를 즉시 식별."""
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

    def _report_downloaded(self, job_id: str, target: str):
        try:
            self._client.mark_downloaded(job_id, target)
        except Exception as e:
            logger.error("다운로드 완료 보고 실패 (%s): %s", target, e)

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
