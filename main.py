import uvicorn
from fastapi import FastAPI

from routers.base import base_router
from routers.tests import tests_router


app = FastAPI(
    title="Playwright 測試",
    description="使用 FastAPI 進行 Playwright 測試",
    version="0.1.0",
)

app.include_router(router=base_router)
app.include_router(router=tests_router, prefix="/tests", tags=["Tests"])


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
