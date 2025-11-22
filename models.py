from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from database import Base


class TestList(Base):
    __tablename__ = "test_list"

    test_id = Column(String, primary_key=True, index=True)
    description = Column(Text)
    last_result = Column(String)
    last_run_start_time = Column(String)
    last_run_end_time = Column(String)
    last_run_execution_time = Column(Float)
    last_run_progress = Column(Integer)

    # 建立與 TestPath 和 TestRun 的關聯
    paths = relationship(
        "TestPath", back_populates="test", cascade="all, delete-orphan"
    )
    runs = relationship("TestRun", back_populates="test", cascade="all, delete-orphan")


class TestPath(Base):
    __tablename__ = "test_paths"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_name = Column(String, ForeignKey("test_list.test_id"))
    path = Column(String)

    test = relationship("TestList", back_populates="paths")


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(String, ForeignKey("test_list.test_id"), index=True)
    result = Column(String)
    start_time = Column(String)
    end_time = Column(String)
    execution_time = Column(Float)
    progress = Column(Integer)
    log_content = Column(Text)

    test = relationship("TestList", back_populates="runs")
