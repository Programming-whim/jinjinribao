"""更新检查模块：HEAD 请求对比文件大小"""

import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
import urllib.error

from app.constants import APP_VERSION, UPDATE_EXE_DOWNLOAD_URL


def check_for_updates(exe_url=None, local_size=0, timeout=10):
    """通过 HEAD 请求对比远程文件大小判断是否有更新
    返回 (has_update, remote_size, exe_url)
    """
    url = exe_url or UPDATE_EXE_DOWNLOAD_URL

    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "DailyReportUpdater/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_length = resp.headers.get("Content-Length")
            remote_size = int(content_length) if content_length else 0

        if remote_size > 0 and remote_size != local_size:
            return True, remote_size, url
        return False, remote_size, url

    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        return False, 0, url


def async_check_for_updates(on_result, exe_url=None, local_size=0):
    """异步检查更新，完成后回调 on_result(has_update, remote_size, exe_url)"""

    def _run():
        result = check_for_updates(exe_url=exe_url, local_size=local_size)
        on_result(*result)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def download_update(exe_url, on_progress, on_complete, on_error, timeout=120):
    """下载更新文件，通过回调报告进度
    on_progress(percent, downloaded_mb, total_mb)
    on_complete(file_path)
    on_error(error_message)
    """

    def _run():
        try:
            req = urllib.request.Request(exe_url, headers={"User-Agent": "DailyReportUpdater/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                total_size = resp.headers.get("Content-Length")
                total_size = int(total_size) if total_size else 0

                fd, tmp_path = tempfile.mkstemp(suffix=".exe")
                os.close(fd)

                downloaded = 0
                chunk_size = 8192

                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            downloaded_mb = downloaded / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            on_progress(percent, round(downloaded_mb, 1), round(total_mb, 1))
                        else:
                            downloaded_mb = downloaded / (1024 * 1024)
                            on_progress(0, round(downloaded_mb, 1), 0)

                on_complete(tmp_path)

        except Exception as e:
            on_error(str(e))

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def apply_update_and_restart(new_exe_path):
    """创建批处理脚本替换旧exe并重启，然后退出当前进程"""
    current_exe = sys.executable
    exe_dir = os.path.dirname(current_exe)
    exe_name = os.path.basename(current_exe)

    bat_path = os.path.join(tempfile.gettempdir(), "_daily_report_update.bat")

    bat_content = f'''@echo off
chcp 65001 >nul
echo 正在完成更新...
timeout /t 2 /nobreak >nul
move /y "{new_exe_path}" "{current_exe}"
if %errorlevel% neq 0 (
    echo 更新失败，请手动替换文件
    pause
    exit /b 1
)
echo 更新完成，正在启动...
start "" "{current_exe}"
del "%~f0"
'''

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        f'cmd.exe /c "{bat_path}"',
        creationflags=CREATE_NO_WINDOW,
        shell=True,
    )

    os._exit(0)
