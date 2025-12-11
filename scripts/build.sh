#!/bin/bash
# ============================================
# 外网环境构建脚本
# 在有网络的机器上运行此脚本构建Docker镜像
# ============================================

set -e

IMAGE_NAME="aider-reviewer"
IMAGE_TAG="${1:-latest}"
EXPORT_PATH="${2:-.}"

echo "=========================================="
echo "Aider Code Review - 镜像构建脚本"
echo "=========================================="

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker"
    exit 1
fi

# 切换到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

echo ""
echo "[1/3] 构建Docker镜像..."
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

echo ""
echo "[2/3] 导出镜像为tar文件..."
EXPORT_FILE="${EXPORT_PATH}/${IMAGE_NAME}_${IMAGE_TAG}.tar"
docker save -o "${EXPORT_FILE}" ${IMAGE_NAME}:${IMAGE_TAG}

echo ""
echo "[3/3] 压缩镜像文件..."
gzip -f "${EXPORT_FILE}"

echo ""
echo "=========================================="
echo "构建完成！"
echo "镜像文件: ${EXPORT_FILE}.gz"
echo "文件大小: $(du -h "${EXPORT_FILE}.gz" | cut -f1)"
echo ""
echo "下一步: 将以下文件复制到内网服务器"
echo "  1. ${EXPORT_FILE}.gz (镜像文件)"
echo "  2. 整个项目目录 (代码文件)"
echo "=========================================="
