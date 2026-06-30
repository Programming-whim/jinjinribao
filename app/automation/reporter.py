"""
Playwright 自动化引擎：登录、导航、填写日报、提交。
在 daemon 线程中运行，通过 callback 向 GUI 报告状态。
每次运行打开一个新的 Chrome 窗口，完成后关闭。
"""

import re
import time
import os
import subprocess

from playwright.sync_api import sync_playwright

from app.constants import (
    LOGIN_URL,
    DAILY_REPORT_NAV_TEXT, WRITE_REPORT_BUTTON_TEXT,
    FIELD_LABELS,
    PAGE_LOAD_TIMEOUT, LOGIN_TIMEOUT, NAV_TIMEOUT,
)
from app.automation import selectors

# 模块级变量，用于保持失败后的浏览器进程存活
_keep_alive_pw = None
_keep_alive_browser = None


def _cleanup_keep_alive():
    """清理上次失败后保留的浏览器进程"""
    global _keep_alive_pw, _keep_alive_browser
    if _keep_alive_browser is not None:
        try:
            _keep_alive_browser.close()
        except Exception:
            pass
    if _keep_alive_pw is not None:
        try:
            _keep_alive_pw.stop()
        except Exception:
            pass
    _keep_alive_pw = None
    _keep_alive_browser = None


