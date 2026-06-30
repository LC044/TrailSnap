# Server 任务管理模块问题分析与优化结论

> 分析对象：`package/server` 后端任务管理子系统
> 涉及文件：`app/service/task_manager.py`、`app/worker.py`、`app/service/task_worker.py`、`app/service/task_strategy.py`、`app/crud/task.py`、`app/db/models/task.py`、`app/api/tasks.py`、`main.py`
> 设计原始意图见：`package/official-site/docs/dev/task_manager.md`

## 0. 部署前提（本文所有结论的基础假设）

TrailSnap 的目标部署环境是 **NAS + Docker**，其物理特征决定了一切优化方向：

- **CPU 弱、无 GPU**：本机 AI 微服务（PaddleOCR / InsightFace / CLIP）的推理也跑在 **CPU** 上。
- **AI 微服务与 server 通常同机**：两者抢的是**同一份物理 CPU 核**。
- **原图存放在机械硬盘（HDD）**：随机读带宽极低，最怕并发随机读。
- **数据库 / 缩略图存放在固态硬盘（SSD）**：读写快，基本不是瓶颈。

> 关键推论：当前 CPU / IO / AI 三分法的隐含假设是「三类资源正交、互不干扰」，这只在 **AI 跑独立 GPU** 时成立。在 CPU NAS 上，「本机 AI 推理」「server 的 CPU 任务」「HDD 读原图」三者实际争用**同一批物理核 + 同一块机械盘**，三分法不再能描述真实的资源竞争。

---

## 1. 设计意图澄清（这些是刻意设计，不是缺陷）

对照原始设计文档，以下几点是有意为之，应予尊重：

1. **face/ocr/classify/embedding 归为 IO 类**：站在 server 视角，它只是发 HTTP 请求然后 `await`，对 server 而言确是 IO 等待。「是否压垮 AI」的责任被有意下沉给 AI 微服务自己排队。这是合理的关注点分离。
2. **CPU 任务用线程池而非进程池**：`PROCESS_BASIC` 内大量时间花在 HDD 读原图 / MD5 整文件读上（GIL 释放），且进程池在 NAS 上 fork 多进程会内存翻倍、pickle 开销大。**线程池是正确选择**，进程池在此拓扑下不划算。
3. **不依赖认领原子性，而依赖幂等性**：所有任务操作设计为幂等，崩溃后重做不改变结果。因此「claim 无行锁」在单 worker + 幂等前提下可接受。

---

## 2. 任务负载性质重新分解

把 `PROCESS_BASIC`（`basic.py:30-100`）拆开看，它并非纯 CPU，而是 **CPU + HDD IO 混合**：

| 操作 | 真实瓶颈 | 落盘位置 | 说明 |
|---|---|---|---|
| 生成缩略图（解码+缩放+编码） | **CPU** | 读 HDD / 写 SSD | 唯一名副其实的 CPU 密集 |
| 提取 EXIF（读文件头） | **IO（HDD 随机小读）** | HDD | CPU 极轻 |
| 计算 MD5（整文件读） | **IO（HDD 顺序读）** | HDD | 大文件瓶颈完全在 HDD，hashlib 释放 GIL |
| 色彩 / 情绪提取 | CPU | — | 复用已打开的 image_obj |
| 写缩略图 / 写 DB | IO（快） | SSD | 非瓶颈 |

> 结论：`PROCESS_BASIC` 标为 "CPU" 是「以最重的缩略图为准」的近似，掩盖了内部大量 HDD IO 成分。在 HDD 拓扑下，它的真实第一瓶颈往往是 **HDD 读原图**，而非 CPU 核数。

此外，**face/ocr/classify/embedding 在发 AI 请求前也要从磁盘读原图转 base64**（如 `face.py:159-169`）。若 preview 命中 SSD 则只抢 AI 算力；若回退到原图（`face.py:161`）则**同时抢 HDD 读带宽 + 本机 AI 算力**，是双重瓶颈。

---

## 3. 核心问题清单

### 3.1 同机 CPU 超额订阅（最严重，设计前提未贯彻）

设计假设「AI = IO，责任下沉给微服务自行排队」。但在 CPU NAS 同机部署下：

