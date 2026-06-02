"""AI 日报内容生成器 - 使用 OpenAI 兼容 API（DeepSeek / 硅基流动等）"""

import json
import urllib.request
import urllib.error

from app.constants import (
    FIELD_LABELS, DEFAULT_AI_API_URL, DEFAULT_AI_ROLE,
)


def _build_system_prompt(field1_content, role_description):
    role = role_description.strip()
    if not role:
        role = DEFAULT_AI_ROLE
    field_list = "\n".join(
        f"{i}. {label}" for i, label in enumerate(FIELD_LABELS[1:], start=2)
    )
    return (
        f"我是一名{role}，今天完成了以下工作：\n\n"
        f"{field1_content}\n\n"
        f"请帮我补充日报剩余部分，根据以上工作总结延伸出以下各字段的内容：\n\n"
        f"{field_list}\n\n"
        f"要求：每个字段写1-3句话，内容真诚具体，基于我的工作总结来延伸，"
        f"用序号开头直接写内容不要加字段名。"
    )


def detect_model(api_url, api_key):
    """调用 /models 端点自动检测可用的聊天模型"""
    url = f"{api_url.rstrip('/')}/models"
    req = urllib.request.Request(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    preferred = ["deepseek-chat", "gpt-3.5-turbo", "qwen-turbo", "glm-4", "moonshot-v1"]
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return preferred[0]

    models = []
    raw = body.get("data", body.get("models", []))
    for item in raw:
        name = item.get("id", item.get("model", item.get("name", "")))
        if name:
            models.append(name)
    if not models:
        return preferred[0]

    for p in preferred:
        for m in models:
            if p.lower() in m.lower():
                return m
    return models[0]


def generate_report(field1_content, api_key, api_url=None, model=None,
                    role_description=None, max_tokens=2048, status_callback=None):
    if api_url is None:
        api_url = DEFAULT_AI_API_URL
    if model is None:
        if status_callback:
            status_callback("正在检测可用模型...", "info")
        model = detect_model(api_url, api_key)
        if status_callback:
            status_callback(f"自动检测到模型: {model}", "ai")
    if role_description is None:
        role_description = DEFAULT_AI_ROLE

    return _do_generate(field1_content, api_key, api_url, model, role_description, max_tokens, status_callback)


def _parse_ai_response(text):
    result = {}
    fields = FIELD_LABELS[1:]
    lines = text.strip().split("\n")
    current_field = None
    current_content = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        matched = None
        for i, label in enumerate(fields):
            prefixes = [f"{i+2}.", f"{i+2}、", f"**{i+2}**", f"## {i+2}", f"字段{i+2}", label[:8]]
            for prefix in prefixes:
                if line.startswith(prefix):
                    matched = label
                    rest = line[len(prefix):].strip().lstrip("：:").strip()
                    break
            if matched:
                break
        if matched:
            if current_field is not None and current_content:
                result[current_field] = "\n".join(current_content).strip()
            current_field = matched
            current_content = [rest] if rest else []
        else:
            if current_field is not None:
                current_content.append(line)

    if current_field is not None and current_content:
        result[current_field] = "\n".join(current_content).strip()

    for label in fields:
        if label not in result:
            result[label] = ""

    return result


def _do_generate(field1_content, api_key, api_url, model, role_description, max_tokens, status_callback):

    url = f"{api_url.rstrip('/')}/chat/completions"

    system_prompt = _build_system_prompt(field1_content, role_description)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个专业的日报填写助手，请严格按照格式输出。只输出内容，不要输出任何解释或额外文字。"},
            {"role": "user", "content": system_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    if status_callback:
        status_callback("正在连接 AI 服务...", "info")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        raise RuntimeError(f"API 请求失败 ({e.code}): {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络连接失败: {e.reason}")

    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError("AI 未返回任何内容，请检查 API Key 是否正确")

    content = choices[0].get("message", {}).get("content", "")

    if status_callback:
        status_callback("AI 生成完成，正在解析...", "success")

    return _parse_ai_response(content)
