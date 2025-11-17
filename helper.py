import os
import re
from datetime import datetime
from pathlib import Path

import allure
import yaml
from playwright.sync_api import Page
import sqlite3

from settings import ROOT_PATH


class CustomPage(Page):
    def __init__(self, page: Page):
        super().__init__(page._impl_obj)
        self._page = page
        self._img_count = 1

    def cp_screenshot(self, *args, img_name="", **kwargs):
        os.makedirs("screenshots", exist_ok=True)

        if "path" not in kwargs:
            img_name = (
                datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                if not img_name
                else img_name
            )
            kwargs["path"] = f"screenshots/({self._img_count}){img_name}.png"
        else:
            kwargs["path"] = re.sub(
                r"\.(?=[^.]+$)", f"_({self._img_count}).", kwargs["path"]
            )

        self._img_count += 1

        return self._page.screenshot(*args, **kwargs)

    def cp_screenshot_and_attach(self, img_name=""):
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


def get_test(test_id: str):
    with open("test_id_list.yaml", "r", encoding="utf-8") as f:
        test_id_list = yaml.safe_load(f)

    test_info = test_id_list.get(test_id)

    if test_info is None:
        raise ValueError(f"找不到測試 ID '{test_id}' 的相關資訊")

    test_platform = re.search(r"^(.*?)Test", test_id).group(1)

    return test_platform, test_info


def get_test_data(test_platform: str, file_name: str):
    try:
        with open(
            f"{ROOT_PATH}/test_data/{test_platform}/{file_name}.yaml",
            "r",
            encoding="utf-8",
        ) as yaml_file:
            yaml_data = yaml.safe_load(yaml_file)

        return yaml_data
    except FileNotFoundError:
        print(
            f'Error: "{ROOT_PATH}/test_data/{test_platform}/{file_name}.yaml" not found.'
        )
        return {}
    except yaml.YAMLError as e:
        print(
            f"Error parsing {ROOT_PATH}/test_data/{test_platform}/{file_name}.yaml: {e}"
        )
        return {}


def update_tag_registry(items, db_path=f"{ROOT_PATH}/test_registry.db"):
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

    # 連線到資料庫
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 建立表格 (如果不存在)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            name TEXT PRIMARY KEY,
            description TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS test_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_name TEXT,
            path TEXT,
            FOREIGN KEY (tag_name) REFERENCES tags (name) ON DELETE CASCADE
        )
    """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_name ON test_paths (tag_name)")

    # 使用交易來確保原子性
    try:
        cursor.execute("BEGIN")
        # 清空舊資料
        cursor.execute("DELETE FROM tags")
        cursor.execute("DELETE FROM test_paths")

        # 插入新資料
        for tag_name, data in sorted(temp_registry.items()):
            # 使用最後一個非空的 docstring 作為描述
            description = next((d for d in reversed(data["descriptions"]) if d), "")
            cursor.execute(
                "INSERT INTO tags (name, description) VALUES (?, ?)",
                (tag_name, description),
            )

            paths_to_insert = [(tag_name, path) for path in sorted(list(data["paths"]))]
            cursor.executemany(
                "INSERT INTO test_paths (tag_name, path) VALUES (?, ?)", paths_to_insert
            )

        conn.commit()
        print(f"Successfully updated test registry in '{db_path}'")
    except Exception as e:
        conn.rollback()
        print(f"Failed to update test registry: {e}")
    finally:
        conn.close()


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
