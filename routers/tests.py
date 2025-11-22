import asyncio
from datetime import datetime
import os
import io
import re
import subprocess
from typing import AsyncGenerator, List, Set
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    Depends,
)
from pydantic import ValidationError
from starlette.websockets import WebSocketState

import settings
from helper import get_allure_results_dir, log_test_run
from database import AsyncSessionLocal
from models import TestRun, TestPath
from routers.schemas import (
    BaseReceive,
    ReportInfo,
    ReportListResp,
    TestResultResp,
    TestStatusResp,
    TestLogResp,
    TestMessageResp,
    TestProgressResp,
    WSExecuteCommand,
)

tests_router = APIRouter()


# Dependency to get an async database session
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@tests_router.get("/api/status", response_model=TestStatusResp)
async def get_all_test_statuses():
    """獲取所有測試資訊(任務狀態、上次測試結果...)"""
    test_status = TestStatusResp(data=settings.TEST_MANAGER)
    return test_status.model_dump(mode="json")


@tests_router.post("/api/stop_tests", response_model=TestMessageResp)
async def stop_tests(data: BaseReceive):
    """
    根據 test_id 停止正在執行的測試。
    """
    test_id = data.test_id
    test_info = settings.TEST_MANAGER.get(test_id)

    if not test_info or not test_info.get("process"):
        stop_tests_resp = TestMessageResp(
            test_id=test_id,
            data=TestMessageResp.DataModel(
                level="error",
                message=f'測試任務 "{test_id}" 不存在或非測試中，無法停止',
            ),
        )
        return stop_tests_resp.model_dump(mode="json")

    process = test_info["process"]
    if process.returncode is not None:
        # 競爭條件：測試剛結束，但 run_test_task 的 finally 區塊還沒執行。
        # 在此處手動清理狀態，使其與 finally 區塊的行為保持一致。
        test_info["status"] = "idle"
        test_info["process"] = None
        stop_tests_resp = TestMessageResp(
            test_id=test_id,
            data=TestMessageResp.DataModel(
                level="error",
                message=f'測試任務 "{test_id}" 已執行完畢，無法停止',
            ),
        )
        return stop_tests_resp.model_dump(mode="json")

    try:
        process.terminate()
        print(f"已向測試任務 '{test_id}' (PID: {process.pid}) 發送終止請求...")

        # 等待一小段時間，看程序是否自行結束
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
            message = f'測試任務 "{test_id}" 已被成功停止。'
        except asyncio.TimeoutError:
            # 如果超時後仍在運行，則強制終止 (SIGKILL)
            print(f"測試任務 '{test_id}' 未在 5 秒內響應，將強制終止...")
            process.kill()
            await process.wait()  # 等待強制終止完成
            message = f'測試任務 "{test_id}" 因無響應而被強制停止'

        print(message)
        test_info["status"] = "stopped"  # 無論如何，最終狀態都標記為 stopped
        stop_tests_resp = TestMessageResp(
            test_id=test_id,
            data=TestMessageResp.DataModel(
                level="warning",
                message=message,
            ),
        )
        await broadcast(stop_tests_resp)
        return stop_tests_resp.model_dump(mode="json")

    except Exception as e:
        print(f"停止測試 {test_id} 時發生錯誤: {e}")
        stop_tests_resp = TestMessageResp(
            test_id=test_id,
            data=TestMessageResp.DataModel(
                level="error",
                message=f"停止測試 {test_id} 時發生錯誤: {e}",
            ),
        )
        return stop_tests_resp.model_dump(mode="json")


@tests_router.get("/api/log/", response_model=TestLogResp)
async def get_test_log(
    test_id: str = None,
    run_id: int = None,
    db: AsyncSession = Depends(get_async_db),
):
    """
    獲取指定測試的日誌。
    - 如果提供 run_id，則獲取該次執行的日誌。
    - 如果未提供 run_id，則獲取最新一次執行的日誌。
    """
    log = None
    if run_id:
        stmt = select(TestRun.log_content, TestRun.test_id).where(TestRun.id == run_id)
        result = await db.execute(stmt)
        run = result.first()
        if run:
            log, test_id = run
    elif test_id:
        stmt = (
            select(TestRun.log_content)
            .where(TestRun.test_id == test_id)
            .order_by(desc(TestRun.id))
            .limit(1)
        )
        result = await db.execute(stmt)
        log = result.scalar_one_or_none()
    else:
        raise ValueError("未提供 test_id 或 run_id")

    if log is None:
        return TestLogResp(
            test_id=test_id,
            data=TestLogResp.DataModel(log="暫無日誌可供查看，請執行測試後再重新查看"),
        )

    return TestLogResp(test_id=test_id, data=TestLogResp.DataModel(log=log))


