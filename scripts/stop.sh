#!/bin/bash
# ============================================
# 停止服务脚本
# ============================================

CONTAINER_NAME="aider-code-review"

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "停止容器: ${CONTAINER_NAME}"
    docker stop ${CONTAINER_NAME}
    echo "容器已停止"
else
    echo "容器未运行: ${CONTAINER_NAME}"
fi