- server 按 IO 并发（实际 4~8）向 AI 微服务发请求 → AI 微服务被迫同时处理 4~8 个 **CPU 推理**。
- AI 推理框架（Paddle / ONNX / OpenBLAS / MKL）默认 intra-op 线程数 = `cpu_count`，**单个请求就能吃满所有核**。
- 与此同时 server 的 CPU 组又在并行解码缩略图。

→ 结果是 **1.5x~2x+ 的 CPU 超卖**：核不够分，大量时间耗在上下文切换与 cache 抖动，**两边都变慢，总吞吐低于错峰串行**。NAS 核少（常见 2~4 核），尤其致命。

「下沉责任」只是把超卖从 server 挪到 AI 服务，**物理核还是那些**。server 端的 AI 请求并发与 AI 微服务自身的线程数，这两个旋钮在同机部署时**必须协同**，当前完全独立放飞。

### 3.2 HDD 随机读并发未被建模（第二严重）

调度只把磁盘当「持久化 / 读写分离」，没把 **HDD 随机读带宽**当作受限资源：

- 读原图的任务（PROCESS_BASIC、EXTRACT_METADATA、face/ocr 回退原图）都打 HDD。
- IO 并发 4~8 意味着 4~8 路**并发随机读**机械盘 → 磁头寻道风暴 → 吞吐断崖下跌，**比串行还慢**。
- 「IO 并发 = 10」这个数字是按**网络 IO**（AI 请求）定的，却和**「HDD 读原图」这种完全不同性质的 IO 混在同一个桶**，用同一并发数不合适。

### 3.3 MD5 二次读盘浪费

缩略图阶段 `Image.open` 已把原图读进内存（`basic.py:44`），但 `calculate_file_md5`（`basic.py:78`）又**独立打开文件把整图从 HDD 再读一遍**。几万张照片在机械盘上等于多读一整轮，且与「读原图做缩略图」抢同一块盘。

### 3.4 前期 AI 模型抖动（内存缓冲破坏优先级抢占，最严重的吞吐杀手）

这是本机 AI 资源利用上最伤性能的问题，由**两个机制叠加**且**集中在处理前期**爆发：

**触发链路：**
1. `PROCESS_BASIC`（CPU 队列）跑得很快，每完成一个就在 `handle_completion`（`basic.py:289-301`）一次性派生 6 个**不同优先级**的下游任务：metadata / face(10) / ocr(7) / classify(9) / embedding(8) / visual(1)。
2. **前期** DB 里这些下游任务总量还不多，IO 队列的 `qsize < QUEUE_THRESHOLD(50)`（`task_worker.py:365`）几乎总成立 → producer 每轮都去 DB 拉，且因总量少，**face/ocr/classify/embedding 多种类型被同时拉进 IO 队列**。
3. IO consumer 并发 4~8（`task_worker.py:445-482`）**同时消费不同类型** → AI 微服务被迫同时持有多个模型，并反复加载/卸载切换。

**内存缓冲是「优先级盲区」**：producer 只在队列低于阈值时才回 DB 拉（`task_worker.py:354-365`），一旦低优先级批次进了内存队列，DB 中**新到的高优先级任务必须等内存队列排空才被看见**——这与「严格优先级抢占」天然矛盾。

**为何只在前期**：到了中后期，PROCESS_BASIC 全部跑完不再产新任务，DB 里积压**大量同一高优先级类型**（如几万个 face=10），producer 按 `priority DESC` 拉取（`task_worker.py:382`）天然全是 face，face 耗尽才轮到 classify → **自动单类型，问题消失**。所以痛点精确落在前期 basic 与下游任务交织的窗口。

**期望行为**：对共享单一 AI 服务的任务，**严格按全局优先级抢占式串行处理**——选当前 DB 里最高优先级的那个类型，把它（在持续产出下）做到耗尽，再切下一类型。这样 AI 服务同一时刻只加载一个模型，模型加载次数从「任务数量级」降到「类型数量级」。

