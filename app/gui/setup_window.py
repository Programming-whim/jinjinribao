"""首次使用引导：填写账号密码"""

import os
import customtkinter as ctk
from PIL import Image
from app.constants import (
    TD_BRAND, TD_BRAND_HOVER, TD_BRAND_LIGHT, TD_BRAND_SUBTLE,
    TD_BG_PAGE, TD_BG_CONTAINER, TD_BORDER_LEVEL1, TD_SUCCESS,
    TD_TEXT_PRIMARY, TD_TEXT_SECONDARY, TD_TEXT_PLACEHOLDER,
)


class SetupWindow(ctk.CTk):
    EYE_OPEN = "◉"
    EYE_CLOSED = "◎"

    def __init__(self, on_complete):
        super().__init__()
        self._on_complete = on_complete
        self._pw_visible = False
        self._title = "精进日报自动填写工具"
        self.title(self._title)
        self.geometry("440x500")
        self.resizable(False, False)
        self.configure(fg_color=TD_BG_PAGE)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 440) // 2
        y = (sh - 500) // 2
        self.geometry(f"440x500+{x}+{y}")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._username.focus_set()

    def _build_ui(self):
        header = ctk.CTkFrame(
            self, fg_color=TD_BG_CONTAINER, height=100, corner_radius=0,
        )
        header.pack(fill="x")
        header.pack_propagate(False)

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=32, pady=(0, 0))

        ctk.CTkLabel(
            header_inner,
            text="",
            image=ctk.CTkImage(
                light_image=Image.open(os.path.join(os.path.dirname(__file__), "..", "..", "logo.png")),
                size=(36, 36),
            ),
        ).pack(side="left", pady=(32, 0))

        ctk.CTkLabel(
            header_inner, text="欢迎使用",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(side="left", padx=(12, 0), pady=(34, 0))

        ctk.CTkLabel(
            header_inner, text="日报自动填写工具",
            font=ctk.CTkFont(size=12),
            text_color=TD_TEXT_SECONDARY,
        ).pack(side="left", padx=(6, 0), pady=(40, 0))

        ctk.CTkFrame(header, height=1, fg_color=TD_BORDER_LEVEL1).pack(fill="x", side="bottom")

        self._card = ctk.CTkFrame(
            self, fg_color=TD_BG_CONTAINER, corner_radius=10,
            border_width=1, border_color=TD_BORDER_LEVEL1,
        )
        self._card.pack(fill="x", padx=24, pady=(28, 16))

        inner = ctk.CTkFrame(self._card, fg_color="transparent")
        inner.pack(padx=24, pady=28, fill="x")

        ctk.CTkLabel(
            inner, text="首次使用请填写登录账号，后续将自动记住",
            font=ctk.CTkFont(size=11),
            text_color=TD_TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 20))

        ctk.CTkLabel(
            inner, text="手机号 / 账号",
            font=ctk.CTkFont(size=11), text_color=TD_TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", pady=(0, 6))
        self._username = ctk.CTkEntry(
            inner, font=ctk.CTkFont(size=13), height=40,
            placeholder_text="请输入手机号",
            border_color=TD_BORDER_LEVEL1, corner_radius=6,
        )
        self._username.pack(fill="x", pady=(0, 18))

        pw_label_row = ctk.CTkFrame(inner, fg_color="transparent")
        pw_label_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            pw_label_row, text="密码",
            font=ctk.CTkFont(size=11), text_color=TD_TEXT_SECONDARY, anchor="w",
        ).pack(side="left")

        self._eye_btn = ctk.CTkButton(
            pw_label_row,
            text=self.EYE_CLOSED,
            width=30, height=20,
            font=ctk.CTkFont(size=14),
            corner_radius=4,
            fg_color="transparent",
            hover_color=TD_BRAND_SUBTLE,
            text_color=TD_TEXT_PLACEHOLDER,
            command=self._toggle_pw_visibility,
        )
        self._eye_btn.pack(side="right")

        pw_row = ctk.CTkFrame(inner, fg_color="transparent")
        pw_row.pack(fill="x", pady=(0, 24))

        self._password = ctk.CTkEntry(
            pw_row, font=ctk.CTkFont(size=13), height=40,
            placeholder_text="请输入密码", show="*",
            border_color=TD_BORDER_LEVEL1, corner_radius=6,
        )
        self._password.pack(side="left", fill="x", expand=True)

        self._pw_eye_inline = ctk.CTkButton(
            pw_row,
            text="👁",
            width=36, height=40,
            font=ctk.CTkFont(size=16),
            corner_radius=6,
            fg_color=TD_BG_CONTAINER,
            hover_color=TD_BORDER_LEVEL1,
            text_color=TD_TEXT_PLACEHOLDER,
            border_width=1,
            border_color=TD_BORDER_LEVEL1,
            command=self._toggle_pw_visibility,
        )
        self._pw_eye_inline.pack(side="right", padx=(6, 0))

        self._confirm_btn = ctk.CTkButton(
            inner, text="登 录",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, corner_radius=8,
            fg_color=TD_BRAND, hover_color=TD_BRAND_HOVER,
            command=self._do_login,
        )
        self._confirm_btn.pack(fill="x")

    def _toggle_pw_visibility(self):
        self._pw_visible = not self._pw_visible
        if self._pw_visible:
            self._password.configure(show="")
            self._eye_btn.configure(text=self.EYE_OPEN, text_color=TD_BRAND)
            self._pw_eye_inline.configure(text="👁", text_color=TD_BRAND, border_color=TD_BRAND)
        else:
            self._password.configure(show="*")
            self._eye_btn.configure(text=self.EYE_CLOSED, text_color=TD_TEXT_PLACEHOLDER)
            self._pw_eye_inline.configure(text="👁", text_color=TD_TEXT_PLACEHOLDER, border_color=TD_BORDER_LEVEL1)

    def _do_login(self):
        username = self._username.get().strip()
        password = self._password.get().strip()
        if not username or not password:
            self._shake_field(self._username if not username else self._password)
            return

        self._confirm_btn.configure(
            text="正在登录...",
            state="disabled",
            fg_color=TD_TEXT_PLACEHOLDER,
        )
        self._username.configure(state="disabled")
        self._password.configure(state="disabled")
        self._eye_btn.configure(state="disabled")
        self._pw_eye_inline.configure(state="disabled")

        self.after(600, lambda: self._show_success(username, password))

    def _show_success(self, username, password):
        overlay = ctk.CTkFrame(
            self, fg_color=TD_SUCCESS, corner_radius=10,
            width=280, height=80,
        )
        overlay.place(relx=0.5, rely=0.55, anchor="center")
        overlay.lift()

        inner = ctk.CTkFrame(overlay, fg_color="transparent")
        inner.pack(expand=True)

        ctk.CTkLabel(
            inner, text="✓  登录成功",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="white",
        ).pack()

        ctk.CTkLabel(
            inner, text="正在进入系统...",
            font=ctk.CTkFont(size=11),
            text_color="#D1FAE5",
        ).pack(pady=(4, 0))

        self.after(900, lambda: self._finish_login(username, password))

    def _finish_login(self, username, password):
        self._on_complete(username, password)
        self.destroy()

    def _shake_field(self, widget):
        orig_border = widget.cget("border_color")
        widget.configure(border_color="#EF4444")
        self.after(80, lambda: widget.configure(border_color="#EF4444"))
        self.after(160, lambda: widget.configure(border_color=TD_BORDER_LEVEL1))
        self.after(260, lambda: widget.configure(border_color="#EF4444"))
        self.after(400, lambda: widget.configure(border_color=orig_border))

    def _on_close(self):
        self.destroy()

    def destroy(self):
        super().destroy()
