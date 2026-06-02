"""定时设置页：定时开关 + 时间选择 + 状态显示"""

import customtkinter as ctk
from app.constants import (
    DEFAULT_SCHEDULE_TIME,
    TD_BRAND, TD_BRAND_HOVER, TD_BRAND_LIGHT, TD_BRAND_SUBTLE,
    TD_BG_COMPONENT, TD_BG_CONTAINER, TD_BG_PAGE,
    TD_BORDER_LEVEL1, TD_BORDER_LEVEL2,
    TD_TEXT_PRIMARY, TD_TEXT_SECONDARY, TD_TEXT_PLACEHOLDER,
    TD_SUCCESS, TD_ERROR,
)
from app.gui.animations import JellyEffects


class ScheduleTab(ctk.CTkFrame):
    def __init__(self, master, config_manager, animator=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._cfg = config_manager
        self._animator = animator
        self._build_ui()
        self._load_from_config()
        self._apply_effects()

    def _apply_effects(self):
        if not self._animator:
            return
        JellyEffects.apply_button_jelly(self._save_btn, self._animator)
        JellyEffects.apply_card_hover(self._card, self._animator)

    def _build_ui(self):
        self._card = ctk.CTkFrame(
            self, fg_color=TD_BG_CONTAINER, corner_radius=10,
            border_width=1, border_color=TD_BORDER_LEVEL1,
        )
        self._card.pack(fill="x", padx=24, pady=(24, 12))

        inner = ctk.CTkFrame(self._card, fg_color="transparent")
        inner.pack(padx=32, pady=28, fill="x")

        ctk.CTkLabel(
            inner, text="定时自动填写",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            inner, text="开启后系统将每天在指定时间自动执行日报填写",
            font=ctk.CTkFont(size=12),
            text_color=TD_TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 20))

        self._switch = ctk.CTkSwitch(
            inner,
            text="启用定时自动填写",
            font=ctk.CTkFont(size=13),
            command=self._on_switch,
        )
        self._switch.pack(anchor="w", pady=(0, 20))

        ctk.CTkFrame(
            inner, height=1, fg_color=TD_BORDER_LEVEL1,
        ).pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            inner, text="每日执行时间",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TD_TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 10))

        time_row = ctk.CTkFrame(inner, fg_color="transparent")
        time_row.pack(fill="x", pady=(0, 20))

        hours = [f"{h:02d}" for h in range(24)]
        minutes = [f"{m:02d}" for m in range(60)]

        self._hour_menu = ctk.CTkOptionMenu(
            time_row, values=hours, width=80, height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=6,
            fg_color=TD_BG_COMPONENT,
            button_color=TD_BRAND,
            button_hover_color=TD_BRAND_HOVER,
        )
        self._hour_menu.pack(side="left")

        ctk.CTkLabel(
            time_row, text=" : ",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(side="left")

        self._min_menu = ctk.CTkOptionMenu(
            time_row, values=minutes, width=80, height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=6,
            fg_color=TD_BG_COMPONENT,
            button_color=TD_BRAND,
            button_hover_color=TD_BRAND_HOVER,
        )
        self._min_menu.pack(side="left")

        ctk.CTkLabel(
            time_row, text="  24 小时制",
            font=ctk.CTkFont(size=11),
            text_color=TD_TEXT_PLACEHOLDER,
        ).pack(side="left", pady=(6, 0))

        self._save_btn = ctk.CTkButton(
            inner, text="保存定时设置", width=140, height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            fg_color=TD_BRAND, hover_color=TD_BRAND_HOVER,
            command=self._save,
        )
        self._save_btn.pack(anchor="w", pady=(0, 16))

        ctk.CTkFrame(
            inner, height=1, fg_color=TD_BORDER_LEVEL1,
        ).pack(fill="x", pady=(0, 16))

        self._status_label = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(size=12),
            text_color=TD_TEXT_PLACEHOLDER,
            anchor="w",
        )
        self._status_label.pack(fill="x", pady=(0, 4))

        self._last_run_label = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(size=11),
            text_color=TD_TEXT_PLACEHOLDER,
            anchor="w",
        )
        self._last_run_label.pack(fill="x")

    def _load_from_config(self):
        sched = self._cfg.get_schedule_settings()
        if sched.get("enabled"):
            self._switch.select()
        else:
            self._switch.deselect()

        time_str = sched.get("time", DEFAULT_SCHEDULE_TIME)
        parts = time_str.split(":")
        h = parts[0] if len(parts) >= 1 else "18"
        m = parts[1] if len(parts) >= 2 else "00"
        self._hour_menu.set(h)
        self._min_menu.set(m)
        self._update_status()

    def _on_switch(self):
        pass

    def _save(self):
        enabled = bool(self._switch.get())
        time_str = f"{self._hour_menu.get()}:{self._min_menu.get()}"
        self._cfg.set_schedule_settings(enabled, time_str)
        self._update_status()
        if self._animator:
            JellyEffects.trigger_save_pulse(self._save_btn, self._animator)

    def _update_status(self):
        sched = self._cfg.get_schedule_settings()
        if sched.get("enabled"):
            self._status_label.configure(
                text=f"状态: 已启用  ·  每天 {sched.get('time')} 自动执行",
                text_color=TD_SUCCESS,
            )
        else:
            self._status_label.configure(
                text="状态: 未启用",
                text_color=TD_TEXT_PLACEHOLDER,
            )

    def update_last_run(self, time_str, success=True):
        icon = "成功" if success else "失败"
        color = TD_SUCCESS if success else TD_ERROR
        self.after(0, lambda: self._last_run_label.configure(
            text=f"上次执行: {time_str}  {icon}",
            text_color=color,
        ))
