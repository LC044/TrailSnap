# 定期导入性能基准

复用 CI E2E 的 smoke 和 p0 数据目录，固定提交见 `import-v1.json`，版本为 v1。
照片、数据库、模型缓存和报告均不提交到仓库。只记录数据版本与提交，不维护内容清单。

## 运行

需要 Linux Docker 引擎和 Python 3.10+；Windows 可在 WSL 中运行。先构建当前代码：

```bash
docker build --build-arg RAILWAY_HISTORY_SEED_REQUIRED=false -t trailsnap-import-benchmark:local package/server
cp tests/.env.test.ci tests/.env.test
pwsh tests/scripts/run-tests.ps1 -Layer performance -Scope import
```

同一脚本默认依次执行 low / medium / high，各一轮。每档对 server 和 ai **分别**限制
1 / 2 / 4 CPU 与 3 / 4 / 5 GiB 内存，PostgreSQL 固定 0.5 CPU / 1 GiB，禁用 swap。
这是同一主机的资源预算模拟，不等于三种真实 CPU、磁盘或 GPU。CI runner 的可用 CPU
不足时，高档配额也不会创造额外算力；报告保留 Docker 主机信息与实际容器限制。
各档固定 `ORT_INTRA_OP_THREADS=1` 和 `AI_INFERENCE_THREADS=1`，避免推理库按宿主机
全部 CPU 创建大量线程而在低档配额中反复抢占；因此结果对应这份固定推理配置。
同时将容器 CPU affinity 限制到对应数量的可用逻辑核，避免 InsightFace 内部会话
按宿主机核数建立线程池。各服务共享这些逻辑核；配额是上限，不是独占算力。
AI 使用 `import_ai_entry.py` 启动真实应用，为 InsightFace 内部会话补上传递同一份
SessionOptions；该库默认绕过应用的 ONNX 工厂。只统一线程配置，不替换推理或业务处理。

可通过 `TS_PERF_OUTPUT`、`TS_PERF_BASELINE` 配置输出目录和历史结果。
需要重复测试或选档时，底层运行器支持：

```bash
python tests/performance/import_benchmark.py --profiles low medium high --repetitions 5 --output tests/artifacts/my-benchmark
```

每轮创建随机命名的独立网络和容器，结束只移除自己的容器及匿名卷；不重置已有数据库。
模型文件可共享缓存，模型下载在计时前完成；每轮新建 AI 进程，推理引擎初始化计入总耗时。
原文件目录只读挂载，并复制到容器内相同路径后才开始计时；不包含文件准备耗时。
操作系统文件缓存没有清除，不能将该场景称为磁盘冷启动。

## 指标与通过条件

- 从添加文件夹 HTTP 请求前的单调时钟开始计时；直到首次轮询验证完整完成。
- 三轮连续完整完成才确认结束；确认窗口另列，主耗时包含最多一次采样延迟。
- 从数据库读取完整任务状态（包含延迟重试、未在 UI 分类中展示的派生任务）。
- 所有必需任务必须成功，扫描记录存在且成功；文件数一致，每张照片有有效尺寸。
- 图片及动态照片的 basic / metadata / face / ocr / classification / image_embedding
  标记必须均为 true；视频检查 basic / metadata。禁用普通 E2E 的 OCR 五张限制。
- 排除 VISUAL_DESCRIPTION 和 RECOGNIZE_TICKET；报告不能代表远程模型性能。
- SSE 用于逐任务排队/执行时间诊断；完成判定依赖落库状态，不依赖 SSE 是否完整。
- 失败、取消、超时、意外漏处理不会计入成功中位数；有失败的档位整体标为失败。

输出 `result.json`、`report.md` 和每轮 `tasks.csv`、`progress.jsonl`、服务日志。
单次测量用于初始基线，不能证明小幅优化或提供可靠 P95。建议稳定后运行五轮比较中位数。
历史比较仅对兼容的数据集、主机、模型文件 SHA256 与 AI/数据库镜像生效；代码 SHA 保留但不作为兼容条件。

## 每日 CI 与记录留存

`.github/workflows/import-benchmark.yml` 每天北京时间 04:00 运行，也支持手动触发；
修改基准的 PR 自动运行，用于合并前验证。GitHub 定时调度可能延迟，合并到默认分支后生效。
结果写入 Actions job summary，并作为 `import-benchmark-<run-id>-<attempt>` artifact
保留 90 天，不向仓库提交测试数据。超过 90 天需要在过期前下载归档。

工作流从默认分支的最近成功基准 artifact 读取历史结果；排除 PR 数据、过期产物和
其他工作流。同一组兼容配置计算总耗时中位数变化率，首次运行显示无基线。
GitHub 托管 runner 硬件与宿主负载仍可能变化，变化率用于观察趋势，不作性能门禁。

```powershell
pwsh tests/scripts/run-tests.ps1 -Layer performance -Scope import-unit
```

上述快速测试覆盖完成判定、派生任务、失败/取消、缺失处理标记和基线兼容性。
