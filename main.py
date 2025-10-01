import io
import sys

import uvicorn
from fastapi import FastAPI, Request


from routers.base import base_router
from routers.tests import tests_router


app = FastAPI(
    title="Playwright 測試",
    description="使用 FastAPI 進行 Playwright 測試",
    version="0.1.0",
)

#
# class StreamInterceptor(io.StringIO):
#     def __init__(self, original_stream):
#         super().__init__()
#         self.original_stream = original_stream
#         self.content = ""
#
#     def write(self, s):
#         self.original_stream.write(s)  # 繼續輸出到 terminal
#         self.content += s  # 同時儲存輸出內容
#
#     def flush(self):
#         self.original_stream.flush()
#
#
# @app.middleware("http")
# async def capture_output(request: Request, call_next):
#     """Middleware 攔截 stdout/stderr 並存入 request.state"""
#     stdout_interceptor = StreamInterceptor(sys.stdout)
#     stderr_interceptor = StreamInterceptor(sys.stderr)
#
#     # 替換標準輸出
#     sys.stdout = stdout_interceptor
#     sys.stderr = stderr_interceptor
#     print(1234)
#     print(request)
#
#     response = await call_next(request)  # 繼續處理請求
#     print(456)
#     # 將攔截到的 stdout 和 stderr 存入 request.state
#     request.state.stdout = stdout_interceptor.content
#     request.state.stderr = stderr_interceptor.content
#
#     # 恢復原本的 stdout 和 stderr
#     sys.stdout = stdout_interceptor.original_stream
#     sys.stderr = stderr_interceptor.original_stream
#
#     print(f"{sys.stdout.}")
#     print(f"{sys.stderr=}")
#
#     return response


app.include_router(router=base_router)
app.include_router(router=tests_router, prefix="/tests", tags=["Tests"])


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
