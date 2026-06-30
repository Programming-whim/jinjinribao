"""常量定义：URL、字段标签、默认值、定时器参数等"""

LOGIN_URL = "https://ssc.homedo.com/login"
LOGIN_BUTTON_TEXT = "立即登录"
DAILY_REPORT_NAV_TEXT = "精进日报"
WRITE_REPORT_BUTTON_TEXT = "去写日报"
SUBMIT_BUTTON_TEXTS = ["提交", "保存"]

DEFAULT_USERNAME = ""
DEFAULT_PASSWORD = ""

FIELD_LABELS = [
    "一、付出不亚于任何人的努力，谁比你更努力",
    "二、以终为始，每天完成六件主航道的事",
    "三、民主生活会改善",
    "四、需兄弟部门配合与知晓项",
    "五、明日计划工作项",
    "六、每天反省二点，并告知伙伴与家人",
    "七、不受干扰，杜绝感性烦恼，争取每天快乐",
    "八、纯粹助人，争取每天做三件利他的事情",
]

DEFAULT_FIELD_CONTENT = {
    label: "" for label in FIELD_LABELS
}

DEFAULT_SCHEDULE_TIME = "18:00"
DEFAULT_SCHEDULE_ENABLED = False

SCHEDULE_POLL_INTERVAL_MS = 10_000

DEFAULT_HEADLESS = False
DEFAULT_STEP_DELAY = 1.0

DEFAULT_AUTO_SUBMIT = False

PAGE_LOAD_TIMEOUT = 30000
LOGIN_TIMEOUT = 20000
NAV_TIMEOUT = 15000

APP_TITLE = "牛马工具2.0"
APP_WIDTH = 1100
APP_HEIGHT = 780

# ========== 更新检查配置 ==========
APP_VERSION = "2.6.1"
UPDATE_EXE_DOWNLOAD_URL = "https://hmd-mall-product.homedo.com/homedo-oss/static/1780022550008/牛马工具2.0.exe"
UPDATE_CHANGELOG_URL = "https://hmd-mall-product.homedo.com/homedo-oss/static/1781581281516/CHANGELOG.txt"

# ========== AI 生成配置 ==========
DEFAULT_AI_API_KEY = "ark-8c1835ca-f11c-4872-9093-e1beaff0e508-01e0a"
DEFAULT_AI_API_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_AI_MODEL = "doubao-seed-2-0-lite-260428"
DEFAULT_AI_ROLE = ""

# ========== 五项清单 API 配置 ==========
CHECKLIST_API_BASE = "https://dida.homedo.com"
CHECKLIST_LOGIN_API = "/api/oauth/Login"
CHECKLIST_CURRENT_USER_API = "/api/oauth/CurrentUser"
CHECKLIST_USER_CENTER_API = "/api/permission/Users/{userId}"
CHECKLIST_DEFAULTS_API = "/api/system/DataInterface/732473345005652549/Actions/Preview"
# Step 1: 保存表单数据
CHECKLIST_SUBMIT_API = "/api/visualdev/OnlineDev/537986998195978437"
# Step 2: 发送桌面通知
CHECKLIST_NOTICE_API = "/api/usual/gxh/desktop/notice"
# Step 3: 触发工作流（多个候选 DataInterface ID，遍历直到找到数据）
CHECKLIST_WORKFLOW_API_IDS = [
    "591849154481778501",
    "575009934601707397",
    "575191423075311493",
    "641598226767760197",
]
CHECKLIST_WORKFLOW_API_PREFIX = "/api/system/DataInterface/"
CHECKLIST_WORKFLOW_API_SUFFIX = "/Actions/Preview"
# Step 4: 推送任务（已督办）
CHECKLIST_BATCH_PUSH_API = "/api/usual/fiveInventory/batchPush"
CHECKLIST_DICTIONARY_API = "/api/system/DictionaryData/All"

# 回复/评价相关
CHECKLIST_TASK_LIST_API = "/api/usual/MeetingTaskFulfill/getList"
CHECKLIST_REPLY_API = "/api/system/DataInterface/540537303597120133/Actions/Preview"
CHECKLIST_EVALUATE_API = "/api/system/DataInterface/540538275006315141/Actions/Preview"
CHECKLIST_READ_STATUS_API = "/api/system/DataInterface/636889455445148421/Actions/Preview"
CHECKLIST_TASK_DETAIL_API = "/api/system/DataInterface/540502795636238149/Actions/Preview"
CHECKLIST_UPDATE_TASK_API = "/api/usual/fiveInventory/updateFiveInventoryTaskStatus/"
CHECKLIST_SELF_COMPLETE_API = "/api/system/DataInterface/694514618499872645/Actions/Preview"

# 清单类型（字典编码: qingdanleixing）
CHECKLIST_TYPE_DICT_CODE = "qingdanleixing"
# 中心分类（字典编码: ZXFL）
CHECKLIST_CENTER_DICT_CODE = "ZXFL"
# 区域（字典编码: area）
CHECKLIST_AREA_DICT_CODE = "area"
# 紧急程度（字典编码: JJCD）
CHECKLIST_URGENCY_DICT_CODE = "JJCD"

# RSA 公钥（用于登录密码加密，与前端 JSEncrypt 一致）
CHECKLIST_RSA_PUBLIC_KEY = "MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAL3jEtY/Pv96Vfeh4DOYid1CPZmv6/xdVKjvqKLwsOIfXIujSpWB2diyUnNo9p4FOt7iwIFZk03BQ81Pc1BtC6ECAwEAAQ=="

# ========== 字体配置 ==========
FONT_FAMILY = "Microsoft YaHei UI"  # 主字体（现代中文字体，接近苹果风格）
FONT_FAMILY_MONO = "Consolas"       # 等宽字体（日志/代码）
