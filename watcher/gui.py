import ctypes
import logging
import os
import queue
import subprocess
import sys
from tkinter import messagebox

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

import customtkinter as ctk

import config
import fonts

logger = logging.getLogger(__name__)

# Pretendard 등록 (멱등)
fonts.register()

# 컬러 팔레트 (light, dark) — CTk가 appearance_mode에 따라 자동 선택
_BG = ("#F5F5F7", "#2C2C2E")
_FRAME_BG = ("#FFFFFF", "#3A3A3C")
_TEXT = ("#1F1F1F", "#E0DDD9")
_TEXT_MUTED = ("#6E6E73", "#8E8A85")
_GREEN = ("#34A853", "#8BC5A3")
_CORAL = ("#E14B3D", "#D4897A")
_BLUE = ("#3B6EA5", "#7A9EB8")
_GRAY = ("#C7C7CC", "#5A5856")
_LOG_BG = ("#F2F2F7", "#333335")
_LOG_TEXT = ("#1F1F1F", "#D0CCC8")
_FONT = fonts.family()
_APPEARANCE_LABELS = {"system": "시스템", "light": "라이트", "dark": "다크"}
_APPEARANCE_REVERSE = {v: k for k, v in _APPEARANCE_LABELS.items()}


def _prompt_restart(app: "WatcherApp"):
    """설정 저장 후 재시작 여부 확인. 사용자가 동의하면 즉시 재시작."""
    if messagebox.askyesno(
        "재시작",
        "설정 변경 사항을 적용하려면 재시작이 필요합니다.\n지금 재시작하시겠습니까?",
        parent=app,
    ):
        app.restart_app()


