# 桌面人脸识别 CPU 利用率调查（2026-10-12）

## 结论

当前桌面运行现场的主要瓶颈是 **SQLite 人物匹配查询的执行计划，以及慢查询占用写事务和人脸任务槽位形成的反压**。不是 SQLite 提交刷盘慢，也没有证据表明 AI 接纳队列是主因。CPU 周期性冲高再回落，符合推理完成后等待后端匹配、落库，再发送下一批的链路。

初始调查使用实际运行进程的日志、py-spy 采样和 SQLite 只读查询。当时未修改应用代码或用户数据，SQL 对照只验证查询性能。后续源码修复与验证见本文最后一节。

## 运行现场

- 桌面主后端 PID 49556，任务 worker PID 63712，AI PID 63960。
- 通过进程打开文件确认实际运行数据库是 `%LOCALAPPDATA%/TrailSnap/data/trailsnap.sqlite`。桌面目录指针中的其他路径不能代替这项运行时证据。
- 固定只读事务开始于本地时间 00:46:21：21,763 张照片、992 条人脸，已归属人物的人脸为 0。
- 运行日志显示人脸批大小已经是 8，且同时存在两个人脸请求；不能把源码原先较小的批次配置直接当成本次现场原因。
- 当前模型为 `buffalo_m`，实际 ONNX provider 是 `CPUExecutionProvider`，没有使用 RTX 4090。

## 日志统计

取 00:33:50 后至统计时的当前运行日志。主后端和 AI 各自统计，没有请求关联 ID，因此两组中位数不能直接相减当作精确分阶段耗时。

| 指标 | 样本数 | 中位数 | P95 | 最大值 |
| --- | ---: | ---: | ---: | ---: |
| 后端人脸批次总时间（每批 8 张） | 106 | 7,806.3 ms | 25,748.2 ms | 42,403.2 ms |
| 后端 commit 时间 | 106 | 0.8 ms | 8.1 ms | 207.7 ms |
| 后端写入协调锁等待 | 106 | 0.0 ms | 8,789.9 ms | 21,869.7 ms |
| AI 人脸请求总时间 | 108 | 1,494.9 ms | 5,486.1 ms | 11,608.0 ms |
| AI 接纳等待 | 106 | 0.0 ms | 0.1 ms | 0.4 ms |

日志位置：`%LOCALAPPDATA%/TrailSnap/logs/server.log`、`ai.log`。commit 时间不覆盖全部 SQL、flush 或匹配计算，不能因为 commit 很快就排除数据库查询。

## 采样证据

用 `uvx py-spy record --pid <PID> --duration <秒数> --rate 20 --idle --format speedscope` 采样运行进程：worker 30 秒，AI 20 秒，均无采样错误。

- worker 的 `task-batch_1` 在约 29.95 秒采样中有约 15.35 秒位于 `_resolve_assigned_candidates`；`task-batch_2` 也有约 4.55 秒位于此处。
- 另一个批次线程有约 11.05 秒位于 `_admit_writer` 等待写入协调锁。
- 任务结果删除、扩展等待状态更新也出现 SQLite 写入等待，说明长写事务影响同库其他任务。
- AI 8 个 `face-batch` 线程的 `process_image` 栈时间合计约 20.35 线程秒，占 8 × 19.95 线程秒的约 12.8%。这是线程栈驻留比例，**不是系统 CPU 使用率**；ONNX 原生线程不在这项 Python 线程比例中。它说明图片处理线程多数时间没有在处理图片，支持请求供应不足的判断。

采样文件保存在本机临时目录：

- `%TEMP%/trailsnap-face-server-profile.json`
- `%TEMP%/trailsnap-face-ai-profile.json`
- `%TEMP%/trailsnap-face-query-benchmark.json`（固定只读事务 SQL 对照原始结果）

## 慢查询及放大机制

`package/server/app/service/face_cluster.py:175` 的 `_resolve_assigned_candidates` 验证有限的人脸候选 ID，但现有 JOIN 被 SQLite 规划成：

```text
SEARCH photos USING INDEX ix_photos_owner_id (owner_id=?)
SEARCH faces USING INDEX idx_face_photo_id (photo_id=? AND rowid=?)
```

这意味着先遍历用户的照片，再结合候选 ID 查询人脸，候选数量扩大时成本迅速上升。

当前已归属人物的人脸为 0，而 `_sqlite_nearest_assigned_face` 仍为每个新检测的人脸扩大验证窗口，直到遍历全部候选。没有可匹配人物时，这些查找必然返回空结果。

`package/server/app/service/tasks/face.py:225` 先 flush 新人脸，再在同一事务调用 `assign_face_to_identity`。`AIBatchSession` 从首次写入持有进程内 SQLite 写入协调锁，直到 commit/rollback/close。因此上述慢查询在持锁状态执行，其他批次即使已经推理完成，也只能等待。

人脸资源限制覆盖整个批次，包括读取图片、AI 请求、人物匹配和写入。两个批次都在匹配或等写锁时，下一批不会进入 AI，形成推理阶段有负载、结果处理阶段大量空闲的周期。单纯增加 AI 并发会进一步积压结果，不能解决慢查询。

