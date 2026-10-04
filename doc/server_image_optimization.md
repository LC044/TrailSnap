# Server 镜像精简实测

测量日期：2026-10-04。基线为已发布的 `siyuan044/trailsnap-server:0.17.0`，镜像索引摘要 `sha256:f8f59fec68bd9d6db340196937da3ff3dec9111ac2f55840db57b0f63f0099ba`。优化代码基于 master `1e9a86f4`，在本地 Ubuntu WSL Docker 中构建；现有发布标签和远端镜像保持原状。

## 测量口径

- 解压大小：Docker `image inspect` 的 `Size`，按架构分别比较，不包含运行后写入数据卷的文件。
- 压缩大小：把优化前后镜像推送到同一个本地 Registry，读取 manifest 中 `layers[].size` 的总和。不是把整个文件系统压成一个文件后的估算；不包含 manifest 和配置的小额元数据。
- 全文 MB 为十进制 `1,000,000 bytes`，GB 为 `1,000,000,000 bytes`；与 MiB/GiB 显示存在差异。Docker Hub 和不同导出器的压缩方式可能使下载大小略有不同。

## 最终体积

| 架构 / 口径 | 原镜像 MB | 优化后 MB | 减少 MB | 降幅 |
|---|---:|---:|---:|---:|
| AMD64 解压大小 | 1377.1 | 576.6 | 800.5 | 58.1% |
| AMD64 压缩层总量 | 506.5 | 197.9 | 308.6 | 60.9% |
| ARM64 解压大小 | 1285.0 | 588.8 | 696.2 | 54.2% |
| ARM64 压缩层总量 | 476.0 | 193.5 | 282.4 | 59.3% |

精确字节数：AMD64 解压 `1377109820 → 576610074`；压缩 `506539570 → 197915184`；ARM64 解压 `1284984916 → 588832827`；压缩 `475977278 → 193535774`。

## 优化范围

1. FFmpeg 改为固定版本及 SHA256 的源码构建，使用共享库；保留软件解码器、容器格式、滤镜、H.264 编码、AV1 解码和 HTTPS，去掉图形播放、设备采集、硬件加速及自动探测的外部依赖。不再带入 LLVM、Mesa、语音合成等系统库。编译器、头文件和安装工具留在构建阶段，运行镜像保留许可证及来源说明。
2. 字体使用固定 Noto 源码提交中的简体中文常规 OTF，校验 SHA256 并保留许可证，取代整套多地区、多字重、多字体家族包。
3. Docker 中的视频读取、尺寸/时长、缩略图统一走 FFmpeg/FFprobe，保留多个候选帧评分和黑帧避让，省去 OpenCV 及其附带的重复编解码库。桌面和原生环境继续保留 OpenCV。
4. 移除未使用的 `langchain-community`、`ollama` 和被仓库内定制模块替代的第三方 `reverse-geocoder`；补充实际直接使用的 NumPy/SciPy 声明，锁文件减少 11 个包，其余包版本未升级。
5. Python 多阶段安装，不把 uv、下载缓存和编译缓存带入运行镜像。删除 SciPy/scikit-learn 的测试目录；NumPy 的测试辅助模块被 SciPy 运行代码导入，因此保留。
6. 中国离线定位种子构建时压缩为 `CN.csv.gz`，首次启动原子解压到数据卷，兼容原有未压缩种子。解压后内容一致，用户后续删除文件不会被重新播种。首次启动后数据卷仍保留约 70.4 MB 的原始地点文件，与之前的运行需求一致。
7. 排除本地数据库、开发文件和文档。保留铁路 CSV、GeoJSON、迁移和运行代码。为 GitHub 构建增加 GHA 缓存配置，以复用媒体编译和 Python 安装层；缓存效果尚未在远端 CI 实测。

## AMD64 文件盘点

以下是文件内容大小，不能直接与 Docker 层大小相加：

| 范围 | 原镜像 MB | 优化后 MB |
|---|---:|---:|
| Python 虚拟环境 | 559.4 | 366.5 |
| 字体目录 | 96.7 | 16.4 |
| `/usr/local`（含 Python 和安装工具） | 90.9 | 33.5 |
| 应用资源（含定位种子） | 88.0 | 29.0 |

新构建的 FFmpeg 程序及共享库约 25.1 MB。NumPy、SciPy、scikit-learn、Pillow/HEIF 等实际功能依赖保留；未以删除聚类、定位、HEIC 或视频功能换取体积下降。

## 验证

- 统一入口：`pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component server -Level full`：2752 通过、3 跳过、0 失败。
- 构建时直接验证 SciPy 空间索引、scikit-learn 聚类导入及影片生成能力，防止精简后出现缺失模块/共享库。
- 容器中验证 API 路由导入、DBSCAN/AgglomerativeClustering 实际执行、离线种子 SHA256 一致、中文字体有不同字形。
- 真实素材：带音轨 H.264、HEVC、VP9、AV1、带旋转矩阵的视频、黑色首帧后出现正常内容的视频。验证解码、尺寸、时长、缩略图、黑帧避让及带中文的影片预览。
- 静态照片导出为 1920×1080，动态预览为 640×360，输出为静音 H.264 且每段 30 帧；验证拼接、MP4 快速开始及 480px 封面生成。
- AMD64 和 ARM64 的上述完整容器功能验证均通过；ARM64 经 QEMU 运行。两种架构均完成实际镜像构建及 Registry 推送测量。

优化镜像配置 ID：AMD64 `sha256:cc2bbf75746c19e759c7b25560bd13cd61ccdd2a2bd7f0d067a81efa15133c95`；ARM64 `sha256:57d5e8e4387d9f3c434adce07a632e1a705bb5a57ef15909c70be7815833b58e`。

原始证据在本地 `tests/artifacts/image-size/`：镜像 inspect JSON、Registry manifest、文件盘点、两种架构构建日志、容器功能验证日志和单元测试日志。该目录不提交到仓库。

## 使用与边界

```sh
docker buildx build --platform linux/amd64 --load -t trailsnap-server:optimized package/server
docker buildx build --platform linux/arm64 --load -t trailsnap-server:optimized-arm64 package/server
docker image inspect trailsnap-server:optimized --format '{{.Size}}'
```

首次源码编译比直接安装发行版包更慢，后续可以复用构建缓存。ARM64 本地通过 QEMU 构建和运行，模拟器性能不用于评估实际设备的影片生成速度。

软件媒体构建不提供 GPU 加速和摄像头采集。新增视频功能如需额外外部编码器，应明确开启并验证；本次验证覆盖上述常见素材格式，不声称覆盖任意特殊编码格式。
