import os

DEBUG_MODE = True

ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT_PATH, "test_registry.db")  # 保持這個路徑給 aiosqlite 使用


def initialize_test_manager():
    """
    從 test_registry.db 初始化 TEST_MANAGER。
    服務啟動時，從資料庫讀取所有可用的測試標籤並建立預設狀態。
    """
    manager = {}

    # 將 import 移至函式內部，避免循環匯入
    from sqlalchemy.orm import Session
    from database import SyncSessionLocal
    from models import TestList

    if not os.path.exists(DB_PATH):
        print(f"Warning: Database '{DB_PATH}' not found. TEST_MANAGER will be empty.")
        print("Please run pytest with the collection plugin to generate it.")
        return {}

    db: Session = SyncSessionLocal()
    try:
        # 使用 ORM 查詢所有測試
        all_tests = db.query(TestList).order_by(TestList.test_id).all()
        for test in all_tests:
            manager[test.test_id] = {
                "description": test.description,
                "status": "idle",  # idle, running
                "connections": set(),
                "progress": test.last_run_progress if test.last_run_progress else 0,
                "process": None,
                "last_result": test.last_result or "NOT RUN",
                "last_excuted_time": None,
                "start_time": test.last_run_start_time,
                "end_time": test.last_run_end_time,
                "execution_time": (
                    f"{test.last_run_execution_time:.2f}"
                    if test.last_run_execution_time is not None
                    else None
                ),
            }
    except Exception as e:
        print(
            f"Error reading from database: {e}. The database might be empty or corrupt."
        )
    finally:
        db.close()
    return manager


# 全局測試狀態管理器
TEST_MANAGER = initialize_test_manager()
