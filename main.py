"""牛马工具2.0 — Web 版入口"""

import os
import sys

# PyInstaller 打包后资源在 _MEIPASS 临时目录中
if getattr(sys, 'frozen', False):
    _ROOT = sys._MEIPASS
else:
    _ROOT = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _ROOT)

import webview
from app.webgui.api import Api
from app.constants import APP_TITLE, APP_WIDTH, APP_HEIGHT

HTML_DIR = os.path.join(_ROOT, "app", "webgui", "web")


def main():
    api = Api()

    window = webview.create_window(
        title=APP_TITLE,
        url=os.path.join(HTML_DIR, "index.html"),
        width=APP_WIDTH,
        height=APP_HEIGHT,
        min_size=(900, 600),
        js_api=api,
    )
    api.set_window(window)

    webview.start(debug=False)


if __name__ == "__main__":
    main()
