import asyncio
import json
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
        if test_id in settings.RUNNING_TASKS.keys():
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
        process_result = await loop.run_in_executor(None, sync_run, test_args)
        settings.RUNNING_TASKS[test_id_list] = process_result

        for test_id in test_id_list:
            settings.RUNNING_TASKS.pop(test_id, None)

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
    if test_id in settings.RUNNING_TASKS.keys():
        status = "測試中"
    else:
        status = "非測試中"

    return {"test_id": test_id, "status": status}


@tests_router.websocket("/ws/run_tests")
async def ws_run_tests(websocket: WebSocket):
    await websocket.accept()
    tasks_started_by_this_ws = []
    try:
        # 前端送 test_ids，例如 "ClientTest00001,ClientTest00002"
        test_ids = await websocket.receive_text()
        test_id_list = test_ids.split(",")

        # 檢查是否有測試正在進行
        testing_ids = [
            tid for tid in test_id_list if tid in settings.RUNNING_TASKS.keys()
        ]
        if testing_ids:
            resp = {
                "type": "warning",
                "message": f"{','.join(testing_ids)} 測試正在進行中，無法重複執行",
            }
            await websocket.send_json(resp)
            return

        # 準備 pytest 參數
        test_args = ["pytest"]
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

        # 開 subprocess 執行 pytest
        process = await asyncio.create_subprocess_exec(
            *test_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 標記正在執行
        settings.RUNNING_TASKS[test_id_list] = process
        tasks_started_by_this_ws = test_id_list  # 記錄是此連線啟動了這些測試
        resp = {
            "type": "info",
            "message": f"執行測試: {','.join(test_id_list)}",
        }
        await websocket.send_json(resp)

        # 即時讀取 stdout
        async def stream_output(stream, log_type):
            async for line in stream:
                resp = {
                    "type": log_type,
                    "message": line.decode(
                        locale.getpreferredencoding(), errors="ignore"
                    ).rstrip(),
                }
                await websocket.send_json(resp)

        # 同時處理 stdout 和 stderr
        await asyncio.gather(
            stream_output(process.stdout, "log"),
            stream_output(process.stderr, "log"),  # stderr 也視為 log
        )

        # 等待結束
        exit_code = await process.wait()
        await websocket.send_text(f"=== 測試完成，exit_code={exit_code} ===")

        # 傳回結果
        status = "PASS" if exit_code == 0 else "FAIL"
        resp = {
            "type": "result",
            "exit_code": exit_code,
            "status": status,
            "message": f"{','.join(test_id_list)} 測試完成，結果為[ {status} ]，詳細log請查看日誌",
        }
        # 傳送 JSON 字串給前端
        await websocket.send_json(resp)

    except WebSocketDisconnect:
        print("客戶端中斷連線")
    except Exception as e:
        resp = {
            "type": "error",
            "message": f"測試 {','.join(test_id_list)} 出現錯誤，請點擊 LiveMessage 查看即時訊息，Error: {str(e)}",
        }
        await websocket.send_json(resp)
    finally:
        # 只清理由這個 WebSocket 連線啟動的任務
        for test_id in tasks_started_by_this_ws:
            if test_id in settings.RUNNING_TASKS.keys():
                settings.RUNNING_TASKS.pop(test_id, None)
        await websocket.close()


@tests_router.websocket("/ws/run_tests/stop_test")
async def ws_stop_test(websocket: WebSocket):
    await websocket.accept()
    try:
        # 前端送 test_ids，例如 "ClientTest00001,ClientTest00002"
        test_ids = await websocket.receive_text()
        test_id_list = test_ids.split(",")

        # 檢查是否有測試正在進行
        testing_ids = [
            tid for tid in test_id_list if tid in settings.RUNNING_TASKS.keys()
        ]
        if not testing_ids:
            resp = {
                "type": "warning",
                "message": f"{','.join(testing_ids)} 測試並未在進行中，無法停止該測試",
            }
            await websocket.send_json(resp)
            return

        for test_id in testing_ids:
            process = settings.RUNNING_TASKS.get(test_id)
            if process:
                process.terminate()  # 終止測試進程
                await websocket.send_json(
                    {"type": "info", "message": f"已停止測試 {test_id}"}
                )
            settings.RUNNING_TASKS.pop(test_id, None)

    except WebSocketDisconnect:
        print("客戶端中斷連線")
    except Exception as e:
        resp = {
            "type": "error",
            "message": f"Error: {str(e)}",
        }
        await websocket.send_json(resp)
    finally:
        await websocket.close()
