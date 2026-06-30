"""Flask 路由 + SocketIO 事件处理"""

import os
import json
import threading
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, Response
from flask_socketio import emit

from app.config_manager import ConfigManager
from app.constants import FIELD_LABELS, APP_VERSION, APP_TITLE

bp = Blueprint("main", __name__)

# 全局状态
_cfg: ConfigManager = None
_socketio = None
_is_running = False


def init_config_manager():
    global _cfg
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    config_path = os.path.normpath(config_path)
    if os.path.exists(config_path):
        _cfg = ConfigManager(config_path=config_path)
    else:
        _cfg = None


def init_scheduler(socketio):
    global _socketio
    _socketio = socketio
    if _cfg is not None:
        from app.scheduler.scheduler import ReportScheduler
        scheduler = ReportScheduler(
            time_str_getter=lambda: _cfg.get_schedule_settings().get("time", "18:00"),
            enabled_getter=lambda: _cfg.get_schedule_settings().get("enabled", False),
            trigger_callback=lambda: _trigger_automation_internal(),
        )
        scheduler.start()


def _is_logged_in():
    return _cfg is not None


def _status_callback(message, level="info"):
    """桥接日志到 SocketIO"""
    if _socketio:
        ts = datetime.now().strftime("%H:%M:%S")
        prefix_map = {"info": "[INFO]", "success": "[ OK ]", "error": "[ERR]", "ai": "[ AI ]"}
        tag = prefix_map.get(level, "[???]")
        _socketio.emit("log_message", {
            "time": ts,
            "tag": tag,
            "message": message,
            "level": level,
        })


# ────────────────────────────────────────────────────────────────
# 页面路由
# ────────────────────────────────────────────────────────────────

@bp.route("/")
def index():
    if not _is_logged_in():
        return redirect(url_for("main.login_page"))
    return redirect(url_for("main.operation_page"))


@bp.route("/login")
def login_page():
    if _is_logged_in():
        return redirect(url_for("main.operation_page"))
    return render_template("login.html", app_title=APP_TITLE)


@bp.route("/login", methods=["POST"])
def do_login():
    global _cfg
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"ok": False, "msg": "账号和密码不能为空"}), 400

    config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    config_path = os.path.normpath(config_path)
    _cfg = ConfigManager(config_path=config_path)
    _cfg.set_account(username, password)
    return jsonify({"ok": True})


@bp.route("/logout", methods=["POST"])
def logout():
    global _cfg
    if _cfg:
        _cfg.set_account("", "")
        _cfg.save()
        _cfg = None
    return jsonify({"ok": True})


@bp.route("/workspace")
def operation_page():
    if not _is_logged_in():
        return redirect(url_for("main.login_page"))
    username, _ = _cfg.get_account()
    fields = _cfg.get_field_contents()
    ai_settings = _cfg.get_ai_settings()
    auto_submit = _cfg.get_auto_submit()
    return render_template(
        "operation.html",
        app_title=APP_TITLE,
        app_version=APP_VERSION,
        username=username,
        fields=fields,
        field_labels=FIELD_LABELS,
        ai_settings=ai_settings,
        auto_submit=auto_submit,
        active_page="工作台",
    )


@bp.route("/config")
def config_page():
    if not _is_logged_in():
        return redirect(url_for("main.login_page"))
    username, _ = _cfg.get_account()
    fields = _cfg.get_field_contents()
    ai_settings = _cfg.get_ai_settings()
    return render_template(
        "config.html",
        app_title=APP_TITLE,
        app_version=APP_VERSION,
        username=username,
        fields=fields,
        field_labels=FIELD_LABELS,
        ai_settings=ai_settings,
        active_page="内容配置",
    )


@bp.route("/schedule")
def schedule_page():
    if not _is_logged_in():
        return redirect(url_for("main.login_page"))
    username, _ = _cfg.get_account()
    sched = _cfg.get_schedule_settings()
    return render_template(
        "schedule.html",
        app_title=APP_TITLE,
        app_version=APP_VERSION,
        username=username,
        schedule=sched,
        active_page="定时设置",
    )


# ────────────────────────────────────────────────────────────────
# API 路由
# ────────────────────────────────────────────────────────────────

