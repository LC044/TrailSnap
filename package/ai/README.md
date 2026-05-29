# TrailSnap AI Service

TrailSnap 的 AI 微服务模块，负责处理所有计算机视觉相关的任务，包括 OCR（文字识别）、人脸检测与识别、物体检测等。

## 功能特性

- **OCR 识别**: 基于 PaddleOCR (RapidOCR)，支持多语言文字识别，专门针对火车票、行程单优化。
- **人脸识别**: 基于 InsightFace，支持人脸检测、特征提取、人脸聚类。
- **物体检测**: 基于 YOLO，用于识别照片场景和物体。
- **车票识别**: 基于 YOLO + PaddleOCR (RapidOCR)，支持火车票关键信息结构化提取（车次、日期、车站、座次、姓名等）。
- **LLM 托管**: 支持本地 llama.cpp 运行大语言模型，提供 OpenAI 格式的 LLM 代理。

## 环境要求

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (依赖管理工具)
- CUDA 12.x (如果使用 GPU 加速)

## 安装

1. 进入目录：
   ```bash
   cd package/ai
   ```

2. 安装依赖：

   本项目使用 `uv` 进行依赖管理，请根据硬件环境选择安装命令（部分库安装需要使用c++编译器，Windows下需要安装Microsoft C++ BuildTools，请自行查看教程并安装）。

   Windows需要指定编码格式：`$env:CMAKE_ARGS="-DCMAKE_C_FLAGS=/utf-8 -DCMAKE_CXX_FLAGS=/utf-8"; uv sync --extra cpu`

   **CPU 版本**:
   ```bash
   uv sync --extra cpu
   ```

   **GPU 版本 (CUDA 12.8)**:
   ```bash
   uv sync --extra gpu
   ```

## 运行

使用 `uvicorn` 启动服务：

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

服务默认运行在 `8001` 端口。

## LLM 模型安装

TrailSnap 内置 AI 连接使用 MiniCPM-V-4_6-Q4_K_M 多模态模型，需要安装 llama.cpp。

### Windows

1. 下载 llama.cpp 预编译版本：
   ```bash
   # 使用 winget 安装
   winget install llama.cpp

   # 或手动下载：https://github.com/ggerganov/llama.cpp/releases
   # 解压后将 llama-server.exe 添加到系统 PATH
   ```

2. 验证安装：
   ```bash
   llama-server --version
   ```

### Linux

```bash
# 下载并编译 llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
mkdir build && cd build
cmake .. -DLLAMA_CURL=ON
cmake --build . --config Release
sudo cp llama-server /usr/local/bin/
```

### macOS

```bash
# 使用 Homebrew 安装
brew install llama.cpp

# 或手动下载预编译版本：https://github.com/ggerganov/llama.cpp/releases
```

### 模型下载

llama.cpp 安装完成后，启动 AI 服务时会自动下载 MiniCPM-V-4_6-Q4_K_M 模型（约 4GB）。

如需手动下载：
```bash
# 模型通常位于 ~/.cache/llama.cpp/ 或项目配置的模型路径
# 首次启动会自动下载
```

## API 文档

启动服务后，访问 Swagger UI 查看接口文档：
http://localhost:8001/docs

## Docker 部署

构建并运行 Docker 镜像：

```bash
# 构建镜像（CPU版本）
docker build -t trailsnap-ai .

# # 构建镜像（GPU版本）
# docker build -t trailsnap-ai -f Dockerfile.gpu .

# 运行容器
docker run -d -p 8001:8001 --name trailsnap-ai trailsnap-ai
```