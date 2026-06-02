"""工作台首页：操作按钮 + 日报内容预览 + 实时日志"""

import customtkinter as ctk
from app.constants import (
    FIELD_LABELS, DEFAULT_AI_ROLE,
    TD_BRAND, TD_BRAND_HOVER, TD_BRAND_LIGHT, TD_BRAND_SUBTLE,
    TD_BG_COMPONENT, TD_BG_CONTAINER, TD_BORDER_LEVEL1, TD_SHADOW,
    TD_TEXT_PRIMARY, TD_TEXT_SECONDARY, TD_TEXT_PLACEHOLDER,
    TD_ERROR, TD_SUCCESS, TD_WARNING,
)
from app.gui.animations import JellyEffects


class OperationTab(ctk.CTkFrame):
    def __init__(
        self, master, trigger_callback, ai_generate_callback=None,
        animator=None, config_manager=None, on_edit_config=None,
        **kwargs
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._trigger = trigger_callback
        self._ai_generate = ai_generate_callback
        self._animator = animator
        self._cfg = config_manager
        self._on_edit_config = on_edit_config
        self._ai_running = False
        self._preview_labels = {}
        self._build_ui()
        self._apply_effects()
        self._load_preview()

    def _build_ui(self):
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True)

        # 滚动条修复：确保 canvas 可滚动
        canvas = getattr(self._scroll, '_parent_canvas', None)
        if canvas is not None:
            canvas.configure(yscrollincrement=15)

        self._build_hero_card()
        self._build_input_row()
        self._build_preview_card()

        # 延迟绑定滚轮事件，确保内部控件创建完成后再绑定
        self.after(200, self._setup_scroll_fix)

    def _setup_scroll_fix(self):
        """修复滚动条无法正常滚动的问题"""
        sf = self._scroll
        canvas = getattr(sf, '_parent_canvas', None)
        if canvas is None:
            return

        # 确保内部帧不抢占滚动区域高度
        scroll_frame = getattr(sf, '_scrollable_frame', None)
        if scroll_frame is not None:
            scroll_frame.bind('<Configure>',
                lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        # 绑定鼠标滚轮事件到所有内部控件
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-3 * (event.delta / 120)), 'units')

        def _bind_all_children(widget):
            for child in widget.winfo_children():
                child.bind('<MouseWheel>', _on_mousewheel, add='+')
                _bind_all_children(child)

        _bind_all_children(sf)
        canvas.bind('<MouseWheel>', _on_mousewheel, add='+')
        sf.bind('<MouseWheel>', _on_mousewheel, add='+')

    def _build_hero_card(self):
        self._btn_card = ctk.CTkFrame(
            self._scroll, fg_color=TD_BG_CONTAINER, corner_radius=10,
            border_width=1, border_color=TD_BORDER_LEVEL1,
        )
        self._btn_card.pack(fill="x", padx=20, pady=(16, 10))

        inner = ctk.CTkFrame(self._btn_card, fg_color="transparent")
        inner.pack(padx=24, pady=(20, 20), fill="x")

        # 标题行
        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x")

        ctk.CTkLabel(
            header_row,
            text="日报自动填写",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(side="left")

        # 提交模式开关放在标题行右侧
        self._auto_submit_switch = ctk.CTkSwitch(
            header_row,
            text="自动提交",
            font=ctk.CTkFont(size=11),
            command=self._on_submit_switch,
        )
        self._auto_submit_switch.pack(side="right")

        ctk.CTkLabel(
            inner,
            text="AI 生成内容后一键填写，无需跳转即可完成日报",
            font=ctk.CTkFont(size=11),
            text_color=TD_TEXT_SECONDARY,
        ).pack(anchor="w", pady=(4, 16))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")

        self._ai_btn = ctk.CTkButton(
            btn_row,
            text="✨ AI 智能生成",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=44,
            corner_radius=8,
            fg_color=TD_WARNING,
            hover_color="#D97706",
            command=self._on_ai_click,
        )
        self._ai_btn.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self._btn = ctk.CTkButton(
            btn_row,
            text="🚀 一键填写日报",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=44,
            corner_radius=8,
            fg_color=TD_BRAND,
            hover_color=TD_BRAND_HOVER,
            command=self._on_click,
        )
        self._btn.pack(side="left", fill="x", expand=True)

    def _build_input_row(self):
        row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 10))
        row.columnconfigure(0, weight=1, uniform="half")
        row.columnconfigure(1, weight=1, uniform="half")

        self._build_field1_card(row)
        self._build_role_card(row)

    def _build_field1_card(self, parent):
        self._field1_card = ctk.CTkFrame(
            parent, fg_color=TD_BG_CONTAINER, corner_radius=10,
            border_width=1, border_color=TD_BORDER_LEVEL1,
        )
        self._field1_card.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        inner = ctk.CTkFrame(self._field1_card, fg_color="transparent")
        inner.pack(padx=24, pady=(16, 16), fill="x")

        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 8))

        # 序号标签
        num_label = ctk.CTkLabel(
            header_row,
            text="1",
            width=22, height=22,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=TD_BRAND_LIGHT,
            text_color=TD_BRAND,
            corner_radius=4,
        )
        num_label.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            header_row,
            text=FIELD_LABELS[0],
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # 已记住提示
        self._saved_hint = ctk.CTkLabel(
            header_row,
            text="● 已保存",
            font=ctk.CTkFont(size=10),
            text_color=TD_SUCCESS,
        )

        ctk.CTkLabel(
            inner,
            text="这是你的每日努力基准，填写后自动记住，下次无需重复输入",
            font=ctk.CTkFont(size=10),
            text_color=TD_TEXT_PLACEHOLDER,
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        self._field1_entry = ctk.CTkEntry(
            inner,
            height=40,
            font=ctk.CTkFont(size=12),
            border_color=TD_BORDER_LEVEL1,
            corner_radius=6,
            placeholder_text="",
        )
        self._field1_entry.pack(fill="x")
        self._field1_entry.bind("<KeyRelease>", lambda e: self._on_field1_change())
        self._field1_entry.bind("<FocusOut>", lambda e: self._on_field1_change())

        # 加载字段1内容
        if self._cfg:
            content = self._cfg.get_field_content(FIELD_LABELS[0])
            if content and content.strip():
                self._field1_entry.insert(0, content.strip())
                self._show_saved_hint()

    def _on_field1_change(self):
        if not self._cfg:
            return
        content = self._field1_entry.get().strip()
        self._cfg.set_field_content(FIELD_LABELS[0], content, persist=True)
        if content:
            self._show_saved_hint()
        else:
            self._saved_hint.pack_forget()

    def _show_saved_hint(self):
        self._saved_hint.pack(side="right")

    def refresh_field1(self):
        if not self._cfg:
            return
        content = self._cfg.get_field_content(FIELD_LABELS[0])
        self._field1_entry.delete(0, "end")
        if content and content.strip():
            self._field1_entry.insert(0, content.strip())
            self._show_saved_hint()
        else:
            self._saved_hint.pack_forget()

    def _build_role_card(self, parent):
        self._role_card = ctk.CTkFrame(
            parent, fg_color=TD_BG_CONTAINER, corner_radius=10,
            border_width=1, border_color=TD_BORDER_LEVEL1,
        )
        self._role_card.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        inner = ctk.CTkFrame(self._role_card, fg_color="transparent")
        inner.pack(padx=24, pady=(16, 16), fill="x")

        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            header_row,
            text="职位描述",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(side="left")

        # 已保存提示
        self._role_saved_hint = ctk.CTkLabel(
            header_row,
            text="● 已保存",
            font=ctk.CTkFont(size=10),
            text_color=TD_SUCCESS,
        )

        ctk.CTkLabel(
            inner,
            text="AI 会根据你的职位描述生成日报内容，填写后自动记住",
            font=ctk.CTkFont(size=10),
            text_color=TD_TEXT_PLACEHOLDER,
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        self._role_entry = ctk.CTkTextbox(
            inner,
            height=70,
            font=ctk.CTkFont(size=12),
            wrap="word",
            border_width=1,
            border_color=TD_BORDER_LEVEL1,
            corner_radius=6,
            fg_color=TD_BG_COMPONENT,
        )
        placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
        self._role_entry.insert("1.0", placeholder)
        self._role_entry.configure(text_color=TD_TEXT_PLACEHOLDER)
        self._role_entry.bind("<FocusIn>", self._on_role_focus_in)
        self._role_entry.bind("<FocusOut>", self._on_role_focus_out, add="+")
        self._role_entry.bind("<KeyRelease>", lambda e: self._on_role_change())
        self._role_entry.pack(fill="x")

        # 加载职位描述
        if self._cfg:
            ai = self._cfg.get_ai_settings()
            role = ai.get("prompt_template", "")
            self._role_entry.delete("1.0", "end")
            if role:
                self._role_entry.insert("1.0", role)
                self._role_entry.configure(text_color=TD_TEXT_PRIMARY)
                self._role_saved_hint.pack(side="right")
            else:
                self._role_entry.insert("1.0", placeholder)
                self._role_entry.configure(text_color=TD_TEXT_PLACEHOLDER)

    def _on_role_focus_in(self, event=None):
        current = self._role_entry.get("1.0", "end").strip()
        placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
        if current == placeholder or not current:
            self._role_entry.delete("1.0", "end")
            self._role_entry.configure(text_color=TD_TEXT_PRIMARY)

    def _on_role_focus_out(self, event=None):
        current = self._role_entry.get("1.0", "end").strip()
        if not current:
            placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
            self._role_entry.insert("1.0", placeholder)
            self._role_entry.configure(text_color=TD_TEXT_PLACEHOLDER)

    def _on_role_change(self):
        if not self._cfg:
            return
        role = self._role_entry.get("1.0", "end").strip()
        placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
        if role and role != placeholder:
            ai = self._cfg.get_ai_settings()
            self._cfg.set_ai_settings(
                ai.get("api_key", ""),
                ai.get("api_url", ""),
                "",
                role,
                persist=True,
            )
            self._role_saved_hint.pack(side="right")
        else:
            self._role_saved_hint.pack_forget()

    def refresh_role(self):
        if not self._cfg:
            return
        ai = self._cfg.get_ai_settings()
        role = ai.get("prompt_template", "")
        self._role_entry.delete("1.0", "end")
        if role:
            self._role_entry.insert("1.0", role)
            self._role_entry.configure(text_color=TD_TEXT_PRIMARY)
            self._role_saved_hint.pack(side="right")
        else:
            placeholder = "请输入你的职位\n例：我是一名软件工程师，负责后端开发和系统架构设计"
            self._role_entry.insert("1.0", placeholder)
            self._role_entry.configure(text_color=TD_TEXT_PLACEHOLDER)
            self._role_saved_hint.pack_forget()

    def _build_preview_card(self):
        self._preview_card = ctk.CTkFrame(
            self._scroll, fg_color=TD_BG_CONTAINER, corner_radius=10,
            border_width=1, border_color=TD_BORDER_LEVEL1,
        )
        self._preview_card.pack(fill="x", padx=20, pady=(0, 10))

        # 标题行
        preview_header = ctk.CTkFrame(self._preview_card, fg_color="transparent")
        preview_header.pack(fill="x", padx=20, pady=(16, 12))

        ctk.CTkLabel(
            preview_header,
            text="日报内容预览",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(side="left")

        self._edit_btn = ctk.CTkButton(
            preview_header,
            text="编辑配置",
            width=72, height=28,
            font=ctk.CTkFont(size=11),
            corner_radius=6,
            fg_color=TD_BG_COMPONENT,
            hover_color=TD_BORDER_LEVEL1,
            text_color=TD_TEXT_SECONDARY,
            border_width=1, border_color=TD_BORDER_LEVEL1,
            command=self._on_edit_click,
        )
        self._edit_btn.pack(side="right")

        ctk.CTkFrame(
            self._preview_card, height=1, fg_color=TD_BORDER_LEVEL1,
        ).pack(fill="x", padx=20)

        # 字段2-8内容展示区
        self._preview_container = ctk.CTkFrame(
            self._preview_card, fg_color="transparent",
        )
        self._preview_container.pack(fill="x", padx=20, pady=(12, 20))

        for i, label in enumerate(FIELD_LABELS[1:]):
            row = ctk.CTkFrame(self._preview_container, fg_color="transparent")
            row.pack(fill="x", pady=(8 if i > 0 else 0, 0))

            # 序号标签
            num_label = ctk.CTkLabel(
                row,
                text=f"{i+2}",
                width=20, height=20,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=TD_BRAND_LIGHT,
                text_color=TD_BRAND,
                corner_radius=4,
            )
            num_label.pack(side="left", padx=(0, 8))

            # 字段标题
            short_label = label[:12] + "…" if len(label) > 12 else label
            ctk.CTkLabel(
                row,
                text=short_label,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=TD_TEXT_SECONDARY,
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

            # 内容预览标签
            content_label = ctk.CTkLabel(
                row,
                text="未填写",
                font=ctk.CTkFont(size=11),
                text_color=TD_TEXT_PLACEHOLDER,
                anchor="e",
                wraplength=260,
                justify="right",
            )
            content_label.pack(side="right", padx=(8, 0))
            self._preview_labels[label] = content_label

        self._empty_hint = ctk.CTkLabel(
            self._preview_container,
            text="暂无内容，点击「AI 智能生成」自动填写",
            font=ctk.CTkFont(size=11),
            text_color=TD_TEXT_PLACEHOLDER,
        )

    def _apply_effects(self):
        if not self._animator:
            return
        JellyEffects.apply_button_jelly(self._btn, self._animator)
        JellyEffects.apply_button_jelly(self._ai_btn, self._animator)
        JellyEffects.apply_button_jelly(self._edit_btn, self._animator)
        JellyEffects.apply_card_hover(self._btn_card, self._animator)
        JellyEffects.apply_card_hover(self._field1_card, self._animator)
        JellyEffects.apply_card_hover(self._role_card, self._animator)
        JellyEffects.apply_card_hover(self._preview_card, self._animator)
        JellyEffects.apply_focus_glow(self._field1_entry, self._animator)
        JellyEffects.apply_focus_glow(self._role_entry, self._animator)

    def _load_preview(self):
        if not self._cfg:
            return
        # 加载提交模式
        if self._cfg.get_auto_submit():
            self._auto_submit_switch.select()
        else:
            self._auto_submit_switch.deselect()

        has_any = False
        for label in FIELD_LABELS[1:]:
            content = self._cfg.get_field_content(label)
            lbl = self._preview_labels[label]
            if content and content.strip():
                has_any = True
                preview = content.strip()[:40]
                if len(content.strip()) > 40:
                    preview += "…"
                lbl.configure(text=preview, text_color=TD_TEXT_PRIMARY)
            else:
                lbl.configure(text="未填写", text_color=TD_TEXT_PLACEHOLDER)

        if not has_any:
            self._empty_hint.pack(anchor="center", pady=(8, 0))
        else:
            self._empty_hint.pack_forget()

    def refresh_field_preview(self):
        self._load_preview()

    def _on_submit_switch(self):
        if not self._cfg:
            return
        val = bool(self._auto_submit_switch.get())
        self._cfg.set_auto_submit(val, persist=True)

    def _on_edit_click(self):
        if self._on_edit_config:
            self._on_edit_config()

    def _on_click(self):
        self._trigger()

    def _on_ai_click(self):
        if self._ai_generate:
            self._ai_generate()

    def set_running(self, running):
        if running:
            self._btn.configure(
                state="disabled",
                text="正在执行中...",
                fg_color=TD_TEXT_PLACEHOLDER,
            )
        else:
            self._btn.configure(
                state="normal",
                text="🚀 一键填写日报",
                fg_color=TD_BRAND,
            )

    def reset_btn_color(self):
        """强制还原按钮颜色和状态（用于校验失败时中断动画）"""
        try:
            # 通过 canvas 直接还原颜色（绕过动画修改）
            from app.gui.animations import _set_btn_fg_fast
            _set_btn_fg_fast(self._btn, TD_BRAND)
            self._btn.configure(
                state="normal",
                text="🚀 一键填写日报",
                fg_color=TD_BRAND,
                hover_color=TD_BRAND_HOVER,
            )
            # 同时还原 AI 按钮
            _set_btn_fg_fast(self._ai_btn, TD_WARNING)
            self._ai_btn.configure(
                state="normal",
                text="✨ AI 智能生成",
                fg_color=TD_WARNING,
                hover_color="#D97706",
            )
        except Exception:
            pass

    def set_ai_running(self, running):
        self._ai_running = running
        if running:
            self._ai_btn.configure(
                state="disabled",
                text="AI 生成中...",
                fg_color=TD_TEXT_PLACEHOLDER,
            )
        else:
            self._ai_btn.configure(
                state="normal",
                text="✨ AI 智能生成",
                fg_color=TD_WARNING,
            )

