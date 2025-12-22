"""
统计 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from statistics import StatisticsService
from services.issue_parser import issue_parser, ParsedIssue
from services.report_exporter import report_exporter

router = APIRouter(prefix="/api/stats", tags=["Statistics"])


@router.get("/overview")
async def get_overview(db: Session = Depends(get_db)):
    """获取概览统计"""
    service = StatisticsService(db)
    return service.get_overview()


@router.get("/daily-trend")
async def get_daily_trend(days: int = 30, db: Session = Depends(get_db)):
    """获取每日审查趋势"""
    service = StatisticsService(db)
    return service.get_daily_trend(days)


@router.get("/authors")
async def get_authors(limit: int = 20, db: Session = Depends(get_db)):
    """获取提交人统计"""
    service = StatisticsService(db)
    return service.get_author_statistics(limit)


@router.get("/author/{author_name}")
async def get_author_detail(author_name: str, db: Session = Depends(get_db)):
    """获取指定提交人详情"""
    service = StatisticsService(db)
    return service.get_author_detail(author_name)


@router.get("/projects")
async def get_projects(limit: int = 20, db: Session = Depends(get_db)):
    """获取项目统计"""
    service = StatisticsService(db)
    return service.get_project_statistics(limit)


@router.get("/reviews")
async def get_reviews(
    limit: int = 50, 
    offset: int = 0,
    search: str = None,
    author: str = None,
    project: str = None,
    status: str = None,
    strategy: str = None,
    sort_by: str = Query('created_at', regex="^(created_at|quality_score|issues_count|project_name|author_name)$"),
    order: str = Query('desc', regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    """
    获取审查记录列表（支持搜索、过滤和排序）
    
    - sort_by: 排序字段 (created_at, quality_score, issues_count, project_name, author_name)
    - order: 排序方向 (asc, desc)
    """
    service = StatisticsService(db)
    return service.get_recent_reviews(
        limit, offset, 
        search=search, 
        author=author, 
        project=project,
        status=status,
        strategy=strategy,
        sort_by=sort_by,
        order=order
    )


@router.delete("/review/{task_id}")
async def delete_review(task_id: str, db: Session = Depends(get_db)):
    """删除审查记录"""
    from models import ReviewRecord
    
    review = db.query(ReviewRecord).filter(ReviewRecord.task_id == task_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    db.delete(review)
    db.commit()
    
    return {"status": "deleted", "task_id": task_id}


@router.get("/review/{task_id}")
async def get_review_detail(task_id: str, db: Session = Depends(get_db)):
    """获取审查详情"""
    service = StatisticsService(db)
    result = service.get_review_detail(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Review not found")
    return result


@router.get("/hotspots")
async def get_hotspots(limit: int = 20, db: Session = Depends(get_db)):
    """获取问题热点文件"""
    service = StatisticsService(db)
    return service.get_issue_hotspots(limit)


@router.get("/categories")
async def get_categories(db: Session = Depends(get_db)):
    """获取问题类型分布"""
    service = StatisticsService(db)
    return service.get_issue_categories()


# ==================== 审查详情增强 API ====================

@router.get("/review/{task_id}/issues")
async def get_review_issues(task_id: str, db: Session = Depends(get_db)):
    """获取解析后的问题列表"""
    service = StatisticsService(db)
    review = service.get_review_detail(task_id)
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # 解析报告中的问题
    issues = issue_parser.parse_report(review.get('report', ''))
    
    return {
        "task_id": task_id,
        "total": len(issues),
        "issues": [issue.to_dict() for issue in issues]
    }


@router.get("/review/{task_id}/summary")
async def get_review_summary(task_id: str, db: Session = Depends(get_db)):
    """获取审查总结"""
    service = StatisticsService(db)
    review = service.get_review_detail(task_id)
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # 解析问题
    issues = issue_parser.parse_report(review.get('report', ''))
    
    # 生成总结
    summary = issue_parser.generate_summary(
        issues, 
        quality_score=review.get('quality_score')
    )
    
    return {
        "task_id": task_id,
        "summary": summary.to_dict(),
        "stats": {
            "total_issues": len(issues),
            "critical": sum(1 for i in issues if i.severity.value == "critical"),
            "warning": sum(1 for i in issues if i.severity.value == "warning"),
            "suggestion": sum(1 for i in issues if i.severity.value == "suggestion"),
        }
    }


@router.get("/review/{task_id}/export")
async def export_review_report(
    task_id: str, 
    format: str = "md",
    db: Session = Depends(get_db)
):
    """
    导出审查报告
    
    - format: md (Markdown) 或 html
    """
    service = StatisticsService(db)
    review = service.get_review_detail(task_id)
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # 解析问题和生成总结
    issues = issue_parser.parse_report(review.get('report', ''))
    summary = issue_parser.generate_summary(issues, review.get('quality_score'))
    
    # 根据格式导出
    if format == "html":
        content = report_exporter.export_html(review, issues, summary)
        media_type = "text/html"
        filename = f"review_{task_id[:8]}.html"
    else:
        content = report_exporter.export_markdown(review, issues, summary)
        media_type = "text/markdown"
        filename = f"review_{task_id[:8]}.md"
    
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/review/{task_id}/full")
async def get_review_full(task_id: str, db: Session = Depends(get_db)):
    """获取完整审查详情（包含解析后的问题和总结）"""
    service = StatisticsService(db)
    review = service.get_review_detail(task_id)
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # 解析问题
    issues = issue_parser.parse_report(review.get('report', ''))
    
    # 生成总结
    summary = issue_parser.generate_summary(issues, review.get('quality_score'))
    
    return {
        "review": review,
        "issues": [issue.to_dict() for issue in issues],
        "summary": summary.to_dict(),
    }
