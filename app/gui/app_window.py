"""主窗口：整合标签页、线程管理、定时器、AI 生成、更新检查"""

import os
import sys
import threading
from datetime import date, datetime
import customtkinter as ctk
from PIL import Image

from app.constants import (
    APP_TITLE, APP_WIDTH, APP_HEIGHT, FIELD_LABELS, APP_VERSION,
    TD_BRAND, TD_BRAND_HOVER, TD_BRAND_LIGHT, TD_BRAND_SUBTLE,
    TD_BG_PAGE, TD_BG_CONTAINER, TD_BG_COMPONENT,
    TD_TEXT_PRIMARY, TD_TEXT_SECONDARY, TD_TEXT_PLACEHOLDER,
    TD_BORDER_LEVEL1, TD_SHADOW, TD_ERROR, TD_SUCCESS, TD_WARNING,
    TD_SIDEBAR_BG, TD_SIDEBAR_ACTIVE_BG, TD_SIDEBAR_ACTIVE_TEXT,
    TD_SIDEBAR_TEXT, TD_SIDEBAR_HOVER, SIDEBAR_WIDTH,
)
from app.gui.operation_tab import OperationTab
from app.gui.config_tab import ConfigTab
from app.gui.schedule_tab import ScheduleTab
from app.gui.animations import AnimationScheduler
from app.automation.reporter import DailyReportEngine
from app.scheduler.scheduler import ReportScheduler
from app.ai.generator import generate_report
from app.updater import async_check_for_updates, download_update, apply_update_and_restart


