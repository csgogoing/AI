"""共享 fixture: 整个会话只启动一次 Playwright 浏览器。"""
import os
import pytest
from playwright.sync_api import sync_playwright
BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000")
@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL
@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_PATH"))
        yield browser
        browser.close()
@pytest.fixture()
def page(browser):
    page = browser.new_page()
    yield page
    page.close()