class QueueHandler(logging.Handler):
    """로그를 큐로 전달하여 GUI에서 소비."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))


class WatcherApp(ctk.CTk):
    MAX_LOG_LINES = 1000

    def __init__(self):
        super().__init__()
        self.title("Brother GTX-4 Manager")
        self.geometry("1240x760")
        self.minsize(1080, 640)
        self.configure(fg_color=_BG)

        ctk.set_appearance_mode(config.get_appearance().capitalize())

        self._log_queue = queue.Queue()
        self._observer = None
        self._running = False
        self._agent = None

        self._setup_logging()
        self._build_ui()
        self._poll_log_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ─── 로깅 ───

    def _setup_logging(self):
        handler = QueueHandler(self._log_queue)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        ))
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(logging.INFO)

    # ─── UI 빌드 ───

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        # 탭 뷰
        self._tabview = ctk.CTkTabview(self, fg_color=_BG, segmented_button_fg_color=_FRAME_BG)
        self._tabview.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="nsew")

        self._tab_watcher = self._tabview.add("Watcher")
        self._tab_agent = self._tabview.add("Agent")

        self._build_watcher_tab(self._tab_watcher)
        self._build_agent_tab(self._tab_agent)

        self._tabview.set("Agent")

        # 테마 토글 (탭뷰 우측 상단 오버레이)
        self._theme_menu = ctk.CTkOptionMenu(
            self,
            values=list(_APPEARANCE_LABELS.values()),
            width=90,
            font=(_FONT, 11),
            command=self._on_theme_change,
        )
        self._theme_menu.set(_APPEARANCE_LABELS.get(config.get_appearance(), "시스템"))
        self._theme_menu.place(relx=1.0, x=-12, y=14, anchor="ne")

        # GTX4CMD 파라미터 패널 (우측)
        self._param_panel = ParameterPanel(self)
        self._param_panel.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="ns")

    def _on_theme_change(self, label: str) -> None:
        appearance = _APPEARANCE_REVERSE.get(label, "system")
        ctk.set_appearance_mode(appearance.capitalize())
        config.set_appearance(appearance)

    def _build_watcher_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        # --- 상태 바 ---
        status_frame = ctk.CTkFrame(parent, fg_color=_FRAME_BG, corner_radius=8)
        status_frame.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)

        self._status_dot = ctk.CTkLabel(
            status_frame, text="●", font=(_FONT, 16), text_color=_GRAY,
        )
        self._status_dot.grid(row=0, column=0, padx=(12, 4), pady=8)

        self._status_label = ctk.CTkLabel(
            status_frame, text="중지됨",
            font=(_FONT, 14, "bold"), text_color=_TEXT,
        )
        self._status_label.grid(row=0, column=1, sticky="w")

        # --- 설정 정보 ---
        info_frame = ctk.CTkFrame(parent, fg_color=_FRAME_BG, corner_radius=8)
        info_frame.grid(row=1, column=0, padx=8, pady=4, sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)

        mode_display = "win32print 직접" if config.PRINTER_MODE == "direct" else "GTX4CMD.exe 경유"
        settings = [
            ("프린터", config.PRINTER_NAME),
            ("출력 모드", mode_display),
            ("감시 폴더", config.WATCH_DIR),
            ("렌더 DPI", str(config.RENDER_DPI)),
        ]

        for i, (label, value) in enumerate(settings):
            ctk.CTkLabel(
                info_frame, text=label,
                font=(_FONT, 12), text_color=_TEXT_MUTED,
            ).grid(row=i, column=0, padx=(12, 8), pady=2, sticky="w")
            ctk.CTkLabel(
                info_frame, text=str(value), anchor="w",
                font=(_FONT, 12), text_color=_TEXT,
            ).grid(row=i, column=1, padx=(0, 12), pady=2, sticky="w")

        # --- 설정 버튼 ---
        settings_btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        settings_btn_frame.grid(row=2, column=0, padx=8, pady=(0, 4), sticky="ew")

        self._settings_btn = ctk.CTkButton(
            settings_btn_frame, text="⚙ 설정", command=self._open_settings,
            font=(_FONT, 12), fg_color=_GRAY, hover_color="#6B6360",
            corner_radius=8, width=80, height=28,
        )
        self._settings_btn.pack(side="right")

        # --- 로그 ---
        self._log_text = ctk.CTkTextbox(
            parent, state="disabled",
            font=(_FONT, 11),
            fg_color=_LOG_BG, text_color=_LOG_TEXT,
            corner_radius=8,
        )
        self._log_text.grid(row=3, column=0, padx=8, pady=4, sticky="nsew")

        # --- 시작/정지 버튼 ---
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=4, column=0, padx=8, pady=(4, 8), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        self._start_btn = ctk.CTkButton(
            btn_frame, text="시작", command=self._start,
            font=(_FONT, 13), fg_color=_BLUE,
            hover_color="#6B8EA8", corner_radius=8,
        )
        self._start_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self._stop_btn = ctk.CTkButton(
            btn_frame, text="중지", command=self._stop,
            font=(_FONT, 13), fg_color=_GRAY,
            hover_color="#6B6360", corner_radius=8, state="disabled",
        )
        self._stop_btn.grid(row=0, column=1, padx=(4, 0), sticky="ew")

    def _build_agent_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        # --- 연결 상태 ---
        status_frame = ctk.CTkFrame(parent, fg_color=_FRAME_BG, corner_radius=8)
        status_frame.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)

        self._agent_dot = ctk.CTkLabel(
            status_frame, text="●", font=(_FONT, 16), text_color=_GRAY,
        )
        self._agent_dot.grid(row=0, column=0, padx=(12, 4), pady=8)

        self._agent_status_label = ctk.CTkLabel(
            status_frame, text="중지됨",
            font=(_FONT, 14, "bold"), text_color=_TEXT,
        )
        self._agent_status_label.grid(row=0, column=1, sticky="w")

        # --- 설정 정보 ---
        info_frame = ctk.CTkFrame(parent, fg_color=_FRAME_BG, corner_radius=8)
        info_frame.grid(row=1, column=0, padx=8, pady=4, sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)

        api_key_display = (config.API_KEY[:12] + "...") if config.API_KEY else "(미설정)"
        agent_settings = [
            ("테넌트", config.API_TENANT or "(미설정)"),
            ("서버", config.API_BASE_URL),
            ("API 키", api_key_display),
            ("풀링 간격", f"{config.API_POLL_INTERVAL}초"),
            ("다운로드", config.DOWNLOAD_DIR),
        ]

        for i, (label, value) in enumerate(agent_settings):
            ctk.CTkLabel(
                info_frame, text=label,
                font=(_FONT, 12), text_color=_TEXT_MUTED,
            ).grid(row=i, column=0, padx=(12, 8), pady=2, sticky="w")
            ctk.CTkLabel(
                info_frame, text=str(value), anchor="w",
                font=(_FONT, 12), text_color=_TEXT,
            ).grid(row=i, column=1, padx=(0, 12), pady=2, sticky="w")

        # --- 설정 버튼 ---
        agent_settings_btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        agent_settings_btn_frame.grid(row=2, column=0, padx=8, pady=(0, 4), sticky="ew")

        self._agent_settings_btn = ctk.CTkButton(
            agent_settings_btn_frame, text="⚙ 설정", command=self._open_settings,
            font=(_FONT, 12), fg_color=_GRAY, hover_color="#6B6360",
            corner_radius=8, width=80, height=28,
        )
        self._agent_settings_btn.pack(side="right")

        # --- 로그 (공유) ---
        self._agent_log = ctk.CTkTextbox(
            parent, state="disabled",
            font=(_FONT, 11),
            fg_color=_LOG_BG, text_color=_LOG_TEXT,
            corner_radius=8,
        )
        self._agent_log.grid(row=3, column=0, padx=8, pady=4, sticky="nsew")

        # --- 버튼 ---
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=4, column=0, padx=8, pady=(4, 8), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._auth_btn = ctk.CTkButton(
            btn_frame, text="인증", command=self._authenticate,
            font=(_FONT, 13), fg_color=_GRAY,
            hover_color="#6B6360", corner_radius=8,
        )
        self._auth_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self._agent_start_btn = ctk.CTkButton(
            btn_frame, text="시작", command=self._start_agent,
            font=(_FONT, 13), fg_color=_BLUE,
            hover_color="#6B8EA8", corner_radius=8,
        )
        self._agent_start_btn.grid(row=0, column=1, padx=4, sticky="ew")

        self._agent_stop_btn = ctk.CTkButton(
            btn_frame, text="중지", command=self._stop_agent,
            font=(_FONT, 13), fg_color=_GRAY,
            hover_color="#6B6360", corner_radius=8, state="disabled",
        )
        self._agent_stop_btn.grid(row=0, column=2, padx=(4, 0), sticky="ew")

    # ─── 상태 ───

    def _update_status(self):
        if self._running:
            self._status_dot.configure(text_color=_GREEN)
            self._status_label.configure(text="감시 중")
            self._start_btn.configure(state="disabled", fg_color=_GRAY)
            self._stop_btn.configure(state="normal", fg_color=_CORAL, hover_color="#C47A6B")
        else:
            self._status_dot.configure(text_color=_GRAY)
            self._status_label.configure(text="중지됨")
            self._start_btn.configure(state="normal", fg_color=_BLUE)
            self._stop_btn.configure(state="disabled", fg_color=_GRAY)

    # ─── 시작/정지 ───

    def _start(self):
        if self._running:
            return
        from watcher import start_watching
        self._observer = start_watching()
        self._running = True
        self._update_status()
        logger.info("=== Brother GTX-4 Watcher ===")
        logger.info("프린터: %s", config.PRINTER_NAME)
        logger.info("출력 모드: %s", config.PRINTER_MODE)
        logger.info("감시 폴더: %s", config.WATCH_DIR)

    def _stop(self):
        if not self._running:
            return
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._running = False
        self._update_status()
        logger.info("감시 중지됨")

    # ─── 로그 폴링 ───

    def _poll_log_queue(self):
        has_new = False
        while not self._log_queue.empty():
            try:
                msg = self._log_queue.get_nowait()
                for textbox in (self._log_text, self._agent_log):
                    textbox.configure(state="normal")
                    textbox.insert("end", msg + "\n")
                    textbox.configure(state="disabled")
                has_new = True
            except queue.Empty:
                break

        if has_new:
            self._log_text.see("end")
            self._agent_log.see("end")
            self._trim_log(self._log_text)
            self._trim_log(self._agent_log)

        self.after(100, self._poll_log_queue)

    def _trim_log(self, textbox):
        content = textbox.get("1.0", "end")
        lines = content.split("\n")
        if len(lines) > self.MAX_LOG_LINES:
            textbox.configure(state="normal")
            textbox.delete("1.0", f"{len(lines) - self.MAX_LOG_LINES}.0")
            textbox.configure(state="disabled")

    # ─── Agent ───

    def _authenticate(self):
        import threading
        from auth import authenticate

        if not config.API_TENANT:
            logger.error("테넌트가 설정되지 않았습니다. 설정에서 입력하세요.")
            return

        def _auth_thread():
            try:
                api_key = authenticate(config.API_BASE_URL, config.API_TENANT)
                config.save_value("api", "api_key", api_key)
                config.reload()
                logger.info("API 키 저장 완료")
            except Exception as e:
                logger.error("인증 실패: %s", e)

        threading.Thread(target=_auth_thread, daemon=True).start()

    def _start_agent(self):
        from agent import AgentWorker

        if self._agent and self._agent.is_running:
            return
        self._agent = AgentWorker()
        self._agent.start()
        self._update_agent_status()

    def _stop_agent(self):
        if self._agent:
            self._agent.stop()
            self._agent = None
        self._update_agent_status()

    def _update_agent_status(self):
        running = self._agent and self._agent.is_running
        if running:
            self._agent_dot.configure(text_color=_GREEN)
            self._agent_status_label.configure(text="풀링 중")
            self._agent_start_btn.configure(state="disabled", fg_color=_GRAY)
            self._agent_stop_btn.configure(state="normal", fg_color=_CORAL, hover_color="#C47A6B")
        else:
            self._agent_dot.configure(text_color=_GRAY)
            self._agent_status_label.configure(text="중지됨")
            self._agent_start_btn.configure(state="normal", fg_color=_BLUE)
            self._agent_stop_btn.configure(state="disabled", fg_color=_GRAY)

    # ─── 설정 다이얼로그 ───

    def _open_settings(self):
        SettingsDialog(self)

    # ─── 종료 ───

    def _on_closing(self):
        self._stop()
        self._stop_agent()
        self.destroy()

    # ─── 재시작 ───

    def restart_app(self):
        """현재 watcher/agent 정지 후 새 프로세스로 재시작."""
        self._stop()
        self._stop_agent()
        args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, *sys.argv]
        try:
            subprocess.Popen(args, close_fds=True)
        finally:
            self.destroy()
            os._exit(0)


class SettingsDialog(ctk.CTkToplevel):
    """설정 편집 다이얼로그."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("설정")
        self.geometry("520x860")
        self.minsize(520, 760)
        self.configure(fg_color=_BG)
        self.transient(parent)
        self.grab_set()
        self._parent = parent

        self.grid_columnconfigure(1, weight=1)

        row = 0

        # --- printer ---
        row = self._section_header("프린터", row)
        self._printer_name = self._entry_row("프린터명", config.PRINTER_NAME, row)
        row += 1
        self._printer_mode = self._combo_row(
            "출력 모드", ["direct", "gtx4cmd"], config.PRINTER_MODE, row,
        )
        row += 1

        # --- gtx4cmd ---
        row = self._section_header("GTX4CMD", row)
        self._exe_path = self._entry_row("exe 경로", config.GTX4CMD_EXE, row)
        row += 1

        browse_btn = ctk.CTkButton(
            self, text="찾기...", command=self._browse_exe,
            font=(_FONT, 11), fg_color=_GRAY, hover_color="#6B6360",
            width=60, height=24, corner_radius=6,
        )
        browse_btn.grid(row=row - 1, column=2, padx=(4, 12), pady=2)

        platen_options = ["0: 16x21", "1: 16x18", "2: 14x16", "3: 10x12", "4: 7x8"]
        current_platen = platen_options[config.PLATEN_SIZE] if config.PLATEN_SIZE < len(platen_options) else platen_options[0]
        self._platen_size = self._combo_row("플래튼 크기", platen_options, current_platen, row)
        row += 1

        ink_options = ["0: Color Only", "1: White Only", "2: Color+White", "3: Black Only"]
        current_ink = ink_options[config.INK] if config.INK < len(ink_options) else ink_options[0]
        self._ink = self._combo_row("잉크 조합", ink_options, current_ink, row)
        row += 1

        self._copies = self._entry_row("인쇄 매수", str(config.COPIES), row)
        row += 1
        self._position = self._entry_row("인쇄 위치", config.POSITION, row)
        row += 1

        # --- folder ---
        row = self._section_header("폴더", row)
        self._watch_dir = self._entry_row("감시 폴더", config.WATCH_DIR, row)
        row += 1
        self._done_dir = self._entry_row("완료 폴더", config.DONE_DIR, row)
        row += 1
        self._error_dir = self._entry_row("에러 폴더", config.ERROR_DIR, row)
        row += 1

        # --- render ---
        row = self._section_header("렌더링", row)
        self._render_dpi = self._entry_row("DPI", str(config.RENDER_DPI), row)
        row += 1

        # --- api ---
        row = self._section_header("Agent (API)", row)
        self._api_tenant = self._entry_row("테넌트", config.API_TENANT, row)
        row += 1
        self._api_base_url = self._entry_row("서버 URL", config.API_BASE_URL, row)
        row += 1
        self._api_poll_interval = self._entry_row("풀링 간격 (초)", str(config.API_POLL_INTERVAL), row)
        row += 1
        self._download_dir = self._entry_row("다운로드 폴더", config.DOWNLOAD_DIR, row)
        row += 1

        # --- 저장 버튼 ---
        save_btn = ctk.CTkButton(
            self, text="저장", command=self._save,
            font=(_FONT, 13), fg_color=_BLUE,
            hover_color="#6B8EA8", corner_radius=8,
        )
        save_btn.grid(row=row, column=0, columnspan=3, padx=12, pady=12, sticky="ew")

    def _section_header(self, text: str, row: int) -> int:
        ctk.CTkLabel(
            self, text=text, font=(_FONT, 13, "bold"), text_color=_TEXT,
        ).grid(row=row, column=0, columnspan=2, padx=12, pady=(12, 4), sticky="w")
        return row + 1

    def _entry_row(self, label: str, value: str, row: int) -> ctk.CTkEntry:
        ctk.CTkLabel(
            self, text=label, font=(_FONT, 11), text_color=_TEXT_MUTED,
        ).grid(row=row, column=0, padx=(12, 8), pady=2, sticky="w")
        entry = ctk.CTkEntry(self, font=(_FONT, 11), fg_color=_LOG_BG, text_color=_TEXT)
        entry.grid(row=row, column=1, padx=(0, 12), pady=2, sticky="ew")
        entry.insert(0, value)
        return entry

    def _combo_row(self, label: str, values: list, current: str, row: int) -> ctk.CTkComboBox:
        ctk.CTkLabel(
            self, text=label, font=(_FONT, 11), text_color=_TEXT_MUTED,
        ).grid(row=row, column=0, padx=(12, 8), pady=2, sticky="w")
        combo = ctk.CTkComboBox(
            self, values=values, font=(_FONT, 11),
            fg_color=_LOG_BG, text_color=_TEXT, dropdown_fg_color=_FRAME_BG,
        )
        combo.grid(row=row, column=1, padx=(0, 12), pady=2, sticky="ew")
        combo.set(current)
        return combo

    def _browse_exe(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="GTX4CMD.exe 선택",
            filetypes=[("실행 파일", "*.exe"), ("모든 파일", "*.*")],
        )
        if path:
            self._exe_path.delete(0, "end")
            self._exe_path.insert(0, path)

    def _save(self):
        config.save_value("printer", "name", self._printer_name.get())
        config.save_value("printer", "mode", self._printer_mode.get())
        config.save_value("gtx4cmd", "exe_path", self._exe_path.get())
        config.save_value("gtx4cmd", "platen_size", self._platen_size.get().split(":")[0])
        config.save_value("gtx4cmd", "ink", self._ink.get().split(":")[0])
        config.save_value("gtx4cmd", "copies", self._copies.get())
        config.save_value("gtx4cmd", "position", self._position.get())
        config.save_value("folder", "watch", self._watch_dir.get())
        config.save_value("folder", "done", self._done_dir.get())
        config.save_value("folder", "error", self._error_dir.get())
        config.save_value("render", "dpi", self._render_dpi.get())

        config.save_value("api", "tenant", self._api_tenant.get())
        config.save_value("api", "base_url", self._api_base_url.get())
        config.save_value("api", "poll_interval", self._api_poll_interval.get())
        config.save_value("download", "dir", self._download_dir.get())

        config.reload()
        logger.info("설정 저장 완료")
        self.destroy()
        _prompt_restart(self._parent)


