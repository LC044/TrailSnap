# 使用官方Python镜像作为基础镜像
FROM python:3.12.12-slim

WORKDIR /app

# 下载预编译的 llama.cpp 二进制文件
# 根据 CPU 架构 (arm64 或 x86_64) 下载对应的 ubuntu 包
# 提取 TARGETARCH 参数 (由 docker buildx 提供，如 amd64 或 arm64)
ARG TARGETARCH
RUN apt-get update && apt-get install -y curl tar && \
    if [ "$TARGETARCH" = "arm64" ]; then \
        curl -L -o llama.tar.gz https://github.com/ggml-org/llama.cpp/releases/download/b9354/llama-b9354-bin-ubuntu-arm64.tar.gz; \
    else \
        curl -L -o llama.tar.gz https://github.com/ggml-org/llama.cpp/releases/download/b9354/llama-b9354-bin-ubuntu-x64.tar.gz; \
    fi && \
    mkdir -p /usr/local/llama && \
    tar -xzf llama.tar.gz -C /usr/local/llama --strip-components=1 && \
    rm llama.tar.gz

# 注册动态链接库并将 bin 目录加入环境变量
ENV LD_LIBRARY_PATH="/usr/local/llama:/usr/local/llama/lib64:${LD_LIBRARY_PATH}"
ENV PATH="/usr/local/llama:${PATH}"
RUN ldconfig

# 安装编译依赖（g++等），这是解决insightface编译失败的关键
RUN apt-get update && apt-get install -y --no-install-recommends --fix-missing \
    # insightface编译依赖
    build-essential \
    g++ \
    cmake \
    # OpenCV核心运行依赖（仅保留必需项）
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# 复制项目所有文件到工作目录
COPY . .

# 复制依赖文件并安装
RUN pip install uv
RUN uv sync --extra cpu

# 暴露端口
EXPOSE 8001
# 核心：将虚拟环境的bin目录加入PATH
ENV PATH="/app/.venv/bin:$PATH"
# 运行应用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
