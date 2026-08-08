# syntax=docker/dockerfile:1
#
# TrailSnap AI 服务 —— CPU 版（onnxruntime）
# 三阶段构建：llama 拉取 → builder 编译 → runtime 精简。
# 相比单阶段：最终镜像不含 build-essential/g++/cmake、不含 pytest 等开发依赖、无 uv/pip 缓存。

# ============ stage 1: 拉取 llama.cpp 预编译二进制 ============
# 独立成 stage，让 runtime 不必安装 curl/tar。
# 根据 CPU 架构 (arm64 或 x86_64) 下载对应的 ubuntu 包。
FROM python:3.12.12-slim AS llama
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates tar && \
    rm -rf /var/lib/apt/lists/* && \
    if [ "$TARGETARCH" = "arm64" ]; then \
        curl -L -o llama.tar.gz https://github.com/ggml-org/llama.cpp/releases/download/b9354/llama-b9354-bin-ubuntu-arm64.tar.gz; \
    else \
        curl -L -o llama.tar.gz https://github.com/ggml-org/llama.cpp/releases/download/b9354/llama-b9354-bin-ubuntu-x64.tar.gz; \
    fi && \
    mkdir -p /usr/local/llama && \
    tar -xzf llama.tar.gz -C /usr/local/llama --strip-components=1 && \
    rm llama.tar.gz

# ============ stage 2: builder —— 编译 insightface C++ 扩展 + uv sync ============
FROM python:3.12.12-slim AS builder
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_DOWNLOADS=never
# insightface 编译依赖（仅此阶段需要，不进入 runtime）
RUN apt-get update && apt-get install -y --no-install-recommends --fix-missing \
    build-essential \
    g++ \
    cmake \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
# 先拷依赖清单，代码变动不失效依赖层缓存
COPY pyproject.toml uv.lock ./
# --no-dev：运行时不需要 pytest 等开发依赖；--no-cache：不留 uv 缓存
RUN uv sync --extra cpu --no-dev --no-cache

# ============ stage 3: runtime —— 只含运行时依赖 ============
FROM python:3.12.12-slim AS runtime
WORKDIR /app
# OpenCV 核心运行依赖。python:3.12-slim 自带 libstdc++6，满足 insightface 编译产物链接需求。
# libgomp1：llama-server（预编译 llama.cpp 二进制）依赖 OpenMP 运行库 libgomp.so.1。
#   旧单阶段构建靠 build-essential/g++ 经 gcc→libgomp1 顺带带入；多阶段后 build 工具
#   仅存在于 builder，runtime 必须显式安装，否则 llama-server 启动即报
#   "libgomp.so.1: cannot open shared object file: No such file or directory"。
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# llama-server 二进制及其动态库，并注册到库搜索路径
COPY --from=llama /usr/local/llama /usr/local/llama
ENV LD_LIBRARY_PATH="/usr/local/llama:/usr/local/llama/lib64"
ENV PATH="/usr/local/llama:/app/.venv/bin:${PATH}"
RUN ldconfig

# 从 builder 拷入已编译好的虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 应用代码
COPY . .

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
