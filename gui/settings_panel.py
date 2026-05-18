"""SettingsSlidePanel — 우측 슬라이드 패널 (spec §8).

b-module 섹션:
- 페어링 (Agent API)
- 프린터
- 폴더
- GTX4CMD 파라미터 (필수 항목만 — 전체 30+ 항목은 config.ini 직접 편집)
- 렌더링
- 정보
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import config
from auth import authenticate
from fonts import family as _font_family

from . import theme

logger = logging.getLogger(__name__)


def _open_in_editor(path: Path) -> None:
    if not path.exists():
        return
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-t", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class SettingsPanel(ctk.CTkFrame):
    WIDTH = 400
    ANIM_MS = 220
    ANIM_STEPS = 12

    def __init__(self, root: ctk.CTk) -> None:
        super().__init__(root, width=self.WIDTH, corner_radius=0, fg_color=theme.SURFACE)
        self._open = False

        self.place(relx=1.0, rely=0, anchor="ne", relheight=1.0, x=self.WIDTH)
        self._build()

    # ── 외부 API ─────────────────────────────
    def open(self) -> None:
        if self._open:
            return
        self._open = True
        self.lift()
        self._slide(target_x=0)

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self._slide(target_x=self.WIDTH)

    def toggle(self) -> None:
        if self._open:
            self.close()
        else:
            self.open()

    def _slide(self, *, target_x: int) -> None:
        info = self.place_info()
        current_x = int(float(info.get("x", 0)))
        delta = (target_x - current_x) / self.ANIM_STEPS
        step_delay = max(1, self.ANIM_MS // self.ANIM_STEPS)

        def step(i: int) -> None:
            new_x = int(current_x + delta * i)
            self.place_configure(x=new_x)
            if i < self.ANIM_STEPS:
                self.after(step_delay, lambda: step(i + 1))
            else:
                self.place_configure(x=target_x)

        step(1)

    # ── UI ──────────────────────────────────
    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(
            header,
            text="설정",
            font=ctk.CTkFont(family=_font_family(), size=14, weight="bold"),
            text_color=theme.TEXT,
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="⨯",
            width=32,
            font=ctk.CTkFont(family=_font_family(), size=14),
            command=self.close,
        ).pack(side="right")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._section(body, "페어링 (Agent API)", self._build_pairing)
        self._section(body, "프린터", self._build_printer)
        self._section(body, "폴더", self._build_folders)
        self._section(body, "GTX4CMD 파라미터", self._build_gtx4cmd)
        self._section(body, "렌더링", self._build_render)
        self._section(body, "정보", self._build_info)

        # 저장 (전체)
        save_row = ctk.CTkFrame(self, fg_color="transparent")
        save_row.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(
            save_row,
            text="설정 저장 (재시작 필요)",
            font=ctk.CTkFont(family=_font_family(), size=12, weight="bold"),
            command=self._save_all,
        ).pack(fill="x")

        self._save_msg = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=10),
            text_color=theme.SUCCESS,
        )
        self._save_msg.pack(fill="x", padx=12, pady=(0, 8))

    def _section(self, parent, title: str, builder) -> None:
        wrap = ctk.CTkFrame(parent, corner_radius=theme.CORNER, fg_color=theme.SURFACE_2)
        wrap.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            wrap,
            text=title,
            font=ctk.CTkFont(family=_font_family(), size=12, weight="bold"),
            text_color=theme.TEXT,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        inner = ctk.CTkFrame(wrap, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=(0, 10))
        builder(inner)

    def _entry(self, parent, label: str, value: str, row: int) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(family=_font_family(), size=11)).grid(
            row=row, column=0, sticky="w", pady=2
        )
        entry = ctk.CTkEntry(parent, font=ctk.CTkFont(family=_font_family(), size=11))
        entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
        entry.insert(0, value)
        return entry

    def _combo(self, parent, label: str, values: list[str], current: str, row: int) -> ctk.CTkComboBox:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(family=_font_family(), size=11)).grid(
            row=row, column=0, sticky="w", pady=2
        )
        combo = ctk.CTkComboBox(parent, values=values, font=ctk.CTkFont(family=_font_family(), size=11))
        combo.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
        combo.set(current)
        return combo

    # ── 페어링 ──────────────────────────────
    def _build_pairing(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        self._api_tenant = self._entry(parent, "스토어 ID", config.API_TENANT, 0)
        self._api_base_url = self._entry(parent, "Base URL", config.API_BASE_URL, 1)
        self._api_poll_interval = self._entry(parent, "풀링 간격(초)", str(config.API_POLL_INTERVAL), 2)
        # API Key는 페어링 플로우에서 자동 설정 — 마스킹 표시만
        ctk.CTkLabel(parent, text="API Key", font=ctk.CTkFont(family=_font_family(), size=11)).grid(
            row=3, column=0, sticky="w", pady=2
        )
        self._api_key_label = ctk.CTkLabel(
            parent,
            text=self._format_api_key(config.API_KEY),
            font=ctk.CTkFont(family=_font_family(), size=11),
        )
        self._api_key_label.grid(row=3, column=1, sticky="w", padx=(8, 0), pady=2)

        # 페어링 액션
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._pair_button = ctk.CTkButton(
            actions,
            text="지금 인증",
            width=120,
            font=ctk.CTkFont(family=_font_family(), size=11, weight="bold"),
            command=self._start_pairing,
        )
        self._pair_button.pack(side="right")

        self._pair_msg = ctk.CTkLabel(
            parent,
            text="스토어 ID 입력 후 '지금 인증'을 누르면 브라우저가 열립니다",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=10),
            text_color=theme.TEXT_MUTED,
            wraplength=320,
            justify="left",
        )
        self._pair_msg.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    @staticmethod
    def _format_api_key(key: str) -> str:
        return "(미설정)" if not key else f"●●●●{key[-4:]}"

    def _start_pairing(self) -> None:
        tenant = self._api_tenant.get().strip()
        base_url = self._api_base_url.get().strip() or "https://store.dpl.shop"
        if not tenant:
            self._pair_msg.configure(text="스토어 ID를 먼저 입력하세요", text_color=theme.DANGER)
            return
        # 현재 입력값 즉시 반영 — authenticate가 config 값을 참조하지 않더라도 안전
        config.save_value("api", "tenant", tenant)
        config.save_value("api", "base_url", base_url)
        config.reload()
        self._pair_button.configure(state="disabled", text="인증 중...")
        self._pair_msg.configure(text="브라우저에서 승인하세요", text_color=theme.TEXT_MUTED)
        threading.Thread(target=self._run_pairing, args=(base_url, tenant), daemon=True).start()

    def _run_pairing(self, base_url: str, tenant: str) -> None:
        try:
            api_key = authenticate(base_url, tenant)
            config.save_value("api", "api_key", api_key)
            config.reload()
            self.after(0, self._on_pairing_success)
        except Exception as e:
            logger.exception("인증 실패")
            self.after(0, lambda: self._on_pairing_failed(str(e)))

    def _on_pairing_success(self) -> None:
        self._api_key_label.configure(text=self._format_api_key(config.API_KEY))
        self._pair_button.configure(state="normal", text="지금 인증")
        self._pair_msg.configure(text="인증 완료 — Agent를 시작할 수 있습니다", text_color=theme.SUCCESS)

    def _on_pairing_failed(self, reason: str) -> None:
        self._pair_button.configure(state="normal", text="지금 인증")
        self._pair_msg.configure(text=f"인증 실패: {reason}", text_color=theme.DANGER)

    # ── 프린터 ──────────────────────────────
    def _build_printer(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(parent, text="프린터명(들)", font=ctk.CTkFont(family=_font_family(), size=11)).grid(
            row=0, column=0, sticky="w", pady=2
        )

        printer_row = ctk.CTkFrame(parent, fg_color="transparent")
        printer_row.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        printer_row.grid_columnconfigure(0, weight=1)

        # 다중 프린터(쉼표 구분) 지원 — 직접 입력 유지
        self._printer_name = ctk.CTkEntry(printer_row, font=ctk.CTkFont(family=_font_family(), size=11))
        self._printer_name.grid(row=0, column=0, sticky="ew")
        self._printer_name.insert(0, config.PRINTER_NAME)

        # 설치된 프린터 목록 선택 → Entry 값 교체
        self._printer_menu = ctk.CTkOptionMenu(
            printer_row,
            values=["선택..."],
            width=90,
            font=ctk.CTkFont(family=_font_family(), size=10),
            command=self._on_printer_picked,
        )
        self._printer_menu.set("선택...")
        self._printer_menu.grid(row=0, column=1, padx=(4, 0))

        ctk.CTkButton(
            printer_row,
            text="↻",
            width=28,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=self._refresh_printers,
        ).grid(row=0, column=2, padx=(2, 0))

        self._printer_mode = self._combo(parent, "출력 모드", ["direct", "gtx4cmd"], config.PRINTER_MODE, 1)

        # 초기 로드 (Windows에서만 실제 목록 채워짐)
        self._refresh_printers()

    def _refresh_printers(self) -> None:
        """설치된 프린터 목록을 다시 읽어 OptionMenu에 반영한다."""
        from printer import list_printers

        printers = list_printers()
        values = printers if printers else ["(설치된 프린터 없음)"]
        self._printer_menu.configure(values=values)
        self._printer_menu.set("선택...")

    def _on_printer_picked(self, name: str) -> None:
        """OptionMenu에서 프린터를 선택했을 때 Entry 값을 교체한다."""
        if not name or name in ("선택...", "(설치된 프린터 없음)"):
            return
        self._printer_name.delete(0, "end")
        self._printer_name.insert(0, name)
        self._printer_menu.set("선택...")

    # ── 폴더 ────────────────────────────────
    def _build_folders(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        self._watch_dir = self._entry(parent, "감시(incoming)", config.INCOMING_DIR, 0)
        self._done_dir = self._entry(parent, "완료(done)", config.DONE_DIR, 1)
        self._error_dir = self._entry(parent, "에러(error)", config.ERROR_DIR, 2)
        self._download_dir = self._entry(parent, "다운로드", config.DOWNLOAD_DIR, 3)

    # ── GTX4CMD (필수만, 전체는 config.ini) ──
    def _build_gtx4cmd(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)

        # exe 경로 + browse
        ctk.CTkLabel(parent, text="exe 경로", font=ctk.CTkFont(family=_font_family(), size=11)).grid(
            row=0, column=0, sticky="w", pady=2
        )
        self._exe_path = ctk.CTkEntry(parent, font=ctk.CTkFont(family=_font_family(), size=11))
        self._exe_path.grid(row=0, column=1, sticky="ew", padx=(8, 4), pady=2)
        self._exe_path.insert(0, config.GTX4CMD_EXE)
        ctk.CTkButton(
            parent,
            text="찾기",
            width=50,
            font=ctk.CTkFont(family=_font_family(), size=10),
            command=self._browse_exe,
        ).grid(row=0, column=2, padx=(0, 0), pady=2)

        platen_opts = ["0: 16x21", "1: 16x18", "2: 14x16", "3: 10x12", "4: 7x8"]
        current_platen = platen_opts[config.PLATEN_SIZE] if config.PLATEN_SIZE < len(platen_opts) else platen_opts[0]
        self._platen_size = self._combo(parent, "플래튼", platen_opts, current_platen, 1)

        ink_opts = ["0: Color", "1: White", "2: Color+White", "3: Black"]
        current_ink = ink_opts[config.INK] if config.INK < len(ink_opts) else ink_opts[0]
        self._ink = self._combo(parent, "잉크", ink_opts, current_ink, 2)

        self._copies = self._entry(parent, "매수", str(config.COPIES), 3)
        self._position = self._entry(parent, "위치(8자리)", config.POSITION, 4)

        ctk.CTkLabel(
            parent,
            text="고급 파라미터는 config.ini 직접 편집",
            font=ctk.CTkFont(family=_font_family(), size=10),
            text_color=theme.TEXT_MUTED,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # ── 렌더링 ──────────────────────────────
    def _build_render(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        self._render_dpi = self._entry(parent, "DPI", str(config.RENDER_DPI), 0)

    # ── 정보 ────────────────────────────────
    def _build_info(self, parent) -> None:
        ctk.CTkLabel(
            parent,
            text=str(config.INI_PATH),
            font=ctk.CTkFont(family=_font_family(), size=10),
            anchor="w",
            wraplength=320,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        ctk.CTkButton(
            parent,
            text="config.ini 편집",
            width=120,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=lambda: _open_in_editor(Path(config.INI_PATH)),
        ).grid(row=1, column=0, sticky="w", pady=2)

    def _browse_exe(self) -> None:
        path = filedialog.askopenfilename(
            title="GTX4CMD.exe 선택",
            filetypes=[("실행 파일", "*.exe"), ("모든 파일", "*.*")],
        )
        if path:
            self._exe_path.delete(0, "end")
            self._exe_path.insert(0, path)

    # ── 저장 ────────────────────────────────
    def _save_all(self) -> None:
        try:
            config.save_value("api", "tenant", self._api_tenant.get())
            config.save_value("api", "base_url", self._api_base_url.get())
            config.save_value("api", "poll_interval", self._api_poll_interval.get())

            config.save_value("printer", "name", self._printer_name.get())
            config.save_value("printer", "mode", self._printer_mode.get())

            config.save_value("paths", "incoming", self._watch_dir.get())
            config.save_value("paths", "done", self._done_dir.get())
            config.save_value("paths", "error", self._error_dir.get())
            config.save_value("download", "dir", self._download_dir.get())

            config.save_value("gtx4cmd", "exe_path", self._exe_path.get())
            config.save_value("gtx4cmd", "platen_size", self._platen_size.get().split(":")[0])
            config.save_value("gtx4cmd", "ink", self._ink.get().split(":")[0])
            config.save_value("gtx4cmd", "copies", self._copies.get())
            config.save_value("gtx4cmd", "position", self._position.get())
            config.save_value("render", "dpi", self._render_dpi.get())
            config.reload()
            self._save_msg.configure(text="저장됨 — 적용을 위해 재시작하세요", text_color=theme.SUCCESS)
        except Exception as e:
            self._save_msg.configure(text=f"저장 실패: {e}", text_color=theme.DANGER)
