#!/bin/bash
# ============================================
# 内网环境部署脚本
# 在内网服务器上运行此脚本部署服务
# ============================================

set -e

IMAGE_NAME="aider-reviewer"
IMAGE_TAG="${1:-latest}"

echo "=========================================="
echo "Aider Code Review - 内网部署脚本"
echo "=========================================="

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker"
    exit 1
fi

# 切换到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

# 检查镜像文件是否存在
IMAGE_FILE="${IMAGE_NAME}_${IMAGE_TAG}.tar.gz"
if [ ! -f "${IMAGE_FILE}" ]; then
    echo "警告: 未找到镜像文件 ${IMAGE_FILE}"
    echo "尝试查找未压缩的tar文件..."
    IMAGE_FILE="${IMAGE_NAME}_${IMAGE_TAG}.tar"
    if [ ! -f "${IMAGE_FILE}" ]; then
        echo "错误: 镜像文件不存在，请先从外网导出镜像"
        exit 1
    fi
fi

echo ""
echo "[1/4] 加载Docker镜像..."
if [[ "${IMAGE_FILE}" == *.gz ]]; then
    gunzip -c "${IMAGE_FILE}" | docker load
else
    docker load -i "${IMAGE_FILE}"
fi

echo ""
echo "[2/4] 检查环境配置..."
if [ ! -f ".env" ]; then
    echo "警告: .env文件不存在，从模板创建..."
    cp .env.example .env
    echo "请编辑 .env 文件配置必要的环境变量！"
fi

echo ""
echo "[3/4] 检查SSH密钥配置..."
if [ ! -d "${HOME}/.ssh" ]; then
    echo "警告: SSH密钥目录不存在"
    echo "请确保已配置访问Git仓库的SSH密钥"
fi

echo ""
echo "[4/4] 启动服务..."
docker-compose up -d

echo ""
echo "=========================================="
echo "部署完成！"
echo ""
echo "服务状态:"
docker-compose ps
echo ""
echo "查看日志: docker-compose logs -f"
echo "停止服务: docker-compose down"
echo "=========================================="