@tests_router.get("/api/reports/{test_id}", response_model=ReportListResp)
async def get_test_report(test_id: str):
    """
    獲取指定測試 ID 的所有歷史報告列表。
    回傳的 URL 是可以直接在瀏覽器中打開的靜態路徑。
    """
    safe_test_id = test_id.replace(",", "_")
    report_dir = os.path.join(settings.ROOT_PATH, "reports", safe_test_id)

    if not os.path.isdir(report_dir):
        return ReportListResp(reports=[])

    report_infos = []
    # 正則表達式，用於從檔名中解析時間戳
    # 檔名格式: {safe_test_id}_YYYYMMDD_HHMMSS.html
    pattern = re.compile(rf"^{re.escape(safe_test_id)}_(\d{{8}}_\d{{6}})\.html$")

    for filename in os.listdir(report_dir):
        match = pattern.match(filename)
        if match:
            try:
                timestamp_str = match.group(1)
                # 將 'YYYYMMDD_HHMMSS' 格式的時間戳轉換為更易讀的格式
                dt_object = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")

                report_infos.append(
                    ReportInfo(
                        file_name=filename,
                        url=f"/reports/{safe_test_id}/{filename}",
                        created_at=formatted_time,
                    )
                )
            except (ValueError, IndexError):
                continue  # 如果檔名格式不符，則跳過

    # 根據生成時間降序排序，最新的報告在最前面
    report_infos.sort(key=lambda r: r.created_at, reverse=True)

    return ReportListResp(reports=report_infos)


async def broadcast(resp: TestMessageResp | TestResultResp | TestProgressResp):
    """向特定測試的所有監聽者回傳訊息"""
    test_id = resp.model_dump().get("test_id")

    if test_id in settings.TEST_MANAGER:
        connections: Set[WebSocket] = settings.TEST_MANAGER[test_id]["connections"]
        disconnected = set()

        for connection in connections.copy():
            try:
                # 檢查連線狀態
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_json(resp.model_dump(mode="json"))
                else:
                    disconnected.add(connection)
            except (RuntimeError, Exception) as e:
                print(f"發送訊息時發生錯誤 (test_id: {test_id}): {e}")
                disconnected.add(connection)

        connections.difference_update(disconnected)


