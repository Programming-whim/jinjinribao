"""配置管理：JSON 文件持久化，支持加载、保存、更新"""

import json
import os
from datetime import datetime, date
from app.constants import (
    FIELD_LABELS, DEFAULT_FIELD_CONTENT,
    DEFAULT_SCHEDULE_TIME, DEFAULT_SCHEDULE_ENABLED,
    DEFAULT_HEADLESS, DEFAULT_STEP_DELAY,
    DEFAULT_USERNAME, DEFAULT_PASSWORD,
    DEFAULT_AUTO_SUBMIT,
    DEFAULT_AI_API_KEY, DEFAULT_AI_API_URL, DEFAULT_AI_MODEL, DEFAULT_AI_ROLE,
)


class ConfigManager:
    def __init__(self, config_path="config.json"):
        self._path = config_path
        self._data = {}
        self.load()

    def _defaults(self):
        fields = {label: "" for label in FIELD_LABELS}
        return {
            "fields": fields,
            "schedule": {
                "enabled": DEFAULT_SCHEDULE_ENABLED,
                "time": DEFAULT_SCHEDULE_TIME,
            },
            "browser": {
                "headless": DEFAULT_HEADLESS,
                "step_delay": DEFAULT_STEP_DELAY,
            },
            "account": {
                "username": DEFAULT_USERNAME,
                "password": DEFAULT_PASSWORD,
            },
            "auto_submit": DEFAULT_AUTO_SUBMIT,
            "ai": {
                "api_key": DEFAULT_AI_API_KEY,
                "api_url": DEFAULT_AI_API_URL,
                "model": DEFAULT_AI_MODEL,
                "prompt_template": DEFAULT_AI_ROLE,
            },
        }

    def load(self):
        defaults = self._defaults()
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._data = self._merge(defaults, stored)
                self._migrate_fields()
            except (json.JSONDecodeError, IOError):
                self._data = defaults
        else:
            self._data = defaults
        self.save()

    def _merge(self, defaults, stored):
        result = {}
        for key, default_val in defaults.items():
            if key in stored:
                if (isinstance(default_val, dict) and isinstance(stored[key], dict)
                        and key != "fields"):
                    result[key] = self._merge(default_val, stored[key])
                else:
                    result[key] = stored[key]
            else:
                result[key] = default_val
        for key, val in stored.items():
            if key not in defaults:
                result[key] = val
        return result

    def _migrate_fields(self):
        """迁移旧格式：多日列表 -> 单字符串（取今天对应的值）"""
        fields = self._data.get("fields", {})
        today_idx = min(datetime.now().weekday(), 6)
        for label in FIELD_LABELS:
            if label in fields:
                val = fields[label]
                if isinstance(val, list):
                    # 旧格式：数组，取今天对应的值，超出范围则取第一个非空值
                    if 0 <= today_idx < len(val) and val[today_idx]:
                        fields[label] = val[today_idx]
                    else:
                        # 取第一个非空值，若全空则为空字符串
                        fields[label] = next((v for v in val if v), "")
                elif not isinstance(val, str):
                    fields[label] = ""
            else:
                fields[label] = ""
        # 清理多余字段
        self._data["fields"] = {k: v for k, v in fields.items() if k in FIELD_LABELS}
        # 清理已废弃的 current_day
        self._data.pop("current_day", None)

    def save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ---- 字段操作 ----
    def get_field_content(self, label):
        fields = self._data.get("fields", {})
        val = fields.get(label, "")
        if isinstance(val, list):
            return val[0] if val else ""
        return val if isinstance(val, str) else ""

    def set_field_content(self, label, content, persist=True):
        self._data.setdefault("fields", {})[label] = content
        if persist:
            self.save()

    # ---- 批量操作 ----
    def get_field_contents(self):
        """获取所有字段内容（扁平字典）"""
        return {label: self.get_field_content(label) for label in FIELD_LABELS}

    def set_all_fields(self, fields_dict, persist=True):
        """批量保存所有字段"""
        fields = self._data.setdefault("fields", {})
        for label, content in fields_dict.items():
            if label in FIELD_LABELS:
                fields[label] = content
        if persist:
            self.save()

    def reset_all_fields(self):
        self._data["fields"] = {label: "" for label in FIELD_LABELS}
        self.save()

    # ---- schedule ----
    def get_schedule_settings(self):
        return dict(self._data.get("schedule", {"enabled": False, "time": "18:00"}))

    def set_schedule_settings(self, enabled, time_str):
        self._data["schedule"] = {"enabled": enabled, "time": time_str}
        self.save()

    # ---- browser ----
    def get_browser_settings(self):
        return dict(self._data.get("browser", {"headless": False, "step_delay": 1.0}))

    # ---- account ----
    def get_account(self):
        acc = self._data.get("account", {})
        return acc.get("username", DEFAULT_USERNAME), acc.get("password", DEFAULT_PASSWORD)

    def set_account(self, username, password, persist=True):
        self._data["account"] = {"username": username, "password": password}
        if persist:
            self.save()

    # ---- auto_submit ----
    def get_auto_submit(self):
        return self._data.get("auto_submit", DEFAULT_AUTO_SUBMIT)

    def set_auto_submit(self, enabled, persist=True):
        self._data["auto_submit"] = bool(enabled)
        if persist:
            self.save()

    # ---- AI settings ----
    def get_ai_settings(self):
        defaults = {
            "api_key": DEFAULT_AI_API_KEY,
            "api_url": DEFAULT_AI_API_URL,
            "model": DEFAULT_AI_MODEL,
            "prompt_template": DEFAULT_AI_ROLE,
        }
        stored = self._data.get("ai", {})
        defaults.update(stored)
        return defaults

    def set_ai_settings(self, api_key, api_url, model, prompt_template, persist=True):
        self._data["ai"] = {
            "api_key": api_key,
            "api_url": api_url,
            "model": model,
            "prompt_template": prompt_template,
        }
        if persist:
            self.save()

    # ---- 更新检查 ----
    def get_last_check_date(self):
        return self._data.get("last_check_date", "")

    def set_last_check_date(self, check_date):
        self._data["last_check_date"] = check_date
        self.save()

    def should_check_today(self):
        last = self.get_last_check_date()
        today = date.today().isoformat()
        return last != today

    def get_local_exe_size(self):
        return self._data.get("local_exe_size", 0)

    def set_local_exe_size(self, size):
        self._data["local_exe_size"] = size
        self.save()

    def get_skip_exe_size(self):
        return self._data.get("skip_exe_size", 0)

    def set_skip_exe_size(self, size):
        self._data["skip_exe_size"] = size
        self.save()

    # ---- bulk ----
    def get_all(self):
        return dict(self._data)

    def export_config(self, export_path):
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def import_config(self, import_path):
        with open(import_path, "r", encoding="utf-8") as f:
            imported = json.load(f)
        self._data = self._merge(self._defaults(), imported)
        self._migrate_fields()
        self.save()
