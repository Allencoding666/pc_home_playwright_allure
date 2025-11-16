import os
import re
from datetime import datetime
from pathlib import Path

import allure
import yaml
from playwright.sync_api import Page

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


def update_tag_registry(items):
    """
    掃描所有測試項目，生成一個 tag 到測試路徑的映射，並寫入 YAML 檔案。
    """
    # 暫存區，用於收集帶有 order 和 docstring 資訊的測試
    temp_registry = {}
    for item in items:
        # 一個測試可以有多個 tag 標記
        for marker in item.iter_markers("tag"):
            tag_name = marker.kwargs.get("name")
            order = marker.kwargs.get("order")
            docstring = ""
            if hasattr(item.function, "__doc__") and item.function.__doc__:
                docstring = item.function.__doc__.strip()

            if tag_name:
                # 如果 tag name 不在字典裡，就初始化一個空列表
                temp_registry.setdefault(tag_name, [])
                # 存入 (order, nodeid, docstring) 元組，並避免重複添加
                if not any(
                    entry[1] == item.nodeid for entry in temp_registry[tag_name]
                ):
                    temp_registry[tag_name].append((order, item.nodeid, docstring))

    # 處理排序並建立最終的註冊表
    final_registry = {}
    for tag_name, entries in temp_registry.items():
        # 根據 order 排序，order 為 None 的排在後面
        entries.sort(key=lambda x: x[0] if x[0] is not None else float("inf"))
        # 提取排序後的 nodeid 列表
        paths = [nodeid for order, nodeid, doc in entries]
        # 提取最後一個（order 最大）的 docstring 作為描述
        description = entries[-1][2] if entries else ""
        final_registry[tag_name] = {"paths": paths, "description": description}

    # 將註冊表寫入專案根目錄的 tag_registry.yaml
    output_file = f"{ROOT_PATH}/tag_registry.yaml"
    with open(output_file, "w", encoding="utf-8") as f:
        # allow_unicode=True 確保中文能正確寫入
        # sort_keys=True 讓輸出的 tag 字母排序，更易讀
        yaml.dump(final_registry, f, allow_unicode=True, sort_keys=True)


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
