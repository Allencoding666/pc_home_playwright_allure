import os
import re
import yaml

DEBUG_MODE = True

ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
LOGS_PATH = os.path.join(ROOT_PATH, "logs")


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
    從 tag_registry.yaml 初始化 TEST_MANAGER。
    服務啟動時，掃描所有可用的測試標籤並建立預設狀態。
    """
    manager = {}
    os.makedirs(LOGS_PATH, exist_ok=True)  # 確保 logs 資料夾存在
    tag_registry_path = os.path.join(ROOT_PATH, "tag_registry.yaml")
    try:
        with open(tag_registry_path, "r", encoding="utf-8") as f:
            tags = yaml.safe_load(f)
            if not tags:
                return {}
            for tag_name, tag_info in tags.items():
                last_run_info = _get_last_run_info_from_log(tag_name)
                manager[tag_name] = {
                    # 增加對舊格式的相容性：如果 tag_info 是 dict，則 get description；如果是 list，則 description 為空字串
                    "description": (
                        tag_info.get("description", "")
                        if isinstance(tag_info, dict)
                        else ""
                    ),
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
    except FileNotFoundError:
        print(f"Warning: {tag_registry_path} not found. TEST_MANAGER will be empty.")
    return manager


# 全局測試狀態管理器
TEST_MANAGER = initialize_test_manager()
