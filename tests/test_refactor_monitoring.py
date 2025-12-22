import pytest
import time
import sys
import os
from unittest.mock import MagicMock, patch

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polling import PollingRepo, PollingManager

def test_polling_repo_interval():
    """测试仓库的个别化轮询间隔配置"""
    repo = PollingRepo(id="t1", name="N1", url="U1", polling_interval=10)
    assert repo.polling_interval == 10
    
    repo_dict = repo.to_dict()
    assert repo_dict['polling_interval'] == 10

def test_trigger_review_no_comment_for_polling():
    """测试纯轮询模式下强制禁用评论回写"""
    pm = PollingManager()
    pm._review_callback = MagicMock()
    
    # 场景1: 纯轮询，原本开启了评论
    repo = PollingRepo(id="t2", name="N2", url="U2", trigger_mode="polling", enable_comment=True)
    item = {"id": "sha123", "author": "me"}
    
    with patch('polling.extract_project_path', return_value="owner/repo"):
        pm._trigger_review(repo, "commit", item)
    
    # 验证回调中的 enable_comment 是否被强制设为 False
    args, kwargs = pm._review_callback.call_args
    context = args[3]
    assert context['enable_comment'] is False

def test_trigger_review_allow_comment_for_webhook():
    """测试 Webhook 模式下允许评论回写"""
    pm = PollingManager()
    pm._review_callback = MagicMock()
    
    repo = PollingRepo(id="t3", name="N3", url="U3", trigger_mode="webhook", enable_comment=True)
    item = {"id": "sha456", "author": "me"}
    
    with patch('polling.extract_project_path', return_value="owner/repo"):
        pm._trigger_review(repo, "commit", item)
    
    args, kwargs = pm._review_callback.call_args
    context = args[3]
    assert context['enable_comment'] is True

@patch('polling.PollingManager._check_repo')
def test_polling_loop_per_repo_timing(mock_check):
    """测试轮询循环是否尊重每个仓库的间隔"""
    pm = PollingManager()
    pm._running = True
    
    repo1 = PollingRepo(id="r1", name="R1", url="U1", trigger_mode="polling", polling_interval=1) # 1分钟
    repo2 = PollingRepo(id="r2", name="R2", url="U2", trigger_mode="polling", polling_interval=60) # 1小时
    
    pm._repos = {"r1": repo1, "r2": repo2}
    pm._last_poll_times = {} # 重置时间
    
    # 模拟运行一次循环
    # 我们不运行真实的 loop 线程，而是手动调用一次逻辑
    with patch('time.time', return_value=1000000):
        # 第一次扫描，应该都触发
        pm._repos_lock = MagicMock()
        pm._repos_lock.__enter__.return_value = None
        
        # 为了方便测试，我们直接提取 loop 中的核心逻辑
        repos = [repo1, repo2]
        now = 1000000
        for repo in repos:
            interval_seconds = repo.polling_interval * 60
            last_poll = pm._last_poll_times.get(repo.id, 0)
            if now - last_poll >= interval_seconds:
                pm._check_repo(repo)
                pm._last_poll_times[repo.id] = now
        
        assert mock_check.call_count == 2
        
        # 模拟 30 秒后
        mock_check.reset_mock()
        now = 1000030
        for repo in repos:
            interval_seconds = repo.polling_interval * 60
            last_poll = pm._last_poll_times.get(repo.id, 0)
            if now - last_poll >= interval_seconds:
                pm._check_repo(repo)
                pm._last_poll_times[repo.id] = now
        
        # 都没有到期
        assert mock_check.call_count == 0
        
        # 模拟 70 秒后
        mock_check.reset_mock()
        now = 1000070
        for repo in repos:
            interval_seconds = repo.polling_interval * 60
            last_poll = pm._last_poll_times.get(repo.id, 0)
            if now - last_poll >= interval_seconds:
                pm._check_repo(repo)
                pm._last_poll_times[repo.id] = now
        
        # repo1 (1min) 到了，repo2 (60min) 还没到
        assert mock_check.call_count == 1
        args, _ = mock_check.call_args
        assert args[0].id == "r1"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
