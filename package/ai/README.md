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

   **OpenVINO 版本**（Intel CPU/NPU 上通常比 ONNX Runtime 更快）:
   ```bash
   uv sync --extra openvino
   ```

   > 三个 extra（`cpu` / `gpu` / `openvino`）互斥，每次只能安装其中一个。切换后端时请先 `uv sync` 覆盖安装。

## LLM 模型安装

TrailSnap 内置 AI 连接使用 MiniCPM-V-4_6-Q4_K_M 多模态模型，需要安装 llama.cpp。

### Windows

1. 下载 llama.cpp 预编译版本：
   ```bash
   # 使用 winget 安装
   winget install llama.cpp
   winget install ffmpeg

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
brew install ffmpeg

# 或手动下载预编译版本：https://github.com/ggerganov/llama.cpp/releases
```

### 模型下载

llama.cpp 安装完成后，启动 AI 服务时会自动下载 MiniCPM-V-4_6-Q4_K_M 模型（约 4GB）。

如需手动下载：
```bash
# 模型通常位于 ~/.cache/llama.cpp/ 或项目配置的模型路径
# 首次启动会自动下载
```

## 运行

使用 `uvicorn` 启动服务：

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

服务默认运行在 `8001` 端口。

## 推理后端选择

AI 服务的推理后端按 **CUDA > OpenVINO > CPU** 优先级自动探测，无需手动配置：

- **人脸 / 物体分类 / 票据检测 / 图像向量**：走 ONNX Runtime，由 `app/services/onnx_providers.py` 统一探测可用 EP（`get_onnx_providers()` 进程内 `lru_cache` 只探测一次）。安装 `gpu` extra 时优先 CUDAExecutionProvider，安装 `openvino` extra 时优先 OpenVINO EP，否则回退 CPUExecutionProvider。
- **OCR / 车票 OCR**：走 RapidOCR 自有的引擎配置口（不经过 `get_onnx_providers()`），在 `app/services/ocr_service.py` 中按 `torch.cuda` → `openvino` → `onnxruntime` 顺序选择引擎。

> ⚠️ **OpenVINO 并发限制**：OpenVINO 的 `InferRequest.infer()` 是同步且非线程安全的，同一 RapidOCR 实例被多线程并发调用会抛 `Infer Request is busy`。`ocr_service.detect_text` 与 `ticket_service.detect` 共享同一 OCR 实例，已通过 `openvino_infer_lock()` 串行化 OpenVINO 推理；ONNX Runtime / Torch 后端线程安全，锁为 no-op，不影响吞吐。LATENCY 模式下单次推理已用 intra-op 线程吃满 CPU，串行化不损失性能。

可通过环境变量 `OPENVINO_DEVICE` 强制指定 OpenVINO 设备（如 `NPU` / `CPU`），默认按 `openvino.Core().available_devices()` 自动探测（NPU 优先，否则 CPU）。

## 环境变量

服务从 `data/.env`（不存在时使用默认值）读取配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MODEL_PATH` | `data/models` | 模型文件根目录 |
| `LLM_MODEL_PATH` | `""` | 本地 LLM 模型路径（留空则首次启动自动下载 MiniCPM-V-4_6-Q4_K_M） |
| `LLM_SERVER_PORT` | `8002` | llama.cpp 子进程监听端口 |
| `LLM_IDLE_TIMEOUT` | `300` | LLM 子进程空闲多久后退出（秒） |
| `IDLE_TIMEOUT` | `600` | 服务整体空闲多久后 `sys.exit(0)` 释放内存（秒，仅非 Windows 生效） |
| `CHECK_INTERVAL` | `60` | 空闲检查轮询间隔（秒） |
| `OPENVINO_DEVICE` | 自动探测 | 强制指定 OpenVINO 设备 |

## API 文档

启动服务后，访问 Swagger UI 查看接口文档：
http://localhost:8001/docs

主要接口分组：

| 前缀 | 说明 |
| --- | --- |
| `/face` | 人脸检测、特征提取、聚类 |
| `/ocr` | 通用文字识别（批量 base64） |
| `/tickets` | 火车票 / 飞机票结构化识别 |
| `/object-detection` | 场景与物体检测 |
| `/classification` | 图像分类 |
| `/embedding` | 图像向量（CLIP） |
| `/emotion` | 情绪色彩 |
| `/v1` | OpenAI 兼容的 LLM 代理 |
| `/ai` | AI 模型配置 |
| `/health-check` | 健康检测 |

各接口的请求 / 响应结构见 Swagger UI，每个路由有独立的 Pydantic 模型（如 `OCRResponse`、`TicketRecognitionResponse`）。

## 内存与空闲重启

非 Windows 平台下，服务在 `IDLE_TIMEOUT`（默认 600 秒）无请求后会调用 `sys.exit(0)` 主动退出，由容器编排器或进程管理器重启以释放模型占用的内存。Windows 平台不启用该机制。LLM 子进程由 `app/services/llm_manager.py` 管理，独立于主服务的空闲检查，默认 5 分钟空闲后销毁。

## 性能测试

查看[性能测试指南](./tests/perf/README.md)

## 项目结构

```
package/ai/
├── main.py                      # FastAPI 入口，lifespan、中间件、路由挂载、空闲重启
├── app/
│   ├── config.py                # 配置（环境变量 → Settings）
│   ├── routers/                 # FastAPI 路由，按域拆分（face/ocr/tickets/...）
│   ├── services/                # 模型加载与推理服务（懒加载，由 model_manager 统一管理）
│   │   ├── model_manager.py     # 单例模型管理：懒加载 + 空闲释放 + 线程安全
│   │   ├── model_downloader.py  # 启动时后台预下载权重
│   │   ├── llm_manager.py       # llama.cpp 子进程生命周期与空闲退出
│   │   ├── onnx_providers.py    # 统一 ONNX EP 探测（CUDA > OpenVINO > CPU）
│   │   ├── ocr_service.py       # RapidOCR 引擎 + OpenVINO 并发锁
│   │   └── ...
│   └── core/logger.py           # JSON 队列日志（与 server 同构）
├── tests/                       # pytest（smoke/regression/slow/model + 按域 module marker）
└── data/                        # 运行时数据：.env、模型权重
```

## Docker 部署

构建并运行 Docker 镜像：

```bash
# 构建镜像（CPU版本）
docker build -t trailsnap-ai .

# 构建镜像（GPU版本）
docker build -t trailsnap-ai -f Dockerfile.gpu .

# 构建镜像（OpenVINO版本）
docker build -t trailsnap-ai -f Dockerfile.openvino .

# 运行容器
docker run -d -p 8001:8001 --name trailsnap-ai trailsnap-ai
```

CI（`.github/workflows/docker-build-push-ai.yml`）会在 `v*.*.*` tag 推送或提交信息包含 `构建ai` / `构建AI` 时，分别构建 CPU / GPU / OpenVINO 三个变体并推送至 Docker Hub，对应镜像 tag 后缀为空 / `-gpu` / `-openvino`（如 `trailsnap-ai:0.6.0`、`trailsnap-ai:0.6.0-gpu`、`trailsnap-ai:0.6.0-openvino`）。OpenVINO 变体仅在 `linux/amd64` 构建（`onnxruntime-openvino` / `openvino` 官方 wheel 主要面向 x86_64）。