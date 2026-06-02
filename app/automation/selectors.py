"""
选择器集中管理 - 网站改版时只需修改此文件。
每个选择器定义为列表，依次尝试，提高兼容性。
"""

# ---- 登录页 ----
LOGIN_BUTTON_SELECTORS = [
    ("text", "立即登录"),
    ("role", "button", "立即登录"),
    ("css", "button:has-text('立即登录')"),
    ("css", "[class*='login'] button"),
    ("css", "[class*='submit']"),
    ("css", ".login-btn"),
    ("css", ".btn-login"),
    ("css", "button[type='submit']"),
    ("css", "input[type='submit']"),
]

# 用户名/手机号输入框（覆盖管小花平台 + 通用场景）
USERNAME_INPUT_SELECTORS = [
    ("css", "input[placeholder*='手机']"),
    ("css", "input[placeholder*='账号']"),
    ("css", "input[placeholder*='用户']"),
    ("css", "input[name='username']"),
    ("css", "input[name='account']"),
    ("css", "input[name='phone']"),
    ("css", "input[name='mobile']"),
    ("css", "input[type='tel']"),
    ("css", "input[autocomplete='username']"),
]

# 密码输入框
PASSWORD_INPUT_SELECTORS = [
    ("css", "input[type='password']"),
    ("css", "input[placeholder*='密码']"),
    ("css", "input[name='password']"),
    ("css", "input[autocomplete='current-password']"),
]

# ---- 导航 ----
DAILY_REPORT_NAV_SELECTORS = [
    ("text", "精进日报"),
    ("css", "a:has-text('精进日报')"),
    ("css", ".menu-item:has-text('精进日报')"),
    ("css", "[class*='menu'] >> text=精进日报"),
    ("css", ".nav-item:has-text('精进日报')"),
]

WRITE_REPORT_SELECTORS = [
    ("text", "去写日报"),
    ("css", "button:has-text('去写日报')"),
    ("css", "a:has-text('去写日报')"),
    ("css", ".btn:has-text('去写日报')"),
]

# ---- 提交 ----
SUBMIT_BUTTON_SELECTORS = [
    ("role", "button", "提交"),
    ("text", "提交"),
    ("css", "button:has-text('提交')"),
    ("role", "button", "保存"),
    ("text", "保存"),
    ("css", "button:has-text('保存')"),
    ("css", ".submit-btn"),
    ("css", "button[type='submit']"),
]

# ---- 日报字段 ----
# 通用策略：通过标签文本定位，再找邻近的可编辑元素
# 富文本编辑器常见选择器
RICH_TEXT_EDITORS = [
    ".ql-editor",                      # Quill
    ".w-e-text-container",             # WangEditor
    ".edui-editor",                    # UEditor
    ".tox-edit-area",                  # TinyMCE
    ".cke_contents textarea",          # CKEditor
    "[contenteditable='true']",        # 通用 contenteditable
]


def get_field_xpath(label_prefix):
    """返回用于定位字段输入框的 XPath 策略列表。
    label_prefix: 字段标签前缀（如 '一、付出'）
    """
    # 截取前6个字符作为匹配前缀，避免完整标签太长
    short = label_prefix[:6]
    return [
        # 策略1: 找到包含标签文字的 div/span/label，然后找同级/子级的 textarea/input/contenteditable
        f"//*[contains(text(),'{short}')]/ancestor::div[contains(@class,'form')]//textarea",
        f"//*[contains(text(),'{short}')]/ancestor::div[contains(@class,'item')]//textarea",
        f"//*[contains(text(),'{short}')]/following::textarea[1]",
        f"//*[contains(text(),'{short}')]/following::input[1]",
        # 策略2: 找包含标签文字的容器，然后找其中的 contenteditable
        f"//*[contains(text(),'{short}')]/ancestor::div[contains(@class,'form')]//*[@contenteditable='true']",
        f"//*[contains(text(),'{short}')]/ancestor::div[contains(@class,'item')]//*[@contenteditable='true']",
        f"//*[contains(text(),'{short}')]/following::*[@contenteditable='true'][1]",
        # 策略3: 更宽泛 - 找任何包含该文字的元素后面的可编辑元素
        f"//*[contains(.,'{short}')]/following-sibling::*//textarea[1]",
        f"//*[contains(.,'{short}')]/following-sibling::*//*[@contenteditable='true'][1]",
    ]
