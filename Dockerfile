# Comedy Agent —— 多阶段构建 Dockerfile
# 阶段一：构建依赖
FROM python:3.11-slim as builder

WORKDIR /app

# 安装编译依赖（部分 Python 包需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖定义
COPY pyproject.toml .
COPY src ./src

# 安装到虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -e ".[dev]"

# 阶段二：运行镜像
FROM python:3.11-slim

WORKDIR /app

# 安装运行时系统依赖
# unstructured 需要 poppler/tesseract（可选），这里保留最小依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制源码与数据
COPY src ./src
COPY data ./data
COPY skills ./skills
COPY pyproject.toml .
COPY README.md .

# 安装为可编辑模式（引用已存在的 venv 包）
RUN pip install --no-cache-dir -e .

# 数据卷（向量库、SQLite、知识库）
VOLUME ["/app/data", "/app/chroma_data"]

# 非 root 用户运行
RUN useradd -m -u 1000 comedy && chown -R comedy:comedy /app
USER comedy

# 端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["uvicorn", "comedy_agent.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
