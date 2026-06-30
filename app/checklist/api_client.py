"""
五项清单 API 客户端
- 登录获取 Token
- 获取当前用户信息、所属中心
- 获取表单默认值（区域、紧急程度）
- 获取数据字典（清单类型、中心列表、区域列表、紧急程度）
- 提交/批量提交五项清单
"""

import time
import urllib.request
import urllib.parse
import json
import base64
from datetime import datetime
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from app.constants import (
    CHECKLIST_API_BASE,
    CHECKLIST_LOGIN_API,
    CHECKLIST_CURRENT_USER_API,
    CHECKLIST_USER_CENTER_API,
    CHECKLIST_DEFAULTS_API,
    CHECKLIST_SUBMIT_API,
    CHECKLIST_NOTICE_API,
    CHECKLIST_WORKFLOW_API_IDS,
    CHECKLIST_WORKFLOW_API_PREFIX,
    CHECKLIST_WORKFLOW_API_SUFFIX,
    CHECKLIST_BATCH_PUSH_API,
    CHECKLIST_DICTIONARY_API,
    CHECKLIST_RSA_PUBLIC_KEY,
    CHECKLIST_TASK_LIST_API,
    CHECKLIST_REPLY_API,
    CHECKLIST_EVALUATE_API,
    CHECKLIST_READ_STATUS_API,
    CHECKLIST_TASK_DETAIL_API,
    CHECKLIST_UPDATE_TASK_API,
    CHECKLIST_SELF_COMPLETE_API,
)


