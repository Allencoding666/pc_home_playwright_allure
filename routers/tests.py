import asyncio
import locale
import os
import re
import subprocess
from typing import List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

import helper
import settings


tests_router = APIRouter()


@tests_router.get("/status")
async def get_all_test_statuses():
    """獲取所有正在執行的測試任務狀態"""
    # 改為從新的 BROADCAST_MANAGER 獲取狀態
    running_tests = list(settings.BROADCAST_MANAGER.keys())
    return {"running_tests": running_tests}


@tests_router.get("/log/{test_id}")
async def get_test_log(test_id: str):
    """獲取指定測試的歷史日誌"""
    log_dir = os.path.join(settings.ROOT_PATH, "logs")
    # 替換掉檔名中可能引起問題的字元
    safe_test_id = test_id.replace(",", "_")
    log_file_path = os.path.join(log_dir, f"{safe_test_id}.log")

    if not os.path.exists(log_file_path):
        raise HTTPException(status_code=404, detail=f"找不到測試 '{test_id}' 的日誌。")

    with open(log_file_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    return {"test_id": test_id, "log": log_content}


class StopTestPayload(BaseModel):
    test_ids: str


@tests_router.post("/stop")
async def stop_tests(payload: StopTestPayload):
    """
    根據 test_id 停止正在執行的測試。
    允許多個 test_id，以逗號分隔。
    """
    test_id_list = payload.test_ids.split(",")
    stopped_ids = []
    not_running_ids = []
    error_ids = {}

    # 注意：這裡的 payload.test_ids 應該是執行時的組合 ID，例如 "TestID1,TestID2"
    test_ids_key = payload.test_ids
    if test_ids_key in settings.BROADCAST_MANAGER:
        process = settings.BROADCAST_MANAGER[test_ids_key].get("process")
        if process and process.returncode is None:  # 確保進程仍在執行
            try:
                # 終止子進程
                process.terminate()
                # run_test_task 中的 finally 區塊會處理後續清理
                stopped_ids.append(test_ids_key)
            except Exception as e:
                error_ids[test_ids_key] = str(e)
        else:
            not_running_ids.append(test_ids_key)
    else:
        not_running_ids.extend(test_id_list)

    return {
        "message": "停止測試指令已處理完成。",
        "stopped_ids": stopped_ids,
        "not_running_ids": not_running_ids,
        "errors": error_ids,
    }


async def broadcast(test_ids: str, message: dict):
    """向特定測試的所有監聽者廣播訊息"""
    if test_ids in settings.BROADCAST_MANAGER:
        connections: Set[WebSocket] = settings.BROADCAST_MANAGER[test_ids][
            "connections"
        ]
        for connection in connections:
            await connection.send_json(message)


async def run_test_task(test_ids: str, test_id_list: List[str], test_args: List[str]):
    """在背景執行單次測試任務，並透過 WebSocket 回報進度"""
    log_dir = os.path.join(settings.ROOT_PATH, "logs")
    os.makedirs(log_dir, exist_ok=True)
    try:
        # 開 subprocess 執行 pytest
        process = await asyncio.create_subprocess_exec(
            *test_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 標記正在執行
        for test_id in test_id_list:
            settings.RUNNING_TASKS[test_id] = (
                process  # 保留給舊 stop API 的相容性，但建議棄用
            )
        settings.BROADCAST_MANAGER[test_ids]["process"] = process

        resp = {
            "test_id": test_ids,
            "type": "info",
            "log": f"執行測試: {test_ids}",
        }
        await broadcast(test_ids, resp)

        # 即時讀取 stdout
        async def stream_output(stream, log_file):
            async for raw_line in stream:
                line = raw_line.decode(
                    locale.getpreferredencoding(), errors="ignore"
                ).rstrip()
                log_file.write(line + "\n")
                log_file.flush()

                # 檢查是否為進度回報
                progress_match = re.match(r"^PROGRESS:(\d+)$", line)
                if progress_match:
                    percentage = int(progress_match.group(1))
                    settings.BROADCAST_MANAGER[test_ids]["progress"] = percentage
                    progress_resp = {
                        "test_id": test_ids,
                        "type": "progress",
                        "percentage": percentage,
                    }
                    await broadcast(test_ids, progress_resp)
                else:
                    log_resp = {
                        "test_id": test_ids,
                        "type": "log",
                        "log": line,
                    }
                    await broadcast(test_ids, log_resp)

        # 同時處理 stdout 和 stderr
        safe_test_ids = test_ids.replace(",", "_")
        log_file_path = os.path.join(log_dir, f"{safe_test_ids}.log")
        with open(log_file_path, "w", encoding="utf-8") as log_f:
            await asyncio.gather(
                stream_output(process.stdout, log_f),
                stream_output(process.stderr, log_f),
            )

        # 等待結束
        exit_code = await process.wait()
        end_resp = {
            "test_id": test_ids,
            "type": "info",
            "message": f"{test_ids} 測試結束",
            "log": f"=== {test_ids} 測試結束，exit_code={exit_code} ===",
        }
        await broadcast(test_ids, end_resp)

        # 傳回結果
        test_result = "PASS" if exit_code == 0 else "FAIL"
        resp = {
            "test_id": test_ids,
            "type": "success" if test_result == "PASS" else "error",
            "message": f"{test_ids} 測試完成，結果為[ {test_result} ]，詳細資訊請查看測試即時訊息",
            "log": f"{test_ids} 測試完成，結果為[ {test_result} ]",
        }
        await broadcast(test_ids, resp)

    except Exception as e:
        print(e)
        resp = {
            "test_id": test_ids,
            "type": "error",
            "message": f"Error: 測試 {test_ids} 執行期間出現錯誤，詳細資訊請查看測試即時訊息",
            "log": f"Error: 測試 {test_ids} 執行期間出現錯誤: {str(e)}",
        }
        await broadcast(test_ids, resp)
    finally:
        # 關閉所有監聽此任務的 WebSocket 連線
        if test_ids in settings.BROADCAST_MANAGER:
            connections = list(
                settings.BROADCAST_MANAGER[test_ids]["connections"]
            )  # 複製一份以安全遍歷
            for connection in connections:
                if connection.client_state != 3:
                    await connection.close()
            settings.BROADCAST_MANAGER.pop(test_ids, None)

        # 清理舊的狀態標記
        for test_id in test_id_list:
            if test_id in settings.RUNNING_TASKS:
                settings.RUNNING_TASKS.pop(test_id, None)


@tests_router.websocket("/ws/test_manager")
async def ws_test_manager(websocket: WebSocket):
    """
    透過 WebSocket 管理測試任務。
    接收 JSON 指令來執行或停止測試。

    接收格式:
    - 執行測試: {"command": "execute_test", "test_id": "TestID1,TestID2"}
    """
    await websocket.accept()
    test_ids_to_monitor = None
    try:
        data = await websocket.receive_json()
        command = data.get("command")
        test_ids = data.get("test_id")

        if command == "execute_test" and test_ids:
            test_ids_to_monitor = test_ids
            test_id_list = test_ids.split(",")

            # 檢查是否有測試正在進行 (檢查 BROADCAST_MANAGER)
            if test_ids in settings.BROADCAST_MANAGER:
                # 測試已在執行，將此新連線加入廣播列表
                settings.BROADCAST_MANAGER[test_ids]["connections"].add(websocket)
                current_progress = settings.BROADCAST_MANAGER[test_ids]["progress"]
                resp = {
                    "test_id": test_ids,
                    "type": "warning",
                    "message": f"{test_ids} 測試正在進行中，已為您連接至即時進度。",
                    "progress": current_progress,
                }
                await websocket.send_json(resp)
            else:
                # 測試未執行，啟動新測試
                settings.BROADCAST_MANAGER[test_ids] = {
                    "connections": {websocket},
                    "progress": 0,
                    "process": None,
                }

                # 準備 pytest 參數
                test_args: List[str] = [
                    "pytest",
                    "-vs",
                ]  # 加上 -vs 可以在日誌中看到詳細輸出
                test_args.extend(helper.build_pytest_test_paths(test_id_list))

                # 將測試作為背景任務執行
                asyncio.create_task(run_test_task(test_ids, test_id_list, test_args))

            # 讓連線保持開啟，以接收廣播
            while True:
                await websocket.receive_text()  # 等待客戶端斷開

        else:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "無效的指令格式，需要 'command':'execute_test' 和 'test_id'。",
                }
            )

    except WebSocketDisconnect:
        print(f"客戶端中斷連線: {websocket.client}")
    finally:
        # 從廣播列表中移除此連線
        if test_ids_to_monitor and test_ids_to_monitor in settings.BROADCAST_MANAGER:
            # 使用 discard 而不是 remove，這樣即使 websocket 不在集合中也不會引發錯誤
            settings.BROADCAST_MANAGER[test_ids_to_monitor]["connections"].discard(
                websocket
            )
            # 如果這是最後一個連線，可以考慮是否要清理 BROADCAST_MANAGER，但目前邏輯是等測試任務結束才清理

        # 確保連線關閉
        if websocket.client_state != 3:
            await websocket.close()