class DailyReportEngine:
    def __init__(self, field_contents, account, status_callback=None,
                 step_delay=1.0, headless=False, auto_submit=False,
                 manual_callback=None):
        self._fields = field_contents
        self._username, self._password = account
        self._cb = status_callback or (lambda m, l: None)
        self._delay = step_delay
        self._headless = headless
        self._auto_submit = auto_submit
        self._manual_cb = manual_callback  # 需要手动操作时的回调
        self._pw = None
        self._browser = None

    def _log(self, msg, level="info"):
        self._cb(msg, level)

    def _wait(self, seconds=None):
        time.sleep(seconds if seconds is not None else self._delay)

    # ------------------------------------------------------------------
    # 通用选择器操作
    # ------------------------------------------------------------------
    def _try_click(self, page, selector_list, desc, timeout=5000):
        for sel in selector_list:
            try:
                if sel[0] == "role":
                    loc = page.get_by_role(sel[1], name=sel[2])
                elif sel[0] == "text":
                    loc = page.locator(f"text={sel[1]}")
                elif sel[0] == "css":
                    loc = page.locator(sel[1])
                else:
                    continue
                if loc.first.is_visible(timeout=timeout):
                    try:
                        loc.first.click(timeout=3000)
                    except Exception:
                        # 普通点击失败，尝试 force 点击（绕过遮挡）
                        try:
                            loc.first.click(force=True, timeout=3000)
                        except Exception:
                            # 再尝试 JS 点击
                            loc.first.evaluate("el => el.click()")
                    self._log(f"已点击: {desc}")
                    return True
            except Exception:
                continue
        self._log(f"未找到按钮: {desc}", "error")
        return False

    def _try_fill(self, page, selector_list, value, desc, timeout=5000):
        for sel in selector_list:
            try:
                if sel[0] == "css":
                    loc = page.locator(sel[1])
                elif sel[0] == "text":
                    loc = page.locator(f"text={sel[1]}")
                else:
                    continue
                if loc.first.is_visible(timeout=timeout):
                    loc.first.click()
                    self._wait(0.2)
                    loc.first.fill(value)
                    self._log(f"已填入: {desc}")
                    return True
            except Exception:
                continue
        return False

    def _click_write_report(self, page):
        """点击'去写日报'按钮"""
        from app.constants import WRITE_REPORT_BUTTON_TEXT
        from app.automation import selectors as sel_mod

        # 策略1: 使用选择器列表
        for selector in sel_mod.WRITE_REPORT_SELECTORS:
            try:
                if selector[0] == "text":
                    loc = page.locator(f"text={selector[1]}")
                elif selector[0] == "css":
                    loc = page.locator(selector[1])
                elif selector[0] == "role":
                    loc = page.get_by_role(selector[1], name=selector[2])
                else:
                    continue
                if loc.first.is_visible(timeout=5000):
                    try:
                        loc.first.click(timeout=3000)
                    except Exception:
                        try:
                            loc.first.click(force=True, timeout=3000)
                        except Exception:
                            loc.first.evaluate("el => el.click()")
                    self._log(f"已点击: {WRITE_REPORT_BUTTON_TEXT}")
                    return True
            except Exception:
                continue

        # 策略2: 使用通用帧内点击
        return self._click_in_any_frame(page, WRITE_REPORT_BUTTON_TEXT, WRITE_REPORT_BUTTON_TEXT, timeout=8000)

    # ------------------------------------------------------------------
    # JS 兜底填写登录表单
    # ------------------------------------------------------------------
    def _js_fill_login(self, page, username, password):
        try:
            result = page.evaluate("""(username, password) => {
                const inputs = document.querySelectorAll('input');
                let phoneFilled = false, pwFilled = false;

                for (const inp of inputs) {
                    if (inp.type === 'password' && inp.offsetParent !== null) {
                        inp.focus();
                        const setter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inp, password);
                        inp.dispatchEvent(new Event('input', {bubbles: true}));
                        inp.dispatchEvent(new Event('change', {bubbles: true}));
                        pwFilled = true;
                        break;
                    }
                }

                for (const inp of inputs) {
                    if (inp.type === 'password' || inp.offsetParent === null) continue;
                    const ph = (inp.placeholder || '').toLowerCase();
                    const nm = (inp.name || '').toLowerCase();
                    if (ph.includes('手机') || ph.includes('账号') || ph.includes('用户')
                        || nm.includes('phone') || nm.includes('mobile')
                        || nm.includes('account') || nm.includes('username')
                        || inp.type === 'tel') {
                        inp.focus();
                        const setter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inp, username);
                        inp.dispatchEvent(new Event('input', {bubbles: true}));
                        inp.dispatchEvent(new Event('change', {bubbles: true}));
                        phoneFilled = true;
                        break;
                    }
                }

                if (!phoneFilled) {
                    for (const inp of inputs) {
                        if (inp.type !== 'password' && inp.type !== 'hidden'
                            && inp.offsetParent !== null && !inp.value) {
                            inp.focus();
                            const setter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value').set;
                            setter.call(inp, username);
                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                            phoneFilled = true;
                            break;
                        }
                    }
                }

                return { phoneFilled, pwFilled };
            }""", username, password)
            if result.get("phoneFilled") and result.get("pwFilled"):
                self._log("JS 兜底填写成功")
                return True
            else:
                self._log(f"JS 填写结果: 手机={result.get('phoneFilled')}, 密码={result.get('pwFilled')}")
                return False
        except Exception as e:
            self._log(f"JS 填写失败: {e}", "error")
            return False

    # ------------------------------------------------------------------
    def _click_in_any_frame(self, page, text, desc, timeout=8000):
        frames = [page] + list(page.frames)
        for frame in frames:
            try:
                loc = frame.locator(f"text={text}")
                if loc.first.is_visible(timeout=timeout):
                    try:
                        loc.first.click(timeout=3000)
                    except Exception:
                        try:
                            loc.first.click(force=True, timeout=3000)
                        except Exception:
                            loc.first.evaluate("el => { if (el && el.click) el.click(); }")
                    self._log(f"已点击: {desc}")
                    return True
            except Exception:
                continue
        try:
            el = page.get_by_text(text).first
            try:
                el.click(timeout=timeout)
            except Exception:
                try:
                    el.click(force=True, timeout=timeout)
                except Exception:
                    el.evaluate("e => { if (e && e.click) e.click(); }")
            self._log(f"已点击: {desc}")
            return True
        except Exception:
            pass
        # 最终兜底：JS 全局搜索并点击
        try:
            clicked = page.evaluate(f"""() => {{
                const els = document.querySelectorAll('*');
                for (const el of els) {{
                    if (el.textContent && el.textContent.trim().includes('{text}')
                        && el.offsetParent !== null && el.children.length === 0) {{
                        el.click();
                        return true;
                    }}
                }}
                return false;
            }}""")
            if clicked:
                self._log(f"已点击(JS兜底): {desc}")
                return True
        except Exception:
            pass
        self._log(f"未找到: {desc}", "error")
        return False

    # ------------------------------------------------------------------
    def _fill_report_field(self, page, label, content):
        if not content:
            self._log(f"跳过空字段: {label[:10]}...")
            return True

        short_label = label[:8]

        xpaths = selectors.get_field_xpath(label)
        for xpath in xpaths:
            try:
                loc = page.locator(f"xpath={xpath}")
                if loc.first.is_visible(timeout=3000):
                    self._type_into(loc.first, content, page)
                    self._log(f"已填写: {short_label}...")
                    return True
            except Exception:
                continue

        try:
            result = page.evaluate("""(labelPrefix) => {
                const allEls = document.querySelectorAll('div, span, label, p, h1, h2, h3, h4');
                for (const el of allEls) {
                    if (el.textContent && el.textContent.includes(labelPrefix)) {
                        let container = el.closest('.form-item, .form-group, [class*="form"], [class*="item"], [class*="field"]')
                            || el.parentElement;
                        if (container) {
                            const editable = container.querySelector(
                                'textarea, input[type="text"], [contenteditable="true"], .ql-editor, .w-e-text-container'
                            );
                            if (editable) return { found: true, tag: editable.tagName, ce: editable.contentEditable };
                            const iframe = container.querySelector('iframe');
                            if (iframe) return { found: true, iframe: true, src: iframe.src };
                        }
                    }
                }
                return { found: false };
            }""", short_label)

            if result.get("found"):
                if result.get("iframe"):
                    for frame in page.frames:
                        try:
                            body = frame.locator("body")
                            if body.first.is_visible(timeout=2000):
                                self._type_into(body.first, content, page)
                                self._log(f"已填写(iframe): {short_label}...")
                                return True
                        except Exception:
                            continue
                else:
                    page.evaluate("""(labelPrefix, content) => {
                        const allEls = document.querySelectorAll('div, span, label, p, h1, h2, h3, h4');
                        for (const el of allEls) {
                            if (el.textContent && el.textContent.includes(labelPrefix)) {
                                let container = el.closest('.form-item, .form-group, [class*="form"], [class*="item"], [class*="field"]')
                                    || el.parentElement;
                                if (container) {
                                    const editable = container.querySelector('textarea, input[type="text"]');
                                    if (editable) {
                                        editable.value = content;
                                        editable.dispatchEvent(new Event('input', {bubbles: true}));
                                        editable.dispatchEvent(new Event('change', {bubbles: true}));
                                        return true;
                                    }
                                    const ce = container.querySelector('[contenteditable="true"], .ql-editor, .w-e-text-container');
                                    if (ce) {
                                        ce.innerHTML = content;
                                        ce.dispatchEvent(new Event('input', {bubbles: true}));
                                        return true;
                                    }
                                }
                            }
                        }
                        return false;
                    }""", short_label, content)
                    self._log(f"已填写(JS): {short_label}...")
                    return True
        except Exception as e:
            self._log(f"JS 填写 {short_label}... 失败: {e}", "error")

        self._log(f"无法定位字段: {short_label}...，请检查页面结构", "error")
        return False

    def _type_into(self, locator, content, page):
        try:
            tag = locator.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            tag = ""
        try:
            is_ce = locator.evaluate("el => el.contentEditable === 'true'")
        except Exception:
            is_ce = False

        if tag in ("textarea", "input"):
            locator.fill(content)
            locator.dispatch_event("input")
            locator.dispatch_event("change")
        elif is_ce or tag == "div":
            locator.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(content, delay=5)
        else:
            locator.fill(content)
            locator.dispatch_event("input")

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run(self):
        page = None
        failed = False
        try:
            self._log("正在启动浏览器...")
            # 先清理上次失败残留的浏览器进程
            _cleanup_keep_alive()
            self._wait(1)  # 等待进程完全退出

            # 启动 Playwright，带重试
            self._pw = None
            for attempt in range(3):
                try:
                    self._pw = sync_playwright().start()
                    self._log("Playwright 引擎已启动")
                    break
                except Exception as e:
                    self._log(f"Playwright 启动尝试 {attempt+1}/3 失败: {e}")
                    self._wait(2)
            if self._pw is None:
                raise RuntimeError("Playwright 引擎启动失败，请尝试重启工具后重试")

            # 尝试多种浏览器启动方式
            self._browser = self._launch_browser()
            page = self._browser.new_page()
            page.on("dialog", lambda d: d.accept())

            # 1. 打开登录页
            self._log("正在打开登录页面...")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT)
            self._wait(3)
            self._log("已打开登录页面")

            # 2. 登录
            self._log("正在登录...")
            self._do_login(page)
            self._wait(2)
            self._log("登录成功")

            # 3. 导航到精进日报
            self._log("正在进入精进日报...")
            self._wait(2)
            if not self._click_in_any_frame(page, DAILY_REPORT_NAV_TEXT, "精进日报", timeout=NAV_TIMEOUT):
                raise RuntimeError("未找到'精进日报'入口，页面结构可能已更新")
            page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
            self._wait(2)
            self._log("已进入精进日报页面")

            # 4. 点击"去写日报"
            self._log("正在点击'去写日报'...")
            self._wait(2)
            if not self._click_write_report(page):
                raise RuntimeError("未找到'去写日报'按钮，请检查页面是否已加载完成")
            page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
            self._wait(2)
            self._log("已进入日报填写界面")

            # 5. 填写所有字段
            self._log("开始填写日报内容...")
            filled = 0
            for label in FIELD_LABELS:
                content = self._fields.get(label, "")
                if self._fill_report_field(page, label, content):
                    filled += 1
                self._wait(0.5)
            self._log(f"已完成 {filled}/{len(FIELD_LABELS)} 个字段填写")

            # 6. 根据配置决定自动提交或手动提交
            if self._auto_submit:
                self._do_auto_submit(page)
            else:
                self._show_manual_overlay(page)

        except Exception as e:
            failed = True
            self._log(f"操作失败: {e}", "error")
            self._log("正在打开浏览器，请手动完成日报填写...", "info")
            # 失败时尝试导航到日报页面，方便用户手动填写
            if page is not None:
                try:
                    self._navigate_to_report_page(page)
                except Exception:
                    pass
        finally:
            self._cleanup(failed=failed)

    # ------------------------------------------------------------------
    # 浏览器启动：多种策略尝试
    # ------------------------------------------------------------------
    def _launch_browser(self):
        """尝试多种方式启动浏览器"""
        import os
        # 优先 Edge（稳定性更好），然后 Chrome
        for name, channel in [("Edge", "msedge"), ("Chrome", "chrome")]:
            try:
                browser = self._pw.chromium.launch(
                    channel=channel, headless=self._headless,
                )
                self._log(f"{name} 浏览器已启动")
                return browser
            except Exception as e:
                self._log(f"{name} (channel) 启动失败: {e}")

        # 策略2: 直接查找系统浏览器可执行文件
        edge_paths = [
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
        chrome_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        for name, paths in [("Edge", edge_paths), ("Chrome", chrome_paths)]:
            for path in paths:
                if os.path.isfile(path):
                    try:
                        browser = self._pw.chromium.launch(
                            executable_path=path, headless=self._headless,
                        )
                        self._log(f"{name} 浏览器已启动 ({path})")
                        return browser
                    except Exception as e:
                        self._log(f"{name} ({path}) 启动失败: {e}")

        # 策略3: 使用 Playwright 内置 Chromium
        try:
            browser = self._pw.chromium.launch(headless=self._headless)
            self._log("Chromium 内置浏览器已启动")
            return browser
        except Exception as e:
            self._log(f"Chromium 内置浏览器启动失败: {e}")

        raise RuntimeError("未检测到可用的浏览器，请确保已安装 Chrome 或 Edge")

    # ------------------------------------------------------------------
    # 登录：先填账密再点击登录
    # ------------------------------------------------------------------
    def _do_login(self, page):
        if "login" not in page.url.lower():
            self._log("已经是登录状态，跳过登录")
            return
    
        self._log("等待登录表单加载...")
        try:
            page.wait_for_selector(
                "input[type='password'], input[placeholder*='密码'], input[placeholder*='手机']",
                timeout=10000,
            )
        except Exception:
            self._log("等待输入框超时，尝试继续...")
    
        self._wait(1)
    
        # ---- 填写账号密码（兼容 Vue/React 响应式框架）----
        # 策略1: JS 原生 setter + 事件分发，确保 Vue 能检测到值变化
        js_filled = self._js_fill_login(page, self._username, self._password)
    
        if not js_filled:
            # 策略2: Playwright fill() 兆底
            self._log("JS 填写未完成，使用 Playwright fill() 补充...")
            self._try_fill(
                page, selectors.USERNAME_INPUT_SELECTORS, self._username, "手机号", timeout=5000
            )
            self._wait(0.3)
            self._try_fill(
                page, selectors.PASSWORD_INPUT_SELECTORS, self._password, "密码", timeout=5000
            )
    
        self._wait(1)
    
        # ---- 点击登录按钮（管小花平台是 div.loginBtn，不是标准 button）----
        login_done = False
    
        # 尝试1: Playwright 原生点击（能触发完整 DOM 事件链，Vue 可正常响应）
        login_done = self._try_click(
            page, selectors.LOGIN_BUTTON_SELECTORS, "立即登录", timeout=5000
        )
    
        # 尝试2: JS 精确点击 div.loginBtn
        if not login_done:
            try:
                clicked = page.evaluate("""() => {
                    const btn = document.querySelector('div.loginBtn, .loginBtn');
                    if (btn) { btn.click(); return true; }
                    // 兆底：查找任何包含“登录”文字的可点击元素
                    const allEls = document.querySelectorAll('*');
                    for (const el of allEls) {
                        if (el.children.length === 0
                            && el.textContent && el.textContent.trim().includes('登录')
                            && el.offsetParent !== null
                            && window.getComputedStyle(el).cursor === 'pointer') {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if clicked:
                    self._log("已通过 JS 点击登录按钮")
                    login_done = True
            except Exception as e:
                self._log(f"JS 点击登录失败: {e}")
    
        # 尝试3: Enter 键提交
        if not login_done:
            try:
                page.keyboard.press("Enter")
                self._log("已通过 Enter 键提交登录")
                login_done = True
            except Exception:
                pass
    
        # 等待登录结果
        if login_done:
            self._wait_for_login_complete(page, auto_clicked=True)
        else:
            self._log("未能自动点击登录按钮，请在浏览器中手动点击登录", "error")
            self._wait_for_manual_login(page)

    def _wait_for_login_complete(self, page, auto_clicked=False):
        """等待登录完成，同时检测 URL 变化和页面状态"""
        if auto_clicked:
            # 自动点击后先等待 URL 跳转
            try:
                page.wait_for_url(
                    re.compile(r"(?!.*login)"),
                    timeout=LOGIN_TIMEOUT,
                )
                return
            except Exception:
                if "login" not in page.url.lower():
                    return
                # URL 未变，检查登录表单是否已消失
                try:
                    page.wait_for_selector(
                        "input[type='password']",
                        state="hidden",
                        timeout=5000,
                    )
                    self._log("登录表单已消失，登录成功")
                    self._wait(2)
                    return
                except Exception:
                    pass
                # 可能遇到验证码
                self._log("登录未成功跳转，可能需要手动完成验证", "error")
                self._wait_for_manual_login(page)

    def _wait_for_manual_login(self, page):
        """等待用户手动登录，隐藏遮罩并置顶浏览器"""
        # 通知 GUI 需要手动操作
        if self._manual_cb:
            try:
                self._manual_cb()
            except Exception:
                pass
        # 把浏览器窗口置顶
        try:
            page.bring_to_front()
        except Exception:
            pass
        self._log("请在浏览器中手动完成登录，等待5分钟...", "info")
        # 同时检测 URL 变化和登录表单消失
        start_time = time.time()
        while time.time() - start_time < 300:  # 5分钟
            try:
                # 检查 URL 是否已离开登录页
                if "login" not in page.url.lower():
                    self._log("检测到已登录成功（URL跳转），继续执行...")
                    self._wait(2)
                    return
            except Exception:
                pass
            try:
                # 检查登录表单是否已消失
                pw_visible = page.locator("input[type='password']").first.is_visible(timeout=500)
                if not pw_visible:
                    self._log("检测到已登录成功（表单消失），继续执行...")
                    self._wait(2)
                    return
            except Exception:
                # 密码框不存在，可能已登录
                self._log("检测到已登录成功，继续执行...")
                self._wait(2)
                return
            self._wait(3)  # 每3秒检查一次
        raise RuntimeError("登录超时，请检查账号密码或手动完成验证")

    # ------------------------------------------------------------------
    # 自动提交：尝试点击提交按钮
    # ------------------------------------------------------------------
    def _do_auto_submit(self, page):
        self._log("正在尝试自动提交...")
        self._wait(1)

        submitted = False
        for sel in selectors.SUBMIT_BUTTON_SELECTORS:
            try:
                if sel[0] == "role":
                    loc = page.get_by_role(sel[1], name=sel[2])
                elif sel[0] == "text":
                    loc = page.locator(f"text={sel[1]}")
                elif sel[0] == "css":
                    loc = page.locator(sel[1])
                else:
                    continue
                if loc.first.is_visible(timeout=3000):
                    loc.first.click()
                    submitted = True
                    self._log("已点击提交按钮", "success")
                    break
            except Exception:
                continue

        if not submitted:
            try:
                clicked = page.evaluate("""() => {
                    const btns = document.querySelectorAll(
                        'button, [role="button"], input[type="submit"]');
                    for (const btn of btns) {
                        const text = (btn.textContent || btn.value || '').trim();
                        if ((text.includes('提交') || text.includes('保存'))
                            && btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if clicked:
                    submitted = True
                    self._log("已通过 JS 点击提交按钮", "success")
            except Exception as e:
                self._log(f"JS 点击提交失败: {e}", "error")

        if submitted:
            self._wait(2)
            page.evaluate("""() => {
                const overlay = document.createElement('div');
                overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;'
                    + 'background:rgba(0,0,0,0.4);z-index:99999;display:flex;'
                    + 'align-items:center;justify-content:center;';
                const box = document.createElement('div');
                box.style.cssText = 'background:#fff;border-radius:12px;padding:32px 40px;'
                    + 'text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.15);max-width:400px;';
                box.innerHTML = '<div style="font-size:40px;margin-bottom:12px;">&#9989;</div>'
                    + '<div style="font-size:18px;font-weight:bold;margin-bottom:8px;">日报已自动提交成功</div>'
                    + '<div style="font-size:14px;color:#666;margin-bottom:20px;">此提示3秒后自动关闭</div>';
                overlay.appendChild(box);
                document.body.appendChild(overlay);
                setTimeout(() => overlay.remove(), 3000);
            }""")
            self._log("自动提交完成", "success")
        else:
            self._log("未找到提交按钮，请手动提交", "error")
            self._show_manual_overlay(page)

    # ------------------------------------------------------------------
    # 手动提交：弹出提示让用户自行提交
    # ------------------------------------------------------------------
    def _show_manual_overlay(self, page):
        page.evaluate("""() => {
            const overlay = document.createElement('div');
            overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;'
                + 'background:rgba(0,0,0,0.4);z-index:99999;display:flex;'
                + 'align-items:center;justify-content:center;';
            const box = document.createElement('div');
            box.style.cssText = 'background:#fff;border-radius:12px;padding:32px 40px;'
                + 'text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.15);max-width:400px;';
            box.innerHTML = '<div style="font-size:40px;margin-bottom:12px;">&#9989;</div>'
                + '<div style="font-size:18px;font-weight:bold;margin-bottom:8px;">日报内容已自动填写完成</div>'
                + '<div style="font-size:14px;color:#666;margin-bottom:20px;">请检查内容无误后，手动点击底部「提交」按钮</div>'
                + '<button onclick="this.closest(\\'div[style] \\').parentElement.remove()" '
                + 'style="background:#1677ff;color:#fff;border:none;border-radius:6px;'
                + 'padding:8px 32px;font-size:14px;cursor:pointer;">知道了</button>';
            overlay.appendChild(box);
            overlay.addEventListener('click', (e) => { if(e.target===overlay) overlay.remove(); });
            document.body.appendChild(overlay);
        }""")
        self._log("已弹出提示，等待手动提交", "success")

    # ------------------------------------------------------------------
    # 失败时导航到日报页面，方便用户手动填写
    # ------------------------------------------------------------------
    def _navigate_to_report_page(self, page):
        """尝试导航到日报填写页面"""
        try:
            # 先尝试点击精进日报入口
            if "login" not in page.url.lower():
                self._click_in_any_frame(page, DAILY_REPORT_NAV_TEXT, "精进日报", timeout=8000)
                self._wait(2)
                self._click_write_report(page)
                self._wait(2)
                # 弹出提示
                page.evaluate("""() => {
                    const overlay = document.createElement('div');
                    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;'
                        + 'background:rgba(0,0,0,0.4);z-index:99999;display:flex;'
                        + 'align-items:center;justify-content:center;';
                    const box = document.createElement('div');
                    box.style.cssText = 'background:#fff;border-radius:12px;padding:32px 40px;'
                        + 'text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.15);max-width:400px;';
                    box.innerHTML = '<div style="font-size:40px;margin-bottom:12px;">&#9888;&#65039;</div>'
                        + '<div style="font-size:18px;font-weight:bold;margin-bottom:8px;">自动填写失败</div>'
                        + '<div style="font-size:14px;color:#666;margin-bottom:20px;">已打开日报页面，请手动填写并提交</div>'
                        + '<button onclick="this.closest(\\'div[style] \\').parentElement.remove()" '
                        + 'style="background:#1677ff;color:#fff;border:none;border-radius:6px;'
                        + 'padding:8px 32px;font-size:14px;cursor:pointer;">知道了</button>';
                    overlay.appendChild(box);
                    overlay.addEventListener('click', (e) => { if(e.target===overlay) overlay.remove(); });
                    document.body.appendChild(overlay);
                }""")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------
    def _cleanup(self, failed=False):
        if failed:
            self._log("自动填写失败，浏览器已保持打开，请手动完成操作", "error")
            # 失败时保持浏览器存活，方便用户手动操作
            self._keep_browser_alive()
        elif self._auto_submit:
            self._log("填写完成")
            # 自动提交成功，可以安全关闭浏览器
            self._close_browser()
        else:
            self._log("填写完成，请检查内容后手动点击「提交」按钮")
            self._log("浏览器将保持打开，提交后可自行关闭", "info")
            # 手动提交模式：保持浏览器存活，让用户可以提交
            self._keep_browser_alive()

    def _keep_browser_alive(self):
        """将浏览器引用转移到模块级变量，保持浏览器进程存活"""
        global _keep_alive_pw, _keep_alive_browser
        # 先清理上次残留的进程
        _cleanup_keep_alive()
        _keep_alive_pw = self._pw
        _keep_alive_browser = self._browser
        self._pw = None
        self._browser = None

    def _close_browser(self):
        """关闭浏览器和 Playwright 引擎"""
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None
