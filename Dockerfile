# Dockerfile - Aider Code Review 中间件
# 设计原则：镜像仅包含运行环境，代码通过Volume挂载

FROM python:3.10-slim

LABEL maintainer="AI Team"
LABEL description="Aider Code Review Middleware Service"
LABEL version="1.0.0"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 创建非root用户
RUN groupadd -r reviewer && useradd -r -g reviewer reviewer

# 创建必要目录
RUN mkdir -p /app /app/data /tmp/aider_reviewer /home/reviewer/.ssh \
    && chown -R reviewer:reviewer /app /tmp/aider_reviewer /home/reviewer

# 安装Python依赖
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# 设置工作目录
WORKDIR /app

# 切换到非root用户
USER reviewer

# 暴露端口
EXPOSE 5000

# 健康检查 (使用curl)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# 启动命令
CMD ["python", "review_server.py"]
