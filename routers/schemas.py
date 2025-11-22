from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# ====================================
# | Receive |
# ====================================


class BaseReceive(BaseModel):
    test_id: str


# ====================================
# | Response |
# ====================================


class BaseResp(BaseModel):
    """WebSocket 發送的格式"""

    type: Literal["test_status", "test_log", "message", "test_result", "progress"]
    test_id: Optional[str] = Field(default=None, description="測試或任務的唯一 ID")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        description="訊息建立時間",
    )
    data: Optional[dict[str, Any]] = Field(
        default={}, description="根據不同 type 攜帶的詳細資料"
    )


class TestStatusResp(BaseResp):
    type: Literal["test_status"] = "test_status"

    class TestInfoModel(BaseModel):
        description: str
        status: Literal["idle", "running", "stopped"]
        progress: int
        start_time: Optional[str]
        end_time: Optional[str]
        execution_time: Optional[str]
        last_result: Optional[
            Literal["PASS", "FAIL", "ERROR", "STOPPED", "NO TEST LOG", "NOT RUN"]
        ]

    data: dict[str, TestInfoModel]


class TestLogResp(BaseResp):
    type: Literal["test_log"] = "test_log"
    test_id: str

    class DataModel(BaseModel):
        log: str

    data: DataModel


class TestMessageResp(BaseResp):
    type: Literal["message"] = "message"
    test_id: str = ""

    class DataModel(BaseModel):
        level: Literal["info", "warning", "success", "error"] = "info"
        message: str

    data: DataModel


class TestProgressResp(BaseResp):
    type: Literal["progress"] = "progress"
    test_id: str = ""

    class DataModel(BaseModel):
        percentage: int

    data: DataModel


class ReportInfo(BaseModel):
    """單一報告的資訊"""

    file_name: str = Field(description="報告檔案名稱")
    url: str = Field(description="可直接訪問的報告 URL")
    created_at: str = Field(description="報告生成時間 (YYYY-MM-DD HH:MM:SS)")


class ReportListResp(BaseModel):
    """測試報告列表的回應模型"""

    reports: list[ReportInfo]


class TestResultResp(BaseModel):
    type: Literal["test_result"] = "test_result"
    test_id: str

    class DataModel(BaseModel):
        test_result: Literal["PASS", "FAIL"]

    data: DataModel


# ====================================
# | WebSocket |
# ====================================


class WSExecuteCommand(BaseModel):
    """WebSocket 接收測試任務的格式"""

    command: str
    test_id: str


class WSMessageData(BaseModel):
    level: Literal["info", "warning", "success", "error"]
    content: str


class WSMessage(BaseResp):
    type: Literal["message"]
    data: WSMessageData