> 权衡：前期并发度看似下降，但省掉的模型反复加载/卸载开销（CPU 推理换模型常达秒级）远大于并发损失，**实际吞吐很可能上升**，且同时只驻留一个模型，内存更稳——对 NAS 尤其划算。代价是单张照片「全部分析完成」的延迟变长（吞吐换延迟，批量场景的正确取舍）；严格优先级下低优先级类型（如 visual）在前期会被饿死，符合预期语义。

### 3.5 builtin / external 视觉描述的并发判定反了

`task_worker.py:389-392`：

```python
if cat == 'AI' and task.owner_id:
    if user_config.ai.analysis_connection_id == 'builtin':
        cat = 'IO'   # builtin 被丢进高并发 IO 队列
```

- **本机 builtin LLM**（最稀缺、还和 face/ocr 抢同机 CPU）→ 被放进并发 4~8 的 IO 桶 → 打爆本机推理。
- **外部 API**（不占本机资源、天然高并发、按量付费）→ 留在 AI 桶锁死并发 1 → 白白浪费云端并行，描述任务极慢。

两个方向恰好都配反：**builtin 该严格串行，external 该放开高并发**。

### 3.6 face 聚类的同 owner 竞态

`assign_face_to_identity` / `process_unassigned_faces`（`face.py:215-223`）修改**同一 owner 的 identity 全局状态**。同一用户的多个 face 批次在 IO 桶里 4~8 并行时，两个本应合并的新面孔可能各自建 identity，产生竞态。这也使「幂等性」假设在 face 上不完全成立。**face 应按 owner 串行**。

### 3.7 全库级任务缺少单例约束

`SIMILAR_PHOTO_CLUSTERING` / `FIND_DUPLICATE_PHOTOS` / `ORGANIZE_PHOTOS` / `BATCH_RENAME` 等操作全库或大范围状态，但当前**没有「同类型同时只跑一个」的约束**。用户连点两次会并行跑两个全库聚类，互相覆盖结果。

### 3.8 cancel 不生效

`cancel_task`（`crud/task.py:154-158`）仅置状态为 CANCELLED。任务一旦进入 PROCESSING 并下发到内存队列/线程池，**无法中断**；且 `_flush_results` 回写时不检查 CANCELLED，会覆盖/删除该行。取消语义是假的。

### 3.9 `_flush_results` 整批 rollback 导致结果丢失

`handle_completion` 抛异常会触发整批 `db.rollback()`（`task_worker.py:770-772`），**同批次其它本应删除/标记失败的结果全部丢失**，这些任务下次又被重跑。

### 3.10 空转的进程池

`ProcessPoolExecutor` 在 `start()` 时 fork 了 `cpu_count` 个进程（`task_worker.py:220`），但**全代码无任何 strategy 使用它**（已确认）。每个子进程 fork 了整个应用内存却零提交，**纯浪费内存**——对内存紧张的 NAS 是实打实的损耗。

### 3.11 文档与实现漂移

| 项 | 设计文档 | 实际代码 |
|---|---|---|
| IO 并发 | 10 | 4 / 8 |
| AI 并发 | 2 | 1 |
| 优先级 | SCAN=10, BASIC=9 | SCAN=100, BASIC=99（`task.py:37`） |
| 进程池 | 「CPU 密集型用 ProcessPool」 | 从未使用，空转 |
| 状态 | 4 态 | 实有 CANCELLED 第 5 态 |

### 3.12 其它小问题

- `get_task`（`api/tasks.py:225-240`）对不存在的任务**伪造一个 COMPLETED 假 Task**，掩盖 404，前端无法区分「已完成被删」与「ID 不存在」。
- `PRESERVED_TASK_TYPES = set()`（`task_worker.py:709`）恒为空，所有 COMPLETED 任务立即删除，**完成历史不可查**（`grouped_status` 中 completed 恒为 0）。
- `task_worker.py:6` `from re import S` 无用误导入。
- scheduler weekly 模式按分钟字符串精确匹配（`task_manager.py:237`），循环在 sleep 时可能**错过该分钟**；多进程部署会重复触发。

---

## 4. 任务并行 / 串行矩阵（CPU NAS 前提下的目标）

