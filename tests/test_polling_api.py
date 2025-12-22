import pytest
from fastapi.testclient import TestClient
import json
import uuid
import sys
import os
from unittest.mock import patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from review_server import app
from polling import polling_manager, PollingRepo

client = TestClient(app)

@pytest.fixture
def mock_git_ls_remote():
    with patch('subprocess.run') as mock_run:
        # 默认模拟成功
        mock_run.return_value = MagicMock(returncode=0, stdout="sha1\trefs/heads/main\n", stderr="")
        yield mock_run

def test_add_repo_api(mock_git_ls_remote):
    """测试添加仓库接口"""
    repo_data = {
        "id": "api-test-1",
        "name": "API Test Repo",
        "url": "https://github.com/test/repo.git",
        "verify": True,
        "platform": "github",
        "branch": "main"
    }
    
    response = client.post("/api/polling/repos", json=repo_data)
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
        
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "added"
    
    # 验证是否保存在manager中
    assert polling_manager.get_repo("api-test-1") is not None

def test_test_connectivity_api(mock_git_ls_remote):
    """测试连通性校验接口"""
    test_data = {
        "url": "https://github.com/test/repo.git",
        "auth_type": "token",
        "token": "secret"
    }
    
    # 模拟成功
    response = client.post("/api/polling/repos/test", json=test_data)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # 模拟失败
    mock_git_ls_remote.return_value = MagicMock(returncode=128, stderr="Authentication failed")
    response = client.post("/api/polling/repos/test", json=test_data)
    assert response.json()["success"] is False
    assert "Authentication failed" in response.json()["message"]

def test_verify_all_repos_api(mock_git_ls_remote):
    """测试批量校验接口"""
    # 先添加一两个仓库
    polling_manager.add_repo(PollingRepo(id="v1", name="R1", url="u1"))
    polling_manager.add_repo(PollingRepo(id="v2", name="R2", url="u2"))
    
    response = client.post("/api/polling/repos/verify-all")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "v1" in data["results"]
    assert "v2" in data["results"]

def test_delete_repo_api():
    """测试删除仓库接口"""
    polling_manager.add_repo(PollingRepo(id="del-1", name="To Delete", url="url"))
    
    response = client.delete("/api/polling/repos/del-1")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    
    assert polling_manager.get_repo("del-1") is None

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
