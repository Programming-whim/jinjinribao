"""Flask Web 路由：登录、工作台、配置、定时、API"""

import os
import sys
import threading
import json
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, jsonify

from app.config_manager import ConfigManager
from app.constants import FIELD_LABELS, APP_VERSION

bp = Blueprint("main", __name__)

# config.json 放在 main.py 同级目录
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(_BASE, "config.json")


def get_cfg():
    return ConfigManager(config_path=CONFIG_PATH)


def get_socketio():
    from flask import current_app
    return current_app.extensions["socketio"]


# ==================== 页面路由 ====================

@bp.route("/")
def index():
    if not os.path.exists(CONFIG_PATH):
        return redirect(url_for("main.login_page"))
    cfg = get_cfg()
    username, _ = cfg.get_account()
    if not username.strip():
        return redirect(url_for("main.login_page"))
    return redirect(url_for("main.operation_page"))


@bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username and password:
            cfg = get_cfg()
            cfg.set_account(username, password)
            return redirect(url_for("main.operation_page"))
    return render_template("login.html")


@bp.route("/logout")
def logout():
    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
    return redirect(url_for("main.login_page"))


@bp.route("/operation")
def operation_page():
    cfg = get_cfg()
    username, _ = cfg.get_account()
    fields = cfg.get_field_contents()
    auto_submit = cfg.get_auto_submit()
    ai_settings = cfg.get_ai_settings()
    return render_template("operation.html",
                           username=username,
                           fields=fields,
                           field_labels=FIELD_LABELS,
                           auto_submit=auto_submit,
                           ai_settings=ai_settings,
                           version=APP_VERSION)


@bp.route("/config")
def config_page():
    cfg = get_cfg()
    username, password = cfg.get_account()
    browser = cfg.get_browser_settings()
    ai_settings = cfg.get_ai_settings()
    auto_submit = cfg.get_auto_submit()
    return render_template("config.html",
                           username=username,
                           password=password,
                           browser=browser,
                           ai_settings=ai_settings,
                           auto_submit=auto_submit)


@bp.route("/schedule")
def schedule_page():
    cfg = get_cfg()
    sched = cfg.get_schedule_settings()
    username, _ = cfg.get_account()
    return render_template("schedule.html",
                           username=username,
                           schedule=sched)


# ==================== API 路由 ====================

@bp.route("/api/save_fields", methods=["POST"])
def save_fields():
    data = request.get_json()
    cfg = get_cfg()
    fields = data.get("fields", {})
    cfg.set_all_fields(fields)
    return jsonify({"ok": True})


@bp.route("/api/save_config", methods=["POST"])
def save_config():
    data = request.get_json()
    cfg = get_cfg()
    if "username" in data and "password" in data:
        cfg.set_account(data["username"], data["password"])
    if "auto_submit" in data:
        cfg.set_auto_submit(data["auto_submit"])
    if "ai" in data:
        ai = data["ai"]
        cfg.set_ai_settings(
            ai.get("api_key", ""),
            ai.get("api_url", ""),
            ai.get("model", ""),
            ai.get("prompt_template", ""),
        )
    if "browser" in data:
        browser = data["browser"]
        cfg._data["browser"] = {
            "headless": True,
            "step_delay": browser.get("step_delay", 1.0),
        }
        cfg.save()
    return jsonify({"ok": True})


@bp.route("/api/save_schedule", methods=["POST"])
def save_schedule():
    data = request.get_json()
    cfg = get_cfg()
    cfg.set_schedule_settings(
        data.get("enabled", False),
        data.get("time", "18:00"),
    )
    # 通知 scheduler 重新读取配置
    from flask import current_app
    scheduler = current_app.config.get("SCHEDULER")
    if scheduler:
        scheduler.reload()
    return jsonify({"ok": True})


@bp.route("/api/generate_ai", methods=["POST"])
def generate_ai():
    from app.ai.generator import generate_report
    data = request.get_json()
    field1 = data.get("field1_content", "")
    cfg = get_cfg()
    ai = cfg.get_ai_settings()
    role = ai.get("prompt_template", "")

    socketio = get_socketio()

    def status_cb(msg, level="info"):
        socketio.emit("log", {
            "msg": msg, "level": level,
            "time": datetime.now().strftime("%H:%M:%S")
        })

    try:
        result = generate_report(
            field1,
            api_key=ai["api_key"],
            api_url=ai["api_url"],
            model=ai["model"],
            role_description=role,
            status_callback=status_cb,
        )
        return jsonify({"ok": True, "fields": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@bp.route("/api/run_report", methods=["POST"])
def run_report():
    from app.automation.reporter import DailyReportEngine

    cfg = get_cfg()
    username, password = cfg.get_account()
    fields = cfg.get_field_contents()
    browser = cfg.get_browser_settings()
    auto_submit = cfg.get_auto_submit()

    socketio = get_socketio()

    def status_callback(msg, level="info"):
        socketio.emit("log", {
            "msg": msg, "level": level,
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def run_engine():
        try:
            engine = DailyReportEngine(
                field_contents=fields,
                account=(username, password),
                status_callback=status_callback,
                step_delay=browser.get("step_delay", 1.0),
                headless=True,
                auto_submit=auto_submit,
            )
            engine.run()
        except Exception as e:
            status_callback(f"执行异常: {e}", "error")
        finally:
            status_callback("全部流程执行完毕", "success")

    t = threading.Thread(target=run_engine, daemon=True)
    t.start()
    return jsonify({"ok": True, "msg": "日报填写任务已启动"})
