"""精进日报自动填写工具 - 入口文件（支持桌面模式 & Web模式）"""

import os
import sys
import webbrowser
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def run_web():
    """Web 模式：启动 Flask 服务，本地自动打开浏览器，服务器模式监听 PORT"""
    from flask import Flask
    from flask_socketio import SocketIO
    from app.web.routes import bp, get_cfg
    from app.scheduler.web_scheduler import WebScheduler

    # 服务器模式：Railway 注入 PORT 环境变量
    is_server = bool(os.environ.get("PORT"))
    port = int(os.environ.get("PORT", 5678))
    host = "0.0.0.0" if is_server else "127.0.0.1"

    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "app", "templates"),
        static_folder=os.path.join(BASE_DIR, "app", "static"),
    )
    app.secret_key = os.environ.get("SECRET_KEY", "jinjinribao-local-secret-key")
    app.config["JSON_AS_ASCII"] = False

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    app.register_blueprint(bp)

    # 定时任务
    def scheduled_trigger():
        socketio.emit("log", {
            "msg": "⏰ 定时任务触发，开始执行日报填写...",
            "level": "info",
            "time": ""
        })
        import requests as _req
        try:
            _req.post(f"http://127.0.0.1:{port}/api/run_report", timeout=5)
        except Exception:
            pass

    scheduler = WebScheduler(
        time_getter=lambda: get_cfg().get_schedule_settings().get("time", "18:00"),
        enabled_getter=lambda: get_cfg().get_schedule_settings().get("enabled", False),
        trigger_callback=scheduled_trigger,
    )
    app.config["SCHEDULER"] = scheduler
    scheduler.start()

    # 本地模式自动打开浏览器，服务器模式不打开
    if not is_server:
        url = f"http://127.0.0.1:{port}"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    print(f"\n{'='*50}")
    if is_server:
        print(f"  精进日报工具 - 服务器模式")
        print(f"  监听地址: http://{host}:{port}")
    else:
        print(f"  精进日报工具已启动！浏览器将自动打开")
        print(f"  如果没有自动打开，请手动访问: http://127.0.0.1:{port}")
        print(f"  关闭此窗口即可退出程序")
    print(f"{'='*50}\n")

    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)


def run_desktop():
    """桌面模式：启动 customtkinter GUI"""
    import customtkinter as ctk
    from app.config_manager import ConfigManager
    from app.gui.app_window import AppWindow

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    while True:
        if not os.path.exists(CONFIG_PATH):
            from app.gui.setup_window import SetupWindow
            saved = {}

            def on_complete(username, password):
                saved["username"] = username
                saved["password"] = password

            setup = SetupWindow(on_complete=on_complete)
            setup.mainloop()

            if not saved:
                return

            cfg = ConfigManager(config_path=CONFIG_PATH)
            cfg.set_account(saved["username"], saved["password"])
        else:
            cfg = ConfigManager(config_path=CONFIG_PATH)
            username, _ = cfg.get_account()
            if not username.strip():
                os.remove(CONFIG_PATH)
                continue

        need_logout = {}

        def on_logout():
            need_logout["logout"] = True

        app = AppWindow(config_manager=cfg, on_logout=on_logout)
        app.mainloop()

        if not need_logout.get("logout"):
            return


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--desktop":
        run_desktop()
    else:
        run_web()
