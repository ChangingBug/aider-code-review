#!/bin/bash
# ============================================
# Docker Run 启动脚本
# 使用 docker run 命令启动服务（替代 docker-compose）
# ============================================

set -e

# 配置
IMAGE_NAME="aider-reviewer"
CONTAINER_NAME="aider-code-review"
PORT="${SERVER_PORT:-5000}"

# 获取脚本所在目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 加载环境变量
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "加载环境变量: $PROJECT_DIR/.env"
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
else
    echo "警告: .env 文件不存在，使用默认配置"
fi

# 停止并删除已存在的容器
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "停止并删除已存在的容器: ${CONTAINER_NAME}"
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
fi

echo ""
echo "=========================================="
echo "启动 Aider Code Review 服务"
echo "=========================================="
echo "镜像: ${IMAGE_NAME}"
echo "容器: ${CONTAINER_NAME}"
echo "端口: ${PORT}"
echo ""

# 创建数据目录
mkdir -p "$PROJECT_DIR/data"

# 启动容器
# 注意：Git/vLLM/Aider相关配置已移至Web管理页面（/settings），无需在此配置
docker run -d \
    --name ${CONTAINER_NAME} \
    --restart unless-stopped \
    -p ${PORT}:5000 \
    -v "$PROJECT_DIR:/app:ro" \
    -v "$PROJECT_DIR/data:/app/data" \
    -v "$PROJECT_DIR/.aider.conf.yml:/home/reviewer/.aider.conf.yml:ro" \
    -e LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    -e SERVER_HOST=0.0.0.0 \
    -e SERVER_PORT=5000 \
    -e WORK_DIR_BASE=/tmp/aider_reviewer \
    ${IMAGE_NAME}:latest

echo ""
echo "=========================================="
echo "服务启动成功！"
echo "=========================================="
echo "仪表盘: http://localhost:${PORT}/"
echo "系统设置: http://localhost:${PORT}/#settings"
echo ""
echo "首次使用请访问「系统设置」页面配置："
echo "  - Git平台连接信息（HTTP认证、API Token）"
echo "  - vLLM模型地址"
echo "  - Aider参数"
echo ""
echo "常用命令:"
echo "  查看日志: docker logs -f ${CONTAINER_NAME}"
echo "  停止服务: docker stop ${CONTAINER_NAME}"
echo "  重启服务: docker restart ${CONTAINER_NAME}"
echo "=========================================="


