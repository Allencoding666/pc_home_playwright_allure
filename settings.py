import os
import re
import sqlite3

DEBUG_MODE = True

ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
LOGS_PATH = os.path.join(ROOT_PATH, "logs")
DB_PATH = os.path.join(ROOT_PATH, "test_registry.db")


def _get_last_run_info_from_log(test_id: str) -> dict:
    """從日誌檔案中讀取並解析上一次的測試結果與時間資訊。"""
    default_info = {
        "last_result": "NO TEST LOG",
        "start_time": None,
        "end_time": None,
        "execution_time": None,
    }
    safe_test_id = test_id.replace(",", "_")
    log_file_path = os.path.join(LOGS_PATH, f"{safe_test_id}.log")

    if not os.path.exists(log_file_path):
        return default_info

    try:
        info = default_info.copy()
        info["last_result"] = "ERROR"  # 如果找到檔案但沒內容，預設為 ERROR

        with open(log_file_path, "r", encoding="utf-8") as f:
            # 從檔案末尾反向讀取，尋找相關資訊
            for line in reversed(list(f)):
                if info.get("last_result") in ["NO TEST LOG", "ERROR"]:
                    match = re.match(
                        r"^\s*test_result:\s*(PASS|FAIL|STOPPED|ERROR)\s*$", line
                    )
                    if match:
                        info["last_result"] = match.group(1)

                if info.get("start_time") is None:
                    match = re.match(r"^\s*start_time:\s*(.*)\s*$", line)
                    if match:
                        info["start_time"] = match.group(1)

                if info.get("end_time") is None:
                    match = re.match(r"^\s*end_time:\s*(.*)\s*$", line)
                    if match:
                        info["end_time"] = match.group(1)

                if info.get("execution_time") is None:
                    match = re.match(r"^\s*execution_time:\s*(.*)\s*$", line)
                    if match:
                        info["execution_time"] = match.group(1).strip()

                # 如果所有資訊都找到了，就不用再讀了
                if all(v is not None for k, v in info.items() if k != "last_result"):
                    break
        return info
    except Exception as e:
        print(f"Warning: Could not read or parse log file {log_file_path}: {e}")
        return {**default_info, "last_result": "ERROR"}


def initialize_test_manager():
    """
    從 test_registry.db 初始化 TEST_MANAGER。
    服務啟動時，從資料庫讀取所有可用的測試標籤並建立預設狀態。
    """
    manager = {}
    os.makedirs(LOGS_PATH, exist_ok=True)  # 確保 logs 資料夾存在

    if not os.path.exists(DB_PATH):
        print(f"Warning: Database '{DB_PATH}' not found. TEST_MANAGER will be empty.")
        print("Please run pytest with the collection plugin to generate it.")
        return {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name, description FROM tags ORDER BY name")
        tags = cursor.fetchall()
        for tag in tags:
            last_run_info = _get_last_run_info_from_log(tag["name"])
            manager[tag["name"]] = {
                "description": tag["description"],
                "status": "idle",  # idle, running
                "connections": set(),
                "progress": 0,
                "process": None,
                "last_result": last_run_info["last_result"],
                "last_excuted_time": None,
                "start_time": last_run_info["start_time"],
                "end_time": last_run_info["end_time"],
                "execution_time": last_run_info["execution_time"],
            }
    except sqlite3.OperationalError as e:
        print(
            f"Error reading from database: {e}. The database might be empty or corrupt."
        )
    finally:
        conn.close()
    return manager


# 全局測試狀態管理器
TEST_MANAGER = initialize_test_manager()