def _request(url, method="GET", data=None, headers=None, timeout=15):
    """通用 HTTP 请求，返回 JSON 响应"""
    if headers is None:
        headers = {}
    headers.setdefault("User-Agent", "Mozilla/5.0")
    headers.setdefault("jnpf-origin", "pc")
    headers.setdefault("vue-version", "3")

    if method == "POST" and data is not None:
        if isinstance(data, dict):
            # 默认 JSON
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = data
    else:
        body = None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _form_request(url, params, headers=None, timeout=15):
    """application/x-www-form-urlencoded POST 请求"""
    if headers is None:
        headers = {}
    headers.setdefault("User-Agent", "Mozilla/5.0")
    headers.setdefault("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8")

    body = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _rsa_encrypt_password(plain_password):
    """RSA 公钥加密密码，与前端 JSEncrypt 一致（PKCS1v1.5）"""
    # 构建 PEM 格式公钥
    pem_key = (
        "-----BEGIN PUBLIC KEY-----\n"
        + CHECKLIST_RSA_PUBLIC_KEY
        + "\n-----END PUBLIC KEY-----"
    )
    rsa_key = RSA.import_key(pem_key)
    cipher = PKCS1_v1_5.new(rsa_key)
    encrypted = cipher.encrypt(plain_password.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


class ChecklistAPIClient:
    """五项清单 API 客户端"""

    def __init__(self, base_url=None, status_callback=None, token_expired_callback=None):
        self._base = (base_url or CHECKLIST_API_BASE).rstrip("/")
        self._token = None
        self._user_info = None   # { userId, realName, ... }
        self._center_name = None
        self._cb = status_callback or (lambda m, l="info": None)
        self._on_token_expired = token_expired_callback  # Token 过期时的回调
        self._dict_cache = {}    # enCode -> [{enCode, fullName, id}, ...]

    # ── 认证 ─────────────────────────────────────────────

    def is_logged_in(self):
        return self._token is not None

    def get_token(self):
        return self._token

    def get_user_info(self):
        return self._user_info

    def get_center_name(self):
        return self._center_name

    def login(self, username, password):
        """登录获取 Token，返回 (success, message)"""
        url = self._base + CHECKLIST_LOGIN_API
        try:
            # RSA 加密密码（与前端 JSEncrypt 一致）
            encrypted_pwd = _rsa_encrypt_password(password)
            result = _form_request(url, {
                "account": username,
                "password": encrypted_pwd,
                "code": "",
                "origin": "bpm",
                "timestamp": "0",
                "jnpf_ticket": "0",
                "grant_type": "bpm",
            })
            if result.get("code") == 200 and result.get("data"):
                token = result["data"].get("token", "")
                # token 可能带有 "bearer " 前缀，统一保留原样
                self._token = token
                self._cb("登录成功", "success")
                return True, "登录成功"
            else:
                msg = result.get("info") or result.get("msg", "登录失败，请检查账号密码")
                self._cb(msg, "error")
                return False, msg
        except Exception as e:
            msg = f"登录请求失败: {e}"
            self._cb(msg, "error")
            return False, msg

    def set_token_expired_callback(self, callback):
        """设置 Token 过期回调"""
        self._on_token_expired = callback

    def _check_token_expired(self, result):
        """检查 API 响应是否为 Token 过期/认证失败，若是则清除 Token 并触发回调"""
        code = result.get("code")
        if code in (401, 4001, 40001):
            self._token = None
            self._user_info = None
            if self._on_token_expired:
                self._on_token_expired()
            return True
        return False

    def set_token(self, token):
        """直接设置 Token（用于从缓存恢复）"""
        self._token = token

    def _auth_headers(self):
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = self._token
        return h

    # ── 用户信息 ─────────────────────────────────────────

    def fetch_current_user(self):
        """获取当前用户信息，返回 (success, user_info_dict)"""
        if not self._token:
            return False, "未登录"
        url = self._base + CHECKLIST_CURRENT_USER_API
        try:
            result = _request(url, headers=self._auth_headers())
            if self._check_token_expired(result):
                return False, "Token 已过期"
            if result.get("code") == 200 and result.get("data"):
                # 用户信息在 data.userInfo 中
                self._user_info = result["data"].get("userInfo", result["data"])
                return True, self._user_info
            return False, result.get("info") or result.get("msg", "获取用户信息失败")
        except Exception as e:
            return False, str(e)

    def fetch_user_center(self, user_id=None):
        """获取用户所属中心名称，返回 (success, center_name)"""
        if not self._token:
            return False, "未登录"
        uid = user_id or (self._user_info or {}).get("userId", "")
        if not uid:
            return False, "无用户ID"
        url = self._base + CHECKLIST_USER_CENTER_API.format(userId=uid)
        try:
            result = _request(url, headers=self._auth_headers())
            if result.get("code") == 200 and result.get("data"):
                center = result["data"].get("centerName", "")
                self._center_name = center  # 始终缓存
                return True, center
            return False, result.get("info", "获取中心失败")
        except Exception as e:
            return False, str(e)

    def search_user(self, keyword):
        """按姓名搜索用户，返回 (success, [{id, fullName}])"""
        if not self._token:
            return False, []
        url = self._base + "/api/permission/Users/ImUser/Selector/0"
        try:
            result = _request(url, method="POST", data={"keyword": keyword},
                              headers=self._auth_headers())
            if result.get("code") == 200:
                lst = result.get("data", {}).get("list", [])
                users = [
                    {"id": u.get("id", ""), "fullName": u.get("fullName", "")}
                    for u in lst if u.get("type") == "user"
                ]
                return True, users
            return False, []
        except Exception as e:
            self._cb(f"搜索用户失败: {e}", "error")
            return False, []

    def lookup_user_center(self, keyword):
        """按姓名搜索用户并获取其中心，返回 (success, {userId, fullName, centerName})"""
        ok, users = self.search_user(keyword)
        if not ok or not users:
            return False, f"未找到用户: {keyword}"
        # 取第一个匹配结果
        user = users[0]
        user_id = user["id"]
        full_name = user["fullName"]
        # 获取中心
        url = self._base + CHECKLIST_USER_CENTER_API.format(userId=user_id)
        try:
            result = _request(url, headers=self._auth_headers())
            if result.get("code") == 200 and result.get("data"):
                center_name = result["data"].get("centerName", "")
                return True, {
                    "userId": user_id,
                    "fullName": full_name,
                    "centerName": center_name,
                }
            return False, f"获取 {full_name} 的中心失败"
        except Exception as e:
            return False, str(e)

    # ── 表单默认值 ───────────────────────────────────────

    def fetch_form_defaults(self):
        """获取默认区域和紧急程度，返回 (success, {area, level})"""
        if not self._token:
            return False, {}
        url = self._base + CHECKLIST_DEFAULTS_API
        try:
            result = _request(url, method="POST", data={}, headers=self._auth_headers())
            if result.get("code") == 200 and result.get("data"):
                item = result["data"][0] if result["data"] else {}
                return True, {"area": item.get("area", ""), "level": item.get("level", "")}
            return False, {}
        except Exception as e:
            self._cb(f"获取默认值失败: {e}", "error")
            return False, {}

    # ── 数据字典 ─────────────────────────────────────────

    def fetch_dictionaries(self):
        """获取全部数据字典并缓存，返回字典 enCode -> [{enCode, fullName}] 映射"""
        if not self._token:
            return {}
        url = self._base + CHECKLIST_DICTIONARY_API
        try:
            result = _request(url, headers=self._auth_headers())
            if result.get("code") == 200 and result.get("data"):
                data = result["data"]
                # 数据结构: data.list[].enCode + data.list[].dictionaryList[]
                dict_list = data if isinstance(data, list) else data.get("list", [])
                mapping = {}
                for group in dict_list:
                    code = group.get("enCode", "")
                    items = group.get("dictionaryList", [])
                    if items:
                        mapping[code] = [
                            {
                                "enCode": it.get("enCode", ""),
                                "fullName": it.get("fullName", ""),
                                "id": it.get("id", ""),
                            }
                            for it in items
                        ]
                self._dict_cache = mapping
                return mapping
        except Exception as e:
            self._cb(f"获取字典失败: {e}", "error")
        return {}

    def get_dict_options(self, encode):
        """获取指定字典编码的选项列表 [{enCode, fullName}]"""
        return self._dict_cache.get(encode, [])

    # ── 提交清单（四步流程）──────────────────────────────────

    def submit_checklist(self, item_data, user_id=""):
        """提交单条清单，四步流程：
        1. 保存表单数据 → 获取记录 nos ID
        2. 发送桌面通知
        3. 触发工作流（仅非中心对中心）→ 获取 fId + taskId
        4. batchPush 推送任务 → 状态变为“已督办”
        返回 (success, message)"""
        if not self._token:
            return False, "未登录"

        item_type = str(item_data.get("type", ""))

        # Step 1: 保存表单数据
        url1 = self._base + CHECKLIST_SUBMIT_API
        payload1 = {
            "id": "",
            "data": json.dumps(item_data, ensure_ascii=False),
        }
        try:
            result1 = _request(url1, method="POST", data=payload1, headers=self._auth_headers())
            if self._check_token_expired(result1):
                return False, "Token 已过期，请重新登录"
            if result1.get("code") != 200:
                return False, f"保存失败: {result1.get('msg', '未知错误')}"
            record_id = ""
            data1 = result1.get("data", {})
            if isinstance(data1, dict):
                record_id = data1.get("id", data1.get("data", ""))
            elif isinstance(data1, str):
                record_id = data1
            if not record_id:
                record_id = item_data.get("nos", "")
            self._cb(f"Step1 保存成功, nos={record_id}", "info")
        except Exception as e:
            return False, f"保存请求失败: {e}"

        # Step 2: 发送桌面通知
        if user_id:
            url2 = self._base + CHECKLIST_NOTICE_API
            payload2 = {"pushType": 1, "createByList": [user_id]}
            try:
                _request(url2, method="POST", data=payload2, headers=self._auth_headers())
                self._cb("Step2 通知已发送", "info")
            except Exception as e:
                self._cb(f"Step2 通知发送失败(不影响): {e}", "error")

        # Step 3+4: 仅非“中心对中心”时触发工作流+推送
        if item_type == "1":
            self._cb("中心对中心类型，跳过工作流触发", "info")
            return True, "提交成功"

        # Step 3: 遍历多个 DataInterface ID，找到返回数据的那个
        inv_id = None
        task_id = None
        if record_id:
            payload3 = {
                "paramList": [
                    {
                        "defaultValue": record_id,
                        "fieldName": "fiveInventoryId",
                        "field": "fiveInventoryId",
                    }
                ]
            }
            found_inv_id = None  # 保存第一个找到的 inv_id
            for api_id in CHECKLIST_WORKFLOW_API_IDS:
                url3 = (self._base + CHECKLIST_WORKFLOW_API_PREFIX
                        + api_id + CHECKLIST_WORKFLOW_API_SUFFIX)
                try:
                    result3 = _request(url3, method="POST", data=payload3,
                                       headers=self._auth_headers(), timeout=30)
                    data3 = result3.get("data", None)
                    # 响应格式: [{"fId": 83462, "taskId": 148042}]
                    if isinstance(data3, list) and len(data3) > 0:
                        first = data3[0]
                        cur_inv = first.get("fId", first.get("fiveInventoryId",
                                   first.get("id")))
                        cur_task = first.get("taskId")
                        if not found_inv_id:
                            found_inv_id = cur_inv  # 保存第一个 inv_id
                        if cur_inv and cur_task:
                            inv_id = cur_inv
                            task_id = cur_task
                            self._cb(f"Step3 工作流已触发(ID={api_id}), "
                                     f"invId={inv_id}, taskId={task_id}", "info")
                            break
                except Exception:
                    continue

            # 如果遍历完所有ID都没有带taskId的，用第一个有数据的inv_id
            if not inv_id and found_inv_id:
                inv_id = found_inv_id
                self._cb(f"Step3 找到invId={inv_id}但无taskId", "info")
            elif not inv_id:
                self._cb("Step3 未获取到有效的工作流数据", "error")

        # Step 4: batchPush 推送任务（已督办）
        if inv_id and task_id:
            url4 = self._base + CHECKLIST_BATCH_PUSH_API
            payload4 = {
                "fiveInventoryList": [
                    {
                        "fiveInventoryId": int(inv_id),
                        "taskId": int(task_id),
                    }
                ]
            }
            try:
                result4 = _request(url4, method="POST", data=payload4,
                                   headers=self._auth_headers())
                if result4.get("code") == 200:
                    self._cb("Step4 任务已推送(已督办)", "success")
                else:
                    self._cb(f"Step4 推送失败: {result4.get('msg', '')}", "error")
            except Exception as e:
                self._cb(f"Step4 推送请求失败: {e}", "error")
        elif inv_id and not task_id:
            self._cb("Step4 跳过: 无taskId，无法推送", "info")

        return True, "提交成功"

    def batch_submit(self, items, user_id="", progress_callback=None, cancel_check=None):
        """批量提交清单
        items: list of dict，每个 dict 是一条清单的完整字段
        user_id: 当前用户ID，用于发送通知
        progress_callback(current, total, success, message)
        cancel_check: 可调用对象，返回 True 表示取消
        返回 (success_count, fail_count, messages)
        """
        total = len(items)
        success_count = 0
        fail_count = 0
        messages = []

        for i, item in enumerate(items):
            if cancel_check and cancel_check():
                messages.append("已取消")
                break
            ok, msg = self.submit_checklist(item, user_id=user_id)
            if ok:
                success_count += 1
            else:
                fail_count += 1
            messages.append(msg)
            if progress_callback:
                progress_callback(i + 1, total, ok, msg)
            time.sleep(0.3)

        return success_count, fail_count, messages

    # ── 回复/评价 ─────────────────────────────────────

    def fetch_month_count(self):
        """获取本月已提交的清单数量，返回 int"""
        if not self._token:
            return 0
        # 使用 DataInterface 574601696513187333 按日期过滤
        now = datetime.now()
        beg_date = f"{now.year}-{now.month:02d}-01 00:00:00"
        end_date = f"{now.year}-{now.month:02d}-{now.day:02d} 23:59:59"
        url = self._base + "/api/system/DataInterface/574601696513187333/Actions/Preview"
        try:
            result = _request(url, method="POST",
                              data={
                                  "paramList": [
                                      {"field": "begDate", "defaultValue": beg_date},
                                      {"field": "endDate", "defaultValue": end_date},
                                  ]
                              },
                              headers=self._auth_headers())
            if result.get("code") == 200:
                data = result.get("data", {})
                # 返回格式: {"t1": 总数, "t2": 提报条数, "t3": 被提报条数}
                total = data.get("t2", 0)
                return int(total) if total else 0
            return 0
        except Exception:
            return 0

    def fetch_task_list(self):
        """获取待处理任务列表，返回 (success, list)"""
        if not self._token:
            return False, []
        url = self._base + CHECKLIST_TASK_LIST_API
        try:
            result = _request(url, method="POST",
                              data={"currentPage": 1, "pageSize": 200},
                              headers=self._auth_headers())
            if self._check_token_expired(result):
                return False, []
            if result.get("code") == 200:
                data = result.get("data", {})
                items = data.get("list", [])
                return True, items
            return False, []
        except Exception as e:
            self._cb(f"获取任务列表失败: {e}", "error")
            return False, []

    def reply_task(self, item, reply_text="收到"):
        """回复单条任务，返回 (success, message)"""
        if not self._token:
            return False, "未登录"
        inv_id = item.get("iveId", item.get("fiveInventoryId", ""))
        task_id = item.get("taskId", "")
        task_type = item.get("type", "")

        # Step 1: 提交回复
        url1 = self._base + CHECKLIST_REPLY_API
        payload1 = {"paramList": [
            {"field": "task_progress", "defaultValue": ""},
            {"field": "task_fulfil_description", "defaultValue": reply_text},
            {"field": "file_url"},
            {"field": "status", "defaultValue": 1},
            {"field": "invId", "defaultValue": inv_id},
            {"field": "invStatus", "defaultValue": 4},
        ]}
        try:
            result = _request(url1, method="POST", data=payload1,
                              headers=self._auth_headers())
            if self._check_token_expired(result):
                return False, "Token 已过期，请重新登录"
            if result.get("code") != 200:
                return False, f"回复失败: {result.get('msg', '')}"
        except Exception as e:
            return False, f"回复请求失败: {e}"

        # Step 2: 设置已读状态
        try:
            url2 = self._base + CHECKLIST_READ_STATUS_API
            payload2 = {"paramList": [
                {"field": "invId", "defaultValue": inv_id},
                {"field": "status", "defaultValue": 2},
            ]}
            _request(url2, method="POST", data=payload2,
                     headers=self._auth_headers())
        except Exception:
            pass

        # Step 3: 更新任务状态（自己对自己类型）
        # 浏览器实际调用: 694514618499872645 参数: {field: "id", defaultValue: invId}
        try:
            url3 = self._base + CHECKLIST_SELF_COMPLETE_API
            payload3 = {"paramList": [
                {"field": "id", "defaultValue": inv_id},
            ]}
            _request(url3, method="POST", data=payload3,
                     headers=self._auth_headers())
        except Exception:
            pass

        return True, "回复成功"

    def evaluate_task(self, item, satisfied=True):
        """评价单条任务，返回 (success, message)"""
        if not self._token:
            return False, "未登录"
        inv_id = item.get("iveId", item.get("fiveInventoryId", ""))

        # Step 1: 提交评价 (0=满意, 1=不满意)
        url1 = self._base + CHECKLIST_EVALUATE_API
        payload1 = {"paramList": [
            {"field": "invId", "defaultValue": inv_id},
            {"field": "type", "defaultValue": "0" if satisfied else "1"},
        ]}
        try:
            result = _request(url1, method="POST", data=payload1,
                              headers=self._auth_headers())
            if self._check_token_expired(result):
                return False, "Token 已过期，请重新登录"
            if result.get("code") != 200:
                return False, f"评价失败: {result.get('msg', '')}"
        except Exception as e:
            return False, f"评价请求失败: {e}"

        # Step 2: 设置已读
        try:
            url2 = self._base + CHECKLIST_READ_STATUS_API
            payload2 = {"paramList": [
                {"field": "invId", "defaultValue": inv_id},
                {"field": "status", "defaultValue": 2},
            ]}
            _request(url2, method="POST", data=payload2,
                     headers=self._auth_headers())
        except Exception:
            pass

        return True, "评价成功"

    def batch_reply(self, items, reply_text="收到", progress_callback=None):
        """批量回复任务"""
        total = len(items)
        ok_count = 0
        fail_count = 0
        for i, item in enumerate(items):
            ok, msg = self.reply_task(item, reply_text)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
            if progress_callback:
                progress_callback(i + 1, total, ok, msg)
            time.sleep(0.3)
        return ok_count, fail_count

    def batch_evaluate(self, items, satisfied=True, progress_callback=None):
        """批量评价任务"""
        total = len(items)
        ok_count = 0
        fail_count = 0
        for i, item in enumerate(items):
            ok, msg = self.evaluate_task(item, satisfied)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
            if progress_callback:
                progress_callback(i + 1, total, ok, msg)
            time.sleep(0.3)
        return ok_count, fail_count
