"""Web 后端桥接 Api — 暴露给前端 JS，内部调用现有业务逻辑（零改动）"""

import os
import sys
import time
import calendar
import threading
import json
from datetime import datetime
from collections import deque

from app.config_manager import ConfigManager
from app.automation.reporter import DailyReportEngine
from app.ai.generator import generate_report
from app.constants import (
    FIELD_LABELS, APP_TITLE, APP_VERSION,
    CHECKLIST_API_BASE,
    CHECKLIST_TYPE_DICT_CODE, CHECKLIST_CENTER_DICT_CODE,
    CHECKLIST_AREA_DICT_CODE, CHECKLIST_URGENCY_DICT_CODE,
    DEFAULT_AI_API_KEY, DEFAULT_AI_API_URL, DEFAULT_AI_MODEL, DEFAULT_AI_ROLE,
)
from app.updater import check_for_updates, fetch_latest_changelog, download_update, apply_update_and_exit
from app.checklist.api_client import ChecklistAPIClient

# 平台相关
IS_WINDOWS = sys.platform == "win32"

CONFIG_PATH = "config.json"


class Api:
    """暴露给前端 JS 的 Python API。
    前端通过 window.pywebview.api.xxx() 调用，返回 JSON 或可序列化对象。
    """

    def __init__(self):
        self._cfg = ConfigManager(CONFIG_PATH)
        self._is_running = False
        self._is_ai_generated = False
        self._logs = deque(maxlen=2000)
        self._log_lock = threading.Lock()
        self._window = None  # webview.Window 引用，用于 evaluate_js 推送
        # 调度器
        self._sched_stop = threading.Event()
        self._sched_thread = None
        self._sched_last_run_date = None
        # 自动回复/评价
        self._auto_reply_stop = threading.Event()
        self._auto_reply_thread = None
        self._auto_reply_last_run_date = None

    def set_window(self, window):
        self._window = window

    # ═══════════════════════════════════════════════════════════
    # 日志 / 事件推送
    # ═══════════════════════════════════════════════════════════

    def _append_log(self, message, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        pushed = self._push_event("log", {"ts": ts, "msg": message, "level": level})
        if not pushed:
            # 推送失败时才缓存到队列，等待前端轮询拉取
            with self._log_lock:
                self._logs.append({"ts": ts, "msg": message, "level": level})

    def pull_logs(self):
        """前端调用：拉取并清空日志队列"""
        with self._log_lock:
            items = list(self._logs)
            self._logs.clear()
        return items

    def _push_event(self, event_type, data):
        if self._window:
            try:
                payload = json.dumps(
                    {"type": event_type, "data": data}, ensure_ascii=False
                )
                self._window.evaluate_js(f"handleEvent({payload})")
                return True
            except Exception:
                pass
        return False

    # ═══════════════════════════════════════════════════════════
    # 登录 / 账户
    # ═══════════════════════════════════════════════════════════

    def needs_login(self):
        if not os.path.exists(CONFIG_PATH):
            return True
        username, password = self._cfg.get_account()
        return not username.strip() or not password.strip()

    def auto_login_status(self):
        """启动时检查是否需要登录，返回是否有已保存的凭据"""
        try:
            if not os.path.exists(CONFIG_PATH):
                return {"has_credentials": False}
            username, password = self._cfg.get_account()
            has = bool(username.strip() and password.strip())
            return {"has_credentials": has, "username": username.strip()}
        except Exception:
            return {"has_credentials": False}

    def try_auto_login(self):
        """用已保存的凭据自动登录，成功返回 ok，失败返回 error"""
        try:
            username, password = self._cfg.get_account()
            if not username.strip() or not password.strip():
                return {"ok": False, "error": "没有保存的登录凭据"}
            # 登录校验在 login() 中做，这里直接标记登录成功
            self._cfg.set_account(username, password)
            return {"ok": True, "username": username.strip()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def login(self, username, password):
        try:
            if not username.strip() or not password.strip():
                return {"ok": False, "error": "手机号和密码不能为空"}
            self._cfg.set_account(username, password)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def logout(self):
        try:
            username, _ = self._cfg.get_account()
            self._cfg.set_account(username, "")
            return {"ok": True, "username": username}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_account(self):
        username, _ = self._cfg.get_account()
        return {"username": username}

    def minimize_window(self):
        """最小化窗口到任务栏"""
        if self._window and IS_WINDOWS:
            try:
                import ctypes
                hwnd = ctypes.windll.user32.FindWindowW(None, APP_TITLE)
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            except Exception:
                pass
        return {"ok": True}

    # ═══════════════════════════════════════════════════════════
    # 配置读写
    # ═══════════════════════════════════════════════════════════

    def get_fields(self):
        return self._cfg.get_field_contents()

    def get_field_labels(self):
        """返回字段标签列表（精进日报的8个标准字段）"""
        return {"labels": FIELD_LABELS}

    def get_all_config(self):
        """返回前端展示所需的全部配置快照"""
        ai = self._cfg.get_ai_settings()
        # 遮罩 API Key，防止前端展示/控制台泄露明文
        key = ai.get("api_key", "")
        if key:
            key = key[:7] + "****" + key[-4:] if len(key) > 11 else "****"
        ai["api_key"] = key
        return {
            "fields": self._cfg.get_field_contents(),
            "ai": ai,
            "schedule": self._cfg.get_schedule_settings(),
            "browser": self._cfg.get_browser_settings(),
            "auto_submit": self._cfg.get_auto_submit(),
            "account": {"username": self._cfg.get_account()[0]},
            "version": APP_VERSION,
        }

    def save_all_fields(self, fields):
        self._cfg.set_all_fields(fields)
        return {"ok": True}

    def save_field(self, label, content):
        self._cfg.set_field_content(label, content)
        return {"ok": True}

    def get_ai_settings(self):
        return self._cfg.get_ai_settings()

    def set_ai_settings(self, api_key, api_url, model, prompt_template):
        # 如果传入的是遮罩值（含"****"），说明用户未修改，保留已存储的真实 Key
        if api_key and "****" in api_key:
            api_key = self._cfg.get_ai_settings().get("api_key", api_key)
        self._cfg.set_ai_settings(api_key, api_url, model, prompt_template)
        return {"ok": True}

    def get_auto_submit(self):
        return self._cfg.get_auto_submit()

    def set_auto_submit(self, enabled):
        self._cfg.set_auto_submit(enabled)
        return {"ok": True}

    def get_schedule_settings(self):
        return self._cfg.get_schedule_settings()

    def set_schedule_settings(self, enabled, time_str):
        self._cfg.set_schedule_settings(enabled, time_str)
        return {"ok": True}

    def get_browser_settings(self):
        return self._cfg.get_browser_settings()

    def reset_fields(self):
        self._cfg.reset_all_fields()
        return {"ok": True}

    def export_config(self, path):
        self._cfg.export_config(path)
        return {"ok": True}

    def import_config(self, path):
        try:
            self._cfg.import_config(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # 日报填报
    # ═══════════════════════════════════════════════════════════

    def trigger_fill(self):
        if self._is_running:
            return {"ok": False, "error": "任务正在执行中，请稍候"}

        fields = self._cfg.get_field_contents()
        empty = [l for l, c in fields.items() if not c.strip()]
        if empty:
            return {"ok": False, "error": "填写不完整", "empty_fields": empty}

        self._is_running = True
        self._append_log("─" * 36)
        self._append_log("开始执行日报自动填写...")
        self._append_log("如需要手动操作，请切换到浏览器窗口", "info")

        def _run():
            success = False
            try:
                fields = self._cfg.get_field_contents()
                account = self._cfg.get_account()
                bs = self._cfg.get_browser_settings()
                auto_submit = self._cfg.get_auto_submit()

                self._append_log("开始填写当天日报...")
                if auto_submit:
                    self._append_log("提交模式: 自动提交")
                else:
                    self._append_log("提交模式: 手动提交")

                engine = DailyReportEngine(
                    field_contents=fields,
                    account=account,
                    status_callback=self._append_log,
                    step_delay=bs.get("step_delay", 1.0),
                    headless=bs.get("headless", False),
                    auto_submit=auto_submit,
                )
                engine.run()
                success = True
                self._append_log("日报填写成功！", "success")
            except Exception as e:
                self._append_log(f"执行异常: {e}", "error")
            finally:
                self._is_running = False
                self._push_event("fetch_state", self.get_running_state())

                if success:
                    if self._is_ai_generated:
                        for label in FIELD_LABELS[1:]:
                            self._cfg.set_field_content(label, "", persist=False)
                        self._cfg.save()
                        self._is_ai_generated = False
                        self._append_log("AI生成内容已填写并清空，下次可重新生成", "info")
                    else:
                        self._append_log("日报内容已保留，下次可直接使用", "info")

                self._push_event("fill_done", {"success": success, "ai_generated": self._is_ai_generated})

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return {"ok": True, "running": True}

    def get_running_state(self):
        return {
            "running": self._is_running,
            "ai_generated": self._is_ai_generated,
            "version": APP_VERSION,
        }

    # ═══════════════════════════════════════════════════════════
    # AI 生成
    # ═══════════════════════════════════════════════════════════

    def trigger_ai_generate(self, force_overwrite=False):
        if self._is_running:
            return {"ok": False, "error": "日报填写正在执行中，请稍候"}

        ai = self._cfg.get_ai_settings()
        if not ai.get("api_key", "").strip():
            return {"ok": False, "error": "请先在「内容配置」中填写 API Key"}

        f1 = self._cfg.get_field_content(FIELD_LABELS[0])
        if not f1.strip():
            return {"ok": False, "error": "请先在「内容配置」中填写字段1（付出不亚于任何人的努力）"}

        # 校验职位描述是否填写
        role_description = ai.get("prompt_template", "")
        if not role_description.strip():
            return {"ok": False, "error": "请先在「内容配置」中填写职位描述"}

        self._append_log("─" * 36)
        self._append_log("开始 AI 智能生成日报内容...", "ai")
        self._append_log(f"API: {ai.get('api_url')}", "ai")
        self._append_log(f"模型: {ai.get('model', '自动检测')}", "ai")

        def _run():
            try:
                existed = {l: self._cfg.get_field_content(l) for l in FIELD_LABELS[1:]}
                result = generate_report(
                    field1_content=f1,
                    api_key=ai["api_key"].strip(),
                    api_url=ai["api_url"].strip(),
                    model=ai.get("model", "").strip() or None,  # 传递配置的模型，如果为空则自动检测
                    role_description=ai.get("prompt_template", ""),
                    status_callback=self._append_log,
                )
                for label in FIELD_LABELS[1:]:
                    # 如果是强制覆盖或字段为空，则使用AI生成的内容
                    if force_overwrite or not existed[label].strip():
                        self._cfg.set_field_content(label, result.get(label, ""), persist=False)
                self._cfg.save()
                self._is_ai_generated = True

                self._append_log("AI 生成完成，已保存到当前配置", "success")
                for label in FIELD_LABELS[1:]:
                    if existed[label].strip() and not force_overwrite:
                        self._append_log(f"  {label[:8]}… (保留自定义)", "info")
                    else:
                        c = result.get(label, "")
                        preview = c[:40] + "…" if len(c) > 40 else c
                        if preview:
                            self._append_log(f"  {label[:8]}… → {preview}", "success")

                self._push_event("fetch_state", self.get_running_state())
                self._push_event("ai_done", result)
            except Exception as e:
                self._append_log(f"AI 生成失败: {e}", "error")
                self._push_event("ai_done", {"error": str(e)})
                self._push_event("fetch_state", self.get_running_state())

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return {"ok": True}

    # ═══════════════════════════════════════════════════════════
    # 更新检查
    # ═══════════════════════════════════════════════════════════

    def check_for_updates(self):
        try:
            local_size = self._cfg.get_local_exe_size()
            has_update, remote_size, url, changelog = check_for_updates(
                exe_url=None,
                local_size=local_size,
            )
            if has_update:
                return {
                    "ok": True, "need_update": True,
                    "changelog": changelog, "remote_size": remote_size,
                }
            return {"ok": True, "need_update": False, "version": APP_VERSION}
        except Exception as e:
            return {"ok": False, "error": str(e), "need_update": False}

    def download_and_update(self, exe_url=None):
        try:
            def on_progress(percent, downloaded_mb, total_mb):
                self._push_event("update_progress", {
                    "percent": percent,
                    "downloaded_mb": downloaded_mb,
                    "total_mb": total_mb
                })
                
            def on_complete(path):
                try:
                    self._cfg.set_skip_exe_size(os.path.getsize(path))
                    self._push_event("update_complete", {"ok": True, "path": path})
                except Exception as e:
                    self._push_event("update_complete", {"ok": False, "error": str(e)})

            def on_error(msg):
                self._push_event("update_complete", {"ok": False, "error": msg})

            download_update(exe_url, on_progress, on_complete, on_error)
            return {"ok": True, "running": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def apply_update(self, new_exe_path):
        try:
            apply_update_and_exit(new_exe_path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def clear_cache(self):
        """彻底清除所有缓存：内存缓存 + config.json 持久化缓存，并退出登录"""
        cleared = []
        
        # === 1. 清除内存缓存 ===
        # 清除五项清单 API 缓存
        if hasattr(self, '_checklist_api'):
            api = self._checklist_api
            if api._token:
                api._token = None
                cleared.append("Token(内存)")
            if api._user_info:
                api._user_info = None
                cleared.append("用户信息(内存)")
            if api._center_name:
                api._center_name = None
                cleared.append("所属中心(内存)")
            if api._dict_cache:
                api._dict_cache = {}
                cleared.append("数据字典(内存)")
        
        # 清除日志队列
        with self._log_lock:
            if self._logs:
                self._logs.clear()
                cleared.append("运行日志")
        
        # === 2. 清除 config.json 中的持久化缓存 ===
        try:
            # 清除密码（保留用户名）
            username, old_password = self._cfg.get_account()
            if old_password:
                self._cfg.set_account(username, "")
                cleared.append("登录密码")
            
            # 清除 checklist 相关缓存
            cl_settings = self._cfg.get_checklist_settings()
            if cl_settings.get("token"):
                self._cfg.set_checklist_settings(token="", user_id="", real_name="", 
                                                  center_name="", area="", area_name="")
                cleared.append("清单Token")
            
            # 清除责任人记忆
            owners = self._cfg.get_remembered_owners()
            if owners:
                self._cfg.set_remembered_owners([])
                cleared.append("责任人记忆")
            
            # 清除 BPE 神秘工具凭据
            bpe = self._cfg.get_bpe_settings()
            if bpe.get("username") or bpe.get("password"):
                self._cfg.set_bpe_settings("", "")
                cleared.append("神秘工具凭据")
            
            # 清除自动回复/评价设置
            auto_settings = self._cfg.get_auto_reply_eval_settings()
            if (auto_settings.get("auto_reply_enabled") or 
                auto_settings.get("auto_eval_enabled") or
                auto_settings.get("batch_reply_text")):
                self._cfg.set_auto_reply_eval_settings(
                    auto_reply_enabled=False,
                    auto_eval_enabled=False,
                    auto_reply_text="收到",
                    auto_eval_result="满意",
                    batch_reply_text=""
                )
                cleared.append("自动回复/评价设置")
            
            # 清除 AI 配置（恢复默认）
            ai = self._cfg.get_ai_settings()
            if (ai.get("api_key") or 
                ai.get("model") != DEFAULT_AI_MODEL or
                ai.get("api_url") != DEFAULT_AI_API_URL):
                self._cfg.set_ai_settings(
                    api_key=DEFAULT_AI_API_KEY,
                    api_url=DEFAULT_AI_API_URL,
                    model=DEFAULT_AI_MODEL,
                    prompt_template=DEFAULT_AI_ROLE
                )
                cleared.append("AI配置")
            
            # 清除更新检查记录
            if self._cfg.get_last_check_date():
                self._cfg.set_last_check_date("")
                cleared.append("更新检查记录")
            
            # 清除 EXE 大小记录
            if self._cfg.get_local_exe_size() or self._cfg.get_skip_exe_size():
                # 注意：不清除 local_exe_size，因为它是基准值
                if self._cfg.get_skip_exe_size():
                    self._cfg.set_skip_exe_size(0)
                    cleared.append("跳过更新记录")
            
            # 清除神秘工具留言已读状态
            if self._cfg._data.get('mystery_letter_seen'):
                self._cfg._data['mystery_letter_seen'] = False
                self._cfg.save()
                cleared.append("留言已读状态")
                
        except Exception as e:
            self._append_log(f"清除持久化缓存异常: {e}", "error")
        
        # === 3. 记录并返回 ===
        if cleared:
            msg = f"已清除: {', '.join(cleared)}"
            self._append_log(msg, "success")
            return {"ok": True, "message": msg, "username": username if 'username' in dir() else ""}
        else:
            return {"ok": True, "message": "没有需要清除的缓存", "username": ""}

    def read_local_changelog(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "CHANGELOG.txt")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return {"ok": True, "content": f.read()}
            # fallback to relative path if running from root
            if os.path.exists("CHANGELOG.txt"):
                with open("CHANGELOG.txt", "r", encoding="utf-8") as f:
                    return {"ok": True, "content": f.read()}
            return {"ok": False, "error": "CHANGELOG.txt not found"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # 五项清单
    # ═══════════════════════════════════════════════════════════

    def _get_checklist_api(self):
        """懒初始化 ChecklistAPIClient"""
        if not hasattr(self, '_checklist_api'):
            self._checklist_api = ChecklistAPIClient(
                base_url=self._cfg.get_checklist_settings().get("api_base", CHECKLIST_API_BASE),
                status_callback=self._append_log,
            )
            self._checklist_api.set_token_expired_callback(lambda: self._append_log("清单 Token 已过期", "error"))
        return self._checklist_api

    def checklist_auto_login_if_needed(self):
        """自动登录（未登录时使用 config.json 中存储的账号密码）"""
        try:
            api = self._get_checklist_api()
            if api.is_logged_in():
                return {"ok": True, "logged_in": True, "message": "已登录"}

            username, password = self._cfg.get_account()
            if not username or not password:
                return {"ok": False, "logged_in": False, "message": "未配置账号密码"}

            self._append_log("正在自动登录五项清单...", "info")
            ok, msg = api.login(username, password)
            if ok:
                self._append_log("五项清单自动登录成功", "success")
                # 登录成功后拉取用户信息和中心
                f_ok, f_msg = api.fetch_current_user()
                if f_ok:
                    user_id = (api.get_user_info() or {}).get("userId", "")
                    if user_id:
                        api.fetch_user_center(user_id)
                    self._append_log("五项清单: 已获取用户信息", "info")
                else:
                    self._append_log(f"获取用户信息失败: {f_msg}", "warning")
                return {"ok": True, "logged_in": True, "message": "登录成功"}
            else:
                self._append_log(f"五项清单自动登录失败: {msg}", "error")
                return {"ok": False, "logged_in": False, "message": msg}
        except Exception as e:
            return {"ok": False, "logged_in": False, "message": str(e)}

    def checklist_login(self, username, password):
        """五项清单登录"""
        try:
            api = self._get_checklist_api()
            ok, msg = api.login(username, password)
            if ok:
                self._append_log("五项清单登录成功", "success")
                # 登录成功后拉取用户信息和中心
                f_ok, f_msg = api.fetch_current_user()
                if f_ok:
                    user_id = (api.get_user_info() or {}).get("userId", "")
                    if user_id:
                        api.fetch_user_center(user_id)
                else:
                    self._append_log(f"获取用户信息失败: {f_msg}", "warning")
            else:
                self._append_log(f"五项清单登录失败: {msg}", "error")
            return {"ok": ok, "message": msg, "logged_in": ok}
        except Exception as e:
            return {"ok": False, "error": str(e), "logged_in": False}

    def checklist_auth_status(self):
        """获取五项清单登录状态和用户信息"""
        try:
            api = self._get_checklist_api()
            logged_in = api.is_logged_in()
            info = api.get_user_info() or {}
            center = api.get_center_name() or ""
            # 如果已登录但缓存为空，拉取一次
            if logged_in and (not info or not center):
                if not info:
                    try:
                        api.fetch_current_user()
                        info = api.get_user_info() or {}
                    except Exception:
                        pass
                if not center:
                    try:
                        user_id = info.get("userId", "")
                        if user_id:
                            api.fetch_user_center(user_id)
                            center = api.get_center_name() or ""
                    except Exception:
                        pass
            return {
                "ok": True, "logged_in": logged_in,
                "user_id": str(info.get("userId", "")),
                "real_name": info.get("userName", info.get("realName", "")),
                "center_name": center,
                "area_name": info.get("areaName", ""),
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "logged_in": False}

    def checklist_dicts(self):
        """获取五项清单字典选项，先拉取再返回"""
        try:
            api = self._get_checklist_api()
            if not api.is_logged_in():
                return {"ok": True, "types": [], "centers": [], "areas": [], "urgencies": []}
            api.fetch_dictionaries()
            return {
                "ok": True,
                "types": api.get_dict_options(CHECKLIST_TYPE_DICT_CODE) or [],
                "centers": api.get_dict_options(CHECKLIST_CENTER_DICT_CODE) or [],
                "areas": api.get_dict_options(CHECKLIST_AREA_DICT_CODE) or [],
                "urgencies": api.get_dict_options(CHECKLIST_URGENCY_DICT_CODE) or [],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def checklist_month_count(self):
        """获取本月提交数量"""
        try:
            api = self._get_checklist_api()
            if not api.is_logged_in():
                return {"ok": True, "count": 0}
            count = api.fetch_month_count()
            return {"ok": True, "count": count}
        except Exception:
            return {"ok": True, "count": 0}

    def checklist_submit(self, items_json, urgency_code, area_code, finish_time_str="", interval_min=20, interval_max=30):
        """批量提交五项清单（后台线程执行，前端轮询进度）
        items_json: JSON字符串 [{"content":"...","owner_name":"...","owner_id":"...","owner_center":"..."}]
        finish_time_str: "YYYY-MM-DD HH:MM:SS" 格式的期望完成时间
        interval_min: 最小延迟秒数（默认 20）
        interval_max: 最大延迟秒数（默认 30）
        """
        import json as _json
        import time as _time
        try:
            api = self._get_checklist_api()
            if not api.is_logged_in():
                return {"ok": False, "error": "请先登录五项清单"}

            items = _json.loads(items_json) if isinstance(items_json, str) else items_json

            user_info = api.get_user_info() or {}
            user_id = str(user_info.get("userId", ""))
            real_name = user_info.get("userName", user_info.get("realName", ""))
            my_center = api.get_center_name() or ""

            # 期望完成时间转换为毫秒时间戳（与旧 CTk 版逻辑一致）
            finish_time_ms = 0
            if finish_time_str:
                try:
                    from datetime import datetime
                    dt = datetime.strptime(finish_time_str.strip(), "%Y-%m-%d %H:%M:%S")
                    finish_time_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    self._append_log(f"期望完成时间格式无效: {finish_time_str}", "warning")

            item_dicts = []
            for it in items:
                content = (it.get("content") or "").strip()
                if not content:
                    continue
                owner_name = it.get("owner_name", "") or ""
                owner_id = it.get("owner_id", "") or ""
                owner_center = it.get("owner_center", "") or ""

                if owner_id and owner_id == user_id:
                    cur_type = "2"
                elif owner_center and my_center and owner_center == my_center:
                    cur_type = "5"
                else:
                    cur_type = "1"

                item_dicts.append({
                    "id": "", "flowId": "", "readStatus": "1", "isxs": "1",
                    "task_from": "0",
                    "raise_user_id": "",
                    "raise_user_name": real_name,
                    "raise_user_centre": my_center,
                    "type": cur_type,
                    "area": area_code or "",
                    "crmArea": "",
                    "level": urgency_code or "B",
                    "body": content,
                    "attach_url": [],
                    "owner_user_id": owner_id,
                    "owner_user_name": owner_name,
                    "owner_user_centre": owner_center,
                    "execute_user_id": _json.dumps([owner_id]) if owner_id else "[]",
                    "execute_user_name": owner_name,
                    "finish_time": finish_time_ms,
                    "beforeJudge": 2 if cur_type != "1" else 1,
                    "create_time": "",
                    "meeting_resolution_time": None,
                    "status": 3 if cur_type != "1" else 11,
                    "jnpf_meeting_task_jnpf_is_satisfaction": "-1",
                })

            if not item_dicts:
                return {"ok": False, "error": "请至少填写一条清单内容"}

            import random
            self._append_log(f"━━━ 开始提交 {len(item_dicts)} 条清单（间隔 {interval_min}-{interval_max}秒随机）━━━", "info")

            # 初始化进度状态
            self._cl_submit_cancelled = False  # 取消标志
            self._cl_submit_progress = {
                "running": True, "done": 0, "total": len(item_dicts),
                "ok_count": 0, "fail_count": 0, "error": "",
                "last_submit_time": 0, "interval_sec": 0,
                "interval_min": interval_min, "interval_max": interval_max,
                "cancelled": False
            }

            import time as _builtin_time
            def _run():
                t_start = _time.time()
                total = len(item_dicts)
                ok_count = 0
                fail_count = 0
                try:
                    for i, item in enumerate(item_dicts):
                        # 检查是否已被取消（当前这条仍会提交完，下一条不再提交）
                        if self._cl_submit_cancelled:
                            self._append_log("━━━ 用户终止提交，当前进度保留 ━━━", "warning")
                            break
                        ok, msg = api.submit_checklist(item, user_id=user_id)
                        if ok:
                            ok_count += 1
                        else:
                            fail_count += 1
                        cur = i + 1
                        # 为下一次提交计算随机间隔
                        current_interval = random.uniform(interval_min, interval_max) if cur < total else 0
                        self._cl_submit_progress["done"] = cur
                        self._cl_submit_progress["ok_count"] = ok_count
                        self._cl_submit_progress["fail_count"] = fail_count
                        self._cl_submit_progress["last_submit_time"] = _builtin_time.time()
                        self._cl_submit_progress["interval_sec"] = current_interval
                        elapsed = _time.time() - t_start
                        status = "✓" if ok else "✗"
                        self._append_log(f"  [{cur}/{total}] {status} ({elapsed:.1f}s) {msg}", "info" if ok else "error")
                        if cur < total:
                            _time.sleep(current_interval)

                    cancelled = self._cl_submit_cancelled
                    self._cl_submit_progress["running"] = False
                    self._cl_submit_progress["ok_count"] = ok_count
                    self._cl_submit_progress["fail_count"] = fail_count
                    self._cl_submit_progress["cancelled"] = cancelled
                    elapsed = _time.time() - t_start
                    if cancelled:
                        self._append_log(f"━━━ 已终止: 成功 {ok_count}, 失败 {fail_count}, 总耗时 {elapsed:.1f}s ━━━", "warning")
                    else:
                        self._append_log(f"━━━ 提交完成: 成功 {ok_count}, 失败 {fail_count}, 总耗时 {elapsed:.1f}s ━━━",
                                         "success" if fail_count == 0 else "error")
                except Exception as e:
                    self._cl_submit_progress["running"] = False
                    self._cl_submit_progress["error"] = str(e)
                    self._append_log(f"清单提交异常: {e}", "error")

            threading.Thread(target=_run, daemon=True).start()
            return {"ok": True, "running": True, "total": len(item_dicts)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def checklist_submit_cancel(self):
        """终止批量提交（当前正在提交的会完成，后续不再提交）"""
        self._cl_submit_cancelled = True
        self._append_log("收到终止指令，当前提交完成后停止...", "warning")
        return {"ok": True}

    def checklist_submit_progress(self):
        """轮询批量提交进度"""
        p = getattr(self, "_cl_submit_progress", None)
        if not p:
            return {"ok": True, "running": False, "done": 0, "total": 0, "ok_count": 0, "fail_count": 0}
        return {"ok": True, **p}

    def checklist_ai_generate(self, prompt, count, api_key, api_url, prototype_content=""):
        """AI 生成五项清单内容"""
        try:
            from app.ai.generator import generate_checklist_items
            # 从配置中获取模型
            ai = self._cfg.get_ai_settings()
            model = ai.get("model", "").strip() or None
            
            self._append_log("─" * 36)
            self._append_log("开始 AI 生成五项清单...", "ai")
            self._append_log(f"API: {api_url}", "ai")
            self._append_log(f"模型: {model or '自动检测'}", "ai")
            
            items = generate_checklist_items(
                api_key=api_key,
                api_url=api_url,
                model=model,
                prompt=prompt or "",
                count=int(count) or 10,
                prototype_content=prototype_content or "",
                status_callback=self._append_log,
            )
            return {"ok": True, "items": items}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def checklist_fetch_prototype(self, url):
        """抓取原型链接内容"""
        try:
            from app.prototype_importer import fetch_prototype_content
            import re
            result = fetch_prototype_content(url, status_callback=self._append_log)
            content = re.sub(r'\s+', '', result.get("content", ""))
            return {"ok": True, "content": content, "page_name": result.get("page_name", "")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # 回复/评价
    # ═══════════════════════════════════════════════════════════

    def reply_get_tasks(self):
        """获取待回复和待评价任务数量及列表"""
        try:
            api = self._get_checklist_api()
            if not api.is_logged_in():
                return {"ok": True, "reply_count": 0, "eval_count": 0, "total_pending": 0}

            ok, items = api.fetch_task_list()
            if not ok:
                return {"ok": True, "reply_count": 0, "eval_count": 0, "total_pending": 0}

            reply_tasks = [it for it in items if it.get("type") == "任务待解决-五项清单"]
            eval_tasks = [it for it in items if it.get("type") == "任务待评分"]
            total = len(reply_tasks) + len(eval_tasks)

            # 只返回摘要给前端
            return {
                "ok": True,
                "reply_count": len(reply_tasks),
                "eval_count": len(eval_tasks),
                "total_pending": total,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "reply_count": 0, "eval_count": 0, "total_pending": 0}

    def reply_batch_reply(self, content):
        """批量回复（后台线程执行，前端轮询进度）"""
        try:
            api = self._get_checklist_api()
            if not api.is_logged_in():
                return {"ok": False, "error": "请先登录"}

            ok, items = api.fetch_task_list()
            if not ok:
                return {"ok": False, "error": "获取任务列表失败"}

            reply_tasks = [it for it in items if it.get("type") == "任务待解决-五项清单"]
            if not reply_tasks:
                return {"ok": True, "count": 0, "msg": "没有待回复任务"}

            # 初始化进度状态
            self._reply_progress = {"running": True, "done": 0, "total": len(reply_tasks), "ok_count": 0, "fail_count": 0, "error": ""}

            def _prog(done, total, ok_flag, msg):
                self._reply_progress["done"] = done
                self._append_log(f"回复进度: {done}/{total}", "info")

            def _run():
                try:
                    ok_c, fail_c = api.batch_reply(reply_tasks, reply_text=content, progress_callback=_prog)
                    self._reply_progress["running"] = False
                    self._reply_progress["ok_count"] = ok_c
                    self._reply_progress["fail_count"] = fail_c
                    self._append_log(f"批量回复完成: 成功{ok_c}, 失败{fail_c}", "success")
                except Exception as e:
                    self._reply_progress["running"] = False
                    self._reply_progress["error"] = str(e)
                    self._append_log(f"批量回复异常: {e}", "error")

            threading.Thread(target=_run, daemon=True).start()
            return {"ok": True, "running": True, "total": len(reply_tasks)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reply_batch_reply_progress(self):
        """轮询批量回复进度"""
        p = getattr(self, "_reply_progress", None)
        if not p:
            return {"ok": True, "running": False, "done": 0, "total": 0, "ok_count": 0, "fail_count": 0}
        return {"ok": True, **p}

    def reply_batch_evaluate(self, result):
        """批量评价（后台线程执行，前端轮询进度）"""
        try:
            api = self._get_checklist_api()
            if not api.is_logged_in():
                return {"ok": False, "error": "请先登录"}

            ok, items = api.fetch_task_list()
            if not ok:
                return {"ok": False, "error": "获取任务列表失败"}

            eval_tasks = [it for it in items if it.get("type") == "任务待评分"]
            if not eval_tasks:
                return {"ok": True, "count": 0, "msg": "没有待评价任务"}

            satisfied = (result == "满意")

            self._eval_progress = {"running": True, "done": 0, "total": len(eval_tasks), "ok_count": 0, "fail_count": 0, "error": ""}

            def _prog(done, total, ok_flag, msg):
                self._eval_progress["done"] = done
                self._append_log(f"评价进度: {done}/{total}", "info")

            def _run():
                try:
                    ok_c, fail_c = api.batch_evaluate(eval_tasks, satisfied=satisfied, progress_callback=_prog)
                    self._eval_progress["running"] = False
                    self._eval_progress["ok_count"] = ok_c
                    self._eval_progress["fail_count"] = fail_c
                    self._append_log(f"批量评价完成: 成功{ok_c}, 失败{fail_c}", "success")
                except Exception as e:
                    self._eval_progress["running"] = False
                    self._eval_progress["error"] = str(e)
                    self._append_log(f"批量评价异常: {e}", "error")

            threading.Thread(target=_run, daemon=True).start()
            return {"ok": True, "running": True, "total": len(eval_tasks)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reply_batch_evaluate_progress(self):
        """轮询批量评价进度"""
        p = getattr(self, "_eval_progress", None)
        if not p:
            return {"ok": True, "running": False, "done": 0, "total": 0, "ok_count": 0, "fail_count": 0}
        return {"ok": True, **p}

    def reply_auto_settings(self):
        """获取自动回复/评价设置"""
        try:
            s = self._cfg.get_auto_reply_eval_settings()
            return {"ok": True, "settings": s}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reply_save_auto_settings(self, auto_reply_enabled, auto_eval_enabled, auto_reply_text, auto_eval_result):
        """保存自动回复/评价设置"""
        try:
            self._cfg.set_auto_reply_eval_settings(
                auto_reply_enabled=bool(auto_reply_enabled),
                auto_eval_enabled=bool(auto_eval_enabled),
                auto_reply_text=str(auto_reply_text or "收到"),
                auto_eval_result=str(auto_eval_result or "满意"),
            )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reply_save_batch_text(self, text):
        """保存批量回复输入框内容"""
        try:
            self._cfg.set_auto_reply_eval_settings(batch_reply_text=str(text or ""))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # 清单责任人搜索
    # ═══════════════════════════════════════════════════════════

    def checklist_search_user(self, keyword):
        """按姓名/手机号搜索用户，返回用户列表"""
        try:
            api = self._get_checklist_api()
            if not api.is_logged_in():
                return {"ok": False, "error": "请先登录", "users": []}
            ok, users = api.search_user(keyword)
            if ok:
                # 对每个用户用 ID 直接查中心
                result = []
                for u in users:
                    user_id = u.get("id", "")
                    entry = {
                        "id": str(user_id),
                        "fullName": u.get("fullName", ""),
                        "centerName": "",
                    }
                    if user_id:
                        try:
                            c_ok, center = api.fetch_user_center(user_id)
                            if c_ok:
                                entry["centerName"] = center or ""
                            else:
                                self._append_log(f"查中心失败(userId={user_id}): {center}", "warning")
                        except Exception as ex:
                            self._append_log(f"查中心异常: {ex}", "warning")
                    result.append(entry)
                return {"ok": True, "users": result}
            return {"ok": True, "users": []}
        except Exception as e:
            return {"ok": False, "error": str(e), "users": []}

    def checklist_get_interval(self):
        """获取批量提交间隔区间秒数"""
        try:
            settings = self._cfg.get_checklist_settings()
            interval_min = settings.get("submit_interval_min", 20)
            interval_max = settings.get("submit_interval_max", 30)
            return {"ok": True, "interval_min": interval_min, "interval_max": interval_max}
        except Exception as e:
            return {"ok": False, "error": str(e), "interval_min": 20, "interval_max": 30}

    def checklist_set_interval(self, interval_min, interval_max):
        """设置批量提交间隔区间秒数"""
        try:
            self._cfg.set_checklist_settings(
                submit_interval_min=int(interval_min),
                submit_interval_max=int(interval_max)
            )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def checklist_save_owners(self, owners_json):
        """保存责任人记忆到 config.json"""
        try:
            owners = json.loads(owners_json) if isinstance(owners_json, str) else owners_json
            self._cfg.set_remembered_owners(owners)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def checklist_load_owners(self):
        """加载记忆的责任人列表"""
        try:
            owners = self._cfg.get_remembered_owners()
            return {"ok": True, "owners": owners}
        except Exception as e:
            return {"ok": False, "error": str(e), "owners": []}

    # ═══════════════════════════════════════════════════════════
    # 神秘工具 — BPE (Breakpoint Parameter Editor)
    # ═══════════════════════════════════════════════════════════

    def bpe_start(self, username, password, api_pattern, date_start, date_end, capacity):
        """启动 BPE 自动化任务（后台线程，日志通过全局日志通道推送）"""
        from app.mystery.bpe_runner import BPERunner

        if getattr(self, '_bpe_runner', None) and self._bpe_runner.is_running:
            return {"ok": False, "error": "已有 BPE 任务在执行中，请等待完成"}

        if not username or not password:
            return {"ok": False, "error": "账号和密码不能为空"}
        if not api_pattern:
            return {"ok": False, "error": "断点接口匹配不能为空"}

        try:
            cap_val = int(capacity) if capacity else 400
            if cap_val <= 0:
                cap_val = 400
        except Exception:
            cap_val = 400

        # 启动即保存凭据，下次自动填充
        self._cfg.set_bpe_settings(username, password)

        self._append_log("─" * 36)
        self._append_log("🔮 BPE 任务启动...")

        def on_log(msg):
            self._append_log(msg)

        def on_finish(ok, msg):
            if ok:
                self._append_log(f"✅ BPE 完成: {msg}", "success")
            else:
                self._append_log(f"❌ BPE 失败: {msg}", "error")
            self._push_event("bpe_done", {"ok": ok, "msg": msg})

        self._bpe_runner = BPERunner(log_callback=on_log, finish_callback=on_finish)
        self._bpe_runner.start(
            username=username,
            password=password,
            api_pattern=api_pattern,
            date_start=date_start,
            date_end=date_end,
            capacity=cap_val,
            headless=False,
        )
        return {"ok": True, "running": True}

    def bpe_status(self):
        """查询 BPE 运行状态"""
        running = getattr(self, '_bpe_runner', None) and self._bpe_runner.is_running
        return {"ok": True, "running": bool(running)}

    def bpe_get_config(self):
        """获取已保存的 BPE 账号密码"""
        s = self._cfg.get_bpe_settings()
        return {"ok": True, "username": s.get("username", ""), "password": s.get("password", "")}

    def mystery_letter_mark_seen(self):
        """标记神秘工具留言已读（持久化到 config.json）"""
        self._cfg._data['mystery_letter_seen'] = True
        self._cfg.save()
        return {"ok": True}

    def mystery_letter_is_seen(self):
        """检查神秘工具留言是否已读"""
        return {"ok": True, "seen": bool(self._cfg._data.get('mystery_letter_seen'))}

    # ═══════════════════════════════════════════════════════════
    # 调度器
    # ═══════════════════════════════════════════════════════════

    def start_schedulers(self):
        """启动所有后台定时器（窗口创建后调用）"""
        self._start_report_scheduler()
        self._start_auto_reply_eval_scheduler()

    def stop_schedulers(self):
        """停止所有后台定时器（窗口关闭前调用）"""
        self._sched_stop.set()
        self._auto_reply_stop.set()

    def _start_report_scheduler(self):
        """日报定时填写 —— 后台线程轮询，每分钟检查一次"""
        if self._sched_thread and self._sched_thread.is_alive():
            return
        self._sched_stop.clear()
        self._sched_thread = threading.Thread(
            target=self._report_scheduler_loop, daemon=True, name="ReportScheduler"
        )
        self._sched_thread.start()

    def _report_scheduler_loop(self):
        while not self._sched_stop.is_set():
            try:
                s = self._cfg.get_schedule_settings()
                if s.get("enabled", False) and not self._is_running:
                    now = datetime.now()
                    target = s.get("time", "20:30")
                    current_hm = now.strftime("%H:%M")
                    if current_hm == target and self._sched_last_run_date != now.date():
                        self._sched_last_run_date = now.date()
                        self._append_log("─" * 36)
                        self._append_log(f"[定时任务] 到达预定时间 {target}，开始自动填写日报")
                        self._execute_scheduled_fill()
            except Exception as e:
                self._append_log(f"[定时任务] 检查异常: {e}", "error")
            # 每分钟轮询一次
            if self._sched_stop.wait(timeout=60):
                break

    def _execute_scheduled_fill(self):
        """执行定时日报填写（不依赖前端交互）"""
        try:
            fields = self._cfg.get_field_contents()
            account = self._cfg.get_account()
            bs = self._cfg.get_browser_settings()
            auto_submit = self._cfg.get_auto_submit()

            empty = [l for l, c in fields.items() if not c.strip()]
            if empty:
                self._append_log(f"[定时任务] 未填写完整: {', '.join(empty[:3])}", "error")
                return

            engine = DailyReportEngine(
                field_contents=fields,
                account=account,
                status_callback=self._append_log,
                step_delay=bs.get("step_delay", 1.0),
                headless=bs.get("headless", True),
                auto_submit=auto_submit,
                manual_callback=None,
            )
            engine.run()
            self._append_log("[定时任务] 日报填写成功", "success")
        except Exception as e:
            self._append_log(f"[定时任务] 执行异常: {e}", "error")

    def _start_auto_reply_eval_scheduler(self):
        """自动回复/评价 —— 后台线程，每月最后一天 20:30 触发"""
        if self._auto_reply_thread and self._auto_reply_thread.is_alive():
            return
        self._auto_reply_stop.clear()
        self._auto_reply_thread = threading.Thread(
            target=self._auto_reply_eval_loop, daemon=True, name="AutoReplyEval"
        )
        self._auto_reply_thread.start()

    def _auto_reply_eval_loop(self):
        while not self._auto_reply_stop.is_set():
            try:
                now = datetime.now()
                today = now.date()
                hm = now.strftime("%H:%M")
                last_day = calendar.monthrange(today.year, today.month)[1]
                if (today.day == last_day and hm == "20:30"
                        and self._auto_reply_last_run_date != today):
                    self._auto_reply_last_run_date = today
                    self._do_auto_reply_and_eval()
            except Exception as e:
                self._append_log(f"[自动处理] 检查异常: {e}", "error")
            if self._auto_reply_stop.wait(timeout=30):
                break

    def _do_auto_reply_and_eval(self):
        """执行自动回复 + 评价"""
        try:
            api = self._get_checklist_api()
            if not api.is_logged_in():
                self._append_log("[自动处理] 未登录五项清单，跳过", "error")
                return

            s = self._cfg.get_auto_reply_eval_settings()
            reply_on = s.get("auto_reply_enabled", False)
            eval_on = s.get("auto_eval_enabled", False)
            if not reply_on and not eval_on:
                return

            self._append_log("─" * 36)
            self._append_log("[自动处理] 月末自动处理开始")

            ok, items = api.fetch_task_list()
            if not ok:
                return

            reply_tasks = [it for it in items if it.get("type") == "任务待解决-五项清单"]
            eval_tasks = [it for it in items if it.get("type") == "任务待评分"]

            if reply_on and reply_tasks:
                text = s.get("auto_reply_text", "收到")
                def _rp(done, total, ok_flag, msg):
                    self._append_log(f"[自动处理] 回复进度: {done}/{total}", "info")
                api.batch_reply(reply_tasks, reply_text=text, progress_callback=_rp)
                self._append_log(f"[自动处理] 批量回复完成: {len(reply_tasks)} 条", "success")

            if eval_on and eval_tasks:
                satisfied = (s.get("auto_eval_result", "满意") == "满意")
                def _ep(done, total, ok_flag, msg):
                    self._append_log(f"[自动处理] 评价进度: {done}/{total}", "info")
                api.batch_evaluate(eval_tasks, satisfied=satisfied, progress_callback=_ep)
                self._append_log(f"[自动处理] 批量评价完成: {len(eval_tasks)} 条", "success")

            self._append_log("[自动处理] 月末自动处理结束", "success")
            self._push_event("auto_done", {"reply_on": reply_on, "eval_on": eval_on})
        except Exception as e:
            self._append_log(f"[自动处理] 执行异常: {e}", "error")
