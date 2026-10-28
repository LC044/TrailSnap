# REQ-209：扫描入队与基本处理调度对照

2026-10-28，Windows，28 个逻辑核。同一台机器顺序运行基线与修改版各三轮，取中位数。基线为 `5764ed6c1232cbb4f7ecf9fb3dce43349f29a51e`，修改版为本次未提交工作区。测试没有停止本机其他应用，存在系统负载波动，不属于专用性能实验机数据。

## 结果

| 指标 | 修改前 | 修改后 | 变化 |
|---|---:|---:|---:|
| 12,000 文件入队 | 50.926 秒 | 5.356 秒 | 9.51 倍速度，耗时减少 89.5% |
| 每轮最长写锁持有时间的中位数 | 6.735 秒 | 0.059 秒 | 减少 99.1% |
| 每轮累计写锁持有时间的中位数 | 50.641 秒 | 0.956 秒 | 减少 98.1% |
| 96 张照片基本处理与入库 | 17.024 秒 | 4.722 秒 | 3.61 倍速度，耗时减少 72.3% |
| 基本处理吞吐 | 5.64 张/秒 | 20.33 张/秒 | 3.61 倍 |
| 基本处理开始至首张提交 | 1.193 秒 | 0.808 秒 | 减少 32.3% |
| 回放条件下最终 CPU 批次并发 | 1 | 4 | 恢复导入保留能力 |

原始数据：[before.json](before.json)、[after.json](after.json)。96 张 JPEG 的逐文件 SHA-256 在两份报告中一致。

## 测量内容与限制

- 扫描测试使用临时目录内 12,000 个文件，调用生产 `_create_tasks_for_new_files`，真实执行 SQLite WAL 查询、路径解析、任务插入和提交；衡量发现文件后的**入队阶段**，不包含目录枚举、已有图库清理、完整 SCAN 生命周期或界面刷新。写锁计时从用户互斥 UPDATE 开始至提交，包含该 UPDATE 可能的等待。
- 基本处理使用固定随机种子 209 生成的 96 张 2400×1600 JPEG，真实运行生产任务执行器、解码、基础元数据、MD5、两种 WebP 缩略图和照片/下游任务落库；照片数量与非空 MD5 均有断言。为了独立测量任务完成时间，基准按单结果确认入库，生产结果循环按批次或时间刷入，首张提交数据不等同 UI 首屏时间。
- 两版均回放 `cpu=99%, memory=50%`，从历史 `cpu=1` 并发开始，线程池、图片配置和磁盘预算相同。这验证调度对**历史降速状态和持续 CPU 压力**的应对；并未同时运行真实 AI 模型，因此不代表完整导入+AI 管线的端到端加速比。只读诊断期间观察到的真实 AI 竞争与此基准分开报告。
- 临时数据库、原图与缩略图均在系统临时目录中生成并在成功结束后清理；不读写用户安装实例或私人照片。不升级/重启 `D:\Program Files\TrailSnap` 中的程序。

## 行为变化

1. 文件真实路径按扫描生命周期缓存，批量规范化在写锁外执行。每批 500 条，锁内只查询本批候选；不再反复加载、解析整个待处理队列。任务保存 `scan_path_key` 用于并发扫描的规范路径去重，保留原始 `file_path`。锁内重新读取目录配置，保证移除目录后不能继续入队。
2. 存在可执行的 SCAN/BASIC 或在途导入时，不再接收后台 AI 新批次；预取任务退回待调度状态，在途推理自然完成，交互优先级任务仍可运行。导入清空后自动恢复；暂停或等待重试的导入不会无限阻塞 AI。
3. 基本处理保留至多 4 个批次的最低并发（受机器档位上限限制）；CPU 压力下降并发时保留该能力。内存达到高水位时下限降为 1，仍可限流；磁盘预算继续生效。此处的 4 是批次，每批 4 张且批内顺序执行。
4. AIMD 的连续降速增加冷却；同一轮并发反馈不再毫秒级连续减半。默认仍为 5 秒，配置为 0 时保留无冷却语义。

## 复现

在仓库根目录，使用已有 `tests/.env.test` 配置；脚本显式创建隔离数据库，不连接配置中的业务数据库进行测试。

```powershell
.\package\server\.venv\Scripts\python.exe -X utf8 package/server/scripts/benchmark_import_priority.py --baseline --rounds 3 --output doc/performance/import-priority-20261028/before.json
.\package\server\.venv\Scripts\python.exe -X utf8 package/server/scripts/benchmark_import_priority.py --rounds 3 --output doc/performance/import-priority-20261028/after.json
```

相关回归使用统一入口，148 项通过（另有 3,787 项按范围未选择）：

```powershell
$env:PYTEST_ADDOPTS='-k "adaptive_limiter or ai_priority_preemption or gallery_reconciliation or scan_folder_helpers or task_execution_reliability or task_worker or ai_batch_performance"'
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component server -Level smoke
Remove-Item Env:PYTEST_ADDOPTS
```

覆盖重复扫描、并发别名去重、两批之间移除目录、晚到完成回调、文件解析不持有写锁、导入阶段 AI 让路/交互执行/结束恢复、过载冷却、历史低并发恢复和内存保护。`git diff --check` 通过。
