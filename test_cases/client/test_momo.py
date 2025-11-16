import allure
import pytest
from playwright.sync_api import expect

from helper import get_test_data
from pages.client.momo import Momo

MOMO_DATA = get_test_data(test_platform="client", file_name="momo")
HOME_PAGE_DATA = MOMO_DATA["home_page"]
SEARCH_PRODUCT_DATA = MOMO_DATA["search_product"]
FAIL_HOME_PAGE_DATA = MOMO_DATA["fail_home_page"]


@pytest.fixture(scope="class", autouse=True)
def init_work(request, create_page):
    request.cls.momo = Momo(create_page)


class TestMomo:
    """測試Momo頁面"""

    momo: Momo

    @pytest.mark.tag(name="ClientTest00001", order=1)
    @pytest.mark.tag(name="ClientTest00002", order=1)
    @pytest.mark.parametrize(
        "data", HOME_PAGE_DATA, ids=lambda data: data["test_info"]["title"]
    )
    def test_momo_home_page(self, data):
        """momo首頁測試"""

        allure.dynamic.title(data["test_info"]["title"])
        allure.dynamic.description(data["test_info"]["desc"])

        self.momo.go_to_home_page()
        self.momo.close_pop_up()
        self.momo.page.cp_screenshot_and_attach(img_name="momo首頁")
        expect(self.momo.page).to_have_title(
            data["test_info"]["verify"]["home_page_title"]
        )

    @pytest.mark.tag(name="ClientTest00002", order=2)
    @pytest.mark.parametrize(
        "data", SEARCH_PRODUCT_DATA, ids=lambda data: data["test_info"]["title"]
    )
    def test_search_product(self, data, sc: callable):
        """測試搜尋指定產品"""

        allure.dynamic.title(data["test_info"]["title"])
        allure.dynamic.description(data["test_info"]["desc"])

        with allure.step(sc("搜尋產品")):
            self.momo.search_product(keyword=data["test_info"]["keyword"])
        with allure.step(sc("點擊第 1 個產品")):
            self.momo.click_product(product_index="1")
        with allure.step(sc("取得產品名稱")):
            product_name = self.momo.get_product_name()
            print(f"產品名稱: {product_name}")
        with allure.step(sc("回首頁")):
            self.momo.go_to_home_page()
            self.momo.close_pop_up()

    @pytest.mark.tag(name="ClientTest00003", order=1)
    @pytest.mark.parametrize(
        "data", FAIL_HOME_PAGE_DATA, ids=lambda data: data["test_info"]["title"]
    )
    def test_fail_momo_home_page(self, data):
        """[FAIL_DEMO]momo首頁測試"""

        allure.dynamic.title(data["test_info"]["title"])
        allure.dynamic.description(data["test_info"]["desc"])

        self.momo.go_to_home_page()
        self.momo.close_pop_up()
        self.momo.page.cp_screenshot_and_attach(img_name="[FAIL_DEMO]momo首頁")
        expect(self.momo.page).to_have_title(
            data["test_info"]["verify"]["home_page_title"]
        )
