"""火山方舟 (Volcengine Ark) Chat Completions API 封装。

真实模式:
    POST https://ark.cn-beijing.volces.com/api/v3/chat/completions
    Authorization: Bearer $ARK_API_KEY
    参考: https://console.volcengine.com/ark/region:cn-beijing/docs/ark/chat-api

Mock 模式:
    未设置 ARK_API_KEY 时自动启用, 用本地预置内容演示完整流程
    (生成 -> 人工检查 -> 执行 -> 汇总 -> Excel 台账), 保证无 Key 也能跑通端到端 demo。
    设置 ARK_API_KEY 后自动切换真实 LLM 调用。
"""
import json
import os
import re

import requests

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seed-2-1-pro-260628"

# ---- Mock 预置内容 -----------------------------------------------------
# 预置脚本均与拾光小店 (webapp) 的页面/选择器一一对应, 可真实执行。
# 浏览器 fixture 由 Script/conftest.py 统一提供, 脚本直接使用 page 参数。

MOCK_SCRIPT_001 = '''\
import os

from playwright.sync_api import expect

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000")
USERNAME = "admin"
PASSWORD = "admin123"


def do_login(page):
    page.goto(f"{BASE_URL}/login")
    page.fill("#username", USERNAME)
    page.fill("#password", PASSWORD)
    page.click("#login-btn")
    page.wait_for_load_state("networkidle")


def test_smoke_login_success(page):
    """冒烟用例1: 正确账号密码登录成功"""
    do_login(page)
    expect(page.locator("#nav-user")).to_have_text("👤 admin")


def test_smoke_login_failure(page):
    """冒烟用例2: 错误密码登录被拦截并提示"""
    page.goto(f"{BASE_URL}/login")
    page.fill("#username", USERNAME)
    page.fill("#password", "wrong-password")
    page.click("#login-btn")
    expect(page.locator("#login-error")).to_be_visible()


def test_smoke_add_cart_and_checkout(page):
    """冒烟用例3: 登录后加购->结算->提交订单->生成订单号"""
    do_login(page)
    page.goto(f"{BASE_URL}/")
    page.locator(".product").first.locator(".add-to-cart").click()
    page.goto(f"{BASE_URL}/cart")
    expect(page.locator("#cart-items .cart-item")).to_have_count(1)
    page.click("#checkout-btn")
    page.fill("#address", "北京市顺义区测试路1号")
    page.fill("#phone", "13800000000")
    page.click("#confirm-order-btn")
    page.wait_for_url("**/order/**")
    expect(page.locator("#order-success")).to_be_visible()
    expect(page.locator("#order-id")).to_contain_text("SO")
'''

MOCK_CASES_001 = [
    {
        "func": "test_smoke_login_success",
        "title": "正确账号密码登录成功",
        "precondition": "已注册账号 admin/admin123",
        "steps": "1. 打开登录页; 2. 输入用户名 admin; 3. 输入密码 admin123; 4. 点击登录",
        "expected": "登录成功跳转首页, 导航栏显示用户 admin",
    },
    {
        "func": "test_smoke_login_failure",
        "title": "错误密码登录被拦截并提示",
        "precondition": "已注册账号 admin",
        "steps": "1. 打开登录页; 2. 输入用户名 admin; 3. 输入错误密码; 4. 点击登录",
        "expected": "页面显示登录错误提示 login-error",
    },
    {
        "func": "test_smoke_add_cart_and_checkout",
        "title": "登录后加购、结算、提交订单生成订单号",
        "precondition": "已登录 admin 账号, 购物车为空",
        "steps": "1. 打开首页; 2. 点击第一个商品加入购物车; 3. 进入购物车; 4. 点击去结算; 5. 填写地址电话; 6. 提交订单",
        "expected": "跳转订单成功页, 显示 order-success 且订单号以 SO 开头",
    },
]

MOCK_SCRIPT_002 = '''\
import os

from playwright.sync_api import expect

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000")
USERNAME = "admin"


def test_smoke_login_empty_password(page):
    """冒烟用例: 空密码登录被拦截并提示"""
    page.goto(f"{BASE_URL}/login")
    page.fill("#username", USERNAME)
    page.fill("#password", "")
    page.click("#login-btn")
    expect(page.locator("#login-error")).to_be_visible()
'''

MOCK_CASES_002 = [
    {
        "func": "test_smoke_login_empty_password",
        "title": "空密码登录被拦截并提示",
        "precondition": "已注册账号 admin",
        "steps": "1. 打开登录页; 2. 输入用户名 admin; 3. 密码留空; 4. 点击登录",
        "expected": "页面显示登录错误提示 login-error",
    },
]