@bp.route("/api/trigger", methods=["POST"])
def api_trigger():
    global _is_running
    if not _is_logged_in():
        return jsonify({"ok": False, "msg": "未登录"}), 401
    if _is_running:
        return jsonify({"ok": False, "msg": "任务正在执行中，请稍候..."}), 409

    fields = _cfg.get_field_contents()
    empty_fields = [label for label, content in fields.items() if not content.strip()]
    if empty_fields:
        msg = "以下日报内容尚未填写，请先完成后再执行：\n" + "\n".join(f"• {f}" for f in empty_fields)
        _status_callback(f"执行失败：有 {len(empty_fields)} 个字段未填写", "error")
        return jsonify({"ok": False, "msg": msg}), 400

    _is_running = True
    if _socketio:
        _socketio.emit("status_update", {"type": "running", "value": True})

    t = threading.Thread(target=_run_automation, daemon=True)
    t.start()
    return jsonify({"ok": True})


def _run_automation():
    global _is_running
    success = False
    try:
        from app.automation.reporter import DailyReportEngine
        fields = _cfg.get_field_contents()
        account = _cfg.get_account()
        browser_settings = _cfg.get_browser_settings()
        auto_submit = _cfg.get_auto_submit()

        _status_callback("开始执行日报自动填写...")
        _status_callback("提交模式: 自动提交" if auto_submit else "提交模式: 手动提交")

        engine = DailyReportEngine(
            field_contents=fields,
            account=account,
            status_callback=_status_callback,
            step_delay=browser_settings.get("step_delay", 1.0),
            headless=browser_settings.get("headless", False),
            auto_submit=auto_submit,
        )
        engine.run()
        success = True
        _status_callback("日报填写成功！", "success")

        # 成功后清空字段2-8
        for label in FIELD_LABELS[1:]:
            _cfg.set_field_content(label, "", persist=False)
        _cfg.save()
        _status_callback("已清空字段2-8，字段1已保留", "info")

        if _socketio:
            _socketio.emit("fields_cleared", {})
    except Exception as e:
        _status_callback(f"执行异常: {e}", "error")
    finally:
        _is_running = False
        if _socketio:
            _socketio.emit("status_update", {"type": "running", "value": False})


def _trigger_automation_internal():
    """供定时调度器调用"""
    global _is_running
    if not _is_logged_in() or _is_running:
        return
    fields = _cfg.get_field_contents()
    empty_fields = [label for label, content in fields.items() if not content.strip()]
    if empty_fields:
        _status_callback(f"定时触发失败：有 {len(empty_fields)} 个字段未填写", "error")
        return
    _is_running = True
    if _socketio:
        _socketio.emit("status_update", {"type": "running", "value": True})
    t = threading.Thread(target=_run_automation, daemon=True)
    t.start()


@bp.route("/api/ai_generate", methods=["POST"])
def api_ai_generate():
    if not _is_logged_in():
        return jsonify({"ok": False, "msg": "未登录"}), 401
    if _is_running:
        return jsonify({"ok": False, "msg": "自动填写正在执行中，请稍候..."}), 409

    ai_settings = _cfg.get_ai_settings()
    if not ai_settings.get("api_key", "").strip():
        return jsonify({"ok": False, "msg": "请先在「内容配置」中填写 API Key"}), 400

    field1_content = _cfg.get_field_content(FIELD_LABELS[0])
    if not field1_content.strip():
        return jsonify({"ok": False, "msg": "请先填写字段1（付出不亚于任何人的努力）"}), 400

    # 校验职位描述是否填写
    ai_settings = _cfg.get_ai_settings()
    role_description = ai_settings.get("prompt_template", "")
    if not role_description.strip():
        return jsonify({"ok": False, "msg": "请先填写职位描述"}), 400

    if _socketio:
        _socketio.emit("status_update", {"type": "ai_running", "value": True})

    t = threading.Thread(target=_run_ai_generate, daemon=True)
    t.start()
    return jsonify({"ok": True})


