"""
验证测试 API 路由
"""
import re
import subprocess
import time

import requests
from fastapi import APIRouter

from settings import SettingsManager

router = APIRouter(prefix="/api/test", tags=["Testing"])


@router.post("/git")
async def test_git_connection():
    """测试Git平台连接"""
    start_time = time.time()
    
    settings = SettingsManager.get_all()
    platform = settings.get('git_platform', 'gitlab')
    enable_comment = settings.get('enable_comment', 'true').lower() == 'true'
    
    # HTTP认证信息（用于克隆仓库）
    http_user = settings.get('git_http_user', '')
    http_password = settings.get('git_http_password', '')
    server_url = settings.get('git_server_url', '')
    
    # API信息（用于回写评论）
    api_url = settings.get('git_api_url', '')
    token = settings.get('git_token', '')
    
    results = []
    overall_success = True
    
    # 1. 验证HTTP认证配置（克隆仓库必需）
    if http_user and http_password and server_url:
        results.append("✓ HTTP认证已配置")
    else:
        missing = []
        if not http_user: missing.append("用户名")
        if not http_password: missing.append("密码")
        if not server_url: missing.append("服务器地址")
        results.append(f"⚠ HTTP认证缺少: {', '.join(missing)}")
    
    # 2. 如果启用了评论回写，验证API Token
    if enable_comment:
        if not api_url or not token:
            results.append("✗ 评论回写已启用但未配置API地址或Token")
            overall_success = False
        else:
            # 验证API连接
            try:
                if platform == 'gitlab':
                    url = f"{api_url}/user"
                    headers = {"PRIVATE-TOKEN": token}
                elif platform == 'gitea':
                    url = f"{api_url}/user"
                    headers = {"Authorization": f"token {token}"}
                elif platform == 'github':
                    url = f"{api_url}/user"
                    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
                else:
                    results.append(f"✗ 不支持的平台: {platform}")
                    overall_success = False
                    url = None
                
                if url:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    user_data = response.json()
                    username = user_data.get('username') or user_data.get('login') or user_data.get('name', 'Unknown')
                    results.append(f"✓ API连接成功 (用户: {username})")
                    
            except requests.exceptions.Timeout:
                results.append("✗ API连接超时")
                overall_success = False
            except requests.exceptions.ConnectionError:
                results.append("✗ 无法连接到API服务器")
                overall_success = False
            except requests.exceptions.HTTPError as e:
                results.append(f"✗ API认证失败: HTTP {e.response.status_code}")
                overall_success = False
            except Exception as e:
                results.append(f"✗ API测试失败: {str(e)}")
                overall_success = False
    else:
        results.append("ℹ 评论回写已关闭，跳过API验证")
    
    elapsed = round(time.time() - start_time, 2)
    
    return {
        "success": overall_success,
        "message": "配置验证完成" if overall_success else "部分配置有问题",
        "details": {
            "platform": platform,
            "enable_comment": enable_comment,
            "checks": results,
            "response_time": f"{elapsed}s"
        }
    }


@router.post("/vllm")
async def test_vllm_connection():
    """测试vLLM模型连接 - 发送真实对话验证"""
    start_time = time.time()
    
    settings = SettingsManager.get_all()
    api_base = settings.get('vllm_api_base', '')
    api_key = settings.get('vllm_api_key', '')
    model_name = settings.get('vllm_model_name', '')
    
    if not api_base:
        return {"success": False, "message": "vLLM API地址未配置", "details": {}}
    
    if not model_name:
        return {"success": False, "message": "模型名称未配置", "details": {}}
    
    try:
        # 发送真实的对话请求验证模型
        url = f"{api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        # 构建简单的测试对话
        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": "Say 'Hello' in one word."}
            ],
            "max_tokens": 10,
            "temperature": 0.1
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        elapsed = round(time.time() - start_time, 2)
        
        # 提取模型回复
        reply = ""
        if 'choices' in result and len(result['choices']) > 0:
            reply = result['choices'][0].get('message', {}).get('content', '')[:50]
        
        return {
            "success": True,
            "message": "模型对话成功",
            "details": {
                "api_base": api_base,
                "model": model_name,
                "reply": reply.strip(),
                "response_time": f"{elapsed}s"
            }
        }
    except requests.exceptions.Timeout:
        elapsed = round(time.time() - start_time, 2)
        return {"success": False, "message": f"模型响应超时 ({elapsed}s)", "details": {"api_base": api_base, "model": model_name}}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "无法连接到vLLM服务器", "details": {"api_base": api_base}}
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json().get('error', {}).get('message', str(e))[:100]
        except:
            error_detail = str(e)[:100]
        return {"success": False, "message": f"请求失败: {error_detail}", "details": {"api_base": api_base, "model": model_name}}
    except Exception as e:
        return {"success": False, "message": f"测试失败: {str(e)[:100]}", "details": {}}


@router.post("/aider")
async def test_aider():
    """测试Aider是否可用"""
    try:
        result = subprocess.run(
            ["aider", "--version"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            # 提取版本号
            version_match = re.search(r'[\d.]+', version)
            version_str = version_match.group(0) if version_match else version[:50]
            
            return {
                "success": True,
                "message": "Aider 可用",
                "details": {
                    "version": version_str
                }
            }
        else:
            # 提供更详细的错误信息
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            return {
                "success": False,
                "message": "Aider 运行失败",
                "details": {
                    "returncode": result.returncode,
                    "error": error_msg[:300] if error_msg else "Unknown error"
                }
            }
    except FileNotFoundError:
        return {"success": False, "message": "Aider 未安装", "details": {"hint": "请运行 pip install aider-chat"}}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Aider 响应超时", "details": {}}
    except Exception as e:
        return {"success": False, "message": f"测试失败: {str(e)}", "details": {}}
