"""BPE (Breakpoint Parameter Editor) — Playwright 自动化执行器

从 PyQt6 版本迁移，去掉 Qt 依赖，改用 threading + callback。
功能：自动登录考勤系统 → 拦截目标接口 → 替换日期范围/条数参数 → 保持浏览器供用户手动截图。
"""

import fnmatch
import json
import threading
from datetime import datetime

LOGIN_URL = "https://aipu.italent.cn/Login#/indexPage"


class BPERunner:
    """BPE 自动化执行器。

    用法：
        runner = BPERunner(log_callback=..., finish_callback=...)
        runner.start(username, password, api_pattern, date_start, date_end, capacity)
    """

    def __init__(self, log_callback=None, finish_callback=None):
        """
        :param log_callback:  fn(msg: str)           — 日志输出
        :param finish_callback: fn(success: bool, msg: str) — 任务结束
        """
        self._log_cb = log_callback or (lambda m: None)
        self._finish_cb = finish_callback or (lambda ok, m: None)
        self._thread: threading.Thread | None = None
        self._running = False

    # ──────────────────────── 公共属性 ────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    # ──────────────────────── 启动入口 ────────────────────────

    def start(self, username: str, password: str, api_pattern: str,
              date_start: str, date_end: str, capacity: int = 400,
              headless: bool = False):
        """在后台线程中启动 Playwright 自动化流程。"""
        if self._running:
            self._log_cb("⚠️ 已有任务在执行中，请等待完成")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            args=(username, password, api_pattern, date_start, date_end, capacity, headless),
            daemon=True,
            name="BPE-Runner",
        )
        self._thread.start()

    # ──────────────────────── 核心流程 ────────────────────────

    def _log(self, msg: str):
        self._log_cb(msg)

    def _finish(self, ok: bool, msg: str):
        self._running = False
        self._finish_cb(ok, msg)

    def _run(self, username, password, api_pattern, date_start, date_end, capacity, headless):
        """Playwright 主流程（在子线程中运行）。"""
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

        browser = None
        breakpoint_consumed = False
        # 构造日期范围字符串：若开始>结束则自动交换
        try:
            d1 = datetime.strptime(date_start, "%Y/%m/%d")
            d2 = datetime.strptime(date_end, "%Y/%m/%d")
            if d1 > d2:
                date_start, date_end = date_end, date_start
        except Exception:
            pass
        date_range = f"{date_start}-{date_end}"

        try:
            self._log("🚀 启动浏览器（使用本地浏览器）")
            with sync_playwright() as p:
                launch_args = ["--start-maximized", "--window-size=1920,1080"]
                # 优先使用本地 Chrome，找不到则回退到 Edge
                browser = None
                for channel in ("chrome", "msedge", None):
                    try:
                        kwargs = {"headless": headless, "args": launch_args}
                        if channel:
                            kwargs["channel"] = channel
                        browser = p.chromium.launch(**kwargs)
                        label = channel or "Playwright Chromium"
                        self._log(f"✅ 已启动浏览器: {label}")
                        break
                    except Exception as e:
                        if channel:
                            self._log(f"⚠️ {channel} 不可用: {e}")
                        else:
                            raise
                if browser is None:
                    self._finish(False, "未找到可用的本地浏览器（Chrome / Edge）")
                    return

                if headless:
                    context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
                else:
                    context = browser.new_context(no_viewport=True)

                page = context.new_page()
                if not headless:
                    self._maximize_window(context, page)

                # ── 路由拦截 ──────────────────────────────────

                def _request_matches(url: str) -> bool:
                    pat = (api_pattern or "").strip()
                    if not pat:
                        return False
                    if "*" in pat or "?" in pat:
                        return fnmatch.fnmatch(url, pat)
                    return pat in url

                def _replace_swiping_card_date(node, dr):
                    changed = False
                    if isinstance(node, dict):
                        if node.get("name") == "Attendance.AttendanceStatistics.SwipingCardDate":
                            node["text"] = dr
                            node["value"] = dr
                            changed = True
                        for v in node.values():
                            if _replace_swiping_card_date(v, dr):
                                changed = True
                    elif isinstance(node, list):
                        for item in node:
                            if _replace_swiping_card_date(item, dr):
                                changed = True
                    return changed

                def _replace_capacity(node):
                    changed = False
                    if isinstance(node, dict):
                        if "capacity" in node:
                            node["capacity"] = capacity or 400
                            changed = True
                        for v in node.values():
                            if _replace_capacity(v):
                                changed = True
                    elif isinstance(node, list):
                        for item in node:
                            if _replace_capacity(item):
                                changed = True
                    return changed

                def handle_route(route, request):
                    nonlocal breakpoint_consumed
                    try:
                        if not _request_matches(request.url):
                            route.continue_()
                            return
                        self._log(f"🎯 命中断点接口: {request.method} {request.url}")
                        breakpoint_consumed = True
                        if request.method == "POST":
                            original_data = request.post_data
                            if original_data:
                                try:
                                    data = json.loads(original_data)
                                    date_changed = _replace_swiping_card_date(data, date_range)
                                    cap_changed = _replace_capacity(data)
                                    modified = json.dumps(data, ensure_ascii=False)
                                    if date_changed:
                                        self._log(f"✏️ 已更新考勤日期范围: {date_range}")
                                    else:
                                        self._log("⚠️ 未找到 SwipingCardDate 字段，已原样放行")
                                    if cap_changed:
                                        self._log(f"✏️ 已固定 capacity 为 {capacity or 400}")
                                    route.continue_(post_data=modified)
                                    return
                                except Exception:
                                    pass
                        route.continue_()
                    except Exception as e:
                        self._log(f"⚠️ 断点处理异常: {e}")
                        try:
                            route.continue_()
                        except Exception:
                            pass

                page.route("**/*", handle_route)
                self._log(f"🌐 打开登录页: {LOGIN_URL}")
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

                # ── 填写账号密码 ──────────────────────────────

                account_ok = self._fill_first(page, [
                    "input[placeholder*='账号']",
                    "input[placeholder*='用户名']",
                    "input[type='text']",
                ], username, "账号")
                if not account_ok:
                    self._finish(False, "未找到账号输入框")
                    return

                pwd_ok = self._fill_first(page, [
                    "input[placeholder*='密码']",
                    "input[type='password']",
                ], password, "密码")
                if not pwd_ok:
                    self._finish(False, "未找到密码输入框")
                    return

                self._ensure_privacy_checked(page)

                if not self._click_login_button(page):
                    self._finish(False, "未找到登录按钮")
                    return

                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except PlaywrightTimeoutError:
                    self._log("⚠️ 登录后 networkidle 超时，继续")

                # ── 导航到"我的假勤" ──────────────────────────

                self._log("➡️ 切换到 导航台")
                if not self._click_text(page, "导航台", timeout=20000):
                    self._finish(False, '未找到"导航台"标签')
                    return

                self._log('⏳ 等待"我的假勤"菜单渲染')
                if not self._wait_my_attendance_ready(page, timeout=30000):
                    self._finish(False, '导航台已切换，但"我的假勤"菜单未出现')
                    return

                self._log("➡️ 进入 我的假勤")
                before_url = page.url
                if not self._click_my_attendance(page, timeout=12000):
                    self._finish(False, '未找到"我的假勤"入口')
                    return

                self._click_fixbox_button(page)

                # SPA：等待 URL 变化或接口命中
                enter_deadline = datetime.now().timestamp() + 15
                while datetime.now().timestamp() < enter_deadline:
                    if breakpoint_consumed or page.url != before_url:
                        break
                    page.wait_for_timeout(300)
                self._log(f"ℹ️ 当前页面: {page.url}")

                if not breakpoint_consumed:
                    self._log("⚠️ 尚未命中目标接口，请检查接口匹配是否正确")

                self._wait_page_settle(page, timeout_ms=45000)

                # 解除路由，保留浏览器供用户手动截图
                try:
                    page.unroute("**/*", handle_route)
                except Exception:
                    pass

                self._log("✅ 已登录并打开目标页，请手动在浏览器中截图/操作，关闭浏览器后任务结束。")
                self._finish(True, "已打开浏览器，手动截图后直接关闭浏览器即可结束。")

                # 心跳保持 CDP 连接活跃
                while True:
                    try:
                        page.wait_for_timeout(15000)
                        page.evaluate("() => 1")
                    except Exception:
                        break

        except Exception as e:
            msg = str(e)
            if "Target closed" in msg or "invalid state" in msg or "InvalidState" in msg:
                self._log("ℹ️ 浏览器已关闭，任务结束")
                self._finish(True, "浏览器已手动关闭，任务结束")
            else:
                self._log(f"❌ 错误: {e}")
                self._finish(False, msg)

    # ──────────────────────── 辅助方法 ────────────────────────

    def _fill_first(self, page, selectors, value, label):
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(timeout=2500)
                locator.fill(value)
                self._log(f"✅ 已填写{label}")
                return True
            except Exception:
                continue
        return False

    def _click_text(self, page, text_value, timeout=15000):
        candidates = [page] + list(page.frames)
        for target in candidates:
            try:
                target.get_by_text(text_value, exact=True).first.click(timeout=timeout)
                return True
            except Exception:
                pass
            try:
                target.get_by_text(text_value).first.click(timeout=timeout)
                return True
            except Exception:
                pass
            try:
                target.locator(f"text={text_value}").first.click(timeout=timeout)
                return True
            except Exception:
                pass
        return False

    def _click_my_attendance(self, page, timeout=12000):
        candidates = [page] + list(page.frames)
        for target in candidates:
            selectors = [
                ".convoy-menu-group__menu-item__title:has-text('我的假勤'):visible",
                ".convoy-menu-group__list-item-wrapper:has-text('我的假勤'):visible",
                ".convoy-menu-group__menu-item:has(.convoy-menu-group__menu-item__title:has-text('我的假勤')):visible",
            ]
            for selector in selectors:
                try:
                    locator = target.locator(selector).first
                    if locator.count() == 0:
                        continue
                    locator.scroll_into_view_if_needed(timeout=1200)
                    try:
                        locator.click(timeout=1500)
                        self._log(f"✅ 已点击我的假勤: {selector}")
                        return True
                    except Exception:
                        pass
                    try:
                        locator.click(timeout=1500, force=True)
                        self._log(f"✅ 已强制点击我的假勤: {selector}")
                        return True
                    except Exception:
                        pass
                    try:
                        box = locator.bounding_box()
                        if box:
                            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                            self._log("✅ 已坐标点击我的假勤")
                            return True
                    except Exception:
                        pass
                    try:
                        locator.evaluate(
                            """(el) => {
                                const clickable = el.closest('.convoy-menu-group__list-item-wrapper')
                                    || el.closest('.convoy-menu-group__menu-item')
                                    || el;
                                ['mouseover','mousedown','mouseup','click'].forEach((type) => {
                                    clickable.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true }));
                                });
                            }"""
                        )
                        self._log("✅ 已事件触发点击我的假勤")
                        return True
                    except Exception:
                        pass
                except Exception:
                    pass
        return self._click_text(page, "我的假勤", timeout=timeout)

    def _wait_my_attendance_ready(self, page, timeout=30000):
        deadline = datetime.now().timestamp() + (timeout / 1000.0)
        while datetime.now().timestamp() < deadline:
            candidates = [page] + list(page.frames)
            for target in candidates:
                selectors = [
                    ".convoy-menu-group__menu-item__title:has-text('我的假勤')",
                    ".convoy-menu-group__list-item-wrapper:has-text('我的假勤')",
                ]
                for selector in selectors:
                    try:
                        loc = target.locator(selector).first
                        if loc.count() > 0 and loc.is_visible():
                            return True
                    except Exception:
                        pass
            page.wait_for_timeout(250)
        return False

    def _is_privacy_checked(self, target):
        checks = [
            ".el-checkbox__input.is-checked",
            ".el-checkbox.is-checked",
            "input[type='checkbox']:checked",
            "[role='checkbox'][aria-checked='true']",
        ]
        for selector in checks:
            try:
                if target.locator(selector).count() > 0:
                    return True
            except Exception:
                pass
        return False

    def _ensure_privacy_checked(self, page, timeout=8000):
        candidates = [page] + list(page.frames)
        for target in candidates:
            if self._is_privacy_checked(target):
                self._log("✅ 隐私协议已勾选")
                return True
            click_targets = [
                ".phoenix-checkbox.phoenix-checkbox--noLabel",
                ".phoenix-checkbox--noLabel",
                "label:has-text('同意')",
                ".el-checkbox:has-text('同意')",
                ".el-checkbox__input",
                "text=同意《隐私政策》",
                "text=同意",
            ]
            for selector in click_targets:
                try:
                    target.locator(selector).first.click(timeout=timeout)
                    target.wait_for_timeout(150)
                    if self._is_privacy_checked(target):
                        self._log("✅ 已勾选隐私协议")
                        return True
                except Exception:
                    pass
        self._log("⚠️ 未能确认隐私协议是否勾选，继续尝试登录")
        return False

    def _click_login_button(self, page, timeout=8000):
        candidates = [page] + list(page.frames)
        selectors = [
            ".phoenix-button:has-text('登录')",
            "button.phoenix-button:has-text('登录')",
            ".phoenix-button",
            "button:has-text('登录')",
            "text=登录",
            ".el-button--primary",
        ]
        for target in candidates:
            for selector in selectors:
                try:
                    target.locator(selector).first.click(timeout=timeout)
                    self._log(f"✅ 已点击登录按钮: {selector}")
                    return True
                except Exception:
                    pass
        return False

    def _click_fixbox_button(self, page, timeout=12000):
        candidates = [page] + list(page.frames)
        selectors = [".fixbox-fixbtn", ".fixbox-fixbtn:visible"]
        for target in candidates:
            for selector in selectors:
                try:
                    loc = target.locator(selector).first
                    if loc.count() == 0:
                        continue
                    loc.scroll_into_view_if_needed(timeout=1200)
                    loc.click(timeout=timeout)
                    self._log("✅ 已点击 fixbox 按钮")
                    return True
                except Exception:
                    pass
        self._log("⚠️ 未找到 fixbox 按钮，继续执行")
        return False

    def _wait_page_settle(self, page, timeout_ms=45000):
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15000))
        except Exception:
            pass

        deadline = datetime.now().timestamp() + (timeout_ms / 1000.0)
        stable_rounds = 0
        last_height = -1
        while datetime.now().timestamp() < deadline:
            try:
                state = page.evaluate(
                    """
                    () => {
                        const selectors = [
                            '.el-loading-mask', '.ant-spin-spinning',
                            '.phoenix-loading', '.loading',
                            '[class*="loading"]', '[class*="spinner"]'
                        ];
                        let loadingVisible = 0;
                        for (const sel of selectors) {
                            const nodes = document.querySelectorAll(sel);
                            nodes.forEach((n) => {
                                const s = window.getComputedStyle(n);
                                const visible = s && s.display !== 'none'
                                    && s.visibility !== 'hidden'
                                    && parseFloat(s.opacity || '1') > 0;
                                if (visible && n.getBoundingClientRect().width > 0
                                        && n.getBoundingClientRect().height > 0) {
                                    loadingVisible += 1;
                                }
                            });
                        }
                        return {
                            readyState: document.readyState,
                            height: document.body ? document.body.scrollHeight : 0,
                            loadingVisible
                        };
                    }
                    """
                )
            except Exception:
                page.wait_for_timeout(300)
                continue

            if (state["height"] == last_height
                    and state["loadingVisible"] == 0
                    and state["readyState"] == "complete"):
                stable_rounds += 1
            else:
                stable_rounds = 0
            last_height = state["height"]

            if stable_rounds >= 3:
                self._log("✅ 页面已稳定")
                return
            page.wait_for_timeout(350)

        self._log("⚠️ 页面稳定等待超时，继续")

    def _maximize_window(self, context, page):
        try:
            cdp = context.new_cdp_session(page)
            win = cdp.send("Browser.getWindowForTarget")
            cdp.send("Browser.setWindowBounds", {
                "windowId": win["windowId"],
                "bounds": {"windowState": "maximized"},
            })
            self._log("✅ 浏览器窗口已最大化")
            return
        except Exception:
            pass
        try:
            page.evaluate("window.moveTo(0, 0); window.resizeTo(screen.availWidth, screen.availHeight);")
            self._log("✅ 浏览器窗口已尝试铺满屏幕")
        except Exception:
            self._log("⚠️ 浏览器窗口最大化失败，请手动点最大化")