class ParameterPanel(ctk.CTkFrame):
    """우측 Print Settings 패널 — GTX Graphics Lab Print Settings 다이얼로그를 본뜸.

    슬라이더/드롭다운/토글 위주, 변경 시 Print Time / Whiteness 추정값 즉시 반영.
    """

    _WIDTH = 480

    _OPTS_PLATEN = [(0, "16x21 inches"), (1, "16x18 inches"), (2, "14x16 inches"),
                    (3, "10x12 inches"), (4, "7x8 inches")]
    _OPTS_INK = [(0, "Color Ink"), (1, "White Ink"), (2, "Color + White Ink"), (3, "Black Ink")]
    _OPTS_MACHINE = [(0, "GTX-422")]
    _OPTS_RESOLUTION = [(1, "1200dpi")]
    _OPTS_WHITE_AS = [(0, "Transparent"), (1, "White Ink")]

    def __init__(self, parent):
        super().__init__(parent, fg_color=_FRAME_BG, corner_radius=8, width=self._WIDTH)
        self._parent = parent
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="Print Settings",
            font=(_FONT, 13, "bold"), text_color=_TEXT,
        ).grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self._scroll.grid(row=1, column=0, padx=6, pady=0, sticky="nsew")
        self._scroll.grid_columnconfigure(1, weight=1)

        self._widgets: dict = {}
        self._row = 0
        self._build_sections()

        # 하단 추정값 (Print Time × / Whiteness %)
        status = ctk.CTkFrame(self, fg_color=_LOG_BG, corner_radius=6)
        status.grid(row=2, column=0, padx=10, pady=(6, 4), sticky="ew")
        status.grid_columnconfigure((0, 1), weight=1)
        self._print_time_label = ctk.CTkLabel(
            status, text="Print Time x1.00",
            font=(_FONT, 11), text_color=_TEXT,
        )
        self._print_time_label.grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self._whiteness_label = ctk.CTkLabel(
            status, text="Whiteness 0%",
            font=(_FONT, 11), text_color=_TEXT,
        )
        self._whiteness_label.grid(row=0, column=1, padx=10, pady=6, sticky="e")

        save_btn = ctk.CTkButton(
            self, text="저장", command=self._save,
            font=(_FONT, 12), fg_color=_BLUE,
            hover_color="#6B8EA8", corner_radius=6, height=32,
        )
        save_btn.grid(row=3, column=0, padx=10, pady=(4, 10), sticky="ew")

        self._update_status()

    # ─── 섹션 빌드 ───

    def _build_sections(self):
        self._add_header("Main Settings")
        self._add_combo("machine_mode", "Machine Mode", "MACHINE_MODE", self._OPTS_MACHINE)
        self._add_combo("resolution", "Resolution", "RESOLUTION", self._OPTS_RESOLUTION)
        self._add_combo("ink", "Select Ink", "INK", self._OPTS_INK)
        self._add_combo("platen_size", "Platen Size", "PLATEN_SIZE", self._OPTS_PLATEN)
        self._add_switch("eco_mode", "Eco Mode", "ECO_MODE")
        self._add_switch("material_black", "Use Background Black Color", "MATERIAL_BLACK")
        self._add_switch("multiple", "Color Multiple Pass Printing", "MULTIPLE")
        self._add_switch("uni_print", "Unidirectional Printing", "UNI_PRINT")

        self._add_header("White Ink Settings")
        self._add_slider("highlight", "Highlight", "HIGHLIGHT", 1, 9)
        self._add_slider("mask", "Mask", "MASK", 1, 5)
        self._add_slider("min_white", "Min White", "MIN_WHITE", 1, 6)
        self._add_slider("choke", "Choke", "CHOKE", 0, 10)
        self._add_switch("pause", "W/C Pause", "PAUSE")

        self._add_header("Color Ink Settings")
        self._add_slider("ink_volume", "Ink Volume", "INK_VOLUME", 1, 10)
        self._add_slider("double_print", "Double Printing", "DOUBLE_PRINT", 0, 3)

        self._add_header("Transparent Color")
        self._add_switch("trans_color", "Use Transparent Color", "TRANS_COLOR")
        self._add_entry("color_trans", "RGB (decimal)", "COLOR_TRANS")
        self._add_slider("tolerance", "Tolerance", "TOLERANCE", 0, 50)

        self._add_header("Image Adjustment")
        self._add_slider("saturation", "Saturation", "SATURATION", 0, 40)
        self._add_slider("brightness", "Brightness", "BRIGHTNESS", 0, 40)
        self._add_slider("contrast", "Contrast", "CONTRAST", 0, 40)

        self._add_header("Color Balance")
        self._add_slider("cyan_balance", "Cyan", "CYAN_BALANCE", -5, 5)
        self._add_slider("magenta_balance", "Magenta", "MAGENTA_BALANCE", -5, 5)
        self._add_slider("yellow_balance", "Yellow", "YELLOW_BALANCE", -5, 5)
        self._add_slider("black_balance", "Black", "BLACK_BALANCE", -5, 5)

        self._add_header("Position & Size")
        self._add_switch("auto_center", "Auto Center", "AUTO_CENTER")
        self._add_entry("position", "Position (8 digits)", "POSITION")
        self._add_entry("size", "Size (8 digits)", "SIZE")
        self._add_entry("magnification", "Magnification (4 digits)", "MAGNIFICATION")
        self._add_combo("white_as", "RGB(255) Interpretation", "WHITE_AS", self._OPTS_WHITE_AS)

        self._add_header("Output")
        self._add_entry("copies", "Copies", "COPIES")

    # ─── 위젯 헬퍼 ───

    def _add_header(self, text: str):
        if self._row > 0:
            ctk.CTkFrame(self._scroll, fg_color="transparent", height=4).grid(
                row=self._row, column=0, columnspan=3, sticky="ew",
            )
            self._row += 1
        ctk.CTkLabel(
            self._scroll, text=text,
            font=(_FONT, 11, "bold"), text_color=_BLUE,
        ).grid(row=self._row, column=0, columnspan=3, padx=4, pady=(8, 4), sticky="w")
        self._row += 1

    def _add_label(self, text: str):
        ctk.CTkLabel(
            self._scroll, text=text,
            font=(_FONT, 11), text_color=_TEXT_MUTED,
        ).grid(row=self._row, column=0, padx=(6, 8), pady=3, sticky="w")

    def _add_combo(self, key: str, label: str, attr: str, options: list):
        self._add_label(label)
        current = getattr(config, attr)
        display = [d for _, d in options]
        match = next((d for v, d in options if v == current), display[0])
        widget = ctk.CTkComboBox(
            self._scroll, values=display, font=(_FONT, 11),
            fg_color=_LOG_BG, text_color=_TEXT, dropdown_fg_color=_FRAME_BG,
            height=28, state="readonly",
            command=lambda _: self._update_status(),
        )
        widget.grid(row=self._row, column=1, columnspan=2, padx=(0, 6), pady=3, sticky="ew")
        widget.set(match)
        self._widgets[key] = {"kind": "combo", "widget": widget, "options": options}
        self._row += 1

    def _add_slider(self, key: str, label: str, attr: str, lo: int, hi: int):
        self._add_label(label)
        current = getattr(config, attr)
        try:
            cur_int = int(current)
        except (TypeError, ValueError):
            cur_int = lo
        cur_int = max(lo, min(hi, cur_int))

        value_label = ctk.CTkLabel(
            self._scroll, text=str(cur_int),
            font=(_FONT, 11), text_color=_TEXT, width=32,
        )
        value_label.grid(row=self._row, column=2, padx=(4, 6), pady=3)

        slider = ctk.CTkSlider(
            self._scroll, from_=lo, to=hi,
            number_of_steps=hi - lo, height=18,
            command=lambda v, lbl=value_label: self._on_slider(v, lbl),
        )
        slider.grid(row=self._row, column=1, padx=(0, 4), pady=3, sticky="ew")
        slider.set(cur_int)
        self._widgets[key] = {"kind": "slider", "widget": slider, "label": value_label}
        self._row += 1

    def _on_slider(self, value: float, label: ctk.CTkLabel):
        label.configure(text=str(int(round(value))))
        self._update_status()

    def _add_switch(self, key: str, label: str, attr: str):
        self._add_label(label)
        current = bool(getattr(config, attr))
        widget = ctk.CTkSwitch(
            self._scroll, text="", width=40,
            command=self._update_status,
        )
        widget.grid(row=self._row, column=1, columnspan=2, padx=(0, 6), pady=3, sticky="w")
        if current:
            widget.select()
        else:
            widget.deselect()
        self._widgets[key] = {"kind": "switch", "widget": widget}
        self._row += 1

    def _add_entry(self, key: str, label: str, attr: str):
        self._add_label(label)
        current = getattr(config, attr)
        widget = ctk.CTkEntry(
            self._scroll, font=(_FONT, 11),
            fg_color=_LOG_BG, text_color=_TEXT, height=28,
        )
        widget.grid(row=self._row, column=1, columnspan=2, padx=(0, 6), pady=3, sticky="ew")
        widget.insert(0, str(current))
        widget.bind("<KeyRelease>", lambda _: self._update_status())
        self._widgets[key] = {"kind": "entry", "widget": widget}
        self._row += 1

    # ─── 값 읽기 ───

    def _read(self, key: str, default=0):
        meta = self._widgets.get(key)
        if not meta:
            return default
        kind = meta["kind"]
        widget = meta["widget"]
        if kind == "slider":
            return int(round(widget.get()))
        if kind == "switch":
            return widget.get() == 1
        if kind == "combo":
            display = widget.get()
            return next((v for v, d in meta["options"] if d == display), default)
        if kind == "entry":
            try:
                return int(widget.get())
            except ValueError:
                return default
        return default

    # ─── 추정값 갱신 ───

    def _update_status(self):
        """현재 위젯 값 기반으로 Print Time × / Whiteness % 갱신.

        Whiteness: 매뉴얼 스크린샷 단서(Highlight=5 → 400%) 기반 (Highlight - 1) × 100%.
        Print Time: 잉크 모드/멀티패스/더블프린팅/매수에 대한 근사 multiplier.
        """
        ink = self._read("ink", 0)
        highlight = self._read("highlight", 5)
        multiple = self._read("multiple", False)
        double_print = self._read("double_print", 0)
        copies = max(1, self._read("copies", 1))

        whiteness = max(0, (highlight - 1) * 100) if ink in (1, 2) else 0
        self._whiteness_label.configure(text=f"Whiteness {whiteness}%")

        if ink == 0:
            mult = 1.0
        elif ink == 1:
            mult = 1.5
        elif ink == 2:
            mult = 2.0
        else:
            mult = 1.0
        if ink in (0, 2) and multiple:
            mult *= 2.0
        if ink == 0 and double_print > 0:
            mult *= (1 + double_print)
        mult *= copies
        self._print_time_label.configure(text=f"Print Time x{mult:.2f}")

    # ─── 저장 ───

    def _save(self):
        for key, meta in self._widgets.items():
            kind = meta["kind"]
            widget = meta["widget"]
            if kind == "combo":
                display = widget.get()
                value = str(next((v for v, d in meta["options"] if d == display),
                                 meta["options"][0][0]))
            elif kind == "slider":
                value = str(int(round(widget.get())))
            elif kind == "switch":
                value = "true" if widget.get() == 1 else "false"
            elif kind == "entry":
                value = widget.get().strip()
            else:
                continue
            config.save_value("gtx4cmd", key, value)

        config.reload()
        logger.info("Print Settings 저장 완료")
        _prompt_restart(self._parent)
