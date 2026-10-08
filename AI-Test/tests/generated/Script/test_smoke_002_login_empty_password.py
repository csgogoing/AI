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
