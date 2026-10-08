from playwright.sync_api import expect, Page


def test_login_password_empty_show_error(page: Page, base_url: str):
    # 访问登录页面
    page.goto(f"{base_url}/login")
    # 输入用户名，密码留空
    page.locator('#username').fill('admin')
    # 点击登录按钮
    page.locator('#login-btn').click()
    # 断言密码输入框触发原生必填校验，处于invalid状态
    expect(page.locator("#password:invalid")).to_be_visible()
    # 断言页面未跳转，仍在登录页
    expect(page).to_have_url(f"{base_url}/login")