## 只读 SQL 对照

在同一固定只读事务里，选取同一组候选 ID，对照现有 JOIN 与相关 EXISTS，每项重复三次取中位数。应用继续运行，所以耗时有负载波动；两种查询均返回 0 条，与当前没有已归属人脸一致。没有执行 UPDATE、INSERT、DELETE、ANALYZE 或建索引。

| 候选数 | 现有 JOIN | 相关 EXISTS |
| --- | ---: | ---: |
| 64 | 498.175 ms | 0.029 ms |
| 448 | 1,137.422 ms | 0.118 ms |
| 954 | 4,902.936 ms | 16.179 ms |

EXISTS 对照保留人脸未删除、已归属人物和用户隔离条件：

```sql
SELECT faces.id, faces.face_identity_id
FROM faces
WHERE faces.id IN (...)
  AND faces.face_identity_id IS NOT NULL
  AND faces.is_deleted = 0
  AND EXISTS (
    SELECT 1 FROM photos
    WHERE photos.id = faces.photo_id AND photos.owner_id = ?
  );
```

对应计划先通过人脸整数主键读取候选，再通过照片主键验证归属，不再从所有用户照片开始循环。954 个候选的查询中位数约改善 303 倍；这是空结果候选验证的微基准，不能宣称整个人脸任务也快 303 倍。已有归属人物的数据仍需另行验证正确性和性能。

## 与分类、embedding 的差异及修复优先级

分类和 embedding 没有人脸链路中的逐人脸全库近邻验证及人物归属步骤，所以相同任务调度器下仍可以很快完成并继续供给 AI。

建议修复顺序：

1. 将 SQLite 候选验证改为从人脸 ID 驱动、通过 EXISTS 保持用户隔离；为没有已归属人物的批次增加一次存在性检查，避免每个人脸反复做必然无结果的匹配。
2. 缩短持有 SQLite 写事务的范围，对多个新脸批量匹配；明确处理同批新增人脸、人物归属变化及事务回滚的语义后再调整计算位置。
3. 修复后用实际图库比较单位时间完成照片数、批次耗时和写锁等待，再判断是否需要调整并发。CPU 跑满本身不是吞吐改善的验收标准。
4. AI 还有独立优化机会：当前 `FaceAnalysis` 未限定 `allowed_modules`，运行日志确认除了检测、识别，还加载并执行 3D/106 点关键点和年龄性别模型；接口输出只消费检测框、五点关键点、置信度和 embedding。可评估仅保留 detection/recognition。本次没有量化裁剪收益。人脸模型初始化也未传入项目统一的 `get_session_options`，这一点需要在推理专项测试中单独核实。

本次调查没有发现 AI 接纳等待明显积压；AI CPU 推理仍有自身成本，但已证实的首要瓶颈应先在后端匹配查询和事务范围解决。

## 源码修复与验证

用户后续授权修复并测试后，修改了 `package/server/app/service/face_cluster.py`：

- SQLite 候选验证共享同一套资格条件，通过相关 EXISTS 验证用户归属，从候选人脸主键开始查询。
- 近邻匹配前查询是否存在其他未删除且已归属人物的参考脸；没有参考时直接返回，不加载向量、不扩大候选窗口。
- 存在性检查每次读取当前事务状态，不缓存否定结果，避免后续新增归属、外部修改或回滚后使用过期判断。
- 保留原有排除自身、用户隔离及人脸删除过滤语义，未改动 PostgreSQL 近邻分支、数据库模型、任务并发或 AI 模型。

没有挪动事务边界或取消 SQLite 写入协调锁；通过消除持锁期间的慢查询缩短匹配耗时。已有未提交的 AI 运行时与任务批次改动保持原样。

### 正确性

新增真实 SQLite 回归覆盖：无参考时跳过向量与候选窗口、后续新增人物归属可见并验证回滚、用户隔离/删除状态和候选主键执行计划、仅有已删除参考时跳过向量。原有最近人物选择、排除自身、向量增量缓存和聚类回归继续通过。

运行仓库统一测试入口：

```powershell
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component server -Level smoke
```

结果：**2887 passed、48 deselected**，耗时 227.61 秒；现有弃用、marker 和部分 mock 协程警告未阻止通过。此次没有修改 AI 实现，因此未重复运行 AI 测试。

### 修复前后匹配对照

新增可复现脚本 `package/server/scripts/benchmark_face_matching.py`。通过 SQLite backup API 从只读源建立临时备份，所有归属场景修改仅发生在临时备份里；保留图库的照片、向量和索引布局，不修改运行数据库。脚本显式关闭 sqlite3 连接以支持 Windows 临时目录清理。

基线为 `eb00dae13b22c81d7984043ef8c6df2e91b558d8` 的原始两个匹配方法，通过 AST 提取并与当前方法使用相同 ORM、向量缓存和同一份数据。最终成功运行开始于 00:56:11，备份有 **21,763 张照片、1,078 张脸**。两种场景各处理相同的 8 个目标人脸，每项三轮，第一轮包含冷缓存成本，中位数如下：

