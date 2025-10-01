import os
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Iterator

import pytest
from playwright.sync_api import sync_playwright, Browser, BrowserContext

from helper import CustomPage


@pytest.fixture(scope="session", autouse=True)
def setup_and_teardown(request):

    print("測試開始時間:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    yield
    print("測試結束時間:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# ====================================
# | 瀏覽器 |
# ====================================
@pytest.fixture(scope="class")
def create_browser(request) -> Iterator[Browser]:
    """每個測試 class 建立一個獨立的瀏覽器實例"""

    with sync_playwright() as p:
        br = p.chromium.launch(headless=False)
        request.cls.br = br
        yield br
        br.close()


@pytest.fixture(scope="class")
def create_context(request, create_browser) -> Iterator[BrowserContext]:
    """每個測試 class 建立一個獨立的瀏覽器上下文"""

    br_ctx = create_browser.new_context()

    # 把 context 存到 class 內，讓 setup_class() 也能用
    request.cls.br_ctx = br_ctx

    yield br_ctx
    br_ctx.close()


@pytest.fixture(scope="class")
def create_page(request, create_context) -> Iterator[CustomPage]:
    """每個測試 class 建立共用的 page"""

    page = create_context.new_page()
    page.set_default_timeout(10000)
    page.set_viewport_size({"width": 1920, "height": 1080})

    # 將 pytest 的 request 物件傳入 CustomPage
    custom_page = CustomPage(page)
    request.cls.page = custom_page

    yield custom_page
    custom_page.close()


def pytest_collection_modifyitems(items):
    """
    讓測試名稱支援中文
    """

    print("pytest_collection_modifyitems")  # TODO
    for item in items:
        item.name = item.name.encode("utf-8").decode("unicode-escape")  # 用例名稱
        item._nodeid = item.nodeid.encode("utf-8").decode("unicode-escape")  # 用例節點


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    results_dir = "allure-results"
    report_dir = "report"
    if not os.path.exists(results_dir):
        print("沒有找到 allure-results，可能是測試沒有產生任何結果")
        return

        # 嘗試在不同系統上找 allure 可執行檔
    candidates = [
        shutil.which("allure"),  # Linux / macOS 一般會有
        shutil.which("allure.cmd"),  # Windows (Scoop/Chocolatey)
        shutil.which("allure.bat"),  # Windows 另一種情況
    ]
    allure_path = next((c for c in candidates if c), None)

    if not allure_path:
        print("找不到 allure CLI，請確認已安裝並設定 PATH")
        return

    print(f"使用 Allure CLI: {allure_path}")

    try:
        subprocess.run([
            allure_path, "generate", "--single-file", results_dir, "--clean", "-o", report_dir
        ], check=True)
        print(f"\nAllure single-file report generated at: {os.path.join(report_dir, 'index.html')}")
    except subprocess.CalledProcessError as e:
        print(f"生成報告失敗: {e}")
        sys.exit(1)
