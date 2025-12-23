import time
from datetime import datetime

import allure
import pytest

from helper import get_test_data
from pages.client.home_page.web_pc_home import PcHome


PC_HOME_DATA = get_test_data(file_path="test_data/client/home_page/pc_home.yaml")
SEARCH_PRODUCT_DATA = PC_HOME_DATA["search_product"]


@pytest.fixture(scope="class", autouse=True)
def init_work(request, create_page):
    request.cls.pc_home = PcHome(create_page)


class TestPcHome:
    """測試PChome頁面"""

    pc_home: PcHome

    # @pytest.mark.tag(name="ClientTest00001", order=1)
    # @pytest.mark.tag(name="ClientTest00002", order=1)
    def test_enter_pc_home(self):
        """測試進入PChome首頁"""

        allure.dynamic.title("進入PChome首頁")
        allure.dynamic.description("開啟瀏覽器後，是否能正常進入PChome首頁")
        self.pc_home.go_to_pc_home()
        self.pc_home.page.cm_screenshot_and_attach(img_name="PChome首頁")

    # @pytest.mark.tag(name="ClientTest00002", order=2)
    @pytest.mark.parametrize(
        "data", SEARCH_PRODUCT_DATA, ids=lambda data: data["test_params"]["name"]
    )
    def test_search_product(self, data):
        """測試搜尋指定產品"""

        allure.dynamic.title(data["test_info"]["title"])
        allure.dynamic.description(data["test_info"]["desc"])
        with allure.step("step 01: 關閉跳出視窗"):
            self.pc_home.close_pop_up()
        with allure.step("step 02: 搜尋產品"):
            self.pc_home.search_product(keyword=data["test_info"]["keyword"])
        with allure.step("step 03: 點擊產品"):
            self.pc_home.click_product(product_index="1")
        with allure.step("step 04: 返回上一頁"):
            self.pc_home.page.go_back()