| 场景 | 修复前 | 修复后 | 匹配阶段速度比 |
| --- | ---: | ---: | ---: |
| 没有已归属参考脸 | 32,563.724 ms | 142.382 ms | 228.7 倍 |
| 有 67 张已归属参考脸 | 1,807.488 ms | 585.136 ms | 3.09 倍 |

两种场景每一轮的匹配人脸 ID、人物 ID 和距离均与基线一致。无人归属场景优化后向量缓存行数为 0，旧实现为 1,078，证明没有再加载不必要的向量。已有归属场景保留原先的向量缓存和匹配计算。

原始数据：[face-matching-20261012.json](face-matching-20261012.json)。重跑示例（在仓库根目录使用 server Python 环境）：

```powershell
package/server/.venv/Scripts/python.exe package/server/scripts/benchmark_face_matching.py `
  --database "$env:LOCALAPPDATA/TrailSnap/data/trailsnap.sqlite" `
  --baseline-ref eb00dae13b22c81d7984043ef8c6df2e91b558d8 `
  --output doc/performance/face-matching-rerun.json
```

脚本输出明确限定为 SQLite 近邻匹配，不包含照片读取、AI、落库提交或调度。测试时桌面任务仍运行，部分时间与冒烟测试重叠，存在负载波动；不能把速度比直接作为整个人脸任务的提速比例。此阶段只修改、验证源码，后续桌面安装与端到端测试如下。

## 桌面重建、安装与实际测速

按用户要求重新构建 website、Server PyInstaller runtime 和 Tauri NSIS 安装包，三个构建均成功。安装包为 `package/desktop/src-tauri/target/release/bundle/nsis/TrailSnap_0.17.3_x64-setup.exe`，本地构建关闭 updater 签名产物，不改动仓库配置。AI 扩展未重建，保持原有 buffalo_m 模型和 CPUExecutionProvider。

- 安装包 SHA256：`E53D73731498978011EF24602079C9FDCF674032428165A11EB3AFBCEA22C544`。
- 已安装 Server 与新构建 Server 的 SHA256 一致：`11A35C0FD214C21FCE8BE996ECB8026A044EC80706B6CAC47384EF3BD8F4CE80`。检查 PyInstaller 内三个修改方法的字节码与当前源码一致。
- 安装前通过 SQLite backup API 备份原图库，quick_check 为 ok。备份在 `%LOCALAPPDATA%/TrailSnap/data/trailsnap.before-face-install-20261012.sqlite`；旧 Server 保留在 `%LOCALAPPDATA%/TrailSnap/server-before-face-20261012`，旧桌面程序也保留副本。
- 原桌面目录指针指向已不存在的 E 盘目录，先备份指针，再恢复为实际运行的 `%LOCALAPPDATA%/TrailSnap` 和端口 54940。安装后确认使用原图库，健康检查 HTTP 200。

通过已安装桌面的 API 对同一批 32 张有人脸照片强制重新识别，旧版和新版各先预热 8 张。测试时暂停其他后台类型，保存并最终恢复原暂停设置。交互任务使用单照片批次，端到端计时包括 worker 启动、读取、AI 推理、数据库写入和任务完成。

| 指标 | 安装前 | 安装后 |
| --- | ---: | ---: |
| 同一批 32 张端到端耗时 | 355.44 秒 | 63.00 秒 |
| 吞吐 | 0.090 张/秒 | 0.508 张/秒 |
| 单照片批次耗时中位数 | 13,916.6 ms | 1,638.8 ms |
| Server 与 AI 平均 CPU（按 28 逻辑处理器归一化） | 20.9% | 71.9% |
| 系统平均 CPU | 39.1% | 86.6% |
| 最大 SQLite writer 等待 | 10,254.8 ms | 103.7 ms |
| 任务失败数 | 0 | 0 |

本次同批端到端速度约为旧版的 **5.64 倍**。对安装前数据库备份与新结果逐张核对：均为 38 张人脸，数量一致，检测框和 embedding 在浮点容差内一致（框 atol=1e-6，embedding atol=1e-5，使用 NumPy 默认 rtol）。旧版测量的一部分时间与 NSIS 压缩重叠，且保持原来的自动并发设置，因此该速度比是本次真实运行观测，不代表所有图库固定提速倍数。

随后仅恢复普通后台人脸检测，测量约 60.09 秒：完成 28 个八照片批次，共 **224 张照片，3.73 张/秒**；批次耗时中位数 1,770.3 ms，Server 与 AI 平均 CPU 62.1%，系统平均 CPU 82.4%，最大 writer 等待 1,174.8 ms。此项包含 worker 启动，照片与对照批次不同，仅用于验证新版普通后台持续吞吐，不能与前面的单照片速度直接比较。

测试结束后恢复原状态：仅 IMAGE_EMBEDDING 保持原先暂停，其他临时暂停类型恢复，AI 扩展状态 ready，健康检查 HTTP 200，桌面继续运行。详细计时、批次日志数据和 CPU 样本见 [desktop-face-live-20261012.json](desktop-face-live-20261012.json)。未提交代码、发布版本或修改 PostgreSQL 实现。
