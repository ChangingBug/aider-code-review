"""
数据库模型定义
使用 SQLAlchemy ORM
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class ReviewStrategy(enum.Enum):
    """审查策略枚举"""
    COMMIT = "commit"
    MERGE_REQUEST = "merge_request"


class ReviewStatus(enum.Enum):
    """审查状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueSeverity(enum.Enum):
    """问题严重程度枚举"""
    CRITICAL = "critical"      # 🔴 严重
    WARNING = "warning"        # 🟡 警告
    SUGGESTION = "suggestion"  # 🔵 建议
    INFO = "info"              # ℹ️ 信息


class ReviewRecord(Base):
    """审查记录表"""
    __tablename__ = 'review_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 任务标识
    task_id = Column(String(36), unique=True, nullable=False, index=True)
    
    # 审查策略
    strategy = Column(SQLEnum(ReviewStrategy), nullable=False)
    status = Column(SQLEnum(ReviewStatus), default=ReviewStatus.PENDING)
    
    # Git平台信息
    platform = Column(String(20), nullable=False)  # gitlab, gitea, github
    project_id = Column(String(100), index=True)
    project_name = Column(String(200))
    
    # 提交/MR信息
    commit_id = Column(String(40), index=True)
    mr_iid = Column(Integer)
    branch = Column(String(200))
    target_branch = Column(String(200))
    
    # 提交人信息
    author_name = Column(String(100), index=True)
    author_email = Column(String(200))
    
    # 审查内容
    files_count = Column(Integer, default=0)
    files_reviewed = Column(Text)  # JSON list of files
    
    # 审查结果
    report = Column(Text)
    issues_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    suggestion_count = Column(Integer, default=0)
    
    # 质量评分 (0-100)
    quality_score = Column(Float)
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    processing_time_seconds = Column(Float)
    
    # 批次进度信息（新增）
    batch_total = Column(Integer, default=1)  # 总批次数
    batch_current = Column(Integer, default=0)  # 当前批次
    batch_results = Column(Text)  # JSON: 每批次结果摘要
    
    # 错误信息
    error_message = Column(Text)

    
    # 关联的问题详情
    issues = relationship("ReviewIssue", back_populates="review", cascade="all, delete-orphan")
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'strategy': self.strategy.value if self.strategy else None,
            'status': self.status.value if self.status else None,
            'platform': self.platform,
            'project_id': self.project_id,
            'project_name': self.project_name,
            'commit_id': self.commit_id,
            'mr_iid': self.mr_iid,
            'branch': self.branch,
            'target_branch': self.target_branch,
            'author_name': self.author_name,
            'author_email': self.author_email,
            'files_count': self.files_count,
            'issues_count': self.issues_count,
            'critical_count': self.critical_count,
            'warning_count': self.warning_count,
            'suggestion_count': self.suggestion_count,
            'quality_score': self.quality_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time_seconds': self.processing_time_seconds,
            # 批次进度
            'batch_total': self.batch_total or 1,
            'batch_current': self.batch_current or 0,
            'batch_results': self.batch_results,
        }



class ReviewIssue(Base):
    """审查发现的问题详情表"""
    __tablename__ = 'review_issues'

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联审查记录
    review_id = Column(Integer, ForeignKey('review_records.id'), nullable=False, index=True)
    review = relationship("ReviewRecord", back_populates="issues")
    
    # 问题信息
    severity = Column(SQLEnum(IssueSeverity), nullable=False)
    file_path = Column(String(500))
    line_number = Column(Integer)
    
    # 问题描述
    title = Column(String(500))
    description = Column(Text)
    suggestion = Column(Text)
    
    # 问题类型分类
    category = Column(String(100))  # security, logic, style, performance, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'review_id': self.review_id,
            'severity': self.severity.value if self.severity else None,
            'file_path': self.file_path,
            'line_number': self.line_number,
            'title': self.title,
            'description': self.description,
            'suggestion': self.suggestion,
            'category': self.category,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
