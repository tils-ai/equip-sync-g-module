"""WatcherApp — 단일 화면 (spec §1, §9). b-module 가먼트 전용 device label.

기존 watcher.py / agent.py 도메인 로직은 그대로 사용.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import customtkinter as ctk

import config

from .cards import StatusCards
from .download_grid import DownloadGrid
from .header import Header
from .log_box import LogBox, attach_logging
from .op_control import OpControlBox
from .recent import RecentList
from .settings_panel import SettingsPanel
from .stats import SessionStats
from . import theme

logger = logging.getLogger(__name__)

WINDOW_TITLE = "가먼트 프린터 매니저"
WINDOW_SIZE = (920, 680)
DEVICE_LABEL = "👕 가먼트 프린터"


def _open_folder(path: str) -> None:
    if not path:
        return
    os.makedirs(path, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _count_pdfs(folder: str) -> int:
    if not folder or not os.path.isdir(folder):
        return 0
    try:
        return sum(1 for n in os.listdir(folder) if n.lower().endswith(".pdf"))
    except OSError:
        return 0


class WatcherApp(ctk.CTk):
    REFRESH_MS = 1500

    def __init__(self) -> None:
        super().__init__()
        self.stats = SessionStats()
        self._log_queue: queue.Queue = queue.Queue()
        self._after_id: Optional[str] = None

        self._observer = None
        self._agent = None
        self._device_poller = None
        self._watcher_running = False
        self._agent_running = False

        theme.apply(config.get_appearance())

        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}")
        self.minsize(720, 540)
        self.configure(fg_color=theme.BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=0)  # 상단 스트립 (현황 + 컨트롤)
        self.grid_rowconfigure(2, weight=1)  # 출력 대기 그리드 (메인)
        self.grid_rowconfigure(3, weight=0)  # 하단 스트립 (최근 처리 + 로그)

        self.header = Header(
            self,
            device_label=DEVICE_LABEL,
            on_settings=self._open_settings,
            on_theme_change=self._on_theme_change,
            appearance=config.get_appearance(),
        )
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.set_pairing("connected" if config.API_KEY else "unpaired")

        # ── 상단 스트립: 현황 카드(좌) + 운영 컨트롤(우) 한 줄 ──
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 4))
        top.grid_columnconfigure(0, weight=0)               # 현황 — 자연 폭(고정)
        top.grid_columnconfigure(1, weight=1)               # 스페이서 — 남는 폭 흡수
        top.grid_columnconfigure(2, weight=0, minsize=300)  # 컨트롤 — 우측 고정 폭

        self.cards = StatusCards(top, on_error_click=lambda: _open_folder(config.ERROR_DIR))
        self.cards.grid(row=0, column=0, sticky="nw")

        self.control = OpControlBox(
            top,
            on_toggle_agent=self._toggle_agent,
            on_toggle_watcher=self._toggle_watcher,
            on_open_folder=lambda: _open_folder(config.INCOMING_DIR),
        )
        self.control.grid(row=0, column=2, sticky="nse")

        # ── 메인: 출력 대기 그리드 ──
        self.download_grid = DownloadGrid(self, on_print=self._on_print_clicked)
        self.download_grid.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)

        # ── 하단 스트립: 최근 처리(좌) + 로그(우) 한 줄 ──
        bottom = ctk.CTkFrame(self, fg_color="transparent", height=160)
        bottom.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 12))
        bottom.grid_propagate(False)  # height 고정 — 메인 그리드가 세로를 가져가도록
        bottom.grid_columnconfigure(0, weight=2)  # 최근 처리
        bottom.grid_columnconfigure(1, weight=3)  # 로그
        bottom.grid_rowconfigure(0, weight=1)

        self.recent = RecentList(bottom)
        self.recent.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.log = LogBox(bottom)
        self.log.grid(row=0, column=1, sticky="nsew")

        attach_logging(self._log_queue)

        self.settings_panel = SettingsPanel(self)

        self.after(200, self._start_services)
        self._tick()
        self._drain_log()

    # ── 외부 인터랙션 ─────────────────────────────────
    def _open_settings(self) -> None:
        self.settings_panel.open()

    def _on_theme_change(self, label: str) -> None:
        appearance = theme.APPEARANCE_REVERSE.get(label, "system")
        applied = theme.apply(appearance)
        config.set_appearance(applied)

    def _toggle_watcher(self) -> None:
        if self._watcher_running:
            self._stop_watcher()
        else:
            # 상호 배타 — 같은 INCOMING/DOWNLOAD 폴더를 둘이 동시에 잡으면 중복 처리됨
            if self._agent_running:
                logger.info("Agent 가 실행 중이라 자동 정지 후 Watcher 를 시작합니다.")
                self._stop_agent()
            self._start_watcher()

    def _toggle_agent(self) -> None:
        if self._agent_running:
            self._stop_agent()
        else:
            if self._watcher_running:
                logger.info("Watcher 가 실행 중이라 자동 정지 후 Agent 를 시작합니다.")
                self._stop_watcher()
            self._start_agent()

    # ── 라이프사이클 ──────────────────────────────────
    def _start_services(self) -> None:
        # 장비 상태 폴러는 agent/watcher 와 독립 — 항상 시작(내부에서 enabled 가드)
        self._start_device_poller()
        # API 인증 정보가 있으면 Agent 모드 우선 (Watcher 와 폴더 충돌 방지)
        if config.API_KEY and config.API_TENANT:
            self._start_agent()
            return
        if config.API_TENANT:
            self.control.set_agent(running=False, detail="미페어링 — Agent 시작 시 자동 인증", enabled=True)
        else:
            self.control.set_agent(running=False, detail="스토어 ID 미설정 — 설정 패널에서 입력", enabled=False)
        # 인증 미설정 시에만 Watcher 자동 시작 (수동 드롭인 처리)
        self._start_watcher()

    def _start_watcher(self) -> None:
        if self._watcher_running:
            return
        try:
            from watcher import start_watching
        except Exception:
            logger.exception("watcher 로딩 실패")
            return
        try:
            self._observer = start_watching()
            self._watcher_running = True
            logger.info("=== 가먼트 Watcher 시작 ===")
            logger.info("감시: %s → 완료: %s", config.INCOMING_DIR, config.DONE_DIR)
        except Exception:
            logger.exception("watcher 시작 실패")

    def _stop_watcher(self) -> None:
        if not self._watcher_running:
            return
        try:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5)
                self._observer = None
        except Exception:
            logger.exception("watcher 정지 실패")
        self._watcher_running = False
        logger.info("watcher 정지됨")

    def _start_agent(self) -> None:
        if self._agent_running:
            return
        if not config.API_TENANT:
            logger.warning("agent 시작 거부 — 스토어 ID 미설정 (설정 패널에서 입력 필요)")
            return
        try:
            from agent import AgentWorker
        except Exception:
            logger.exception("agent 로딩 실패")
            return
        try:
            self._agent = AgentWorker()
            # 세션 카운터/최근 처리 목록 wiring — 없으면 카드/리스트가 영원히 0/빈 상태
            self._agent.on_done = lambda fn: self._on_agent_done(fn)
            self._agent.on_error = lambda fn: self._on_agent_error(fn)
            self._agent.on_downloaded = lambda fn: self._on_agent_downloaded(fn)
            # 출력 큐 그리드 wiring — 콜백은 백그라운드 스레드에서 오므로 after(0) 로 메인 마샬링
            self._agent.on_ready = lambda it: self.after(0, lambda: self.download_grid.add_item(it))
            self._agent.on_printing = lambda iid, pr: self.after(0, lambda: self.download_grid.set_printing(iid, pr))
            self._agent.on_item_done = lambda iid: self.after(0, lambda: self.download_grid.set_done(iid))
            self._agent.on_item_failed = lambda iid, rsn: self.after(0, lambda: self.download_grid.set_failed(iid, rsn))
            self._agent.on_item_removed = lambda iid: self.after(0, lambda: self.download_grid.remove_item(iid))
            self._agent.start()
            self._agent_running = True
            if config.API_KEY:
                logger.info("=== Agent (API 풀링) 시작 — %s ===", config.API_BASE_URL)
            else:
                logger.info("=== Agent 인증 시작 — 브라우저에서 승인 후 풀링 자동 시작 ===")
        except Exception:
            logger.exception("agent 시작 실패")

    def _on_agent_done(self, filename: str) -> None:
        self.stats.on_done()
        self._push_recent(filename, "ok", "출력 완료")

    def _on_agent_error(self, filename: str) -> None:
        self.stats.on_error()
        self._push_recent(filename, "error", "처리 실패")

    def _on_agent_downloaded(self, filename: str) -> None:
        self._push_recent(filename, "ok", "다운로드")

    def _on_print_clicked(self, item_id: str, ink: int) -> None:
        """출력 대기 카드 흰옷(Color)/컬러옷(White+Color) 클릭 → Agent 출력 큐 투입."""
        if self._agent is None:
            return
        if not self._agent.print_ready(item_id, ink):
            logger.info("출력 투입 무시 — 이미 전송 중이거나 없는 항목: %s", item_id)

    def _push_recent(self, filename: str, status: str, detail: str) -> None:
        try:
            import time as _time
            from .recent import ActivityItem
            self.recent.push(ActivityItem(ts=_time.time(), label=filename, status=status, detail=detail))
        except Exception:
            logger.exception("recent push 실패")

    def _stop_agent(self) -> None:
        if not self._agent_running:
            return
        try:
            if self._agent:
                self._agent.stop()
                self._agent = None
        except Exception:
            logger.exception("agent 정지 실패")
        self._agent_running = False
        try:
            self.download_grid.clear()
        except Exception:
            logger.exception("출력 대기 그리드 정리 실패")
        logger.info("agent 정지됨")

    # ── 장비 상태 폴러 ─────────────────────────────────
    def _start_device_poller(self) -> None:
        if self._device_poller is not None:
            return
        try:
            from device_status import DeviceStatusPoller
        except Exception:
            logger.exception("device_status 로딩 실패")
            return
        try:
            self._device_poller = DeviceStatusPoller()
            self._device_poller.on_error = lambda st: self._on_device_error(st)
            self._device_poller.start()
        except Exception:
            logger.exception("장비 상태 폴러 시작 실패")

    def _stop_device_poller(self) -> None:
        try:
            if self._device_poller:
                self._device_poller.stop()
                self._device_poller = None
        except Exception:
            logger.exception("장비 상태 폴러 정지 실패")

    def _on_device_error(self, status: dict) -> None:
        errs = status.get("errors") or []
        detail = "; ".join(errs) if errs else "Error stop"
        label = status.get("current_file") or "장비"
        self._push_recent(label, "error", f"장비 에러 — {detail}")
        logger.error("장비 에러 감지 — %s (status=%s)", detail, status.get("raw"))

    def _update_device_card(self) -> None:
        poller = self._device_poller
        st = poller.latest if poller is not None else None
        if st is None:
            self.cards.set_device("오프라인", "muted")
            return
        state = st.get("state")
        if state == "error":
            self.cards.set_device("에러", "danger")
        elif state == "printing":
            cf = st.get("current_file")
            if cf:
                short = cf if len(cf) <= 14 else cf[:12] + "…"
                self.cards.set_device(f"출력중·{short}", "active")
            else:
                self.cards.set_device("출력중", "active")
        elif state == "init":
            self.cards.set_device("초기화", "muted")
        elif state == "menu":
            self.cards.set_device("메뉴", "muted")
        else:  # ready / standby / unknown
            self.cards.set_device("대기", "muted")

    # ── tick / log ──────────────────────────────────
    def _tick(self) -> None:
        # 현황 카드 = 출력 큐 상태 버킷(그리드 탭과 동일 기준): 대기/처리중/완료/실패.
        # 다운로드 진행 중이면 처리중에 합산. Agent OFF 면 INCOMING PDF 수만 가늠.
        if self._agent_running and self._agent is not None:
            counts = self._agent.status_counts()
            pending = counts["ready"]
            processing = counts["printing"] + (1 if self._agent.is_processing else 0)
            done = counts["done"]
            error = counts["failed"]
        else:
            pending = _count_pdfs(config.INCOMING_DIR)
            processing = 0
            done = self.stats.done
            error = self.stats.error
        self.cards.set_counts(
            pending=pending,
            processing=processing,
            done=done,
            error=error,
        )
        if self._watcher_running:
            self.control.set_watcher(running=True, detail=f"감시 중 · {os.path.basename(config.INCOMING_DIR) or 'incoming'}/")
        else:
            self.control.set_watcher(running=False, detail="정지됨")

        if self._agent_running:
            self.control.set_agent(running=True, detail=f"풀링 중 · {config.API_POLL_INTERVAL}초 간격", enabled=True)
        elif config.API_KEY and config.API_TENANT:
            self.control.set_agent(running=False, detail="정지됨", enabled=True)
        elif config.API_TENANT:
            self.control.set_agent(running=False, detail="미페어링 — Agent 시작 시 자동 인증", enabled=True)
        else:
            self.control.set_agent(running=False, detail="스토어 ID 미설정 — 설정 패널에서 입력", enabled=False)

        self._update_device_card()

        self.control.tick()
        self._after_id = self.after(self.REFRESH_MS, self._tick)

    def _drain_log(self) -> None:
        for _ in range(100):
            try:
                line = self._log_queue.get_nowait()
                self.log.append(line)
            except queue.Empty:
                break
        self.after(150, self._drain_log)

    def _on_close(self) -> None:
        try:
            if self._after_id:
                self.after_cancel(self._after_id)
        except Exception:
            pass
        try:
            self._stop_agent()
        except Exception:
            pass
        try:
            self._stop_watcher()
        except Exception:
            pass
        try:
            self._stop_device_poller()
        except Exception:
            pass
        self.destroy()
