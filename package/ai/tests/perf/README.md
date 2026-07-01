# AI 微服务接口性能压测脚本

针对 AI 微服务（`package/ai`，默认 `http://localhost:8001`）的每个推理接口，提供独立的异步压测脚本，可指定**并发度**与**每次请求的照片数量**，输出 RPS、吞吐、分位延迟等指标，并可选导出 JSON 报告。

## 支持的接口

| 脚本 | 接口 | 路径 | 载荷 |
|------|------|------|------|
| `run_face.py` | 人脸识别 | `POST /face/face-recognition` | images |
| `run_ocr.py` | OCR 文字识别 | `POST /ocr/predict` | images |
| `run_classification.py` | 图像分类 | `POST /classification/` | images |
| `run_embedding_image.py` | 图像向量(CLIP) | `POST /embedding/image` | images |
| `run_embedding_text.py` | 文本向量(CLIP) | `POST /embedding/text` | texts |
| `run_tickets.py` | 车票识别 | `POST /tickets/predict` | images |
| `run_emotion.py` | 情绪色彩提取 | `POST /emotion/` | images |
| `run_all.py` | 串行跑全部接口并输出对比表 | — | — |

> `object-detection` 当前是未实现的桩接口，未纳入压测。

## 前置条件

1. AI 微服务已启动（`uvicorn main:app --port 8001`），各模型加载完成。
2. images 类接口需要测试图片。默认读取 `package/ai/output/`（face crop png，开箱可用），也可用 `--images-dir` 指定自己的图库目录。
3. 在 `package/ai/` 目录下运行，使用 `python -m tests.perf.<script>` 调用，保证包内相对导入正确。

## 通用参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `--base-url` | AI 微服务地址（也可用环境变量 `AI_API_URL`） | `http://localhost:8001` |
| `-c, --concurrency` | 并发请求数 | `4` |
| `-k, --images-per-request` | 每次请求携带的图片/文本数（batch 大小） | `1` |
| `-n, --requests` | 总请求数（>0 按数量跑） | `20` |
| `-d, --duration` | 压测持续秒数（>0 时覆盖 `-n`，按时长跑） | `0` |
| `--images-dir` | 测试图片目录（images 类接口） | `package/ai/output` |
| `--image-limit` | 最多加载图片数（控制内存） | `50` |
| `--warmup` | 预热请求数（不计入统计） | `1` |
| `--timeout` | 单请求超时秒数 | `120` |
| `-o, --output` | JSON 报告输出路径 | 不导出 |
| `--append-report` | 报告已存在时追加而非覆盖 | 关 |
| `--verbose` | 打印进度 | 关 |

> `-n` 与 `-d` 至少指定其一。`-k` 对文本向量接口表示每请求的文本条数。

## 示例

```bash
cd package/ai

# 人脸识别：8 并发、每请求 4 张图、共 50 个请求
python -m tests.perf.run_face -c 8 -k 4 -n 50

# OCR：持续 30 秒，打印进度
python -m tests.perf.run_ocr -c 4 -d 30 --verbose

# 图像分类：每请求 8 张图（真 batch），导出报告
python -m tests.perf.run_classification -c 4 -k 8 -n 30 -o cls_perf.json

# 文本向量：8 并发、每请求 4 条文本、100 请求
python -m tests.perf.run_embedding_text -c 8 -k 4 -n 100

# 全部接口横向对比，只跑 face 和 ocr
python -m tests.perf.run_all --only face,ocr -c 4 -k 2 -n 20 -o perf_report.json

# 全部接口跑一遍
python -m tests.perf.run_all -c 4 -k 2 -n 20 -o perf_report.json
```

## 输出说明

每次压测结束后打印：

```
================================================================
  人脸识别  [/face/face-recognition]
================================================================
  并发度         : 8
  每请求条数     : 4
  总请求         : 50   (成功 50 / 失败 0)
  总条目(图片/文本): 200
  总耗时         : 18.234 s
  请求吞吐 RPS   : 2.74 req/s
  条目吞吐       : 10.97 items/s
  延迟(ms)       : min=...  mean=...  p50=...  p95=...  p99=...  max=...
================================================================
```

`run_all.py` 额外打印横向对比表。`-o` 指定时写入 JSON（结构 `{"reports": [ {endpoint, rps, latency_ms:{p50,p95,...}, ...}, ... ]}`），多次运行加 `--append-report` 可累积对比。

## 实现说明

- 共享引擎 `runner.py`：用 `httpx.AsyncClient` + `asyncio.Semaphore` 控制并发；连接池 `max_connections = concurrency*2`。
- 载荷从池中**按序循环**取（`build_payload` 用请求序号 `seq` 计算），保证可复现、不依赖随机数。
- 接口配置集中在 `endpoints.py`，新增接口只需加一条 `Endpoint` 并写一个薄入口脚本。
- 压测前先做一次探测请求，服务不可达时直接退出，避免空跑。
- 预热请求（`--warmup`）不计入统计，规避首次推理冷启动开销。