# 修正版: 用户检查后发现空密码时浏览器原生 required 校验拦截提交,
# #login-error 为服务端渲染不会出现, 改为断言原生校验激活且页面未跳转。
MOCK_SCRIPT_002_FIX = '''\
import os

from playwright.sync_api import expect

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000")
USERNAME = "admin"


def test_smoke_login_empty_password(page):
    """冒烟用例: 空密码登录被浏览器原生 required 校验拦截"""
    page.goto(f"{BASE_URL}/login")
    page.fill("#username", USERNAME)
    page.click("#login-btn")
    # HTML5 required 校验激活: 密码框为空时处于 invalid 状态
    expect(page.locator("#password:invalid")).to_be_visible()
    # 表单未提交, 仍停留在登录页
    expect(page).to_have_url(f"{BASE_URL}/login")
'''

MOCK_CASES_002_FIX = [
    {
        "func": "test_smoke_login_empty_password",
        "title": "空密码登录被浏览器原生校验拦截",
        "precondition": "已注册账号 admin",
        "steps": "1. 打开登录页; 2. 输入用户名 admin; 3. 密码留空; 4. 点击登录按钮",
        "expected": "密码框处于 invalid 状态(原生 required 校验激活), 页面未跳转仍停留登录页",
    },
]


def _mock_generate(first: bool, content: str = "") -> str:
    """Mock 生成脚本: 首次生成 001 登录冒烟脚本, 续聊新增/修正用例。"""
    if first:
        payload = {
            "action": "create",
            "script_name": "test_smoke_XXX_login.py",
            "summary": "生成登录与下单结算冒烟测试脚本, 覆盖登录成功/失败/加购结算三个用例",
            "script": MOCK_SCRIPT_001,
            "cases": MOCK_CASES_001,
        }
    elif any(k in content for k in ("required", "原生校验", "修正", "校验拦截",
                                     "修复", "找不到", "报错", "update")):
        payload = {
            "action": "update",
            "script_name": "test_smoke_002_login_empty_password.py",
            "summary": "根据人工检查反馈修正: 空密码时浏览器原生 required 校验拦截提交, "
                       "#login-error 为服务端渲染不会出现, 改为断言原生校验激活且页面未跳转",
            "script": MOCK_SCRIPT_002_FIX,
            "cases": MOCK_CASES_002_FIX,
        }
    else:
        payload = {
            "action": "create",
            "script_name": "test_smoke_XXX_login_empty_password.py",
            "summary": "根据对话补充空密码登录被拦截的冒烟用例",
            "script": MOCK_SCRIPT_002,
            "cases": MOCK_CASES_002,
        }
    return json.dumps(payload, ensure_ascii=False)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("ARK_API_KEY")
        self.model = model or os.environ.get("ARK_MODEL") or DEFAULT_MODEL
        self.mock = not self.api_key
        if self.mock:
            print("[LLM] 未检测到 ARK_API_KEY -> 使用 MOCK 模式演示流程。")
            print("[LLM] 设置环境变量 ARK_API_KEY 后自动切换真实模型调用。")

    def chat(self, messages: list[dict], temperature: float = 0.2,
             max_tokens: int = 4000) -> str:
        if self.mock:
            return self._mock_chat(messages)
        try:
            resp = requests.post(
                f"{ARK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            raise LLMError(f"Ark API 调用失败: {e}") from e

    # ---- Mock 模式 ----------------------------------------------------
    def _mock_chat(self, messages: list[dict]) -> str:
        content = messages[-1]["content"] if messages else ""
        if "【任务】生成冒烟测试脚本" in content:
            # 已有脚本段为空 => 首次生成; 非空 => 连续对话(续聊/修正)
            first = "【已有脚本】\n\n" in content or "【已有脚本】\n无" in content
            # 只提取用户的需求文本做关键词判断, 避免提示词模板自带的
            # "required/修复"等词干扰 MOCK 分支路由
            m = re.search(r"【需求】\s*(.*?)\s*\n【已有脚本】", content, re.S)
            requirement = m.group(1) if m else content
            return _mock_generate(first, requirement)
        return json.dumps({"action": "create", "script_name": "",
                           "summary": "MOCK 响应: 请设置 ARK_API_KEY 使用真实 LLM。",
                           "script": "", "cases": []}, ensure_ascii=False)
