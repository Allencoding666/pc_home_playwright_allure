import re
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from helper import CustomAndroidDriver


class Momo:

    def __init__(self, driver: CustomAndroidDriver):
        self.driver = driver

    # ==============================
    # utils
    # ==============================

    def go_to_home_page(self):

        self.driver.cm_wait_ele_clickable(
            '//android.widget.TextView[@content-desc="YouTube"]'
        ).click()

        self.driver.cm_wait_ele_clickable(
            finder="ACCESSIBILITY_ID",
            locator="Search YouTube",
        ).click()

        self.driver.cm_wait_ele_visibility(
            '//android.widget.EditText[@resource-id="com.google.android.youtube:id/search_edit_text"]'
        ).send_keys("appium 教學")

        self.driver.press_keycode(66)  # 66 是 Enter 鍵的 keycode

    # def close_pop_up(self):
    #     """關閉彈出視窗"""

    #     try:
    #         self.page.locator(
    #             '(//div[@data-testid="close-button-container"]//*[name()="g"])[last()]'
    #         ).click(timeout=3000)
    #     except:
    #         # 沒有出現彈出視窗的話，不影響後續操作，直接略過
    #         pass

    # def search_product(self, keyword: str):
    #     """搜尋產品

    #     Args:
    #         keyword: 搜尋關鍵字
    #     """
    #     self.page.locator('//input[@name="search-input"]').fill(keyword)
    #     self.page.locator('//input[@name="search-input"]/../..//button').click()
    #     self.page.wait_for_load_state("load")
    #     self.page.cp_screenshot_and_attach(img_name=f"搜尋[{keyword}]")

    # def click_product(self, product_index: str):
    #     """點擊產品

    #     Args:
    #         product_index: 產品索引，從1開始
    #     """
    #     self.page.locator(
    #         f'(//li[@class="listAreaLi"][{product_index}]//a[@href])[1]'
    #     ).click()

    # def get_product_name(self):
    #     """取得產品名稱"""

    #     url = self.page.url
    #     product_name = ""

    #     # 使用正則表達式判斷 URL 是屬於 'goods' 還是 'TP' 類型
    #     if re.search(r"/goods/", url):
    #         product_name_locator = self.page.locator('//span[@id="osmGoodsName"]')
    #     elif re.search(r"/TP/", url):
    #         product_name_locator = self.page.locator(
    #             '//div[@class="flex justify-start"]//h3'
    #         )
    #     else:
    #         # 如果兩種都不是，可以選擇拋出錯誤或記錄日誌
    #         raise AssertionError(f"FAIL: 未知的商品頁面URL格式({url})")

    #     product_name = product_name_locator.text_content().strip()
    #     if product_name:
    #         self.page.cp_screenshot_and_attach(img_name=f"{product_name}")
    #     return product_name
