import asyncio
import locale
import subprocess

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import helper
import settings


tests_router = APIRouter()


@tests_router.get("/run_tests/")
async def run_tests(test_ids: str):
    """API 來觸發多個 pytest 測試"""

    def sync_run(args):

        return subprocess.run(
            args,
            capture_output=not settings.DEBUG_MODE,  # 捕獲 stdout 和 stderr
            text=True,  # 以文字形式回傳而不是 bytes
            encoding=locale.getpreferredencoding(),  # 取得系統預設編碼
        )

    test_id_list = test_ids.split(",")

    testing_ids = []
    for test_id in test_id_list:
        if test_id in settings.RUNNING_TASKS:
            testing_ids.append(test_id)

    if testing_ids:
        return {"message": f"{','.join(testing_ids)} 測試正在進行中"}

    output = {"exit_code": "", "stdout": "", "stderr": ""}

    try:
        test_args = ["pytest", "-vs"]
        for test_id in test_id_list:
            test_platform, test_info = helper.get_test(test_id)
            if test_info["function_name"] == "test_all":
                test_args += [
                    f"test_cases/{test_platform}/{test_info['file_name']}::{test_info['class_name']}"
                ]
            else:
                test_args += [
                    f"test_cases/{test_platform}/{test_info['file_name']}::{test_info['class_name']}::{test_info['function_name']}"
                ]

        loop = asyncio.get_running_loop()
        settings.RUNNING_TASKS += test_id_list
        process_result = await loop.run_in_executor(None, sync_run, test_args)

        for test_id in test_id_list:
            settings.RUNNING_TASKS.remove(test_id)

        if not settings.DEBUG_MODE:
            output.update(
                {
                    "stdout": process_result.stdout,
                    "stderr": process_result.stderr,
                }
            )

        output.update(
            {
                "test_info": test_ids,
                "exit_code": process_result.returncode,
            }
        )

    except Exception as e:
        output["error"] = str(e)

    return output


@tests_router.get("/test_status/{test_id}")
async def task_status(test_id: str):
    """查詢測試狀態"""
    if test_id in settings.RUNNING_TASKS:
        status = "測試中"
    else:
        status = "非測試中"

    return {"test_id": test_id, "status": status}


@tests_router.websocket("/ws/run_tests")
async def ws_run_tests(websocket: WebSocket):
    await websocket.accept()
    try:
        # 前端送 test_ids，例如 "ClientTest00001,ClientTest00002"
        test_ids = await websocket.receive_text()
        test_id_list = test_ids.split(",")

        # 檢查是否有測試正在進行
        testing_ids = [tid for tid in test_id_list if tid in settings.RUNNING_TASKS]
        if testing_ids:
            await websocket.send_text(f"{','.join(testing_ids)} 測試正在進行中")
            return

        # 準備 pytest 參數
        test_args = ["pytest", "-vs"]
        for test_id in test_id_list:
            test_platform, test_info = helper.get_test(test_id)
            if test_info["function_name"] == "test_all":
                test_args += [
                    f"test_cases/{test_platform}/{test_info['file_name']}::{test_info['class_name']}"
                ]
            else:
                test_args += [
                    f"test_cases/{test_platform}/{test_info['file_name']}::{test_info['class_name']}::{test_info['function_name']}"
                ]

        # 標記正在執行
        settings.RUNNING_TASKS += test_id_list
        # 開 subprocess 執行 pytest
        process = await asyncio.create_subprocess_exec(
            *test_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 即時讀取 stdout
        async for line in process.stdout:
            await websocket.send_text(
                line.decode(locale.getpreferredencoding(), errors="ignore").rstrip()
            )

        # 即時讀取 stderr
        async for line in process.stderr:
            await websocket.send_text(
                "[stderr] "
                + line.decode(locale.getpreferredencoding(), errors="ignore").rstrip()
            )

        # 等待結束
        exit_code = await process.wait()
        await websocket.send_text(f"=== 測試完成，exit_code={exit_code} ===")

    except WebSocketDisconnect:
        print("客戶端中斷連線")
    except Exception as e:
        await websocket.send_text(f"Error: {str(e)}")
    finally:
        for test_id in test_id_list:
            if test_id in settings.RUNNING_TASKS:
                settings.RUNNING_TASKS.remove(test_id)
        await websocket.close()