class AppWindow(ctk.CTk):
    def __init__(self, config_manager, on_logout=None):
        super().__init__()
        self._cfg = config_manager
        self._is_running = False
        self._loading_overlay = None
        self._on_logout_callback = on_logout
        self._animator = AnimationScheduler(self)

        self._setup_window()
        self._build_ui()
        self._setup_scheduler()
        self._animator.start()
        self._store_local_exe_size()
        self._auto_check_update()

    def _setup_window(self):
        self.title(APP_TITLE)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=TD_BG_PAGE)
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - APP_WIDTH) // 2
        y = (sh - APP_HEIGHT) // 2
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}+{x}+{y}")
        self.minsize(900, 640)

    def _build_ui(self):
        self._build_top_bar()
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self._build_sidebar(body)
        self._build_content(body)

    def _build_top_bar(self):
        topbar = ctk.CTkFrame(
            self, fg_color=TD_BG_CONTAINER, height=56, corner_radius=0,
            border_width=0,
        )
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        bar_inner = ctk.CTkFrame(topbar, fg_color="transparent")
        bar_inner.pack(fill="x", padx=24, pady=(0, 0))

        ctk.CTkLabel(
            bar_inner,
            text="",
            image=ctk.CTkImage(
                light_image=Image.open(os.path.join(os.path.dirname(__file__), "..", "..", "logo.png")),
                size=(28, 28),
            ),
        ).pack(side="left", pady=(14, 0))

        ctk.CTkLabel(
            bar_inner,
            text=APP_TITLE,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(side="left", padx=(10, 0), pady=(16, 0))

        ctk.CTkLabel(
            bar_inner,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=TD_TEXT_PLACEHOLDER,
        ).pack(side="left", padx=(8, 0), pady=(20, 0))

        self._update_btn = ctk.CTkButton(
            bar_inner,
            text="检查更新",
            width=72,
            height=28,
            font=ctk.CTkFont(size=10),
            corner_radius=6,
            fg_color=TD_BRAND,
            hover_color=TD_BRAND_HOVER,
            text_color="white",
            command=self._on_check_update,
        )
        self._update_btn.pack(side="right", pady=(15, 0), padx=(0, 10))

        self._logout_btn = ctk.CTkButton(
            bar_inner,
            text="退出登录",
            width=72,
            height=28,
            font=ctk.CTkFont(size=10),
            corner_radius=6,
            fg_color="transparent",
            hover_color=TD_BG_PAGE,
            text_color=TD_TEXT_SECONDARY,
            border_width=1,
            border_color=TD_BORDER_LEVEL1,
            command=self._on_logout,
        )
        self._logout_btn.pack(side="right", pady=(15, 0), padx=(6, 6))

        username, _ = self._cfg.get_account()
        self._user_label = ctk.CTkLabel(
            bar_inner,
            text=f"用户：{username}" if username else "",
            font=ctk.CTkFont(size=10),
            text_color=TD_TEXT_PLACEHOLDER,
        )
        self._user_label.pack(side="right", pady=(20, 0), padx=(0, 14))

        ctk.CTkFrame(topbar, height=1, fg_color=TD_BORDER_LEVEL1).pack(fill="x", side="bottom")

    def _build_sidebar(self, parent):
        sidebar = ctk.CTkFrame(
            parent, fg_color=TD_SIDEBAR_BG, width=SIDEBAR_WIDTH,
            corner_radius=0,
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkFrame(sidebar, height=1, fg_color=TD_BORDER_LEVEL1).pack(fill="x")

        self._nav_buttons = {}
        self._active_page = "工作台"
        nav_items = [
            ("工作台", "📋"),
            ("内容配置", "⚙️"),
            ("定时设置", "⏰"),
        ]

        nav_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_frame.pack(fill="x", padx=8, pady=(12, 0))

        for name, icon in nav_items:
            btn = ctk.CTkButton(
                nav_frame,
                text=f" {icon}  {name}",
                width=SIDEBAR_WIDTH - 16,
                height=40,
                font=ctk.CTkFont(size=12),
                anchor="w",
                corner_radius=8,
                fg_color="transparent",
                hover_color=TD_SIDEBAR_HOVER,
                text_color=TD_SIDEBAR_TEXT,
                command=lambda n=name: self._switch_page(n),
            )
            btn.pack(fill="x", pady=(0, 2))
            self._nav_buttons[name] = btn

        self._set_nav_active("工作台")

        # 分割线
        ctk.CTkFrame(sidebar, height=1, fg_color=TD_BORDER_LEVEL1).pack(fill="x", padx=8, pady=(8, 0))

        # 运行日志区域
        log_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            log_header,
            text="运行日志",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TD_TEXT_SECONDARY,
            anchor="w",
        ).pack(side="left")

        self._log_clear_btn = ctk.CTkButton(
            log_header,
            text="清除",
            width=36, height=20,
            font=ctk.CTkFont(size=9),
            corner_radius=4,
            fg_color=TD_BG_COMPONENT,
            hover_color=TD_BORDER_LEVEL1,
            text_color=TD_TEXT_SECONDARY,
            command=self._clear_log,
        )
        self._log_clear_btn.pack(side="right")

        self._log_box = ctk.CTkTextbox(
            log_frame,
            state="disabled",
            font=ctk.CTkFont(size=9, family="Consolas"),
            wrap="word",
            fg_color=TD_BG_COMPONENT,
            border_width=0,
            corner_radius=4,
        )
        self._log_box.pack(fill="both", expand=True)

        # 底部作者标识
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=8, pady=(0, 12))
        ctk.CTkLabel(
            bottom,
            text="by wbw",
            font=ctk.CTkFont(size=10),
            text_color=TD_TEXT_PLACEHOLDER,
        ).pack(anchor="center")

    def _switch_page(self, name):
        self._set_nav_active(name)
        for n, frame in self._tab_frames.items():
            if n == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        # 切到工作台时刷新预览
        if name == "工作台":
            self._op_tab.refresh_field_preview()

    def _set_nav_active(self, name):
        self._active_page = name
        for n, btn in self._nav_buttons.items():
            if n == name:
                btn.configure(
                    fg_color=TD_SIDEBAR_ACTIVE_BG,
                    text_color=TD_SIDEBAR_ACTIVE_TEXT,
                    font=ctk.CTkFont(size=12, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=TD_SIDEBAR_TEXT,
                    font=ctk.CTkFont(size=12),
                )

    def _build_content(self, parent):
        self._content_area = ctk.CTkFrame(parent, fg_color=TD_BG_PAGE)
        self._content_area.pack(side="left", fill="both", expand=True)

        self._tab_frames = {}

        self._op_tab = OperationTab(
            self._content_area,
            trigger_callback=self._trigger_automation,
            ai_generate_callback=self._trigger_ai_generate,
            animator=self._animator,
            config_manager=self._cfg,
            on_edit_config=lambda: self._switch_page("内容配置"),
        )
        self._tab_frames["工作台"] = self._op_tab

        self._cfg_tab = ConfigTab(
            self._content_area,
            config_manager=self._cfg,
            animator=self._animator,
        )
        self._tab_frames["内容配置"] = self._cfg_tab

        self._sched_tab = ScheduleTab(
            self._content_area,
            config_manager=self._cfg,
            animator=self._animator,
        )
        self._tab_frames["定时设置"] = self._sched_tab

        self._op_tab.pack(fill="both", expand=True)

    def _setup_scheduler(self):
        self._scheduler = ReportScheduler(
            time_str_getter=lambda: self._cfg.get_schedule_settings().get("time", "18:00"),
            enabled_getter=lambda: self._cfg.get_schedule_settings().get("enabled", False),
            trigger_callback=self._trigger_automation,
            tk_root=self,
        )
        self._scheduler.start()

    def destroy(self):
        self._animator.stop()
        super().destroy()

    def _on_logout(self):
        from tkinter import messagebox
        if not messagebox.askyesno("确认退出", "退出登录将清除已保存的账号信息，返回登录页面。"):
            return
        self._cfg.set_account("", "")
        self._cfg.save()
        if self._on_logout_callback:
            self._on_logout_callback()
        self.destroy()

    def _trigger_automation(self):
        if self._is_running:
            self.append_log("任务正在执行中，请稍候...", "error")
            return

        # 校验所有字段是否已填写
        fields = self._cfg.get_field_contents()
        empty_fields = [label for label, content in fields.items() if not content.strip()]
        if empty_fields:
            from tkinter import messagebox
            msg = "以下日报内容尚未填写，请先完成后再执行：\n\n" + "\n".join(f"• {f}" for f in empty_fields)
            messagebox.showwarning("填写不完整", msg)
            # 弹窗关闭后多次还原按钮颜色，确保动画回调都执行完
            self.after(10, self._op_tab.reset_btn_color)
            self.after(100, self._op_tab.reset_btn_color)
            self.after(300, self._op_tab.reset_btn_color)
            self.append_log(f"执行失败：有 {len(empty_fields)} 个字段未填写", "error")
            return

        self._is_running = True
        self._op_tab.set_running(True)
        self._show_loading_overlay()
        self.append_log("─" * 36)
        self.append_log("开始执行日报自动填写...")

        t = threading.Thread(target=self._run_automation, daemon=True)
        t.start()

    def _run_automation(self):
        success = False
        try:
            fields = self._cfg.get_field_contents()
            account = self._cfg.get_account()
            browser_settings = self._cfg.get_browser_settings()
            auto_submit = self._cfg.get_auto_submit()

            self._status_callback("开始填写当天日报...")
            if auto_submit:
                self._status_callback("提交模式: 自动提交")
            else:
                self._status_callback("提交模式: 手动提交")

            engine = DailyReportEngine(
                field_contents=fields,
                account=account,
                status_callback=self._status_callback,
                step_delay=browser_settings.get("step_delay", 1.0),
                headless=browser_settings.get("headless", False),
                auto_submit=auto_submit,
            )
            engine.run()
            success = True
            self._status_callback("日报填写成功！", "success")
        except Exception as e:
            self._status_callback(f"执行异常: {e}", "error")
        finally:
            self._is_running = False
            self.after(0, lambda: self._op_tab.set_running(False))
            self.after(0, self._hide_loading_overlay)
            from datetime import datetime
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._sched_tab.update_last_run(now, success=success)

            if success:
                # 填写成功后清空字段2-8，保留字段1
                for label in FIELD_LABELS[1:]:
                    self._cfg.set_field_content(label, "", persist=False)
                self._cfg.save()
                self._status_callback("已清空字段2-8，字段1已保留", "info")
                self.after(0, lambda: self._op_tab.refresh_field_preview())

    def _status_callback(self, message, level="info"):
        self.append_log(message, level)

    def append_log(self, message, level="info"):
        def _do():
            self._log_box.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            prefix = {"info": "[INFO]", "success": "[ OK ]", "error": "[ERR]", "ai": "[ AI ]"}
            tag = prefix.get(level, "[???]")
            line = f"[{ts}] {tag} {message}\n"

            if level == "error":
                self._log_box.insert("end", line, "error")
                self._log_box.tag_config("error", foreground=TD_ERROR)
            elif level == "success":
                self._log_box.insert("end", line, "success")
                self._log_box.tag_config("success", foreground=TD_SUCCESS)
            elif level == "ai":
                self._log_box.insert("end", line, "ai")
                self._log_box.tag_config("ai", foreground=TD_WARNING)
            else:
                self._log_box.insert("end", line)

            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _trigger_ai_generate(self):
        if self._is_running:
            self.append_log("自动填写正在执行中，请稍候...", "error")
            self.after(10, self._op_tab.reset_btn_color)
            return
        ai_settings = self._cfg.get_ai_settings()
        if not ai_settings.get("api_key", "").strip():
            self.append_log("请先在「内容配置」中填写 API Key", "error")
            self.after(10, self._op_tab.reset_btn_color)
            self.after(100, self._op_tab.reset_btn_color)
            return
        field1_content = self._cfg.get_field_content(FIELD_LABELS[0])
        if not field1_content.strip():
            self.append_log("请先在「内容配置」中填写字段1（付出不亚于任何人的努力）", "error")
            self.after(10, self._op_tab.reset_btn_color)
            self.after(100, self._op_tab.reset_btn_color)
            return
        self._op_tab.set_ai_running(True)
        self.append_log("─" * 36)
        self.append_log("开始 AI 智能生成日报内容...", "ai")
        self.append_log(f"API: {ai_settings.get('api_url')}", "ai")

        t = threading.Thread(target=self._run_ai_generate, daemon=True)
        t.start()

    def _run_ai_generate(self):
        try:
            ai_settings = self._cfg.get_ai_settings()
            field1_content = self._cfg.get_field_content(FIELD_LABELS[0])

            result = generate_report(
                field1_content=field1_content,
                api_key=ai_settings["api_key"].strip(),
                api_url=ai_settings["api_url"].strip(),
                role_description=ai_settings.get("prompt_template", ""),
                status_callback=self._status_callback,
            )

            for label in FIELD_LABELS[1:]:
                content = result.get(label, "")
                self._cfg.set_field_content(label, content, persist=False)
            self._cfg.save()

            self._status_callback("AI 生成完成，已保存到当前配置", "success")
            for label in FIELD_LABELS[1:]:
                content = result.get(label, "")
                preview = content[:40] + "..." if len(content) > 40 else content
                if preview:
                    self._status_callback(f"  {label[:6]}... → {preview}", "success")

            self.after(0, lambda: self._op_tab.refresh_field_preview())
            self.after(0, lambda: self._cfg_tab._load_from_config())
            self.after(200, lambda: self._show_toast("AI 智能生成完成，内容已保存到当前配置"))
        except Exception as e:
            self._status_callback(f"AI 生成失败: {e}", "error")
        finally:
            self.after(0, lambda: self._op_tab.set_ai_running(False))

    def _show_toast(self, message):
        toast = ctk.CTkFrame(
            self, fg_color=TD_BRAND, corner_radius=10,
            width=340, height=52,
        )
        toast.place(relx=0.5, rely=0.85, anchor="center")
        toast.lift()

        inner = ctk.CTkFrame(toast, fg_color="transparent")
        inner.pack(expand=True, padx=20)

        ctk.CTkLabel(
            inner, text="✓",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="white",
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            inner, text=message,
            font=ctk.CTkFont(size=12),
            text_color="white",
        ).pack(side="left")

        fade_alphas = [1.0, 0.8, 0.6, 0.4, 0.2]
        for i, alpha in enumerate(fade_alphas):
            delay = 2200 + i * 200
            self.after(delay, lambda t=toast, a=alpha: self._fade_toast(t, a))
        self.after(3200, lambda t=toast: t.destroy() if t.winfo_exists() else None)

    def _fade_toast(self, toast, alpha):
        if not toast.winfo_exists():
            return
        r, g, b = 22, 163, 74
        color = f"#{int(r * alpha):02x}{int(g * alpha):02x}{int(b * alpha):02x}"
        toast.configure(fg_color=color)

    # ── Loading 遮罩 ────────────────────────────────────
    def _show_loading_overlay(self):
        """显示全屏 loading 遮罩"""
        if hasattr(self, '_loading_overlay') and self._loading_overlay is not None:
            return

        self._loading_overlay = ctk.CTkFrame(self, fg_color="#1F2937", corner_radius=0)
        self._loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._loading_overlay.lift()

        # 中央卡片
        card = ctk.CTkFrame(
            self._loading_overlay,
            fg_color="#FFFFFF", corner_radius=16,
            width=320, height=160,
        )
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        # 加载动画容器
        spinner_frame = ctk.CTkFrame(card, fg_color="transparent")
        spinner_frame.pack(pady=(30, 16))

        # 三个圆点动画
        self._spinner_dots = []
        for i in range(3):
            dot = ctk.CTkLabel(
                spinner_frame,
                text="●",
                font=ctk.CTkFont(size=28),
                text_color=TD_BRAND,
            )
            dot.pack(side="left", padx=8)
            self._spinner_dots.append(dot)

        # 提示文字
        self._loading_label = ctk.CTkLabel(
            card,
            text="操作中，请勿触碰鼠标...",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#374151",
        )
        self._loading_label.pack(pady=(0, 20))

        # 启动动画
        self._spinner_step = 0
        self._animate_spinner()

    def _animate_spinner(self):
        """圆点脉冲动画"""
        if not hasattr(self, '_loading_overlay') or self._loading_overlay is None:
            return
        if not self._loading_overlay.winfo_exists():
            return

        self._spinner_step = (self._spinner_step + 1) % 6
        colors = ["#16A34A", "#22C55E", "#4ADE80", "#86EFAC", "#BBF7D0"]

        for i, dot in enumerate(self._spinner_dots):
            if not dot.winfo_exists():
                continue
            phase = (self._spinner_step + i) % 5
            dot.configure(text_color=colors[phase])

        self.after(200, self._animate_spinner)

    def _hide_loading_overlay(self):
        """隐藏 loading 遮罩"""
        if hasattr(self, '_loading_overlay') and self._loading_overlay is not None:
            try:
                self._loading_overlay.destroy()
            except Exception:
                pass
            self._loading_overlay = None

    def _on_check_update(self):
        self._update_btn.configure(state="disabled", text="检查中...")
        self._do_check_update(manual=True)

    def _auto_check_update(self):
        if self._cfg.should_check_today():
            self.after(1000, lambda: self._do_check_update(manual=False))

    def _store_local_exe_size(self):
        try:
            size = os.path.getsize(sys.executable)
            self._cfg.set_local_exe_size(size)
        except Exception:
            pass

    def _do_check_update(self, manual=False):
        local_size = self._cfg.get_local_exe_size()

        def on_result(has_update, remote_size, exe_url):
            self._cfg.set_last_check_date(date.today().isoformat())
            self.after(0, lambda: self._update_btn.configure(
                state="normal", text="检查更新"
            ))

            if has_update:
                skip_size = self._cfg.get_skip_exe_size()
                if remote_size == skip_size:
                    return
                self.after(0, lambda: self._show_update_dialog(
                    remote_size, exe_url
                ))
            else:
                if manual:
                    self.after(0, lambda: self._show_toast("当前已是最新版本"))

        self._update_btn.configure(state="disabled", text="检查中...")
        async_check_for_updates(on_result=on_result, local_size=local_size)

    def _show_update_dialog(self, remote_size, exe_url):
        dialog = ctk.CTkToplevel(self)
        dialog.title("发现新版本")
        dialog.geometry("400x280")
        dialog.resizable(False, False)
        dialog.configure(fg_color=TD_BG_CONTAINER)
        dialog.transient(self)
        dialog.grab_set()

        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 280) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog,
            text="发现新版本",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(pady=(24, 12))

        info_frame = ctk.CTkFrame(dialog, fg_color=TD_BG_COMPONENT, corner_radius=8)
        info_frame.pack(fill="x", padx=24, pady=(0, 16))

        remote_mb = round(remote_size / (1024 * 1024), 1)
        ctk.CTkLabel(
            info_frame,
            text=f"检测到服务器上有更新版本",
            font=ctk.CTkFont(size=12),
            text_color=TD_TEXT_PRIMARY,
        ).pack(anchor="w", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            info_frame,
            text=f"文件大小：{remote_mb} MB",
            font=ctk.CTkFont(size=12),
            text_color=TD_TEXT_SECONDARY,
        ).pack(anchor="w", padx=16, pady=(0, 12))

        self._update_progress_label = ctk.CTkLabel(
            dialog,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=TD_TEXT_SECONDARY,
        )
        self._update_progress_label.pack(pady=(0, 2))

        self._update_progress_bar = ctk.CTkProgressBar(
            dialog,
            width=340,
            height=8,
            corner_radius=4,
            fg_color=TD_BG_COMPONENT,
            progress_color=TD_BRAND,
        )
        self._update_progress_bar.set(0)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=(12, 20))

        skip_btn = ctk.CTkButton(
            btn_frame,
            text="跳过此版本",
            width=100,
            height=34,
            font=ctk.CTkFont(size=12),
            corner_radius=6,
            fg_color="transparent",
            hover_color=TD_BG_PAGE,
            text_color=TD_TEXT_SECONDARY,
            border_width=1,
            border_color=TD_BORDER_LEVEL1,
            command=lambda: [self._cfg.set_skip_exe_size(remote_size), dialog.destroy()],
        )
        skip_btn.pack(side="left")

        self._update_download_btn = ctk.CTkButton(
            btn_frame,
            text="立即更新",
            width=120,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            fg_color=TD_BRAND,
            hover_color=TD_BRAND_HOVER,
            text_color="white",
            command=lambda: self._start_download(exe_url, remote_size, dialog),
        )
        self._update_download_btn.pack(side="right")

        dialog.protocol("WM_DELETE_WINDOW", lambda: [self._cfg.set_skip_exe_size(remote_size), dialog.destroy()])

    def _start_download(self, exe_url, remote_size, dialog):
        self._update_download_btn.configure(state="disabled", text="下载中...")
        self._update_progress_bar.pack(pady=(0, 8))
        self._update_progress_label.configure(text="准备下载...")

        def on_progress(percent, downloaded_mb, total_mb):
            self.after(0, lambda: self._update_progress_bar.set(percent / 100))
            if total_mb > 0:
                self.after(0, lambda: self._update_progress_label.configure(
                    text=f"下载中... {downloaded_mb}MB / {total_mb}MB ({percent}%)"
                ))
            else:
                self.after(0, lambda: self._update_progress_label.configure(
                    text=f"下载中... {downloaded_mb}MB"
                ))

        def on_complete(file_path):
            self.after(0, lambda: self._update_progress_label.configure(
                text="下载完成，正在安装更新..."
            ))
            self.after(0, lambda: self._update_progress_bar.set(1))
            self.after(500, lambda: self._on_download_complete(file_path, dialog))

        def on_error(error_msg):
            self.after(0, lambda: self._update_progress_label.configure(
                text=f"下载失败：{error_msg}"
            ))
            self.after(0, lambda: self._update_download_btn.configure(
                state="normal", text="重试"
            ))
            def retry():
                self._update_download_btn.configure(state="disabled", text="下载中...")
                download_update(exe_url, on_progress, on_complete, on_error)
            self._update_download_btn.configure(command=retry)

        download_update(exe_url, on_progress, on_complete, on_error)

    def _on_download_complete(self, file_path, dialog):
        dialog.destroy()

        confirm = ctk.CTkToplevel(self)
        confirm.title("更新就绪")
        confirm.geometry("360x180")
        confirm.resizable(False, False)
        confirm.configure(fg_color=TD_BG_CONTAINER)
        confirm.transient(self)
        confirm.grab_set()

        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 360) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        confirm.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            confirm,
            text="更新已下载完成",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TD_TEXT_PRIMARY,
        ).pack(pady=(24, 8))

        ctk.CTkLabel(
            confirm,
            text="点击「立即重启」将关闭当前程序\n并自动完成更新后重新启动",
            font=ctk.CTkFont(size=12),
            text_color=TD_TEXT_SECONDARY,
            justify="center",
        ).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(confirm, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24)

        ctk.CTkButton(
            btn_frame,
            text="稍后再说",
            width=100,
            height=34,
            font=ctk.CTkFont(size=12),
            corner_radius=6,
            fg_color="transparent",
            hover_color=TD_BG_PAGE,
            text_color=TD_TEXT_SECONDARY,
            border_width=1,
            border_color=TD_BORDER_LEVEL1,
            command=confirm.destroy,
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame,
            text="立即重启",
            width=120,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            fg_color=TD_BRAND,
            hover_color=TD_BRAND_HOVER,
            text_color="white",
            command=lambda: apply_update_and_restart(file_path),
        ).pack(side="right")
