"""AI 日报内容生成器 - 使用 OpenAI 兼容 API（DeepSeek / 硅基流动等）"""

import json
import re
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
    total = len(FIELD_LABELS)
    return (
        f"我是一名{role}，今天完成了以下工作：\n\n"
        f"{field1_content}\n\n"
        f"请帮我补充日报剩余部分，根据以上工作总结延伸出以下各字段的内容：\n\n"
        f"{field_list}\n\n"
        f"要求：\n"
        f"1. 必须输出全部 {total - 1} 个字段（序号2到{total}），一个都不能少\n"
        f"2. 每个字段写1-3句话，内容真诚具体，基于我的工作总结来延伸\n"
        f"3. 用序号开头直接写内容不要加字段名\n"
        f"4. 不要出现任何具体的人名或同事姓名，统一用\u201c同事\u201d\u201c伙伴\u201d或职务名称（如\u201c项目经理\u201d\u201c测试同事\u201d）代替\n"
        f"5. 请务必以序号 {total} 的内容作为结尾，不要遗漏最后一个字段"
    )


# 厂商模型回退列表（按优先级排序，从基础到高级）
VENDOR_MODEL_FALLBACK = {
    'doubao': [
        'doubao-seed-2-0-lite-260428',  # Seed 2.0 Lite (默认)
        'doubao-seed-2-0-pro-260215',   # Seed 2.0 Pro
        'doubao-lite-32k',               # 旧版 Lite
        'doubao-pro-32k',                # 旧版 Pro
    ],
    'deepseek': [
        'deepseek-chat',
        'deepseek-reasoner',
    ],
    'openai': [
        'gpt-3.5-turbo',
        'gpt-4',
        'gpt-4-turbo',
    ],
    'qwen': [
        'qwen-turbo',
        'qwen-plus',
        'qwen-max',
    ],
    'glm': [
        'glm-4-flash',
        'glm-4',
        'glm-4-plus',
    ],
    'moonshot': [
        'moonshot-v1-8k',
        'moonshot-v1-32k',
        'moonshot-v1-128k',
    ],
}


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
    preferred = ["doubao-seed-2-0-lite-260428", "deepseek-chat", "gpt-3.5-turbo", "qwen-turbo", "glm-4", "moonshot-v1"]
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


def detect_vendor_from_model(model_name):
    """从模型名称检测厂商"""
    if not model_name:
        return None
    model_lower = model_name.lower()
    for vendor, models in VENDOR_MODEL_FALLBACK.items():
        for m in models:
            if m.lower() in model_lower or model_lower in m.lower():
                return vendor
    # 通过关键词匹配
    if 'doubao' in model_lower or 'seed' in model_lower:
        return 'doubao'
    if 'deepseek' in model_lower:
        return 'deepseek'
    if 'gpt' in model_lower:
        return 'openai'
    if 'qwen' in model_lower:
        return 'qwen'
    if 'glm' in model_lower:
        return 'glm'
    if 'moonshot' in model_lower or 'kimi' in model_lower:
        return 'moonshot'
    return None


def generate_report(field1_content, api_key, api_url=None, model=None,
                    role_description=None, max_tokens=4096, status_callback=None):
    if api_url is None:
        api_url = DEFAULT_AI_API_URL
    if model is None:
        if status_callback:
            status_callback("正在检测可用模型...", "info")
        model = detect_model(api_url, api_key)
        if status_callback:
            status_callback("AI 服务已就绪", "info")
    if role_description is None:
        role_description = DEFAULT_AI_ROLE

    return _do_generate(field1_content, api_key, api_url, model, role_description, max_tokens, status_callback)



