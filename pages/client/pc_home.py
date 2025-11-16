from helper import CustomPage


class PcHome:

    def __init__(self, page: CustomPage):
        self.page = page

    def go_to_pc_home(self, url="https://24h.pchome.com.tw/"):
        self.page.goto(url)

    def close_pop_up(self):
        """關閉彈出視窗"""

        try:
            self.page.locator('//button[@aria-label="close button"]').click()
        except:
            pass

    def search_product(self, keyword: str):
        """搜尋產品

        Args:
            keyword: 搜尋關鍵字
        """
        self.page.locator('//input[@type="search"]').fill(keyword)
        self.page.locator('//button[@data-regression="header_search_button"]').click()
        self.page.wait_for_load_state("load")
        self.page.cp_screenshot_and_attach(img_name=f"搜尋[{keyword}]")

    def click_product(self, product_index: str):
        """點擊產品

        Args:
            product_index: 產品索引，從1開始
        """
        self.page.locator(
            f'(//div[@class="c-listInfoGrid__body"]//li)[{product_index}]'
        ).click()
        product_name = self.page.locator(
            '//div[@class="o-prodMainName o-prodMainName--prodNick"]'
        ).text_content()
        self.page.cp_screenshot_and_attach(img_name=f"{product_name}")
