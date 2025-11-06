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

from helper import CustomPage, update_tag_registry


def pytest_addoption(parser):
    """向 pytest 增加自訂命令列選項"""
    parser.addoption(
        "--run-tag",
        action="store",
        default=None,
        help="僅執行帶有指定標籤的測試案例。例如: --run-tag SmokeTest",
    )


@pytest.fixture(scope="session", autouse=True)
def setup_and_teardown():

    print("測試開始時間:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    yield
    print("測試結束時間:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# ====================================
# | 瀏覽器 |
# ====================================
@pytest.fixture(scope="class")
def create_browser(request) -> Iterator[Browser]:
    """每個測試 class 建立一個獨立的瀏覽器實例"""

    # 從 pytest 的設定中讀取 --headed 參數是否存在
    is_headed = request.config.getoption("--headed")

    with sync_playwright() as p:
        br = p.chromium.launch(headless=not is_headed)
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


def pytest_collection_modifyitems(config, items):
    """
    pytest 收集測試案例後，執行此鉤子函式以修改測試案例列表。
    """

    # 讓測試名稱支援中文
    for item in items:
        item.name = item.name.encode("utf-8").decode("unicode-escape")  # 用例名稱
        item._nodeid = item.nodeid.encode("utf-8").decode("unicode-escape")  # 用例節點

    update_tag_registry(items)

    def get_run_tag_name():
        run_tag_name = config.getoption("--run-tag")
        # 如果沒有指定 --run-tag，則不進行任何操作
        if not run_tag_name:
            return

        selected_items_with_order = []
        deselected_items = []

        for item in items:
            is_selected = False
            # 遍歷所有 'tag' 標記，而不只是最接近的那個
            for marker in item.iter_markers("tag"):
                if marker.kwargs.get("name") == run_tag_name:
                    # 找到匹配的標籤，記錄其 order 值用於排序
                    order = marker.kwargs.get("order")
                    selected_items_with_order.append((item, order))
                    is_selected = True
                    break  # 找到一個匹配就夠了，跳出內層迴圈

            if not is_selected:
                deselected_items.append(item)

        # 根據 'order' 參數對選中的測試案例進行排序
        # order=None 的項目會被排在後面
        selected_items_with_order.sort(key=lambda x: x[1] or float("inf"))

        # 更新 pytest 的項目列表，只保留篩選和排序後的結果
        # 從 (item, order) 元組中提取出 item
        selected_items = [item for item, order in selected_items_with_order]
        config.hook.pytest_deselected(items=deselected_items)
        items[:] = selected_items

    get_run_tag_name()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """
    測試會話結束後，根據 --alluredir 和 --run-tag 生成單一檔案的 Allure 報告。
    """
    run_tag = session.config.getoption("--run-tag")
    results_dir = session.config.getoption("--alluredir")

    # 如果沒有指定 allure 結果目錄或 run_tag，則不生成報告
    if not results_dir or not run_tag:
        print("未指定 --alluredir 或 --run-tag，跳過 Allure 報告生成。")
        return

    if not os.path.exists(results_dir):
        print(f"沒有找到 {results_dir}，可能是測試沒有產生任何結果")
        return

    # --- 找到 Allure CLI ---
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

    # --- 準備報告目錄和檔名 ---
    # 將 tag 中的逗號替換為底線，以建立有效的資料夾和檔案名稱
    safe_run_tag = run_tag.replace(",", "_")
    # 報告將存放在 reports/<safe_run_tag>/ 目錄下
    final_report_dir = os.path.join(os.path.dirname(results_dir), "..", safe_run_tag)
    os.makedirs(final_report_dir, exist_ok=True)

    # 臨時生成目錄，避免多個進程同時寫入同一個 index.html
    temp_generate_dir = os.path.join(final_report_dir, "temp_generate")

    # --- 生成報告 ---
    try:
        subprocess.run(
            [
                allure_path,
                "generate",
                "--single-file",
                results_dir,
                "--clean",
                "-o",
                temp_generate_dir,
            ],
            check=True,
        )
        # --- 重新命名並移動報告 ---
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        custom_name = f"{safe_run_tag}_{now}.html"  # 新的檔名格式
        src = os.path.join(temp_generate_dir, "index.html")
        dst = os.path.join(final_report_dir, custom_name)

        if os.path.exists(src):
            os.rename(src, dst)
            print(f"\nallure single-file report generated at: {dst}")
        else:
            print(f"\n找不到 {src}，無法重新命名報告")

    except subprocess.CalledProcessError as e:
        print(f"生成報告失敗: {e}")
    finally:
        # 清理臨時的 allure results 和生成目錄
        shutil.rmtree(results_dir, ignore_errors=True)
        shutil.rmtree(temp_generate_dir, ignore_errors=True)


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


def pytest_configure(config):
    if not config.pluginmanager.hasplugin("progress_reporter"):
        config.pluginmanager.register(ProgressReporter(), "progress_reporter")

    # 註冊自訂的 marker，避免 pytest 報警
    config.addinivalue_line(
        "markers", "tag(name, order=None): 用於標記測試案例並可選地提供執行順序"
    )
