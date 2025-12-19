"""
数据库管理模块
"""
import os
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from models import Base
from config import config

logger = logging.getLogger("aider-reviewer")

# 数据库文件路径
DATABASE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data',
    'reviews.db'
)

# 确保数据目录存在
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

# 创建数据库引擎（带连接池配置）
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite需要此配置
    poolclass=QueuePool,
    pool_size=5,          # 连接池大小
    max_overflow=10,      # 最大溢出连接数
    pool_timeout=30,      # 连接超时（秒）
    pool_recycle=3600,    # 连接回收时间（秒）
    echo=False            # 设为True可查看SQL日志
)

# SQLite性能优化
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")     # 写前日志模式，提高并发性能
    cursor.execute("PRAGMA synchronous=NORMAL")   # 平衡性能和安全
    cursor.execute("PRAGMA cache_size=-64000")    # 64MB缓存
    cursor.close()

# 创建Session工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_database():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)
    logger.info(f"数据库初始化完成: {DATABASE_PATH}")


def get_db():
    """获取数据库Session（用于FastAPI依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """获取数据库Session（用于后台任务）"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"数据库事务回滚: {e}", exc_info=True)
        raise
    finally:
        db.close()

