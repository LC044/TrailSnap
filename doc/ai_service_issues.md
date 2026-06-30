# AI 微服务性能问题分析与优化

> 分析对象：`package/ai` AI 微服务（FastAPI + PaddleOCR/RapidOCR / InsightFace / CLIP-ONNX）
> 涉及文件：`main.py`、`app/services/model_manager.py`、`app/services/ocr_service.py`、`app/services/embedding_service.py`、`app/services/face_service.py`、`app/routers/face.py`、`app/routers/ocr.py`
> 配套阅读：`doc/task_module_issues.md`（server 端任务调度）—— 本文是「同机 CPU 超额订阅」问题的 AI 服务端一半。

## 0. 部署前提

与 server 一致：**NAS + Docker，CPU 弱、无 GPU，AI 微服务与 server 通常同机**。AI 推理跑在 CPU 上，与 server 的 CPU 任务（缩略图/解码）争用**同一批物理核**。因此 AI 服务的优化核心是：**不阻塞、不独吞核、不浪费内存**，而非「加并发榨干资源」。

---

## 1. 问题清单

### 1.1 同步推理跑在 async 路由里，阻塞事件循环（最严重）

`face_recognition`（`face.py:30` `async def`）、`ocr_predict`（`ocr.py:25` `async def`）内部直接调用：

- `face_service.process_image()`（`face.py:44`）
- `ocr_service.detect_text()`（`ocr.py:52`）

这些是**纯同步 CPU 推理**（ONNXRuntime / InsightFace / RapidOCR），既没有 `await`，也没有丢到线程池。

**后果**：在 async 路由里执行同步重活会**独占 uvicorn 的事件循环线程**。在该图推理完成前，整个进程连 `/health-check` 都无法响应。更糟的是批接口是串行循环（`face.py:40`、`ocr.py:48` 的 `for b64 in request.images`），一个 8 张图的批请求会把事件循环连续锁住 8 次推理时长。

### 1.2 ONNXRuntime 线程数未配置，CPU NAS 上必然超额订阅（治本关键）

- `embedding_service.py:27` `ort.InferenceSession(text_model_path, providers=providers)`
- `embedding_service.py:57` `ort.InferenceSession(vision_model_path, providers=providers)`
- OCR（RapidOCR）、face（InsightFace）同理使用默认线程配置。

**均未设置 `intra_op_num_threads`**。ONNXRuntime 默认 intra-op 线程数 = 物理核数，**单个推理请求就能吃满所有核**。

这正是 `task_module_issues.md` 中「同机 CPU 超额订阅」的 AI 服务端根因：无论 server 端如何限流，只要单个 AI 请求独吞全核，就必然与 server 的 CPU 缩略图任务抢核。**这是治本的一半**（另一半是 server 端的并发控制）。

### 1.3 批量请求是串行单张推理，未用批推理

- OCR（`ocr.py:48`）、face（`face.py:40`）是明确的**逐张 for 循环**。
- 深度模型的批推理（一次喂 N 张）通常显著快于 N 次单张（共享前处理、更好的向量化、更高核利用率）。
- embedding 已经是真批处理（`embedding_service.py:61` `processor(images=images)`），是正确范例，应保持。

### 1.4 base64 解码 / 图像打开在事件循环中执行

`face.py:37` / `ocr.py:45` 每请求 `import base64`（无必要）；更重要的是 base64 解码 + `Image.open`（`embedding_service.py:173-174`）也是同步 CPU 活，同样阻塞事件循环，应随推理一起进线程池。

### 1.5 idle 重启与模型卸载两套机制可能打架

- 进程级：`check_idle_and_restart`（`main.py:34-40`）空闲超 `IDLE_TIMEOUT` 直接 `sys.exit(0)` 靠容器重启释放内存。
- 模型级：`model_manager` 自己有 300s idle 卸载单个模型（`model_manager.py:83`）。

两套机制并存。若 `IDLE_TIMEOUT` ≤ 模型 idle，可能刚卸载模型就又重启整个进程，导致**所有模型冷加载**，比单纯换模型更慢。叠加 server 端「前期模型抖动」时尤其放大。

### 1.6 release 函数多为空壳，内存不真正回收

- `release_paddleocr_model`（`ocr_service.py:48-52`）**只打日志，没释放 RapidOCR 的 session**。
- `model_manager` 在 release 后 `del self.model; gc.collect()`（`model_manager.py:43-45`），但如果 wrapper 内部仍持有 ONNX session 引用而未显式释放，**内存不会真正回收**。
- embedding 的 `_release_model`（`embedding_service.py:133-146`）显式 `del` 掉 session，是正确范例；OCR / face 的 release 需补齐。

