"""
统计服务模块
提供各种统计数据查询
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import func, desc, and_
from sqlalchemy.orm import Session

from models import ReviewRecord, ReviewIssue, ReviewStatus, ReviewStrategy, IssueSeverity


class StatisticsService:
    """统计服务"""

    def __init__(self, db: Session):
        self.db = db

    # ==================== 全局统计 ====================

    def get_overview(self) -> Dict[str, Any]:
        """获取概览统计"""
        total_reviews = self.db.query(ReviewRecord).count()
        completed_reviews = self.db.query(ReviewRecord).filter(
            ReviewRecord.status == ReviewStatus.COMPLETED
        ).count()
        
        total_issues = self.db.query(func.sum(ReviewRecord.issues_count)).scalar() or 0
        
        # 问题分类统计
        critical = self.db.query(func.sum(ReviewRecord.critical_count)).scalar() or 0
        warning = self.db.query(func.sum(ReviewRecord.warning_count)).scalar() or 0
        suggestion = self.db.query(func.sum(ReviewRecord.suggestion_count)).scalar() or 0
        
        # 平均处理时间
        avg_time = self.db.query(func.avg(ReviewRecord.processing_time_seconds)).filter(
            ReviewRecord.processing_time_seconds.isnot(None)
        ).scalar() or 0
        
        # 平均质量评分
        avg_score = self.db.query(func.avg(ReviewRecord.quality_score)).filter(
            ReviewRecord.quality_score.isnot(None)
        ).scalar() or 0
        
        # 按策略统计
        commit_count = self.db.query(ReviewRecord).filter(
            ReviewRecord.strategy == ReviewStrategy.COMMIT
        ).count()
        mr_count = self.db.query(ReviewRecord).filter(
            ReviewRecord.strategy == ReviewStrategy.MERGE_REQUEST
        ).count()
        
        return {
            'total_reviews': total_reviews,
            'completed_reviews': completed_reviews,
            'pending_reviews': total_reviews - completed_reviews,
            'total_issues': int(total_issues),
            'critical_issues': int(critical),
            'warning_issues': int(warning),
            'suggestion_issues': int(suggestion),
            'avg_processing_time': round(avg_time, 2),
            'avg_quality_score': round(avg_score, 1),
            'commit_reviews': commit_count,
            'mr_reviews': mr_count,
        }

    def get_daily_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """获取每日审查趋势"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        results = self.db.query(
            func.date(ReviewRecord.created_at).label('date'),
            func.count(ReviewRecord.id).label('count'),
            func.sum(ReviewRecord.issues_count).label('issues')
        ).filter(
            ReviewRecord.created_at >= start_date
        ).group_by(
            func.date(ReviewRecord.created_at)
        ).order_by(
            func.date(ReviewRecord.created_at)
        ).all()
        
        return [
            {
                'date': str(r.date),
                'count': r.count,
                'issues': int(r.issues or 0)
            }
            for r in results
        ]

    # ==================== 提交人统计 ====================

    def get_author_statistics(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取提交人统计排行"""
        results = self.db.query(
            ReviewRecord.author_name,
            ReviewRecord.author_email,
            func.count(ReviewRecord.id).label('review_count'),
            func.sum(ReviewRecord.issues_count).label('total_issues'),
            func.sum(ReviewRecord.critical_count).label('critical_issues'),
            func.sum(ReviewRecord.warning_count).label('warning_issues'),
            func.avg(ReviewRecord.quality_score).label('avg_score'),
            func.sum(ReviewRecord.files_count).label('total_files')
        ).filter(
            ReviewRecord.author_name.isnot(None)
        ).group_by(
            ReviewRecord.author_name,
            ReviewRecord.author_email
        ).order_by(
            desc('review_count')
        ).limit(limit).all()
        
        return [
            {
                'author_name': r.author_name or 'Unknown',
                'author_email': r.author_email,
                'review_count': r.review_count,
                'total_issues': int(r.total_issues or 0),
                'critical_issues': int(r.critical_issues or 0),
                'warning_issues': int(r.warning_issues or 0),
                'avg_score': round(r.avg_score or 0, 1),
                'total_files': int(r.total_files or 0),
                'issue_rate': round((r.total_issues or 0) / max(r.review_count, 1), 2)
            }
            for r in results
        ]

    def get_author_detail(self, author_name: str) -> Dict[str, Any]:
        """获取指定提交人的详细统计"""
        base_query = self.db.query(ReviewRecord).filter(
            ReviewRecord.author_name == author_name
        )
        
        total = base_query.count()
        completed = base_query.filter(ReviewRecord.status == ReviewStatus.COMPLETED).count()
        
        # 聚合统计
        stats = self.db.query(
            func.sum(ReviewRecord.issues_count).label('total_issues'),
            func.sum(ReviewRecord.critical_count).label('critical'),
            func.sum(ReviewRecord.warning_count).label('warning'),
            func.sum(ReviewRecord.suggestion_count).label('suggestion'),
            func.avg(ReviewRecord.quality_score).label('avg_score'),
            func.avg(ReviewRecord.processing_time_seconds).label('avg_time'),
            func.sum(ReviewRecord.files_count).label('total_files')
        ).filter(
            ReviewRecord.author_name == author_name
        ).first()
        
        # 最近的审查记录
        recent_reviews = base_query.order_by(
            desc(ReviewRecord.created_at)
        ).limit(10).all()
        
        # 每日活跃度 (最近30天)
        start_date = datetime.utcnow() - timedelta(days=30)
        daily_activity = self.db.query(
            func.date(ReviewRecord.created_at).label('date'),
            func.count(ReviewRecord.id).label('count')
        ).filter(
            and_(
                ReviewRecord.author_name == author_name,
                ReviewRecord.created_at >= start_date
            )
        ).group_by(
            func.date(ReviewRecord.created_at)
        ).order_by(
            func.date(ReviewRecord.created_at)
        ).all()
        
        return {
            'author_name': author_name,
            'total_reviews': total,
            'completed_reviews': completed,
            'total_issues': int(stats.total_issues or 0),
            'critical_issues': int(stats.critical or 0),
            'warning_issues': int(stats.warning or 0),
            'suggestion_issues': int(stats.suggestion or 0),
            'avg_quality_score': round(stats.avg_score or 0, 1),
            'avg_processing_time': round(stats.avg_time or 0, 2),
            'total_files': int(stats.total_files or 0),
            'recent_reviews': [r.to_dict() for r in recent_reviews],
            'daily_activity': [
                {'date': str(d.date), 'count': d.count}
                for d in daily_activity
            ]
        }

    # ==================== 项目统计 ====================

    def get_project_statistics(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取项目统计排行"""
        results = self.db.query(
            ReviewRecord.project_name,
            ReviewRecord.project_id,
            ReviewRecord.platform,
            func.count(ReviewRecord.id).label('review_count'),
            func.sum(ReviewRecord.issues_count).label('total_issues'),
            func.count(func.distinct(ReviewRecord.author_name)).label('contributor_count'),
            func.avg(ReviewRecord.quality_score).label('avg_score')
        ).filter(
            ReviewRecord.project_name.isnot(None)
        ).group_by(
            ReviewRecord.project_name,
            ReviewRecord.project_id,
            ReviewRecord.platform
        ).order_by(
            desc('review_count')
        ).limit(limit).all()
        
        return [
            {
                'project_name': r.project_name or f'Project {r.project_id}',
                'project_id': r.project_id,
                'platform': r.platform,
                'review_count': r.review_count,
                'total_issues': int(r.total_issues or 0),
                'contributor_count': r.contributor_count,
                'avg_score': round(r.avg_score or 0, 1)
            }
            for r in results
        ]

    # ==================== 审查记录查询 ====================

    def get_recent_reviews(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """获取最近的审查记录"""
        total = self.db.query(ReviewRecord).count()
        
        reviews = self.db.query(ReviewRecord).order_by(
            desc(ReviewRecord.created_at)
        ).offset(offset).limit(limit).all()
        
        return {
            'total': total,
            'limit': limit,
            'offset': offset,
            'reviews': [r.to_dict() for r in reviews]
        }

    def get_review_detail(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取审查详情"""
        review = self.db.query(ReviewRecord).filter(
            ReviewRecord.task_id == task_id
        ).first()
        
        if not review:
            return None
        
        result = review.to_dict()
        result['report'] = review.report
        result['files_reviewed'] = review.files_reviewed
        result['issues'] = [i.to_dict() for i in review.issues]
        
        return result

    # ==================== 问题热点分析 ====================

    def get_issue_hotspots(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取问题热点文件"""
        results = self.db.query(
            ReviewIssue.file_path,
            func.count(ReviewIssue.id).label('issue_count'),
            func.sum(
                func.case(
                    (ReviewIssue.severity == IssueSeverity.CRITICAL, 1),
                    else_=0
                )
            ).label('critical_count')
        ).filter(
            ReviewIssue.file_path.isnot(None)
        ).group_by(
            ReviewIssue.file_path
        ).order_by(
            desc('issue_count')
        ).limit(limit).all()
        
        return [
            {
                'file_path': r.file_path,
                'issue_count': r.issue_count,
                'critical_count': int(r.critical_count or 0)
            }
            for r in results
        ]

    def get_issue_categories(self) -> List[Dict[str, Any]]:
        """获取问题类型分布"""
        results = self.db.query(
            ReviewIssue.category,
            func.count(ReviewIssue.id).label('count')
        ).filter(
            ReviewIssue.category.isnot(None)
        ).group_by(
            ReviewIssue.category
        ).order_by(
            desc('count')
        ).all()
        
        return [
            {'category': r.category or 'Other', 'count': r.count}
            for r in results
        ]