| 任务 | 竞争的瓶颈资源 | 目标并发 | 理由 |
|---|---|---|---|
| 缩略图解码 / 色彩 | 本机 CPU | 与本机 AI **共享核预算** | GIL + 同机 AI 抢核 |
| EXIF / MD5 / 读原图 | **HDD 读带宽** | **低（1~2）全局闸** | 机械盘怕并发随机读 |
| face / ocr / classify / embedding（本机 AI） | 本机 CPU 推理算力 | **全局 AI 闸（1~2）** | 同机单份算力 |
| face 聚类写 identity | 同 owner 可变状态 | **同 owner 串行** | 避免 identity 竞态 |
| visual_description（builtin） | 本机 LLM | **串行** | 最稀缺，当前配反 |
| visual_description（外部 API） | 云端，不占本机 | **高并发 8~16** | 解耦本机，当前配反 |
| EXTRACT_METADATA（纯解析写 DB） | SSD / CPU 轻 | 中等并发 | 不压 HDD 时可放开 |
| 全库聚类 / 去重 / 整理 / 改名 | 全库状态 / 文件路径 | **同类型 / 同 owner 单例** | 避免重复并行覆盖 |
| 缩略图重生成 / 读 DB 类 | SSD | 高并发 | SSD 快，非瓶颈 |

**数据依赖（必须有序）**：`SCAN_FOLDER → PROCESS_BASIC →（派生）metadata / face / ocr / classify / embedding / visual_description`。阶段间靠「PROCESS_BASIC 完成后才创建下游任务」隐式保证（`basic.py:289-301`），设计正确；同一张图的下游 6 个任务彼此无依赖、可并行（但受上表资源约束）。

---

## 5. 优化方案（按收益排序）

### P0 — 消除前期 AI 模型抖动（单类型抢占调度，零额外查询）

针对 3.4，目标是让本机 AI 服务**同一时刻只加载一个模型**、严格按全局优先级抢占。三步：

1. **本机 AI 任务单独成组，并发 = 1**
   把 face/ocr/classify/embedding/builtin-visual 从 IO 桶拆出归为「本机 AI 组」，consumer 并发设为 1（或显存允许的极小值）。单这一步即可消灭「同时加载多模型」——同一时刻只有一个类型在打 AI 服务。
2. **生产端「单类型锁定」，且复用现有查询（无新增 SQL）**
   `_fetch_tasks_to_queues_sync`（`task_worker.py:378-382`）现有的
   `SELECT ... WHERE status='pending' ORDER BY priority DESC, created_at ASC LIMIT 144`
   **返回结果本身就按优先级排好序**，且走索引 `ix_tasks_status_priority_created`（`task.py:115`），成本 O(LIMIT) 与表大小无关（十几万 pending 也只读前 144 个索引项）。
   改动只在**内存层**：对本机 AI 组，从已取回的行里按 type 分组后**只取优先级最高的那一个 type 的批次入队**，其余类型本轮丢弃（不入队、不改状态）。因结果已排序，直接取 `tasks[0].type` 作为锁定类型即可。**不增加任何数据库查询。**
3. **本机 AI 组内存缓冲压到 ≈1 批**
   去掉该组的 50 条大缓冲，让每轮都重新评估 DB 里的最高优先级类型，保证前期新涌入的高优先级任务（如持续产出的 face）立即抢占，不被已缓冲的低优先级批次挡住。

**行为特征**：前期 fetch 回的 144 行虽混类型，但只挑最高优先级类型入队，PROCESS_BASIC 持续产出使该类型保持最高 → 一个模型做到底；中后期 DB 积压本就单类型，新逻辑取最高类型≈全部，**行为与现状一致、零额外开销**。痛点精确收敛在前期，中后期不受影响。

> 效益：前期并发度略降，但省掉模型反复加载/卸载（CPU 推理换模型常达秒级）的开销远大于并发损失，**实际吞吐很可能上升**，内存占用更稳（同时只驻留一个模型）。

### P0 — 治理同机 CPU 超额订阅（收益最大）

分两层，缺一不可：

