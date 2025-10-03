import os
import re
from datetime import datetime

import allure
import yaml
from playwright.sync_api import Page
from lxml.html import builder
from lxml import html

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