async def run_test_task(test_id: str, test_args: List[str]):
    """在背景執行單次測試任務，並透過 WebSocket 回報進度"""
    start_time = datetime.now()
    final_result = "ERROR"  # 預設結果為錯誤，除非被成功覆蓋
    try:
        # 更新測試狀態為 'running'
        test_info = settings.TEST_MANAGER[test_id]
        test_info["status"] = "running"
        test_info["progress"] = 0

        # 準備環境變數，強制 pytest 子程序使用 UTF-8 輸出，解決日誌亂碼問題
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # 開 subprocess 執行 pytest
        process = await asyncio.create_subprocess_exec(
            *test_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # 標記正在執行的 process
        test_info["process"] = process

        start_test_resp = TestMessageResp(
            test_id=test_id,
            data=TestMessageResp.DataModel(
                level="info", message=f"執行測試: {test_id}"
            ),
        )
        await broadcast(start_test_resp)

        # 即時讀取 stdout
        async def stream_output(stream):
            log_buffer = io.StringIO()
            async for raw_line in stream:
                line = raw_line.decode("utf-8", errors="ignore").rstrip()
                log_buffer.write(line + "\n")

                # 檢查是否為進度回報
                progress_match = re.match(r"^PROGRESS:(\d+)$", line)
                if progress_match:
                    percentage = int(progress_match.group(1))
                    test_info["progress"] = percentage
                    progress_resp = TestProgressResp(
                        test_id=test_id,
                        data=TestProgressResp.DataModel(
                            percentage=percentage,
                        ),
                    )
                    await broadcast(progress_resp)
            return log_buffer.getvalue()

        # 同時處理 stdout 和 stderr
        # 使用 asyncio.gather 並行處理 stdout 和 stderr，並收集它們的內容
        stdout_task = asyncio.create_task(stream_output(process.stdout))
        stderr_task = asyncio.create_task(stream_output(process.stderr))

        stdout_content, stderr_content = await asyncio.gather(stdout_task, stderr_task)
        # 將 stdout 和 stderr 的內容合併為最終的日誌
        log_content = stdout_content + stderr_content

        # 等待結束
        exit_code = await process.wait()

        # 檢查測試是否被手動停止。
        # 如果 status 已經不是 'running'，代表 stop_tests API 已被呼叫，
        # 此時應直接跳到 finally 區塊進行清理，不再發送「測試完成」的訊息。
        if settings.TEST_MANAGER[test_id]["status"] == "stopped":
            final_result = "STOPPED"
            return

        # 傳回測試完成訊息
        final_result = "PASS" if exit_code == 0 else "FAIL"

        finish_test_resp = TestMessageResp(
            test_id=test_id,
            data=TestMessageResp.DataModel(
                level="success" if final_result == "PASS" else "error",
                message=f"{test_id} 測試完成，結果為[ {final_result} ]，詳細資訊請查看TestLog",
            ),
        )
        await broadcast(finish_test_resp)

        # 傳回測試結果
        test_result_resp = TestResultResp(
            test_id=test_id,
            data=TestResultResp.DataModel(test_result=final_result),
        )
        await broadcast(test_result_resp)

        # 更新最終狀態
        test_info["last_result"] = final_result

    except Exception as e:
        print(e)
        error_resp = TestMessageResp(
            test_id=test_id,
            data=TestMessageResp.DataModel(
                level="error",
                message=f"Error: 測試 {test_id} 執行期間出現錯誤，詳細資訊請查看TestLog",
            ),
        )
        await broadcast(error_resp)
    finally:
        # 測試結束後，將最終結果寫入日誌並重設狀態
        if test_id in settings.TEST_MANAGER:
            end_time = datetime.now()
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
            execution_duration = end_time - start_time
            execution_time_sec = execution_duration.total_seconds()
            progress = test_info["progress"]

            # 將執行結果寫入資料庫
            log_test_run(
                test_id,
                final_result,
                start_time_str,
                end_time_str,
                execution_time_sec,
                progress,
                log_content,
            )

            # 同步更新記憶體中的 TEST_MANAGER 狀態 (從資料庫讀取會更一致，但為了效能暫時在記憶體中更新)
            test_info = settings.TEST_MANAGER[test_id]
            test_info["last_result"] = final_result
            test_info["start_time"] = start_time_str
            test_info["end_time"] = end_time_str
            test_info["execution_time"] = f"{execution_time_sec:.2f}"

            # 重設運行狀態
            if test_info["status"] != "stopped":
                test_info["status"] = "idle"
            test_info["process"] = None
            test_info[
                "connections"
            ].clear()  # 清除所有監聽此測試的 WebSocket 連線，因為此輪測試已結束


@tests_router.websocket("/ws/test_manager")
async def ws_test_manager(websocket: WebSocket):
    """
    透過 WebSocket 管理測試任務。
    接收 JSON 指令來執行或停止測試。

    接收格式:
    - 執行測試: {"command": "execute_test", "test_id": "TestID1,TestID2"}
    """
    await websocket.accept()
    # 追蹤此 WebSocket 連線正在監聽的所有測試 ID
    monitored_test_ids: Set[str] = set()
    try:
        while True:
            try:
                # 使用 Pydantic 模型進行驗證和解析前端傳送的資料
                data = await websocket.receive_json()
                cmd = WSExecuteCommand.model_validate(data)
            except WebSocketDisconnect:
                print(f"[WS] 在接收訊息時偵測到斷線")
                raise  # 重新拋出，讓外層的 except 處理
            except ValidationError as e:
                # 如果前端重送的資料驗證失敗，向客戶端發送詳細錯誤
                resp = TestMessageResp(
                    test_id=cmd.test_id if cmd.test_id else "",
                    data=TestMessageResp.DataModel(
                        level="error", message=f"Error: 無效的指令格式({e.errors()})"
                    ),
                )
                await websocket.send_json(resp.model_dump(mode="json"))
            except Exception:
                # 處理非 JSON 或其他格式錯誤
                resp = TestMessageResp(
                    test_id="",
                    data=TestMessageResp.DataModel(
                        level="error", message=f"Error: 訊息格式錯誤，必須為 JSON 格式"
                    ),
                )
                await websocket.send_json(resp.model_dump(mode="json"))
                continue

            if cmd.command == "execute_test":
                # 檢查 test_id 是否存在。如果不存在，可能是服務啟動後才新增的測試。
                # 嘗試重新初始化 TEST_MANAGER 來載入新的測試。
                if cmd.test_id not in settings.TEST_MANAGER:
                    print(f"偵測到新的 test_id: {cmd.test_id}，正在重新載入測試清單...")
                    # 這裡只更新新加入的，不動到正在運行的測試狀態
                    new_manager_data = settings.initialize_test_manager()
                    for test_id, data in new_manager_data.items():
                        if test_id not in settings.TEST_MANAGER:
                            settings.TEST_MANAGER[test_id] = data
                    print("測試清單重新載入完成。")

                # 檢查完全相同的測試組合是否正在執行
                if settings.TEST_MANAGER[cmd.test_id]["status"] == "running":
                    # 如果測試已在執行，將此新連線加入監聽列表
                    # 並記錄此連線正在監聽此 test_id
                    monitored_test_ids.add(cmd.test_id)
                    settings.TEST_MANAGER[cmd.test_id]["connections"].add(websocket)
                    resp = TestMessageResp(
                        test_id=cmd.test_id,
                        data=TestMessageResp.DataModel(
                            level="warning",
                            message=f'請求的測試 "{cmd.test_id}" 正在執行中，已將您加入觀察列表。',
                        ),
                    )
                    await websocket.send_json(resp.model_dump(mode="json"))
                    continue

                # 檢查路徑衝突：要執行的測試是否與正在運行的測試共享任何測試案例
                conflicting_tasks = []
                try:
                    async with AsyncSessionLocal() as db:
                        # 1. 獲取目標測試的所有路徑
                        target_paths_stmt = select(TestPath.path).where(
                            TestPath.tag_name == cmd.test_id
                        )
                        target_paths_result = await db.execute(target_paths_stmt)
                        target_paths = {p for (p,) in target_paths_result.all()}

                        if not target_paths:
                            raise ValueError(
                                f"Test ID '{cmd.test_id}' has no paths in the registry."
                            )

                        # 2. 找出所有正在運行的任務 ID
                        running_task_ids = [
                            tid
                            for tid, tinfo in settings.TEST_MANAGER.items()
                            if tinfo["status"] == "running"
                        ]

                        # 3. 查詢這些正在運行的任務中，是否有任何一個的路徑與目標路徑重疊
                        if running_task_ids:
                            conflict_stmt = (
                                select(TestPath.tag_name)
                                .where(TestPath.tag_name.in_(running_task_ids))
                                .where(TestPath.path.in_(target_paths))
                                .distinct()
                            )
                            conflict_result = await db.execute(conflict_stmt)
                            conflicting_tasks = [
                                tid for (tid,) in conflict_result.all()
                            ]
                except Exception as e:
                    print(f"檢查資源衝突時出錯: {type(e).__name__}: {e}")

                if conflicting_tasks:
                    # 將此連線加入所有衝突任務的監聽列表
                    for task_id in conflicting_tasks:
                        if task_id in settings.TEST_MANAGER:
                            settings.TEST_MANAGER[task_id]["connections"].add(websocket)
                            monitored_test_ids.add(task_id)

                    resp = TestMessageResp(
                        test_id=cmd.test_id,
                        data=TestMessageResp.DataModel(
                            level="warning",
                            message=f"無法執行測試，因為其與正在執行的任務 '{', '.join(conflicting_tasks)}' 發生衝突。已將您加入觀察列表。",
                        ),
                    )
                    await websocket.send_json(resp.model_dump(mode="json"))

                    continue

                # 測試未執行，啟動新測試
                monitored_test_ids.add(cmd.test_id)
                # 將此連線加入監聽列表
                settings.TEST_MANAGER[cmd.test_id]["connections"].add(websocket)
                # 準備 pytest 參數
                allure_results_dir = get_allure_results_dir(cmd.test_id)
                test_args: List[str] = [
                    "pytest",
                    f"--run-tag={cmd.test_id}",
                    f"--alluredir={allure_results_dir}",
                ]

                settings.TEST_MANAGER[cmd.test_id][
                    "last_excuted_time"
                ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # 將測試作為背景任務執行，主迴圈可以繼續接收新訊息
                asyncio.create_task(run_test_task(cmd.test_id, test_args))
            else:
                resp = TestMessageResp(
                    test_id=cmd.test_id,
                    data=TestMessageResp.DataModel(
                        level="error", message=f'Error: 不支援的指令: "{cmd.command}"'
                    ),
                )
                await websocket.send_json(resp.model_dump(mode="json"))

    except WebSocketDisconnect:
        print(f"客戶端中斷連線: {websocket.client}")
    except Exception as e:
        print(f"發生未預期的錯誤: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # 連線關閉時，從其監聽的所有測試任務的 connections 集合中移除此連線
        for test_id in monitored_test_ids:
            if test_id in settings.TEST_MANAGER:
                settings.TEST_MANAGER[test_id]["connections"].discard(websocket)
