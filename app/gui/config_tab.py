"""配置页：账号 + 日报字段 + 保存/导入/导出"""

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app.constants import (
    FIELD_LABELS,
    DEFAULT_AI_API_URL, DEFAULT_AI_ROLE,
    TD_BRAND, TD_BRAND_HOVER, TD_BRAND_LIGHT, TD_BRAND_SUBTLE,
    TD_BG_COMPONENT, TD_BG_CONTAINER, TD_BG_PAGE,
    TD_BORDER_LEVEL1, TD_BORDER_LEVEL2, TD_SHADOW,
    TD_TEXT_PRIMARY, TD_TEXT_SECONDARY, TD_TEXT_PLACEHOLDER,
    TD_TEXT_DISABLED,
)
from app.gui.animations import JellyEffects


class ConfigTab(ctk.CTkFrame):
    def __init__(self, master, config_manager, animator=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._cfg = config_manager
        self._animator = animator
        self._entries = {}
        self._save_after_id = None
        self._toolbar_btns = []
        self._cards = []
        self._build_ui()
        self._load_from_config()
        self._setup_auto_save()
        self._setup_fast_scroll()
        self._apply_effects()

    def _build_ui(self):
        self._build_toolbar()
        self._build_scroll_area()

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=24, pady=(16, 4))

        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        actions.pack(side="right")

        self._save_btn = ctk.CTkButton(
            actions, text="保存配置", width=88, height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6,
            fg_color=TD_BRAND, hover_color=TD_BRAND_HOVER,
            command=self._save,
        )
        self._save_btn.pack(side="left", padx=(0, 6))
        self._toolbar_btns.append(self._save_btn)

        for text, cmd in [
            ("恢复默认", self._reset),
            ("导出配置", self._export),
            ("导入配置", self._import),
        ]:
            btn = ctk.CTkButton(
                actions, text=text, width=76, height=30,
                font=ctk.CTkFont(size=11),
                corner_radius=6,
                fg_color=TD_BG_COMPONENT, hover_color=TD_BORDER_LEVEL1,
                text_color=TD_TEXT_SECONDARY,
                border_width=1, border_color=TD_BORDER_LEVEL1,
                command=cmd,
            )
            btn.pack(side="left", padx=(0, 6))
            self._toolbar_btns.append(btn)

    def _build_scroll_area(self):
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
        )
        self._scroll_frame.pack(fill="both", expand=True, padx=20, pady=(4, 16))

        self._card_container = ctk.CTkFrame(
            self._scroll_frame, fg_color="transparent",
        )
        self._card_container.pack(fill="both", expand=True, padx=4)

        self._build_ai_card()
        self._build_field_card()

    def _build_ai_card(self):
        ai_card = ctk.CTkFrame(
            self._card_container, fg_color=TD_BG_CONTAINER, corner_radius=10,
            border_width=1, border_color=TD_BORDER_LEVEL1,
        )
        ai_card.pack(fill="x", pady=(0, 10))
        self._cards.append(ai_card)

        self._make_section_title(ai_card, "AI 智能生成", padx=20, pady=(18, 12))

        ctk.CTkLabel(
            ai_card, text="配置 AI API 后可一键生成日报内容",
            font=ctk.CTkFont(size=11),
            text_color=TD_TEXT_PLACEHOLDER,
        ).pack(anchor="w", padx=20, pady=(0, 16))

        api_url_row = ctk.CTkFrame(ai_card, fg_color="transparent")
        api_url_row.pack(fill="x", padx=20, pady=(0, 4))
        ctk.CTkLabel(
            api_url_row, text="API 地址",
            font=ctk.CTkFont(size=11), text_color=TD_TEXT_SECONDARY, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            api_url_row, text="DeepSeek / 硅基流动 等兼容接口",
            font=ctk.CTkFont(size=9),
            text_color=TD_TEXT_PLACEHOLDER,
        ).pack(side="right")
        self._ai_url_entry = ctk.CTkEntry(
            ai_card, font=ctk.CTkFont(size=12), height=36,
            placeholder_text="https://api.deepseek.com/v1",
            border_color=TD_BORDER_LEVEL1, corner_radius=6,
        )
        self._ai_url_entry.pack(fill="x", padx=20, pady=(0, 12))

        key_row = ctk.CTkFrame(ai_card, fg_color="transparent")
        key_row.pack(fill="x", padx=20, pady=(0, 4))
        ctk.CTkLabel(
            key_row, text="API Key (暂时免费提供)",
            font=ctk.CTkFont(size=11), text_color=TD_TEXT_SECONDARY, anchor="w",
        ).pack(side="left")
        self._ai_key_entry = ctk.CTkEntry(
            ai_card, font=ctk.CTkFont(size=12), height=36,
            placeholder_text="sk-xxxx...",
            show="*",
            border_color=TD_BORDER_LEVEL1, corner_radius=6,
        )
        self._ai_key_entry.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkFrame(
            ai_card, height=1, fg_color=TD_BORDER_LEVEL1,
        ).pack(fill="x", padx=20)

        role_header = ctk.CTkFrame(ai_card, fg_color="transparent")
        role_header.pack(fill="x", padx=20, pady=(14, 6))
        ctk.CTkLabel(
            role_header, text="职位描述",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TD_TEXT_SECONDARY, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            role_header,
            text="例：软件工程师、产品经理",
            font=ctk.CTkFont(size=9),
            text_color=TD_TEXT_PLACEHOLDER,
        ).pack(side="right")

        self._ai_role_entry = ctk.CTkTextbox(
            ai_card,
            height=100,
            font=ctk.CTkFont(size=13),
            wrap="word",
            border_width=1,
            border_color=TD_BORDER_LEVEL1,
            corner_radius=6,
            fg_color=TD_BG_COMPONENT,
        )
        placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
        self._ai_role_entry.insert("1.0", placeholder)
        self._ai_role_entry.configure(text_color=TD_TEXT_PLACEHOLDER)
        self._ai_role_entry.bind("<FocusIn>", self._on_ai_role_focus_in)
        self._ai_role_entry.bind("<FocusOut>", self._on_ai_role_focus_out, add="+")
        self._ai_role_entry.pack(fill="x", padx=20, pady=(0, 20))

        JellyEffects.apply_focus_glow(self._ai_url_entry, self._animator)
        JellyEffects.apply_focus_glow(self._ai_key_entry, self._animator)
        JellyEffects.apply_focus_glow(self._ai_role_entry, self._animator)

    def _build_field_card(self):
        field_card = ctk.CTkFrame(
            self._card_container, fg_color=TD_BG_CONTAINER, corner_radius=10,
            border_width=1, border_color=TD_BORDER_LEVEL1,
        )
        field_card.pack(fill="both", expand=True, pady=(0, 4))
        self._cards.append(field_card)

        self._make_section_title(field_card, "日报内容", padx=20, pady=(18, 12))

        ctk.CTkLabel(
            field_card,
            text="填写当天日报内容，保存后自动生效",
            font=ctk.CTkFont(size=11),
            text_color=TD_TEXT_PLACEHOLDER,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ctk.CTkFrame(
            field_card, height=1, fg_color=TD_BORDER_LEVEL1,
        ).pack(fill="x", padx=20)

        content_frame = ctk.CTkFrame(field_card, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=(12, 20))

        for i, label in enumerate(FIELD_LABELS):
            # 字段1使用单行输入框，字段2-8使用多行文本框
            is_single_line = (i == 0)

            label_row = ctk.CTkFrame(content_frame, fg_color="transparent")
            label_row.pack(fill="x", pady=(14 if i > 0 else 0, 6))

            ctk.CTkLabel(
                label_row,
                text=label,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=TD_TEXT_PRIMARY,
                anchor="w", wraplength=560,
            ).pack(side="left", fill="x", expand=True)

            if is_single_line:
                tb = ctk.CTkEntry(
                    content_frame,
                    height=36,
                    font=ctk.CTkFont(size=12),
                    border_color=TD_BORDER_LEVEL1,
                    corner_radius=6,
                    placeholder_text="请输入内容",
                )
                tb.pack(fill="x", pady=(0, 0))
            else:
                tb = ctk.CTkTextbox(
                    content_frame,
                    height=52,
                    font=ctk.CTkFont(size=12),
                    wrap="word",
                    border_width=1,
                    border_color=TD_BORDER_LEVEL1,
                    corner_radius=6,
                    fg_color=TD_BG_COMPONENT,
                )
                tb.pack(fill="x", pady=(0, 0))
            self._entries[label] = tb

    @staticmethod
    def _make_section_title(parent, text, padx, pady):
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TD_TEXT_PRIMARY, anchor="w",
        ).pack(fill="x", padx=padx, pady=pady)

    @staticmethod
    def _get_widget_text(widget):
        if isinstance(widget, ctk.CTkTextbox):
            return widget.get("1.0", "end").strip()
        else:
            return widget.get().strip()

    @staticmethod
    def _clear_widget(widget):
        if isinstance(widget, ctk.CTkTextbox):
            widget.delete("1.0", "end")
        else:
            widget.delete(0, "end")

    @staticmethod
    def _set_widget_text(widget, text):
        if isinstance(widget, ctk.CTkTextbox):
            if text:
                widget.insert("1.0", text)
        else:
            if text:
                widget.insert(0, text)

    def _setup_auto_save(self):
        for key, widget in self._entries.items():
            if isinstance(widget, ctk.CTkTextbox):
                widget.bind("<KeyRelease>", lambda e: self._trigger_save())
                widget.bind("<FocusOut>", lambda e: self._trigger_save())
            elif isinstance(widget, ctk.CTkEntry):
                widget.bind("<KeyRelease>", lambda e: self._trigger_save())
                widget.bind("<FocusOut>", lambda e: self._trigger_save())

    def _trigger_save(self):
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
        self._save_after_id = self.after(600, self._do_auto_save)

    def _do_auto_save(self):
        self._save_after_id = None
        self._save(silent=True)
        if self._animator:
            JellyEffects.trigger_save_pulse(self._save_btn, self._animator)

    def _setup_fast_scroll(self):
        sf = self._scroll_frame
        canvas = getattr(sf, '_parent_canvas', None)
        if canvas is None:
            return
        canvas.configure(yscrollincrement=15)
        original_handler = sf._mouse_wheel_all

        def _fast_mouse_wheel_all(event):
            event.delta = int(event.delta * 3)
            original_handler(event)

        sf._mouse_wheel_all = _fast_mouse_wheel_all
        sf.unbind_all("<MouseWheel>")
        sf.bind_all("<MouseWheel>", _fast_mouse_wheel_all, add="+")

    def _apply_effects(self):
        if not self._animator:
            return
        for btn in self._toolbar_btns:
            JellyEffects.apply_button_jelly(btn, self._animator)
        for card in self._cards:
            JellyEffects.apply_card_hover(card, self._animator)
        for key, widget in self._entries.items():
            if isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox)):
                JellyEffects.apply_focus_glow(widget, self._animator)

    def _load_from_config(self):
        for label in FIELD_LABELS:
            widget = self._entries[label]
            content = self._cfg.get_field_content(label)
            self._clear_widget(widget)
            self._set_widget_text(widget, content)

        ai = self._cfg.get_ai_settings()
        self._ai_url_entry.delete(0, "end")
        self._ai_url_entry.insert(0, ai.get("api_url", ""))
        self._ai_key_entry.delete(0, "end")
        self._ai_key_entry.insert(0, ai.get("api_key", ""))
        self._ai_role_entry.delete("1.0", "end")
        role = ai.get("prompt_template", "")
        if role:
            self._ai_role_entry.insert("1.0", role)
            self._ai_role_entry.configure(text_color=TD_TEXT_PRIMARY)
        else:
            placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
            self._ai_role_entry.insert("1.0", placeholder)
            self._ai_role_entry.configure(text_color=TD_TEXT_PLACEHOLDER)

    def _reset_ai_prompt(self):
        self._ai_role_entry.delete("1.0", "end")
        self._ai_role_entry.insert("1.0", DEFAULT_AI_ROLE)
        self._ai_role_entry.configure(text_color=TD_TEXT_PRIMARY)
        self._trigger_save()

    def _on_ai_role_focus_in(self, event=None):
        current = self._ai_role_entry.get("1.0", "end").strip()
        placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
        if current == placeholder or not current:
            self._ai_role_entry.delete("1.0", "end")
            self._ai_role_entry.configure(text_color=TD_TEXT_PRIMARY)

    def _on_ai_role_focus_out(self, event=None):
        current = self._ai_role_entry.get("1.0", "end").strip()
        if not current:
            placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
            self._ai_role_entry.insert("1.0", placeholder)
            self._ai_role_entry.configure(text_color=TD_TEXT_PLACEHOLDER)

    def _save(self, silent=False):
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
            self._save_after_id = None
        self._cfg.set_ai_settings(
            self._ai_key_entry.get().strip(),
            self._ai_url_entry.get().strip(),
            "",
            self._get_widget_text(self._ai_role_entry),
            persist=False,
        )
        fields_data = {}
        for label in FIELD_LABELS:
            widget = self._entries[label]
            fields_data[label] = self._get_widget_text(widget)
        self._cfg.set_all_fields(fields_data, persist=False)
        self._cfg.save()
        if not silent:
            messagebox.showinfo("提示", "配置已保存！")

    def _reset(self):
        if messagebox.askyesno("确认", "是否将所有字段恢复为空？"):
            for key, widget in self._entries.items():
                self._clear_widget(widget)
            self._cfg.reset_all_fields()

    def _export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="daily_report_config.json",
        )
        if path:
            self._cfg.export_config(path)
            messagebox.showinfo("提示", f"配置已导出到:\n{path}")

    def _import(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")],
        )
        if path:
            try:
                self._cfg.import_config(path)
                self._load_from_config()
                messagebox.showinfo("提示", "配置已导入！")
            except Exception as e:
                messagebox.showerror("错误", f"导入失败: {e}")
