"""ConfirmDialog — 되돌릴 수 없는 동작 앞에 세우는 확인 모달.

customtkinter 에 확인 대화상자가 없어 CTkToplevel 로 직접 만든다.
tkinter.messagebox 를 쓰지 않는 이유는 OS 기본 위젯이라 앱 테마와 따로 놀고,
한글 폰트가 등록된 프로세스 폰트를 타지 않기 때문이다.
"""

from __future__ import annotations

import customtkinter as ctk

from fonts import family as _font_family

from . import theme


class ConfirmDialog(ctk.CTkToplevel):
    """예/아니오 확인 모달. `ask()` 로 띄우고 bool 을 받는다."""

    def __init__(
        self,
        parent,
        title: str,
        message: str,
        detail: str = "",
        confirm_text: str = "삭제",
        danger: bool = True,
    ) -> None:
        super().__init__(parent)
        self._result = False

        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=theme.BG)

        accent = theme.DANGER if danger else theme.ACCENT
        accent_hover = theme.DANGER_SOFT if danger else theme.ACCENT_HOVER

        box = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=theme.CORNER_LG)
        box.pack(fill="both", expand=True, padx=theme.SP_2, pady=theme.SP_2)

        ctk.CTkLabel(
            box,
            text=message,
            anchor="w",
            justify="left",
            wraplength=340,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY_LG, weight="bold"),
            text_color=theme.TEXT,
        ).pack(fill="x", padx=20, pady=(20, 6))

        if detail:
            ctk.CTkLabel(
                box,
                text=detail,
                anchor="w",
                justify="left",
                wraplength=340,
                font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY),
                text_color=theme.TEXT_SUB,
            ).pack(fill="x", padx=20, pady=(0, 4))

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(14, 20))
        row.grid_columnconfigure((0, 1), weight=1, uniform="btn")

        _bfont = ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY, weight="bold")
        ctk.CTkButton(
            row,
            text="취소",
            width=10,
            height=42,
            corner_radius=theme.CORNER_SM,
            command=self._cancel,
            font=_bfont,
            fg_color=theme.NEUTRAL_BTN,
            hover_color=theme.NEUTRAL_HOVER,
            text_color=theme.TEXT,
        ).grid(row=0, column=0, padx=(0, theme.SP_1), sticky="ew")

        confirm = ctk.CTkButton(
            row,
            text=confirm_text,
            width=10,
            height=42,
            corner_radius=theme.CORNER_SM,
            command=self._confirm,
            font=_bfont,
            fg_color=accent,
            hover_color=accent_hover,
            text_color=theme.TEXT_ON_ACCENT,
        )
        confirm.grid(row=0, column=1, padx=(theme.SP_1, 0), sticky="ew")

        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._confirm())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._center_on(parent)
        # transient/grab 은 창이 그려진 뒤에 걸어야 일부 WM 에서 무시되지 않는다
        self.after(10, lambda: self._make_modal(confirm))

    def _make_modal(self, focus_widget) -> None:
        try:
            self.transient(self.master)
            self.grab_set()
            self.lift()
            self.focus_force()
            focus_widget.focus_set()
        except Exception:
            pass

    def _center_on(self, parent) -> None:
        self.update_idletasks()
        w, h = max(self.winfo_reqwidth(), 380), self.winfo_reqheight()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x, y = px + (pw - w) // 2, py + (ph - h) // 3
        except Exception:
            x = y = 200
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    def _confirm(self) -> None:
        self._result = True
        self.destroy()

    def _cancel(self) -> None:
        self._result = False
        self.destroy()

    @classmethod
    def ask(cls, parent, title: str, message: str, detail: str = "", confirm_text: str = "삭제") -> bool:
        dlg = cls(parent, title, message, detail, confirm_text)
        parent.wait_window(dlg)
        return dlg._result
