import allure
import pytest

from helper import get_test_data
from pages.client.home_page.android_momo import Momo

MOMO_DATA = get_test_data(file_path="test_data\client\home_page\momo.yaml")
HOME_PAGE_DATA = MOMO_DATA["home_page"]
SEARCH_PRODUCT_DATA = MOMO_DATA["search_product"]
FAIL_HOME_PAGE_DATA = MOMO_DATA["fail_home_page"]


@pytest.fixture(scope="class", autouse=True)
def init_work(request, create_android_driver):
    request.cls.momo = Momo(create_android_driver)


class TestMomo:
    """測試Momo頁面"""

    momo: Momo

    @pytest.mark.tag(name="AndroidClientTest00004", order=1)
    @pytest.mark.parametrize(
        "data", HOME_PAGE_DATA, ids=lambda data: data["test_info"]["title"]
    )
    def test_android_momo_home_page(self, data):
        """momo首頁測試"""

        allure.dynamic.title(data["test_info"]["title"])
        allure.dynamic.description(data["test_info"]["desc"])

        self.momo.go_to_home_page()
        self.momo.driver.screenshot_and_attach(img_name="Android 模擬器主畫面")
