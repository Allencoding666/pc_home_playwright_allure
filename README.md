# Py_Play_Fast_All: Playwright 測試自動化平台

本專案使用 FastAPI 作為後端，整合 Playwright 與 Pytest，打造一個可透過 Web 介面來執行、管理與監控自動化測試的平台，且使用 Allure 產生測試報告。

## ✨ 核心特色

- **Web 操作介面**: 透過 FastAPI 提供的 API、websocket，可以遠端觸發測試、監控執行進度與查看歷史結果。
- **動態測試註冊**: 啟動時自動掃描 `pytest` 測試案例，並將帶有 `@pytest.mark.tag` 標記的測試註冊到資料庫中，方便管理。
- **持久化測試資料庫**: 使用 SQLAlchemy 與 SQLite 儲存所有可執行的測試、歷史執行紀錄與結果摘要。
- **目標式測試執行**: 可透過唯一的 `tag` 名稱指定執行單一或一組測試任務。
- **豐富的測試報告**: 每次執行後自動產生獨立的 Allure 單檔案 HTML 報告，視覺化呈現測試結果、步驟與截圖。
- **進度回報機制**: 在測試執行期間，會即時回報進度百分比，方便前端或監控系統追蹤。
- **結構化報告**: 自動根據測試檔案的目錄結構（如 `client/`, `admin/`）和類別/函式的 docstring，在 Allure 報告中生成父套件、套件和子套件，使報告結構清晰。

## 🛠️ 技術棧

- **Web 框架**: FastAPI
- **瀏覽器自動化**: Playwright
- **測試框架**: Pytest
- **資料庫 ORM**: SQLAlchemy
- **資料庫**: SQLite
- **測試報告**: Allure

## 📂 專案結構

```text
py_play_fast_all/
├── reports/                  # 存放產生的 Allure 報告
│   ├── temp_results/         # Allure 原始 JSON 結果的臨時存放區
│   └── [test_id]/            # 每個測試 ID 的最終報告存放目錄
├── routers/                  # FastAPI 的路由模組
│   ├── base.py
│   └── tests.py
├── test_data/                # 測試資料 (YAML 格式)
├── test_pages/               # 測試頁面的腳本
│   ├── admin/
│   └── client/
├── test_cases/               # Pytest 測試頁面的流程，會使用對應測試頁面的腳本
│   ├── admin/
│   └── client/
├── conftest.py               # Pytest 的主要設定檔，包含 hooks 和 fixtures
├── database.py               # 資料庫連線與 Session 設定
├── helper.py                 # 輔助函式，如資料庫操作、自訂 Page 物件等
├── main.py                   # FastAPI 應用程式的進入點
├── models.py                 # SQLAlchemy 的資料庫模型
├── settings.py               # 專案的全域設定與狀態管理器
└── test_registry.db          # SQLite 資料庫檔案
```

## 🚀 快速開始

### 1. 環境準備

- 確認已安裝 Python 3.8+
- 確認已安裝 Allure Commandline 並將其加入系統 PATH。

### 2. 安裝依賴

```bash
# 1. 複製專案
git clone <your-repo-url>

cd py_play_fast_all

# 2. 建立並啟用虛擬環境 (這邊建議使用python的uv套件管理工具)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# On Mac: curl -LsSf https://astral.sh/uv/install.sh | sh

uv venv

venv\Scripts\activate
# On Mac: source venv/bin/activate

# 3. 安裝 Python 套件
uv pip install -r requirements.txt

# 4. 安裝 Playwright 所需的瀏覽器
playwright install
```

### 3. 首次執行：掃描與註冊測試

在啟動 Web 服務之前，需要先讓 Pytest 掃描所有測試案例，以建立資料庫和測試清單。

```bash
# 執行 pytest 收集模式，這會觸發 conftest.py 中的鉤子函式
pytest --collect-only
```

此命令會：

1. 建立 `test_registry.db` 資料庫檔案與相關表格。
2. 掃描 `tests/` 目錄下所有帶有 `@pytest.mark.tag(name="...")` 的測試。
3. 將測試的 ID、描述等資訊寫入資料庫。

### 4. 啟動 Web 服務

```bash
uv run python main.py
```

服務啟動後，您可以訪問 `http://127.0.0.1:8000/docs` 查看所有可用的 API。

## 📝 使用流程

1. **定義測試案例**:
    在 `tests/` 目錄下建立您的 Playwright 測試檔案。務必為每個需要被 Web UI 納管的測試加上 `@pytest.mark.tag` 標記。

    ```python
    # tests/client/test_momo.py
    import allure
    import pytest
    from playwright.sync_api import expect

    from helper import get_test_data
    from pages.client.momo import Momo

    # 匯入測試參數
    MOMO_DATA = get_test_data(test_platform="client", file_name="momo")
    HOME_PAGE_DATA = MOMO_DATA["home_page"]

    # 使用封裝過的 fixture 來初始化 Page 物件
    @pytest.fixture(scope="class", autouse=True)
    def init_work(request, create_page):
        request.cls.momo = Momo(create_page)


    class TestMomo:
        """測試Momo頁面"""

        momo: Momo

        # 將此測試加上 tag ，以此測試為例， name 為"ClientTest00001"，此為該tag的第 1 個測試
        # 可以在多個測試func加上相同的tag，會根據order去執行測試，若無設定，則系統自己決定順序
        @pytest.mark.tag(name="ClientTest00001", order=1)
        # 將測試參數加入至此測試中
        @pytest.mark.parametrize(
            "data", HOME_PAGE_DATA, ids=lambda data: data["test_info"]["title"]
        )
        def test_momo_home_page(self, data):
            """momo首頁測試"""

            # 使用 allure 針對輸出的測試報告，加上需要的資訊
            allure.dynamic.title(data["test_info"]["title"])
            allure.dynamic.description(data["test_info"]["desc"])

            # 使用 pages/client/momo.py 中的 Momo 物件來操作網頁
            self.momo.go_to_home_page()
            self.momo.close_pop_up()
            self.momo.page.cp_screenshot_and_attach(img_name="momo首頁")
            expect(self.momo.page).to_have_title(
                data["test_info"]["verify"]["home_page_title"]
            )
    ```

2. **更新測試清單**:
    每當新增或修改測試標籤後，重新執行 `pytest --collect-only` 來更新資料庫。

3. **觸發測試**:
   - 透過呼叫 FastAPI 的 `/tests/run/{test_id}` API 端點來啟動測試。`test_id` 對應 `@pytest.mark.tag` 中的 `name`。
   - 或是使用自定義的指令`pytest --run-tag=ClientTest00001`，來測試指定的tag

4. **查看進度與結果**:
   - 呼叫 `/tests/status` 可查看所有測試的即時狀態。

5. **檢視報告**:
   - 透過API執行測試，完成後，Allure 報告會被產生在 `reports/<test_id>/` 目錄下。您可以透過 FastAPI 掛載的靜態路徑 `http://127.0.0.1:8000/reports/<test_id>/<report_name>.html` 來直接在瀏覽器中開啟報告。
   - 若不是透過API，是使用指令執行測試，則報告會自動產生在 `local_reports/` 目錄下。

## 待開發項目

- 使用docker部屬
- 前端、後端部屬到線上
- 研究e2e圖形辨識
- 前端測試報告抽屜，加上pass或fail
- 是否將測試報告的檔案連結，放置資料庫內，且有pass跟fail的欄位
