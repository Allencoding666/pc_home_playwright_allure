import os
import re
from datetime import datetime

import allure
import yaml
from playwright.sync_api import Page
from appium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.by import By


from settings import ROOT_PATH, DB_PATH


class CustomPage(Page):
    """
    一個自訂的 Playwright Page，用於擴充 Page 的功能。
    此類別繼承自 Page 以獲得類型提示和 isinstance 支援，
    但內部透過 __getattr__ 將所有呼叫代理到一個真實的 page 實例，
    從而結合了繼承和組合的優點。
    """

    def __init__(self, page: Page):
        self._page = page
        self._img_count = 1

    def __getattr__(self, name):
        return getattr(self._page, name)

    def reset_counters(self):
        """重置此實例中的所有內部計數器。"""
        self._img_count = 1

    def cm_screenshot_and_attach(self, img_name=""):
        """擷取螢幕截圖並附加到 Allure 報告中。"""
        img_name = (
            datetime.now().strftime("%Y_%m_%d_%H_%M_%S") if not img_name else img_name
        )

        img = self._page.screenshot()

        allure.attach(
            img,
            name=f"({self._img_count}){img_name}",
            attachment_type=allure.attachment_type.PNG,
        )
        self._img_count += 1


class CustomAndroidDriver(webdriver.Remote):
    """
    一個自訂的 Appium Android Driver，用於擴充 webdriver.Remote 的功能。
    採用組合而非繼承，以代理原始 driver 的所有屬性和方法，並添加自訂功能。
    """

    def __init__(self, driver: webdriver.Remote):
        self._driver = driver
        self._finder_map = {
            "XPATH": AppiumBy.XPATH,
            "ACCESSIBILITY_ID": AppiumBy.ACCESSIBILITY_ID,
            "ID": AppiumBy.ID,
        }
        self._img_count = 1

    def __getattr__(self, name):
        """當訪問的屬性在 CustomAndroidDriver 中不存在時，從原始 driver 中尋找。"""
        return getattr(self._driver, name)

    def reset_counters(self):
        """重置此實例中的所有內部計數器。"""
        self._img_count = 1

    def _get_finder(self, finder: str):

        try:
            return self._finder_map[finder]
        except KeyError:
            raise ValueError(f"無效的定位方式: {finder}")

    def cm_wait_ele_visibility(self, locator: str, finder: str = "XPATH", timeout=10):
        """等待元素可見"""

        return WebDriverWait(self._driver, timeout).until(
            EC.visibility_of_element_located((self._get_finder(finder), locator))
        )

    def cm_wait_ele_clickable(self, locator: str, finder: str = "XPATH", timeout=10):
        """等待元素可點擊"""

        return WebDriverWait(self._driver, timeout).until(
            EC.element_to_be_clickable((self._get_finder(finder), locator))
        )

    def screenshot_and_attach(self, img_name=""):
        """擷取螢幕截圖並附加到 Allure 報告中。"""
        img_name = (
            datetime.now().strftime("%Y_%m_%d_%H_%M_%S") if not img_name else img_name
        )
        img = self._driver.get_screenshot_as_png()
        allure.attach(
            img,
            name=f"({self._img_count}){img_name}",
            attachment_type=allure.attachment_type.PNG,
        )
        self._img_count += 1


class StepCounter:
    """一個簡單的步驟計數器，用於在 Allure 報告中生成有序的步驟名稱。"""

    def __init__(self):
        self._count = 0

    def __call__(self, description: str) -> str:
        """
        呼叫實例時，計數器加一並回傳格式化的步驟字串。
        """
        self._count += 1
        return f"Step {self._count:02d}: {description}"


def get_test(test_id: str):
    with open("test_id_list.yaml", "r", encoding="utf-8") as f:
        test_id_list = yaml.safe_load(f)

    test_info = test_id_list.get(test_id)

    if test_info is None:
        raise ValueError(f"找不到測試 ID '{test_id}' 的相關資訊")

    match = re.search(r"^(.*?)Test", test_id)
    if match:
        test_platform = match.group(1)
    else:
        raise ValueError(f"無法從測試 ID '{test_id}' 中解析出測試平台")

    return test_platform, test_info