1. **钳制 AI 微服务自身线程数**（治本的一半）
   给 AI 服务设固定 `OMP_NUM_THREADS` / `cv2.setNumThreads()` / ONNX `intra_op_num_threads`（如核数一半），让单个 AI 请求不再独吞全核。否则上层任何限流都无效。
2. **让「本机 CPU 任务」与「本机 AI 任务」共享一个全局核预算**
   不要 CPU 组与（藏 AI 的）IO 组各自独立放飞。引入一个上限 ≈ 物理核数的全局信号量，二者共用：「此刻要么多跑几个解码、要么跑一两个 AI 推理，但加起来别超核数」。外部 API 任务不占此预算。

### P0 — 修正 builtin / external 视觉描述判定

把 `task_worker.py:389-392` 的逻辑反过来：**builtin → 串行（进本机 AI 桶）；external → 高并发**。并把这一判定**通用化**：所有 AI 任务都按其 `ai_api_url` / `connection_id` 指向本机还是外部，动态归入「本机 AI 桶」或「远程 AI 桶」，而非只对 visual_description 特判。

### P1 — 为「HDD 读原图」加全局低并发闸

在所有读原图处（PROCESS_BASIC 读阶段、metadata、face/ocr 回退原图）前加一个 **全局信号量（1~2）**，把机械盘随机读收敛为接近顺序读。线程池本身可保持较大（让 SSD 写 / DB / CPU 解码并行），但**「读 HDD 原图」这一动作单独限流**——即「线程池大小」与「HDD 读并发」解耦成两个独立旋钮。

### P1 — 消除 MD5 二次读盘

复用缩略图阶段已读入内存的原图数据流顺带计算 MD5，避免第二次打开文件全量读 HDD；或评估用「文件大小 + mtime + 采样块哈希」替代全文件 MD5 做去重判断，把整文件读降为几次小读。

### P1 — face 任务按 owner 串行

对同一 owner 的 face 批次加串行约束（或 per-owner 锁），消除 identity 聚类竞态，使幂等假设成立。

### P1 — 修复 `_flush_results` 整批 rollback

把 `handle_completion` 的异常隔离到单个 type / 单条任务，避免一个失败回滚整批，保证已完成结果不丢失。

### P2 — 全库级任务单例约束

入队前检查同类型（或同 owner）是否已有 PENDING/PROCESSING，有则拒绝或合并，避免重复并行。

### P2 — 让 cancel 真正生效

worker 执行批次时定期检查任务是否被置 CANCELLED；`_flush_results` 回写前跳过已 CANCELLED 的任务，不覆盖其状态。

### P2 — 清理与对齐

- 删除空转的 `ProcessPoolExecutor` 及 `_manage_pool_lifecycle` 中管理它的逻辑，省 NAS 内存。
- `get_task` 对不存在任务返回 404，不伪造假 Task。
- 缓存 `task_type → category` 映射（注册时构建一次），去掉 `worker_loop` 每轮重复的 `get_strategy().task_category`。
- 修正 scheduler 时间匹配（用时间窗口而非精确分钟字符串）；多进程部署用 DB 行锁/唯一约束防重复触发。
- 同步设计文档中漂移的并发数、优先级数值、进程池描述、状态枚举。

---

## 6. 一句话总结

当前架构默认「AI = 独立资源」，所以敢让 CPU / IO / AI 三组无约束并行。**在 CPU NAS + 原图在 HDD 的真实拓扑下，这个前提崩了**：本机 AI 推理与 server 的 CPU 任务抢同一批核，多个 IO 任务并发随机读同一块机械盘。最该做的四件事是——
1. **本机 AI 任务单类型抢占调度 + 并发=1**（治前期模型抖动，零额外查询）；
2. **钳制 AI 服务线程数 + 让本机 CPU/AI 共享核预算**（治 CPU 超卖）；
3. **给 HDD 读原图加低并发全局闸**（治寻道风暴）；
4. **把 builtin/external 视觉描述的并发判定反过来**（本机串行、云端放开）。

并发上限要绑定到「实际竞争的物理资源（核 / HDD 带宽 / 本机算力）」，而不是绑定到「任务叫什么名字」。模型加载次数要降到「类型数量级」，而非「任务数量级」。
