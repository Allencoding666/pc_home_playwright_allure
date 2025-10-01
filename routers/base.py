from fastapi import APIRouter

base_router = APIRouter()


@base_router.get("/")
def start_test():
    """初始頁面"""
    return {"status": "ok", "message": "Playwright 測試服務運行中"}
