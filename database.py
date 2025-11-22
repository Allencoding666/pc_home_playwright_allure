import os
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from settings import ROOT_PATH

# --- Database URL ---
DB_FILENAME = "test_registry.db"
SYNC_DATABASE_URL = f"sqlite:///{os.path.join(ROOT_PATH, DB_FILENAME)}"
ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(ROOT_PATH, DB_FILENAME)}"

# --- Base for Models ---
# 所有 ORM 模型都將繼承這個 Base
Base = declarative_base()

# --- Synchronous Engine & Session ---
# 用於 conftest.py, helper.py, settings.py 等同步操作
sync_engine = create_engine(
    SYNC_DATABASE_URL, connect_args={"check_same_thread": False}
)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# --- Asynchronous Engine & Session ---
# 用於 FastAPI 路由中的非同步操作
async_engine = create_async_engine(ASYNC_DATABASE_URL)
AsyncSessionLocal = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)


def create_db_and_tables():
    """
    根據 models.py 中定義的模型，在資料庫中建立所有表格。
    """
    # 檢查資料庫檔案是否存在，如果不存在，create_all 會自動建立它
    db_path = os.path.join(ROOT_PATH, DB_FILENAME)
    print(f"Ensuring database and tables exist at: {db_path}")
    # 使用同步引擎來建立表格
    Base.metadata.create_all(bind=sync_engine)
    print("Database and tables are ready.")
