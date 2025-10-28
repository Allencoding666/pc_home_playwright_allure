import asyncio
import locale
import subprocess
from typing import List

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
        test_args: List[str] = ["pytest", "-vs"]
        test_args.extend(helper.build_pytest_test_paths(test_id_list))

        loop = asyncio.get_running_loop()
        process_result = await loop.run_in_executor(None, sync_run, test_args)
        for test_id in test_id_list:
            settings.RUNNING_TASKS[test_id] = process_result

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


async def run_test_task(
    websocket: WebSocket, test_ids: str, test_id_list: List[str], test_args: List[str]
):
    """在背景執行單次測試任務，並透過 WebSocket 回報進度"""
    try:
        # 開 subprocess 執行 pytest
        process = await asyncio.create_subprocess_exec(
            *test_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 標記正在執行
        for test_id in test_id_list:
            settings.RUNNING_TASKS[test_id] = process

        resp = {
            "test_id": test_ids,
            "type": "info",
            "log": f"執行測試: {test_ids}",
        }
        await websocket.send_json(resp)

        # 即時讀取 stdout
        async def stream_output(test_ids, stream, log_type):
            # 確保 websocket 連線仍然開啟
            if websocket.client_state == 3:  # DISCONNECTED
                return
            async for line in stream:
                try:
                    resp = {
                        "test_id": test_ids,
                        "type": log_type,
                        "log": line.decode(
                            locale.getpreferredencoding(), errors="ignore"
                        ).rstrip(),
                    }
                    await websocket.send_json(resp)
                except WebSocketDisconnect:
                    print("串流輸出時連線中斷，停止發送。")
                    break

        # 同時處理 stdout 和 stderr
        await asyncio.gather(
            stream_output(test_ids, process.stdout, "log"),
            stream_output(test_ids, process.stderr, "log"),  # stderr 也視為 log
        )

        # 等待結束
        exit_code = await process.wait()
        resp = {
            "test_id": test_ids,
            "type": "info",
            "message": f"{test_ids} 測試結束",
            "log": f"=== {test_ids} 測試結束，exit_code={exit_code} ===",
        }
        await websocket.send_json(resp)

        # 傳回結果
        test_result = "PASS" if exit_code == 0 else "FAIL"
        resp = {
            "test_id": test_ids,
            "type": "success" if test_result == "PASS" else "error",
            "message": f"{test_ids} 測試完成，結果為[ {test_result} ]，詳細資訊請查看測試即時訊息",
            "log": f"{test_ids} 測試完成，結果為[ {test_result} ]",
        }
        # 傳送 JSON 字串給前端
        await websocket.send_json(resp)

    except Exception as e:
        resp = {
            "test_id": test_ids,
            "type": "error",
            "message": f"Error: 測試 {test_ids} 執行期間出現錯誤，詳細資訊請查看測試即時訊息",
            "log": f"Error: 測試 {test_ids} 執行期間出現錯誤: {str(e)}",
        }
        await websocket.send_json(resp)
    finally:
        # 只清理由這個 WebSocket 連線啟動的任務
        for test_id in test_id_list:
            if test_id in settings.RUNNING_TASKS:
                settings.RUNNING_TASKS.pop(test_id, None)


@tests_router.websocket("/ws/run_tests")
async def ws_run_tests(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # 每次請求重置這些變數，確保獨立性
            test_id_list: List[str] = []
            # 前端送 test_ids，例如 "ClientTest00001,ClientTest00002"
            test_ids = await websocket.receive_text()
            test_id_list = test_ids.split(",")

            # 檢查是否有測試正在進行
            testing_ids = [
                tid for tid in test_id_list if tid in settings.RUNNING_TASKS.keys()
            ]
            if testing_ids:
                resp = {
                    "test_id": test_ids,
                    "type": "warning",
                    "message": f"{','.join(testing_ids)} 測試正在進行中，無法重複執行，終止本次測試請求",
                }
                await websocket.send_json(resp)
                continue  # 繼續等待下一個指令

            # 準備 pytest 參數
            test_args: List[str] = ["pytest"]
            test_args.extend(helper.build_pytest_test_paths(test_id_list))

            # 將測試作為背景任務執行，主迴圈可以繼續接收新訊息
            asyncio.create_task(
                run_test_task(websocket, test_ids, test_id_list, test_args)
            )

    except WebSocketDisconnect:
        print("客戶端中斷連線，關閉 WebSocket。")
    finally:
        # 確保連線關閉
        if websocket.client_state != 3:  # WebSocketState.DISCONNECTED
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
                "test_id": test_ids,
                "type": "warning",
                "log": f"{','.join(testing_ids)} 測試並未在進行中，無法停止該測試",
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
            "test_id": test_ids,
            "type": "error",
            "message": f"Error: 停止測試 {test_ids} 時出現錯誤，詳細資訊請查看測試即時訊息",
            "log": f"Error: 停止測試 {test_ids} 時出現錯誤: {str(e)}",
        }
        await websocket.send_json(resp)
    finally:
        await websocket.close()