# 中文数字映射
_CN_NUMS = {2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八"}

# 用于检测人名的上下文词（这些词后面跟的2-3字中文很可能是人名）
_NAME_CONTEXT_BEFORE = r'(?:和|与|向|找|问|帮|请|让|给|叫|跟|由|被|把|同|带)'
_NAME_CONTEXT_AFTER  = r'(?:一起|沟通|对接|协调|配合|反馈|反馈了|说|提出|确认|处理|解决|完成了|完成|那边|那里|这边)'
# 匹配“人名”：2-3个汉字，前后有典型人名上下文
_NAME_PATTERN = re.compile(
    rf'({_NAME_CONTEXT_BEFORE})([\u4e00-\u9fa5]{{2,3}})({_NAME_CONTEXT_AFTER})'
)


def _sanitize_names(text):
    """将疑似人名的词替换为“同事”"""
    def _replace(m):
        before, name, after = m.group(1), m.group(2), m.group(3)
        # 排除常见的非人名词（职位、部门、系统等）
        blacklist = {"领导", "客户", "同事", "伙伴", "团队", "部门", "产品", "项目",
                     "系统", "需求", "接口", "测试", "开发", "设计", "运维", "运营"}
        if name in blacklist:
            return m.group(0)
        return f"{before}同事{after}"
    return _NAME_PATTERN.sub(_replace, text)


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
            num = i + 2
            prefixes = [
                f"{num}.", f"{num}、", f"**{num}**", f"## {num}",
                f"字段{num}",
                f"{_CN_NUMS.get(num, '')}、",   # 中文数字：八、
                label[:8],
            ]
            for prefix in prefixes:
                if prefix and line.startswith(prefix):
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

    # 对每个字段内容做人名脱敏
    for label in fields:
        if label in result and result[label]:
            result[label] = _sanitize_names(result[label])
        elif label not in result:
            result[label] = ""

    return result


# ── 五项清单内容生成 ─────────────────────────────────────

def generate_checklist_items(api_key, api_url=None, model=None,
                             prompt="", count=10, max_tokens=4096,
                             prototype_content=None,
                             status_callback=None, attempted_models=None):
    """AI 生成五项清单内容，返回 list[str]

    prototype_content: 可选的已导入原型文本，AI 会尽量贴近原型内容来生成
    """
    if api_url is None:
        api_url = DEFAULT_AI_API_URL
    if model is None:
        if status_callback:
            status_callback("正在检测可用模型...", "info")
        model = detect_model(api_url, api_key)
        if status_callback:
            status_callback("AI 服务已就绪", "info")

    if not prompt.strip():
        prompt = "请根据以上原型参考内容生成清单" if (prototype_content and prototype_content.strip()) else "前端开发日常工作"

    # 如果有原型内容，拼入 system prompt 作为参照
    prototype_instruction = ""
    if prototype_content and prototype_content.strip():
        prototype_instruction = (
            f"\n\n【原型参考内容】以下是用户导入的需求原型中的内容，"
            f"请尽量贴近以下需求点来生成五项清单内容：\n"
            f"{prototype_content.strip()}\n\n"
            f"要求：生成的清单内容要与原型中的需求点相关，"
            f"每条清单应可对应到原型中的某个功能点或需求点。"
        )

    system = (
        f"你是一个五项清单内容生成助手。请根据用户描述的工作场景，"
        f"生成 {count} 条五项清单内容。\n"
        f"每项内容格式为：中心事件 + 要求达成目标 + 要求完成时间节点\n"
        f"要求：\n"
        f"1. 每条内容独立一行，字数控制在100-300字之间\n"
        f"2. 内容具体可执行，不要太笼统\n"
        f"3. 严禁出现任何具体的人名或同事姓名，统一用“相关同事”“相关负责人”或职务名称（如“项目经理”“测试负责人”）代替\n"
        f"4. 时间节点必须使用相对时间表述，如“3-5个工作日内”“1-2周内”“本月底前”等，"
        f"禁止使用具体日期或具体时刻（如“明天上午10点”“周三下午”等），"
        f"且时间要求不能太紧，且最大不超过2周\n"
        f"5. 不要加序号，直接写内容\n"
        f"6. 只输出 {count} 条的内容，不要输出其他任何文字"
        f"{prototype_instruction}"
    )

    url = f"{api_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt.strip()},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    if status_callback:
        status_callback(f"正在生成 {count} 条清单内容...", "info")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        error_str = f"API 请求失败 ({e.code}): {error_body}"
        
        # 检查是否是模型不可用错误
        if e.code == 404 or 'ModelNotOpen' in error_str or 'InvalidEndpointOrModel' in error_str:
            vendor = detect_vendor_from_model(model)
            if vendor and vendor in VENDOR_MODEL_FALLBACK:
                fallback_models = VENDOR_MODEL_FALLBACK[vendor]
                if attempted_models is None:
                    attempted_models = [model]
                
                next_model = None
                for m in fallback_models:
                    if m not in attempted_models:
                        next_model = m
                        break
                
                if next_model:
                    if status_callback:
                        status_callback(f"模型 {model} 不可用，正在切换到 {next_model}...", "info")
                    attempted_models.append(next_model)
                    return generate_checklist_items(
                        api_key=api_key,
                        api_url=api_url,
                        model=next_model,
                        prompt=prompt,
                        count=count,
                        max_tokens=max_tokens,
                        prototype_content=prototype_content,
                        status_callback=status_callback,
                        attempted_models=attempted_models,
                    )
        
        raise RuntimeError(error_str)
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络连接失败: {e.reason}")

    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError("AI 未返回任何内容，请检查 API Key")

    content = choices[0].get("message", {}).get("content", "")
    if status_callback:
        status_callback("AI 生成完成，正在解析...", "success")

    # 解析：按行拆分，去除空行和序号前缀
    items = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # 去除可能的序号前缀: "1." "1、" "1." "-" 等
        line = re.sub(r'^[\d]+[.\u3001)\]、]\s*', '', line)
        line = re.sub(r'^[-*]\s*', '', line)
        line = line.strip()
        if line:
            items.append(_sanitize_names(line))

    # 如果生成数量超过 count，截断
    if len(items) > count:
        items = items[:count]

    if status_callback:
        status_callback(f"成功解析 {len(items)} 条清单内容", "success")

    return items


def _do_generate(field1_content, api_key, api_url, model, role_description, max_tokens, status_callback, attempted_models=None):

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
        status_callback(f"正在连接 AI 服务...", "info")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        error_str = f"API 请求失败 ({e.code}): {error_body}"
        
        # 检查是否是模型不可用错误（404、ModelNotOpen、InvalidEndpointOrModel等）
        if e.code == 404 or 'ModelNotOpen' in error_str or 'InvalidEndpointOrModel' in error_str:
            # 尝试自动切换其他模型
            vendor = detect_vendor_from_model(model)
            if vendor and vendor in VENDOR_MODEL_FALLBACK:
                fallback_models = VENDOR_MODEL_FALLBACK[vendor]
                # 过滤掉已经尝试过的模型
                if attempted_models is None:
                    attempted_models = [model]
                
                next_model = None
                for m in fallback_models:
                    if m not in attempted_models:
                        next_model = m
                        break
                
                if next_model:
                    if status_callback:
                        status_callback(f"模型 {model} 不可用，正在切换到 {next_model}...", "info")
                    attempted_models.append(next_model)
                    # 递归调用，尝试下一个模型
                    return _do_generate(
                        field1_content, api_key, api_url, next_model,
                        role_description, max_tokens, status_callback, attempted_models
                    )
        
        # 如果无法切换或所有模型都失败，抛出异常
        raise RuntimeError(error_str)
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络连接失败: {e.reason}")

    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError("AI 未返回任何内容，请检查 API Key 是否正确")

    choice = choices[0]
    content = choice.get("message", {}).get("content", "")
    finish_reason = choice.get("finish_reason", "")

    if status_callback:
        status_callback("AI 生成完成，正在解析...", "success")

    result = _parse_ai_response(content)

    # 检查缺失字段
    missing = [FIELD_LABELS[i+1] for i in range(len(FIELD_LABELS)-1) if not result.get(FIELD_LABELS[i+1])]

    # 被截断时用更大 token 重试
    if finish_reason == "length":
        if missing and status_callback:
            status_callback(f"响应被截断，缺少 {len(missing)} 个字段，正在重试...", "info")
        if missing:
            retry_result = _do_generate(
                field1_content, api_key, api_url, model,
                role_description, max_tokens * 2, status_callback
            )
            for label in FIELD_LABELS[1:]:
                if not result.get(label) and retry_result.get(label):
                    result[label] = retry_result[label]
        missing = [FIELD_LABELS[i+1] for i in range(len(FIELD_LABELS)-1) if not result.get(FIELD_LABELS[i+1])]

    # 未被截断但仍有字段缺失（AI 偶尔遗漏末尾字段），用更大 token 重试一次
    if missing and max_tokens < 16384:
        if status_callback:
            status_callback(f"AI 遗漏了 {len(missing)} 个字段，正在补充生成...", "info")
        retry_result = _do_generate(
            field1_content, api_key, api_url, model,
            role_description, max_tokens * 2, status_callback
        )
        for label in FIELD_LABELS[1:]:
            if not result.get(label) and retry_result.get(label):
                result[label] = retry_result[label]

    return result
