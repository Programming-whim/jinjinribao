"""
Playwright 自动化引擎：登录、导航、填写日报、提交。
在 daemon 线程中运行，通过 callback 向 GUI 报告状态。
每次运行打开一个新的 Chrome 窗口，完成后关闭。
"""

import re
import time

from playwright.sync_api import sync_playwright

from app.constants import (
    LOGIN_URL,
    DAILY_REPORT_NAV_TEXT, WRITE_REPORT_BUTTON_TEXT,
    FIELD_LABELS,
    PAGE_LOAD_TIMEOUT, LOGIN_TIMEOUT, NAV_TIMEOUT,
)
from app.automation import selectors


class DailyReportEngine:
    def __init__(self, field_contents, account, status_callback=None,
                 step_delay=1.0, headless=False, auto_submit=False):
        self._fields = field_contents
        self._username, self._password = account
        self._cb = status_callback or (lambda m, l: None)
        self._delay = step_delay
        self._headless = headless
        self._auto_submit = auto_submit
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
                    loc.first.click()
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
                    loc.first.click()
                    self._log(f"已点击: {desc}")
                    return True
            except Exception:
                continue
        try:
            page.get_by_text(text).first.click(timeout=timeout)
            self._log(f"已点击: {desc}")
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
        try:
            self._log("正在启动浏览器...")
            self._pw = sync_playwright().start()
            # Docker/服务器环境需要 --no-sandbox
            launch_args = ['--no-sandbox', '--disable-dev-shm-usage']
            # 优先 Chrome，降级到 Edge，再降级到 Playwright 自带 Chromium
            try:
                self._browser = self._pw.chromium.launch(
                    channel="chrome", headless=self._headless,
                    args=launch_args,
                )
                self._log("Chrome 浏览器已启动")
            except Exception:
                self._log("未检测到 Chrome，尝试启动 Edge...")
                try:
                    self._browser = self._pw.chromium.launch(
                        channel="msedge", headless=self._headless,
                        args=launch_args,
                    )
                    self._log("Edge 浏览器已启动")
                except Exception:
                    self._log("未检测到 Edge，使用内置 Chromium...")
                    try:
                        self._browser = self._pw.chromium.launch(
                            headless=self._headless,
                            args=launch_args,
                        )
                        self._log("Chromium 浏览器已启动")
                    except Exception as e:
                        raise RuntimeError(f"无法启动任何浏览器: {e}")
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
            self._wait()
            if not self._click_in_any_frame(page, WRITE_REPORT_BUTTON_TEXT, "去写日报", timeout=NAV_TIMEOUT):
                raise RuntimeError("未找到'去写日报'按钮")
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
            self._log(f"操作失败: {e}", "error")
        finally:
            self._cleanup()

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

        phone_filled = self._try_fill(
            page, selectors.USERNAME_INPUT_SELECTORS, self._username, "手机号", timeout=8000
        )
        self._wait(0.3)
        pw_filled = self._try_fill(
            page, selectors.PASSWORD_INPUT_SELECTORS, self._password, "密码", timeout=8000
        )

        if not phone_filled or not pw_filled:
            self._log("选择器填写未完成，使用 JS 兜底...")
            self._js_fill_login(page, self._username, self._password)

        self._wait(0.5)

        if not self._try_click(page, selectors.LOGIN_BUTTON_SELECTORS, "立即登录", timeout=8000):
            try:
                clicked = page.evaluate("""() => {
                    const btns = document.querySelectorAll('button, [role="button"], input[type="submit"], span, div');
                    for (const btn of btns) {
                        if (btn.textContent && btn.textContent.trim().includes('立即登录')
                            && btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if clicked:
                    self._log("已通过 JS 点击登录按钮")
                else:
                    raise RuntimeError("未找到登录按钮")
            except Exception as e:
                if "未找到" in str(e):
                    raise
                raise RuntimeError(f"无法点击登录按钮: {e}")

        try:
            page.wait_for_url(
                re.compile(r"(?!.*login)"),
                timeout=LOGIN_TIMEOUT,
            )
        except Exception:
            if "login" in page.url.lower():
                raise RuntimeError("登录失败，请检查账号密码或网络")

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
    # 清理：不关闭浏览器
    # ------------------------------------------------------------------
    def _cleanup(self):
        if self._auto_submit:
            self._log("填写完成")
        else:
            self._log("填写完成，请检查内容后手动点击「提交」按钮")
