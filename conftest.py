import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Iterator

import allure
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
        br = p.chromium.launch()
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


class ProgressReporter:
    def __init__(self):
        self.total_tests = 0
        self.completed_tests = 0

    def pytest_collection_finish(self, session):
        self.total_tests = len(session.items)

    def pytest_runtest_teardown(self, item, nextitem):
        self.completed_tests += 1
        if self.total_tests > 0:
            progress = int((self.completed_tests / self.total_tests) * 100)
            print(f"PROGRESS:{progress}", flush=True)


def pytest_collection_modifyitems(items):
    """
    讓測試名稱支援中文
    """
    for item in items:
        item.name = item.name.encode("utf-8").decode("unicode-escape")  # 用例名稱
        item._nodeid = item.nodeid.encode("utf-8").decode("unicode-escape")  # 用例節點


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    report_dir = "report"
    results_dir = "report/allure_results"
    report_register = "report/report_register"
    if not os.path.exists(results_dir):
        print(f"沒有找到 {results_dir}，可能是測試沒有產生任何結果")
        return

    # 在不同系統上找 allure 可執行檔
    candidates = [
        shutil.which("allure"),  # Linux / macOS 一般會有
        shutil.which("allure.cmd"),  # Windows (Scoop/Chocolatey)
        shutil.which("allure.bat"),  # Windows 另一種情況
    ]
    allure_path = next((c for c in candidates if c), None)

    if not allure_path:
        print("找不到 allure CLI，請確認已安裝並設定 PATH")
        return

    print(f"使用 allure CLI: {allure_path}")

    try:
        subprocess.run(
            [
                allure_path,
                "generate",
                "--single-file",
                results_dir,
                "--clean",
                "-o",
                report_register,
            ],
            check=True,
        )
        # 重新命名 index.html
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        custom_name = f"report_{now}.html"  # 自訂檔名
        src = os.path.join(report_register, "index.html")
        dst = os.path.join(report_dir, custom_name)
        if os.path.exists(src):
            os.rename(src, dst)
            print(f"\nallure single-file report generated at: {dst}")
        else:
            print(f"\n找不到 {src}，無法重新命名報告")
    except subprocess.CalledProcessError as e:
        print(f"生成報告失敗: {e}")
        sys.exit(1)


@pytest.fixture(autouse=True)
def setup_suite(request):
    print(request.node.nodeid)

    # 抓取測試檔案的路徑資訊，看是哪個端口的測試，並設定 Allure 的 parent_suite
    file_path = Path(request.node.fspath)
    parent_folder = file_path.parent.name
    parent_suite_map = {"client": "用戶端測試", "admin": "後台測試", "api": "API 測試"}
    allure.dynamic.parent_suite(parent_suite_map.get(parent_folder, parent_folder))

    # 抓 class docstring，如果有的話就設定為 suite
    if hasattr(request.node, "cls") and request.node.cls:
        class_doc = request.node.cls.__doc__
        if class_doc:
            allure.dynamic.suite(class_doc.strip())

    # 抓 function docstring，如果有的話就設定為 sub_suite
    func_doc = getattr(request.node.function, "__doc__", None)
    if func_doc:
        allure.dynamic.sub_suite(func_doc.strip())


def pytest_configure(config):
    if not config.pluginmanager.hasplugin("progress_reporter"):
        config.pluginmanager.register(ProgressReporter(), "progress_reporter")
