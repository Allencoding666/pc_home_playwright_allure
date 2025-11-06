import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers.base import base_router
from routers.tests import tests_router
from settings import ROOT_PATH

app = FastAPI(
    title="Playwright 測試",
    description="使用 FastAPI 進行 Playwright 測試",
    version="0.1.0",
)

app.include_router(router=base_router)
app.include_router(router=tests_router, prefix="/tests", tags=["Tests"])

# 將 'reports' 資料夾掛載為靜態資源目錄，可透過 /reports URL 訪問
reports_path = os.path.join(ROOT_PATH, "reports")
os.makedirs(reports_path, exist_ok=True)  # 確保目錄存在
app.mount("/reports", StaticFiles(directory=reports_path), name="reports")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
