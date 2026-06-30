"""更新检查模块：HEAD 请求对比文件大小"""

import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
import urllib.error
from urllib.parse import quote, unquote, urlparse, urlunparse

from app.constants import APP_VERSION, UPDATE_EXE_DOWNLOAD_URL, UPDATE_CHANGELOG_URL


def _encode_url(url):
    """对 URL 中的非 ASCII 字符进行百分号编码（幂等，多次调用结果相同）"""
    scheme, netloc, path, params, query, fragment = urlparse(url)
    # 先 unquote 还原已有编码，再 quote 统一编码，避免双重编码
    parts = path.split('/')
    encoded_parts = [quote(unquote(p), safe='') for p in parts]
    encoded_path = '/'.join(encoded_parts)
    return urlunparse((scheme, netloc, encoded_path, params, query, fragment))


def fetch_latest_changelog(url=None, timeout=10):
    """从服务器获取更新日志，只提取最新一个版本的内容"""
    url = url or UPDATE_CHANGELOG_URL
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DailyReportUpdater/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        # 提取最新一个版本的内容（从第一个【v...】到下一个【v...】之间）
        sections = re.split(r'(?=【v)', content)
        for section in sections:
            section = section.strip()
            if section.startswith('【v'):
                return section
        return ""
    except Exception:
        return ""


def _parse_version_from_changelog(changelog):
    """从 changelog 文本中提取版本号，如 '【v2.1.6】' → '2.1.6'，失败返回 None"""
    m = re.search(r'【v([\d.]+)】', changelog)
    return m.group(1) if m else None


def _version_tuple(version_str):
    """将版本号字符串转为可比较的元组，如 '2.1.6' → (2, 1, 6)"""
    try:
        return tuple(int(p) for p in version_str.split('.'))
    except (ValueError, AttributeError):
        return (0,)


def check_for_updates(exe_url=None, local_size=0, timeout=10):
    """通过 HEAD 请求对比远程文件大小 + 版本号比对判断是否有更新
    返回 (has_update, remote_size, exe_url, changelog)
    """
    url = _encode_url(exe_url or UPDATE_EXE_DOWNLOAD_URL)
    changelog = ""

    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "DailyReportUpdater/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_length = resp.headers.get("Content-Length")
            remote_size = int(content_length) if content_length else 0

        if remote_size > 0 and remote_size != local_size:
            changelog = fetch_latest_changelog()
            # 从 changelog 解析远程版本号，与当前 APP_VERSION 比对
            remote_version = _parse_version_from_changelog(changelog)
            if remote_version:
                # 幂等保护：只有远程版本严格大于当前版本才提示更新
                if not (_version_tuple(remote_version) > _version_tuple(APP_VERSION)):
                    return False, remote_size, url, changelog
            # 如果无法解析版本号，回退到文件大小判断（兼容旧逻辑）
            return True, remote_size, url, changelog
        return False, remote_size, url, changelog

    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        return False, 0, url, changelog


def async_check_for_updates(on_result, exe_url=None, local_size=0):
    """异步检查更新，完成后回调 on_result(has_update, remote_size, exe_url, changelog)"""

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
            encoded_url = _encode_url(exe_url or UPDATE_EXE_DOWNLOAD_URL)
            req = urllib.request.Request(encoded_url, headers={"User-Agent": "DailyReportUpdater/1.0"})
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
            # 只截取 URL 最后一段文件名用于提示，避免过长溢出
            short_name = encoded_url.rsplit('/', 1)[-1] if '/' in encoded_url else encoded_url
            on_error(f"{e}\n文件: {short_name}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def apply_update_and_exit(new_exe_path):
    """创建批处理脚本替换旧exe后退出,不自动重启,用户需手动启动"""
    # 安全检查:如果是开发环境或打包环境,不执行更新
    if not getattr(sys, 'frozen', False):
        print("[更新] 开发环境,跳过更新")
        return
    
    current_exe = sys.executable
    exe_name = os.path.basename(current_exe)
    backup_exe = current_exe + ".old"

    bat_path = os.path.join(tempfile.gettempdir(), "_daily_report_update.bat")
    
    # 如果批处理文件已存在,说明上次更新可能失败,先清理
    if os.path.exists(bat_path):
        try:
            os.remove(bat_path)
        except Exception:
            pass

    bat_content = f'''@echo off
setlocal

:: 强制杀死所有同名进程（确保文件锁完全释放）
taskkill /f /im "{exe_name}" >nul 2>&1

:: 等待进程完全退出
timeout /t 3 /nobreak >nul

:: 删除旧备份
if exist "{backup_exe}" del /f "{backup_exe}" >nul 2>&1

:: 重试循环：重命名旧exe（Windows允许重命名运行中的文件）
set "RETRY=0"
:RENAME_LOOP
ren "{current_exe}" "{os.path.basename(backup_exe)}" >nul 2>&1
if %errorlevel% equ 0 goto RENAME_OK
set /a RETRY+=1
if %RETRY% geq 30 (
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto RENAME_LOOP

:RENAME_OK
:: 移动新文件到目标位置
move /y "{new_exe_path}" "{current_exe}" >nul 2>&1
if %errorlevel% neq 0 (
    ren "{backup_exe}" "{os.path.basename(current_exe)}" >nul 2>&1
    exit /b 1
)

:: 清理旧版本备份
del /f "{backup_exe}" >nul 2>&1

:: 延迟后清理批处理自身
timeout /t 1 /nobreak >nul
del "%~f0"
'''

    with open(bat_path, "w", encoding="mbcs") as f:
        f.write(bat_content)

    subprocess.Popen(
        ['cmd.exe', '/c', bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )

    os._exit(0)