→ 后果：「空闲卸载模型省内存」的设计在 OCR 上落空。

### 1.7 单 worker、单例模型（这是正确的设计权衡，勿改）

`uvicorn.run(app, ...)`（`main.py:157`）单进程单 worker + `model_manager` 单例 → 推理天然串行化，**与 server 端「同时只加载一个模型」的目标契合**。

> **不建议**为「提速」而加 uvicorn worker：多 worker 会各自加载一套模型，内存翻倍，违背 NAS 内存约束。问题 1.1 的正解是在**单 worker 内用线程池解阻塞**，而非加 worker。

---

## 2. 优化方案

### P0 — 推理移出事件循环（解阻塞）

把同步推理（含 base64 解码、`Image.open`）用 `await asyncio.to_thread(...)` 或 `run_in_executor` 丢到线程池。ONNXRuntime 的 `session.run` 会释放 GIL，线程池能真正并行。这样事件循环不被阻塞，健康检查与其他请求可正常响应。批接口的整个 for 循环也应包进一次线程池调用，减少线程往返。

### P0 — 限制 ONNXRuntime 线程数（治同机 CPU 超卖）

统一创建 `SessionOptions` 并显式设置：

```python
sess_options = ort.SessionOptions()
sess_options.intra_op_num_threads = N   # NAS 建议核数一半或固定 2~4
sess_options.inter_op_num_threads = 1
session = ort.InferenceSession(path, sess_options, providers=providers)
```

所有 `InferenceSession`（embedding text/image、及 OCR/face 底层）统一应用。RapidOCR 的引擎线程、InsightFace、`cv2.setNumThreads()` 一并钳制。N 设为可配置项（环境变量），便于按 NAS 核数调优。

> 与 server 端「本机 AI 任务限流 + CPU/AI 共享核预算」配合：**server 控请求并发，AI 控单请求线程数，双管齐下才能根治 CPU 超卖。**

### P1 — 补齐 release，真正回收内存

OCR / face 的 `release_func` 显式 `del` 掉内部 session/engine 对象（参照 `embedding_service.py:133-146`），确保 `model_manager` 的空闲卸载能真正释放内存——对内存紧张的 NAS 直接见效。

### P1 — base64 解码 / 图像打开随推理进线程池

把解码与 `Image.open` 与推理打包进同一次 `to_thread` 调用；`import base64` 提到模块顶部。

### P2 — 校准 idle 重启与模型卸载

确认 `IDLE_TIMEOUT`（进程级）> 模型级 idle（300s），避免「刚卸载模型就重启进程」导致全量冷加载。可考虑：常态依赖 model_manager 的单模型卸载省内存，仅在长时间完全空闲时才进程级重启。

### P2 — 视模型 API 评估批推理

embedding 保持现有批处理。OCR/face 若底层支持批输入则改为批推理；若只能逐张，则至少用线程池并行（受 1.2 的线程预算约束，不可无限并行）。

---

## 3. 优先级汇总

| 优先级 | 问题 | 改法 | 收益 |
|---|---|---|---|
| P0 | 同步推理阻塞事件循环（1.1） | `to_thread` 包推理 | 服务不再卡死，可响应健康检查/并发 |
| P0 | ONNX 线程数未限（1.2） | 设 `intra_op_num_threads` | 治同机 CPU 超卖（治本一半） |
| P1 | release 空壳不回收内存（1.6） | 显式 del session | 空闲卸载真正省内存 |
| P1 | base64/解码阻塞循环（1.4） | 随推理进线程池 | 减少事件循环阻塞 |
| P2 | idle 重启与模型卸载叠加（1.5） | 校准 IDLE_TIMEOUT | 避免冷启动雪崩 |
| P2 | 批量串行单张（1.3） | 视模型 API 批推理/线程池 | 有限提升 |
| — | 单 worker 单例（1.7） | **保持不变** | 契合「同时只加载一个模型」 |

---

## 4. 一句话总结

AI 微服务当前最大的两个性能损失是：**同步推理阻塞事件循环**（服务一推理就全卡死）和**ONNX 默认线程数独吞全核**（与 server 抢 CPU）。前者用线程池解，后者用 `intra_op_num_threads` 限——两者合起来，配合 server 端的请求并发控制，才能根治 NAS 同机部署下的 CPU 超额订阅。单 worker + 单例模型是与「同时只加载一个模型」契合的正确设计，不应为提速而加 worker。
