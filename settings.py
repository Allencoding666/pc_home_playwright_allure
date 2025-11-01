import os


ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
LOGS_PATH = os.path.join(ROOT_PATH, "logs")
RUNNING_TASKS = {}

# 用於管理 WebSocket 廣播和進度
# 結構:
# {
#     "TestID1,TestID2": {"connections": {ws1, ws2}, "progress": 25, "process": process_obj}
# }
BROADCAST_MANAGER = {}
DEBUG_MODE = True