def _run_ai_generate():
    try:
        from app.ai.generator import generate_report
        ai_settings = _cfg.get_ai_settings()
        field1_content = _cfg.get_field_content(FIELD_LABELS[0])

        _status_callback("开始 AI 智能生成日报内容...", "ai")
        _status_callback(f"API: {ai_settings.get('api_url')}", "ai")

        result = generate_report(
            field1_content=field1_content,
            api_key=ai_settings["api_key"].strip(),
            api_url=ai_settings["api_url"].strip(),
            role_description=ai_settings.get("prompt_template", ""),
            status_callback=_status_callback,
        )

        for label in FIELD_LABELS[1:]:
            content = result.get(label, "")
            _cfg.set_field_content(label, content, persist=False)
        _cfg.save()

        _status_callback("AI 生成完成，已保存到当前配置", "success")
        for label in FIELD_LABELS[1:]:
            content = result.get(label, "")
            preview = content[:40] + "..." if len(content) > 40 else content
            if preview:
                _status_callback(f"  {label[:6]}... → {preview}", "success")

        if _socketio:
            fields = _cfg.get_field_contents()
            _socketio.emit("ai_complete", {"fields": fields})
    except Exception as e:
        _status_callback(f"AI 生成失败: {e}", "error")
    finally:
        if _socketio:
            _socketio.emit("status_update", {"type": "ai_running", "value": False})


@bp.route("/api/config", methods=["GET"])
def api_get_config():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    return jsonify({
        "ok": True,
        "fields": _cfg.get_field_contents(),
        "ai": _cfg.get_ai_settings(),
        "auto_submit": _cfg.get_auto_submit(),
    })


@bp.route("/api/config", methods=["POST"])
def api_save_config():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    data = request.get_json()

    if "fields" in data:
        for label in FIELD_LABELS:
            if label in data["fields"]:
                _cfg.set_field_content(label, data["fields"][label], persist=False)

    if "ai" in data:
        ai = data["ai"]
        _cfg.set_ai_settings(
            ai.get("api_key", ""),
            ai.get("api_url", ""),
            ai.get("model", ""),
            ai.get("prompt_template", ""),
            persist=False,
        )

    if "auto_submit" in data:
        _cfg.set_auto_submit(bool(data["auto_submit"]), persist=False)

    _cfg.save()
    return jsonify({"ok": True})


@bp.route("/api/config/field1", methods=["POST"])
def api_save_field1():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    data = request.get_json()
    content = data.get("content", "")
    _cfg.set_field_content(FIELD_LABELS[0], content, persist=True)
    return jsonify({"ok": True})


@bp.route("/api/config/role", methods=["POST"])
def api_save_role():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    data = request.get_json()
    role = data.get("role", "")
    ai = _cfg.get_ai_settings()
    _cfg.set_ai_settings(
        ai.get("api_key", ""),
        ai.get("api_url", ""),
        "",
        role,
        persist=True,
    )
    return jsonify({"ok": True})


@bp.route("/api/config/reset", methods=["POST"])
def api_reset_config():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    _cfg.reset_all_fields()
    return jsonify({"ok": True, "fields": _cfg.get_field_contents()})


@bp.route("/api/config/export")
def api_export_config():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    all_data = _cfg.get_all()
    return Response(
        json.dumps(all_data, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=daily_report_config.json"},
    )


@bp.route("/api/config/import", methods=["POST"])
def api_import_config():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    if "file" not in request.files:
        return jsonify({"ok": False, "msg": "未上传文件"}), 400
    f = request.files["file"]
    try:
        imported = json.loads(f.read().decode("utf-8"))
        _cfg._data = _cfg._merge(_cfg._defaults(), imported)
        _cfg._migrate_fields()
        _cfg.save()
        return jsonify({"ok": True, "fields": _cfg.get_field_contents()})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"导入失败: {e}"}), 400


@bp.route("/api/schedule", methods=["GET"])
def api_get_schedule():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "schedule": _cfg.get_schedule_settings()})


@bp.route("/api/schedule", methods=["POST"])
def api_save_schedule():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    data = request.get_json()
    enabled = bool(data.get("enabled", False))
    time_str = data.get("time", "18:00")
    _cfg.set_schedule_settings(enabled, time_str)
    return jsonify({"ok": True})


@bp.route("/api/auto_submit", methods=["POST"])
def api_auto_submit():
    if not _is_logged_in():
        return jsonify({"ok": False}), 401
    data = request.get_json()
    enabled = bool(data.get("enabled", False))
    _cfg.set_auto_submit(enabled, persist=True)
    return jsonify({"ok": True})


# ────────────────────────────────────────────────────────────────
# SocketIO 事件
# ────────────────────────────────────────────────────────────────

@bp.app_errorhandler(404)
def not_found(e):
    return redirect(url_for("main.index"))
