"""SettingsSlidePanel — 우측 슬라이드 패널 (spec §8).

b-module 섹션:
- 페어링 (Agent API)
- 프린터
- 폴더
- 가먼트 CLI 파라미터 (필수 항목만 — 전체 30+ 항목은 config.ini 직접 편집)
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
    WIDTH = 640
    WRAP = 560
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
        self._section(body, "가먼트 CLI 파라미터", self._build_garment_cli)
        self._section(body, "렌더링", self._build_render)
        self._section(body, "정보", self._build_info)

        # 저장 (전체)
        save_row = ctk.CTkFrame(self, fg_color="transparent")
        save_row.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(
            save_row,
            text="설정 저장 (즉시 적용)",
            height=theme.TOUCH_MIN - 8,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY, weight="bold"),
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            text_color=theme.TEXT_ON_ACCENT,
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
        # font=선택값 표시 / dropdown_font=펼친 목록 — 둘 다 지정해야 한글이 기본폰트로 안 깨짐.
        combo = ctk.CTkComboBox(
            parent,
            values=values,
            font=ctk.CTkFont(family=_font_family(), size=11),
            dropdown_font=ctk.CTkFont(family=_font_family(), size=11),
        )
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
            wraplength=self.WRAP,
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

        # 가먼트 디자인 프린터 — 다중 선택, chips UI
        garment_value = ", ".join(config.GARMENT_PRINTER_NAMES)
        self._garment_name, self._garment_menu = self._printer_row(
            parent, "가먼트 프린터", garment_value, row=0,
            on_pick=self._on_garment_picked, refresh=self._refresh_garment_printers,
            hide_entry=True,
        )

        # 선택된 프린터 chips (× 버튼으로 개별 삭제)
        self._garment_chips_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._garment_chips_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 4))

        # 도움말
        ctk.CTkLabel(
            parent,
            text="드롭다운에서 프린터를 선택해 추가, × 버튼으로 개별 삭제.",
            font=ctk.CTkFont(family=_font_family(), size=10),
            text_color=theme.TEXT_MUTED,
            anchor="w",
            wraplength=self.WRAP,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        # 분배 방식 — 2대 이상일 때만 의미 있음
        dispatch_opts = ["round_robin: 순차 회전", "single: 첫 번째만 사용"]
        current_dispatch = dispatch_opts[0] if config.GARMENT_DISPATCH == "round_robin" else dispatch_opts[1]
        self._garment_dispatch = self._combo(parent, "분배 방식", dispatch_opts, current_dispatch, 3)

        self._printer_mode = self._combo(
            parent, "가먼트 출력 모드", ["cli", "direct"], config.GARMENT_MODE, 4
        )
        self._garment_enabled = ctk.CTkSwitch(
            parent, text="가먼트 자동 출력", onvalue=True, offvalue=False,
            font=ctk.CTkFont(family=_font_family(), size=12),
        )
        if config.GARMENT_ENABLED:
            self._garment_enabled.select()
        else:
            self._garment_enabled.deselect()
        self._garment_enabled.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 8))

        # 작업지시서 프린터
        self._work_order_name, self._work_order_menu = self._printer_row(
            parent, "지시서 프린터", config.WORK_ORDER_PRINTER_NAME, row=6,
            on_pick=self._on_work_order_picked, refresh=self._refresh_work_order_printers,
            allow_blank=True,
        )
        self._work_order_enabled = ctk.CTkSwitch(
            parent, text="지시서 자동 출력", onvalue=True, offvalue=False,
            font=ctk.CTkFont(family=_font_family(), size=12),
        )
        if config.WORK_ORDER_ENABLED:
            self._work_order_enabled.select()
        else:
            self._work_order_enabled.deselect()
        self._work_order_enabled.grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 8))

        # 출력 전송 방식 — 수동(작업자가 그리드에서 클릭) / 자동(받는 즉시 전송)
        self._print_mode_opts = ["수동 (작업자 클릭)", "자동 (즉시 전송)"]
        current_print_mode = self._print_mode_opts[1] if config.GARMENT_PRINT_MODE == "auto" else self._print_mode_opts[0]
        self._garment_print_mode = self._combo(parent, "전송 방식", self._print_mode_opts, current_print_mode, 8)

        # 초기 로드 (Windows에서만 실제 목록 채워짐)
        self._refresh_garment_printers()
        self._refresh_work_order_printers()
        self._render_garment_chips()

    def _printer_row(
        self, parent, label: str, value: str, *, row: int, on_pick, refresh,
        allow_blank: bool = False, hide_entry: bool = False,
    ):
        """프린터명 입력 한 줄 — Entry + OptionMenu + 새로고침 버튼. (entry, menu) 반환.

        hide_entry=True 면 entry 는 데이터 저장용으로만 두고 UI 에 노출하지 않는다
        (가먼트 chips UI 와 같이 별도 시각화를 사용하는 경우).
        """
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(family=_font_family(), size=11)).grid(
            row=row, column=0, sticky="w", pady=2
        )
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
        row_frame.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(row_frame, font=ctk.CTkFont(family=_font_family(), size=11))
        entry.insert(0, value)
        if not hide_entry:
            entry.grid(row=0, column=0, sticky="ew")

        # hide_entry 인 경우 menu 가 가로폭을 차지 → 최소 너비 넉넉히. 아니면 120.
        menu = ctk.CTkOptionMenu(
            row_frame,
            values=["선택..."],
            width=240 if hide_entry else 120,
            font=ctk.CTkFont(family=_font_family(), size=11),
            dropdown_font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_pick,
        )
        menu.set("선택...")
        if hide_entry:
            menu.grid(row=0, column=0, sticky="ew")
            menu_col_next = 1
        else:
            menu.grid(row=0, column=1, padx=(4, 0))
            menu_col_next = 2

        ctk.CTkButton(
            row_frame, text="↻", width=28,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=refresh,
        ).grid(row=0, column=menu_col_next, padx=(2, 0))

        return entry, menu

    def _render_garment_chips(self) -> None:
        """_garment_name 의 콤마 분리값을 chips 로 렌더링. 각 chip 의 × 로 개별 삭제."""
        for w in self._garment_chips_frame.winfo_children():
            w.destroy()

        current = self._garment_name.get().strip()
        names = [n.strip() for n in current.split(",") if n.strip()]

        if not names:
            ctk.CTkLabel(
                self._garment_chips_frame,
                text="선택된 프린터 없음",
                font=ctk.CTkFont(family=_font_family(), size=10),
                text_color=theme.TEXT_MUTED,
            ).pack(side="left", padx=4, pady=2)
            return

        for name in names:
            chip = ctk.CTkFrame(
                self._garment_chips_frame,
                fg_color=("gray85", "gray25"),
                corner_radius=12,
            )
            chip.pack(side="left", padx=2, pady=2)
            ctk.CTkLabel(
                chip, text=name,
                font=ctk.CTkFont(family=_font_family(), size=11),
            ).pack(side="left", padx=(8, 2), pady=2)
            ctk.CTkButton(
                chip, text="×", width=22, height=22,
                font=ctk.CTkFont(family=_font_family(), size=13),
                fg_color="transparent",
                hover_color=("gray70", "gray35"),
                command=lambda n=name: self._remove_garment_printer(n),
            ).pack(side="left", padx=(0, 4), pady=2)

    def _remove_garment_printer(self, name: str) -> None:
        """가먼트 프린터 목록에서 한 개 제거 + chips/드롭다운 갱신."""
        current = self._garment_name.get().strip()
        names = [n.strip() for n in current.split(",") if n.strip()]
        if name not in names:
            return
        names.remove(name)
        self._garment_name.delete(0, "end")
        self._garment_name.insert(0, ", ".join(names))
        self._render_garment_chips()
        self._refresh_garment_printers()

    def _refresh_printers_into(self, menu, exclude: list[str] | None = None) -> None:
        from printer import list_printers
        printers = list_printers()
        if exclude:
            excluded = {n.strip() for n in exclude if n.strip()}
            printers = [p for p in printers if p not in excluded]
        values = printers if printers else ["(설치된 프린터 없음)"]
        menu.configure(values=values)
        menu.set("선택...")

    def _refresh_garment_printers(self) -> None:
        # 이미 입력란에 들어 있는 프린터는 드롭다운에서 제외
        current = self._garment_name.get().strip() if hasattr(self, "_garment_name") else ""
        excluded = [n.strip() for n in current.split(",") if n.strip()]
        self._refresh_printers_into(self._garment_menu, exclude=excluded)

    def _refresh_work_order_printers(self) -> None:
        self._refresh_printers_into(self._work_order_menu)

    def _pick_into(self, entry, menu, name: str) -> None:
        if not name or name in ("선택...", "(설치된 프린터 없음)"):
            return
        entry.delete(0, "end")
        entry.insert(0, name)
        menu.set("선택...")

    def _append_into(self, entry, menu, name: str) -> None:
        """다중 입력용 — 끝에 콤마로 추가. 중복은 무시."""
        if not name or name in ("선택...", "(설치된 프린터 없음)"):
            return
        current = entry.get().strip()
        names = [n.strip() for n in current.split(",") if n.strip()]
        if name in names:
            menu.set("선택...")
            return
        names.append(name)
        entry.delete(0, "end")
        entry.insert(0, ", ".join(names))
        menu.set("선택...")

    def _on_garment_picked(self, name: str) -> None:
        # 가먼트는 다중 입력 — append + 드롭다운/chips 재구성
        self._append_into(self._garment_name, self._garment_menu, name)
        self._refresh_garment_printers()
        self._render_garment_chips()

    def _on_work_order_picked(self, name: str) -> None:
        # 지시서는 단일 — 덮어쓰기
        self._pick_into(self._work_order_name, self._work_order_menu, name)

    # ── 폴더 ────────────────────────────────
    def _build_folders(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        self._watch_dir = self._entry(parent, "감시(incoming)", config.INCOMING_DIR, 0)
        self._done_dir = self._entry(parent, "완료(done)", config.DONE_DIR, 1)
        self._error_dir = self._entry(parent, "에러(error)", config.ERROR_DIR, 2)
        self._download_dir = self._entry(parent, "다운로드", config.DOWNLOAD_DIR, 3)

    # ── 가먼트 CLI (필수만, 전체는 config.ini) ──
    def _build_garment_cli(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="기본은 Windows 드라이버명으로 장비 계열을 자동 선택",
            font=ctk.CTkFont(family=_font_family(), size=10),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        cli_opts = ["auto: 자동", "pro: GTXpro", "legacy: GTX-4"]
        current_cli = next((opt for opt in cli_opts if opt.startswith(config.GTX_CLI + ":")), cli_opts[0])
        self._gtx_cli = self._combo(parent, "장비 계열", cli_opts, current_cli, 1)

        platen_opts = ["0: 16x21", "1: 16x18", "2: 14x16", "3: 10x12", "4: 7x8"]
        current_platen = platen_opts[config.PLATEN_SIZE] if config.PLATEN_SIZE < len(platen_opts) else platen_opts[0]
        self._platen_size = self._combo(parent, "플래튼", platen_opts, current_platen, 2)

        ink_opts = ["0: Color", "1: White", "2: Color+White", "3: Black"]
        current_ink = ink_opts[config.INK] if config.INK < len(ink_opts) else ink_opts[0]
        self._ink = self._combo(parent, "잉크", ink_opts, current_ink, 3)

        self._copies = self._entry(parent, "매수", str(config.COPIES), 4)
        self._position = self._entry(parent, "위치(8자리)", config.POSITION, 5)

        ctk.CTkLabel(
            parent,
            text="고급 파라미터는 config.ini 직접 편집",
            font=ctk.CTkFont(family=_font_family(), size=10),
            text_color=theme.TEXT_MUTED,
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))

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
            wraplength=self.WRAP,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        ctk.CTkButton(
            parent,
            text="config.ini 편집",
            width=120,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=lambda: _open_in_editor(Path(config.INI_PATH)),
        ).grid(row=1, column=0, sticky="w", pady=2)


    # ── 저장 ────────────────────────────────
    def _save_all(self) -> None:
        try:
            config.save_value("api", "tenant", self._api_tenant.get())
            config.save_value("api", "base_url", self._api_base_url.get())
            config.save_value("api", "poll_interval", self._api_poll_interval.get())

            config.save_value("printer", "garment_name", self._garment_name.get())
            config.save_value("printer", "garment_mode", self._printer_mode.get())
            config.save_value("printer", "garment_enabled", "true" if self._garment_enabled.get() else "false")
            # 분배 방식 — 콤보 라벨 앞부분만 추출
            dispatch_val = self._garment_dispatch.get().split(":")[0].strip()
            config.save_value("printer", "garment_dispatch", dispatch_val)
            config.save_value("printer", "work_order_name", self._work_order_name.get())
            config.save_value("printer", "work_order_enabled", "true" if self._work_order_enabled.get() else "false")
            # 전송 방식 — 콤보 라벨 → manual/auto
            print_mode_val = "auto" if self._garment_print_mode.get() == self._print_mode_opts[1] else "manual"
            config.save_value("printer", "garment_print_mode", print_mode_val)
            # 하위호환: 기존 name/mode도 가먼트 키와 동기화
            config.save_value("printer", "name", self._garment_name.get())
            config.save_value("printer", "mode", self._printer_mode.get())

            config.save_value("paths", "incoming", self._watch_dir.get())
            config.save_value("paths", "done", self._done_dir.get())
            config.save_value("paths", "error", self._error_dir.get())
            config.save_value("download", "dir", self._download_dir.get())

            config.save_value("garment_cli", "gtx_cli", self._gtx_cli.get().split(":")[0])
            config.save_value("garment_cli", "platen_size", self._platen_size.get().split(":")[0])
            config.save_value("garment_cli", "ink", self._ink.get().split(":")[0])
            config.save_value("garment_cli", "copies", self._copies.get())
            config.save_value("garment_cli", "position", self._position.get())
            config.save_value("render", "dpi", self._render_dpi.get())
            config.reload()
            # agent/dispatcher 가 config 모듈 변수를 매 작업마다 동적으로 읽으므로 재시작 불필요.
            self._save_msg.configure(text="저장됨 — 즉시 적용됨", text_color=theme.SUCCESS)
        except Exception as e:
            self._save_msg.configure(text=f"저장 실패: {e}", text_color=theme.DANGER)
