"""原型导入模块：通过 Axure 原型链接抓取页面文本内容"""

import re
import urllib.parse
import urllib.request
import urllib.error
from html.parser import HTMLParser


class _AxureTextParser(HTMLParser):
    """从 Axure 原型 HTML 中提取纯文本内容"""

    def __init__(self):
        super().__init__()
        self._texts = []
        self._in_base = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if attrs_dict.get("id") == "base":
            self._in_base = True
        if self._in_base:
            self._depth += 1

    def handle_endtag(self, tag):
        if self._in_base:
            self._depth -= 1
            if self._depth <= 0:
                self._in_base = False

    def handle_data(self, data):
        if self._in_base:
            text = data.strip()
            if text:
                self._texts.append(text)


def parse_prototype_url(url):
    """
    解析 Axure 原型链接，从中提取项目基地址和页面名称。

    示例输入:
        http://ax.homedo.com/YF-135948/#id=w6j0kd&p=%E9%98%BF%E7%B1%B3%E5%B7%B4%E6%9C%88%E5%B7%A5%E8%B5%84&g=1

    返回:
        {
            "base": "http://ax.homedo.com/YF-135948",
            "page_name": "阿米巴月工资",
            "page_url": "http://ax.homedo.com/YF-135948/阿米巴月工资.html",
            "project_id": "YF-135948",
        }
    """
    # 分离 hash fragment
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    base = base.rstrip("/")

    # 从 hash fragment 中提取 p 参数
    fragment = parsed.fragment
    params = urllib.parse.parse_qs(fragment)

    page_name_encoded = ""
    if "p" in params:
        page_name_encoded = params["p"][0]

    if not page_name_encoded:
        # 尝试从 path 中提取
        path_parts = parsed.path.rstrip("/").rsplit("/", 1)
        if len(path_parts) > 1:
            page_name_encoded = path_parts[-1]

    page_name = urllib.parse.unquote(page_name_encoded) if page_name_encoded else ""

    if not page_name:
        raise ValueError("无法从链接中解析出页面名称，请检查链接格式")

    # 项目 ID 从路径中提取
    project_id = parsed.path.strip("/").split("/")[0] if parsed.path.strip("/") else ""

    # 构建直接页面 URL
    page_url = f"{base}/{urllib.parse.quote(page_name)}.html"

    return {
        "base": base,
        "page_name": page_name,
        "page_url": page_url,
        "project_id": project_id,
    }


def fetch_prototype_content(url, status_callback=None):
    """
    根据原型链接抓取页面文本内容。

    参数:
        url: Axure 原型链接（如 http://ax.homedo.com/YF-135948/#id=...&p=...）
        status_callback: 可选的状态回调函数 callback(msg, level)

    返回:
        {
            "page_name": "阿米巴月工资",
            "content": "1、报工产量...\n2、...",
            "page_url": "http://ax.homedo.com/YF-135948/阿米巴月工资.html",
        }
    """
    info = parse_prototype_url(url)
    page_url = info["page_url"]
    page_name = info["page_name"]

    if status_callback:
        status_callback(f"正在获取原型页面: {page_name}", "info")

    req = urllib.request.Request(
        page_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"获取原型页面失败 (HTTP {e.code}): {page_url}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络连接失败: {e.reason}")

    # 解析 HTML 提取文本
    parser = _AxureTextParser()
    parser.feed(html)

    content = "\n".join(parser._texts)

    # 如果没有通过 #base 解析到内容，回退到简单正则提取
    if not content:
        content = _fallback_extract(html)

    if status_callback:
        lines = content.strip().split("\n") if content.strip() else []
        status_callback(f"已获取 {len(lines)} 行原型内容", "success")

    return {
        "page_name": page_name,
        "content": content,
        "page_url": page_url,
    }


def _fallback_extract(html):
    """回退方案：用正则从 HTML body 中提取文本"""
    # 移除 script 和 style 标签
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # 提取 body 内容
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if not body_match:
        return ""
    body = body_match.group(1)
    # 移除 HTML 标签
    text = re.sub(r'<[^>]+>', '\n', body)
    # 清理空白行
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return "\n".join(lines)
