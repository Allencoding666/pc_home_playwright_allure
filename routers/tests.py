import asyncio
import locale
import subprocess

from fastapi import APIRouter

import helper
import settings

tests_router = APIRouter()


# @tests_router.get("/run_test/")
# async def run_test(test_id: str):
#     """API 來觸發單一 pytest 測試"""
#
#     def sync_run(args):
#
#         return subprocess.run(args)
#
#     if test_id in settings.RUNNING_TASKS:
#         return {"message": "測試正在進行中"}
#
#     output = {"exit_code": "", "stdout": "", "stderr": ""}
#
#     try:
#         test_platform, test_info = helper.get_test(test_id)
#         loop = asyncio.get_running_loop()
#         settings.RUNNING_TASKS.append(test_id)
#         process_result = await loop.run_in_executor(
#             None,
#             sync_run,
#             [
#                 "pytest",
#                 "-vs",
#                 f"test_cases/{test_platform}/{test_info[0]}::{test_info[1]}::{test_info[2]}"
#             ]
#         )
#         settings.RUNNING_TASKS.remove(test_id)
#
#         output.update(
#             {
#                 "test_info": test_id,
#                 "exit_code": process_result.returncode,
#             }
#         )
#
#     except Exception as e:
#         output["error"] = str(e)
#
#     return output


@tests_router.get("/run_tests/")
async def run_tests(test_ids: str):
    """API 來觸發多個 pytest 測試"""

    def sync_run(args):

        return subprocess.run(
            args,
            capture_output=not settings.DEBUG_MODE,  # 捕獲 stdout 和 stderr
            text=True,  # 以文字形式回傳而不是 bytes
            encoding=locale.getpreferredencoding()  # 取得系統預設編碼
        )

    test_id_list = test_ids.split(',')

    for test_id in test_id_list:
        if test_id in settings.RUNNING_TASKS:
            return {"message": "測試正在進行中"}

    output = {"exit_code": "", "stdout": "", "stderr": ""}

    try:
        test_args = [
            "pytest",
            "-vs"
        ]
        for test_id in test_id_list:
            test_platform, test_info = helper.get_test(test_id)
            if test_info[2] == "test_all":
                test_args += [f"test_cases/{test_platform}/{test_info[0]}::{test_info[1]}"]
            else:
                test_args += [f"test_cases/{test_platform}/{test_info[0]}::{test_info[1]}::{test_info[2]}"]

        loop = asyncio.get_running_loop()
        settings.RUNNING_TASKS += test_id_list
        process_result = await loop.run_in_executor(
            None,
            sync_run,
            test_args
        )

        for test_id in test_id_list:
            settings.RUNNING_TASKS.remove(test_id)

        if not settings.DEBUG_MODE:
            output.update({
                "stdout": process_result.stdout,
                "stderr": process_result.stderr,
            })

        output.update({
            "test_info": test_ids,
            "exit_code": process_result.returncode,
        })

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