def get_test_data(file_path: str):
    try:
        with open(
            f"{ROOT_PATH}/{file_path}",
            "r",
            encoding="utf-8",
        ) as yaml_file:
            yaml_data = yaml.safe_load(yaml_file)

        return yaml_data
    except FileNotFoundError:
        print(f'Error: "{ROOT_PATH}/{file_path}" not found.')
        return {}
    except yaml.YAMLError as e:
        print(f"Error parsing {ROOT_PATH}/{file_path}: {e}")
        return {}


def update_tag_registry(items):
    """
    掃描所有測試項目，生成一個 tag 到測試路徑的映射，並寫入 SQLite 資料庫。
    """
    temp_registry = {}
    for item in items:
        for marker in item.iter_markers("tag"):
            tag_name = marker.kwargs.get("name")
            if tag_name:
                docstring = (
                    item.function.__doc__.strip()
                    if hasattr(item.function, "__doc__") and item.function.__doc__
                    else ""
                )
                temp_registry.setdefault(tag_name, {"paths": set(), "descriptions": []})
                temp_registry[tag_name]["paths"].add(item.nodeid)
                if docstring:
                    temp_registry[tag_name]["descriptions"].append(docstring)

    # 將 import 移至函式內部，避免循環匯入
    from sqlalchemy.orm import Session
    from database import SyncSessionLocal
    from models import TestList, TestPath

    db: Session = SyncSessionLocal()
    try:
        # 1. 獲取新舊 test_id 列表
        new_test_ids = set(temp_registry.keys())
        existing_tests = db.query(TestList.test_id).all()
        existing_test_ids = {test_id for (test_id,) in existing_tests}

        # 2. 找出並刪除過時的 test_id
        ids_to_delete = existing_test_ids - new_test_ids
        if ids_to_delete:
            db.query(TestList).filter(TestList.test_id.in_(ids_to_delete)).delete(
                synchronize_session=False
            )
            print(f"Removed obsolete test IDs: {', '.join(ids_to_delete)}")

        # 3. 更新或插入新的測試項目
        for tag_name, data in sorted(temp_registry.items()):
            description = next((d for d in reversed(data["descriptions"]) if d), "")

            # 使用 merge 來實現 "insert or update"
            # 如果 test_id 已存在，它會更新 description；如果不存在，則會建立新紀錄
            test_item = db.merge(TestList(test_id=tag_name, description=description))

            # 4. 重建 test_paths
            # 先刪除舊的
            db.query(TestPath).filter(TestPath.tag_name == tag_name).delete()
            # 再插入新的
            paths_to_insert = [
                TestPath(tag_name=tag_name, path=path)
                for path in sorted(list(data["paths"]))
            ]
            db.add_all(paths_to_insert)

        db.commit()
        print(f"Successfully updated test list in '{DB_PATH}'")
    except Exception as e:
        db.rollback()
        print(f"Failed to update test list: {e}")
    finally:
        db.close()


def log_test_run(
    test_id: str,
    result: str,
    start_time: str,
    end_time: str,
    execution_time: float,
    progress: int,
    log_content: str,
):
    """將單次測試執行結果記錄到資料庫中"""
    # 將 import 移至函式內部，避免循環匯入
    from sqlalchemy.orm import Session
    from database import SyncSessionLocal
    from models import TestList, TestRun

    db: Session = SyncSessionLocal()
    try:
        # 1. 在 test_runs 中插入新的執行紀錄
        new_run = TestRun(
            test_id=test_id,
            result=result,
            start_time=start_time,
            end_time=end_time,
            execution_time=execution_time,
            progress=progress,
            log_content=log_content,
        )
        db.add(new_run)

        # 2. 更新 test_list 中的最後一次執行結果
        test_item = db.query(TestList).filter(TestList.test_id == test_id).one()
        test_item.last_result = result
        test_item.last_run_start_time = start_time
        test_item.last_run_end_time = end_time
        test_item.last_run_execution_time = execution_time
        test_item.last_run_progress = progress

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Failed to log test run for '{test_id}': {e}")
    finally:
        db.close()


def get_allure_results_dir(test_id: str) -> str:
    """
    根據 test_id 生成一個唯一的 Allure results 目錄路徑。
    這個目錄會被用來暫存 Allure 的 JSON 結果檔案。

    Args:
        test_id: 測試任務的 ID。

    Returns:
        一個唯一的目錄路徑字串。
    """
    safe_test_id = test_id.replace(",", "_")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return os.path.join(
        ROOT_PATH, "reports", "temp_results", f"{safe_test_id}_{timestamp}"
    )
