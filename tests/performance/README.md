# 文件夹扫描性能测试

完整本地 AI 链路、E2E v1 数据集、三档资源模拟及每日 CI 见 [定期导入性能基准](IMPORT_BENCHMARK.md)。

一条命令在**全新空白测试库**上跑“添加图库 → 文件夹扫描 → 本地处理链路”，
统计每个任务类型的排队耗时、执行耗时、完成吞吐，并输出 Markdown / JSON /
CSV 报告。默认不启动 AI 服务，只测本地链路。

## 一键运行

```powershell
# 默认：生成 100 张测试照片，启动 server，重建测试库，测完关服务 + 删库
pwsh .\tests\scripts\run-perf.ps1

# 用已有照片目录（真实图库；-Photos 会被忽略）
pwsh .\tests\scripts\run-perf.ps1 -SourceFolder 'D:\Photos\sample'

# 更大规模
pwsh .\tests\scripts\run-perf.ps1 -Photos 500

# 保留现场（server 和测试库都不删）
pwsh .\tests\scripts\run-perf.ps1 -KeepServices -KeepDatabase

# 自定义停滞判定（扫描结束后连续无进展多少秒算失败；默认 120s）
pwsh .\tests\scripts\run-perf.ps1 -StallSeconds 180

# 指定报告目录
pwsh .\tests\scripts\run-perf.ps1 -OutputDir .\tests\artifacts\performance\baseline
```

> 使用 `-SourceFolder` 时不需要传 `-Photos`，传了也会忽略。

报告默认写入 `tests/artifacts/performance/<run-id>/`：

| 文件 | 内容 |
|---|---|
| `report.md` | 人类可读报告：总耗时、吞吐、各任务耗时分布、失败任务、环境 |
| `report.json` | 完整原始指标，便于 CI 比较基线 |
| `tasks.csv` | 每个任务的排队/执行/总耗时明细 |
| `console.log` | benchmark 控制台输出 |
| `server.log` | 本次启动的 server 日志（可定位时） |

## 测什么

默认暂停 6 个 AI 任务类型（人脸、OCR、分类、向量、视觉描述、票据识别），
只保留本地链路：

```
SCAN_FOLDER（扫描目录）
  └─ PROCESS_BASIC ×N（解码、缩略图、基础信息）
       └─ EXTRACT_METADATA ×N（EXIF/GPS/时间等元数据）
```

因此不需要启动 AI 服务，适合在开发机或 CI 上快速回归。完整 AI 链路
（人脸/OCR/分类/向量/描述）是后续扩展项，当前版本不把它混入“链路排空”和
报告通过判定，避免 AI 服务未就绪时产生假通过。

## 指标口径

- **总耗时**：从调用“添加图库”接口开始，到最后一个核心任务完成（或扫描状态变化）
  为止；用于确认排空的 2 秒安静窗口不计入耗时。
- **扫描任务耗时**：`SCAN_FOLDER` 从创建到完成，包含排队 + 枚举文件。
- **排队耗时**：任务创建 → 开始处理（优先使用数据库时间戳）。
- **执行耗时**：开始处理 → 完成（客户端单调时钟）。
- **总耗时 P50/P95**：排队 + 执行；下游任务没有 `task.created` 事件时也能正确
  计入排队时间。
- **吞吐**：照片数 / 总耗时，单位“张/秒”。

退出码：

| 退出码 | 含义 |
|---|---|
| `0` | 通过 |
| `2` | 基本完成但有异常（例如扫描新增数不一致） |
| `3` | 总超时 |
| `4` | 停滞（扫描结束但任务长时间无进展） |
| `1` | 任务失败 / 执行错误 / 清理失败 |

已完成的任务行会被后端删除，因此耗时主要来自 `/tasks/events` SSE 事件到达时的
客户端单调时钟；排队时间优先使用数据库时间戳。`/tasks/` 轮询只作为兜底，
用于补上漏掉的 `processing` 快照。

## 环境变量

脚本读取 `tests/.env.test` 中的 `TS_API_BASE_URL` / `TS_DB_URL` 等，并提供以下
可选覆盖项（通常不需要手改）：

| 变量 | 默认 | 作用 |
|---|---|---|
| `TS_PERF_PHOTO_COUNT` | 100 | 自动生成的测试照片数 |
| `TS_PERF_SOURCE_FOLDER` | — | 复用已有照片目录 |
| `TS_PERF_TIMEOUT_SECONDS` | 300 | 等待链路排空的上限 |
| `TS_PERF_STALL_SECONDS` | 120 | 连续无任务完成多久判定停滞并提前收尾 |
| `TS_PERF_SETTLE_SECONDS` | 2 | 判定“排空”前的安静窗口 |
| `TS_PERF_PAUSE_SETTLE_SECONDS` | 6 | 暂停 AI 任务后等待 worker 同步的时间 |
| `TS_PERF_POLL_INTERVAL` | 0.5 | `/tasks/` 兜底轮询间隔 |

## 约束与安全

- 仅支持 `-Mode dev`（本地 uv 进程）。docker 模式的宿主机照片目录映射尚未纳入。
- 默认会 **DROP `TS_DB_URL` 指向的测试库** 再重建。运行前确认它指向独立测试库，
  不要指向个人开发库。脚本只会删除库名包含 `test`/`perf`/`ci` 的 PostgreSQL 库，
  否则直接拒绝；仓库默认的 `tests/.env.test` 就是独立测试库。
- 自动生成的照片放在 `tests/.cache/performance-scan/<run-id>/photos/`，测后删除；
  用 `-KeepFixture` 可保留。已有目录只登记为外部图库，不会删除源文件。
- 测试结束后会先停止本次启动的服务，再删除测试库；`-KeepServices` /
  `-KeepDatabase` 可分别保留。服务生命周期脚本不会覆盖这里显式设置的
  重置/保留开关。
