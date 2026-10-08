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
