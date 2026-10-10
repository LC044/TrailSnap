# AI 处理优化与桌面实测包（2026-10-10）

本地测试版沿用 0.17.2 版本号，未发布 Release。包含此前基础处理优化与本次 AI 处理优化。

## 改动

- OCR 按图片批次提交，取消每段文字提交和刷新；特征向量按批次查询、提交。
- 人脸结果按批次提交，身份分配支持延迟提交，智能相册按所有成功图片一起更新。
- 场景分类收到结果后再替换 AI 标签；新标签通过 flush 获取 ID，缓存限定在当前会话与用户。
- 识别批次在后台线程创建和关闭自己的数据库会话，SQLite 识别写事务在进程内协调；网络等待不占写锁。
- AI 队列按类型分阶段执行：阶段开始选择最高优先级类型，只预取该类型；执行中、预取中、结果等待落库和等待重试的任务全部清空后才切换。同类型批次仍可并行，满额时不会跳过队首去运行其他模型。
- AI 请求按模型类别协调，切换前等待上一类请求全部完成并释放不再需要的模型缓存；流式响应与取消请求均等待请求生命周期结束。票据保留自身必需的 OCR 依赖，特征提取保留 CLIP 依赖。桌面和普通 AI 服务默认启用，环境变量 `AI_SINGLE_MODEL_FAMILY=false` 可关闭 AI 服务侧的类别协调。
- 多核机器的分类、特征提取默认请求并发提高到 2；默认推理线程预算最高 8，并为其他工作保留余量。
- 桌面启动也应用统一线程预算；OpenVINO OCR 保留保护共享 InferRequest 的锁。
- 记录批次总时间、提交时间、写入协调等待、AI 接纳等待和 OpenVINO OCR 锁等待/推理时间。

## SQLite 写入对比

独立临时数据库，SQLite WAL + FULL，10 张图片每张 100 段 OCR 文字，优化后每两张图片提交一次，与高并发档的 OCR 批次一致。各三轮取中位数，包含旧记录删除、文字入库与处理状态更新。

| 指标 | 优化前 | 优化后 |
| --- | ---: | ---: |
| 写入耗时中位数 | 2.154 秒 | 0.054 秒 |
| 提交次数 | 1020 | 5 |
| 写入速度 | 1 倍 | 39.85 倍 |

这不是 AI 端到端速度。没有包含图片读取、模型排队、模型加载和推理；测试使用本机磁盘，结果不能直接推算其他机器的收益。原始结果见 `ocr-sqlite-writes.json`；重跑脚本为 `package/server/scripts/benchmark_ai_writes.py`。

## 验证和安装

- 后端全量冒烟：2772 passed、48 deselected（包含阶段、重试和暂停验证）。
- 最后补充线程所有权、事件循环响应和回滚验证后，照片域冒烟：484 passed、2334 deselected。
- AI 冒烟：379 passed（包含同类并发、跨类等待、模型释放、流式响应和取消验证）。
- AI 打包产物 `--self-check`、`--startup-check` 均返回 0。
- 本机覆盖安装退出码 0；主后端与 AI Gateway 健康检查均返回 HTTP 200。
- 已比较已安装 Server/AI 可执行文件的 SHA-256，与最终构建产物一致。
- 后端清理 PyInstaller 缓存后完整重打包，并逐一比对嵌入字节码与源码：后端 17 个改动模块、AI 6 个改动模块全部匹配。
- 本地 NSIS 构建覆盖配置关闭 `createUpdaterArtifacts`，无需发布私钥；正式发布配置保持原样。

安装包：`package/desktop/src-tauri/target/release/bundle/nsis/TrailSnap_0.17.2_x64-setup.exe`

SHA-256：`334BABBA8950D347324478BDE635731B6D44AC0D446C4594328F91A6F6341EB6`

本机数据库备份：`%LOCALAPPDATA%/TrailSnap/data/trailsnap.before-ai-performance-20261010.sqlite`，使用 SQLite backup API，quick_check 返回 ok。

旧 AI 运行时：`%LOCALAPPDATA%/TrailSnap/ai-extensions/core-ai/runtime/trailsnap-ai-before-performance-20261010`。

本次阶段调度版本安装前另外备份数据库至 `%LOCALAPPDATA%/TrailSnap/data/trailsnap.before-ai-phase-20261010.sqlite`（quick_check 返回 ok），上一版 AI 运行时保留在 `%LOCALAPPDATA%/TrailSnap/ai-extensions/core-ai/runtime/trailsnap-ai-before-phase-20261010`。覆盖安装退出码 0，安装文件哈希匹配，重启后两个健康检查均返回 HTTP 200；日志确认从 `CLASSIFY_IMAGE` 阶段开始执行。

## 实测

在已启动的桌面程序中使用同一批照片、同一并发档比较。已经完成的任务通常会跳过，需要使用应用现有的重新识别操作；冷启动模型加载时间和模型热运行吞吐应分别观察。

主任务日志里的 `AI batch timing` 记录总时间、commit_ms、writer_wait_ms 和提交次数。AI 日志里的 `Desktop AI request timing`、`AI admission timing` 与 `OCR inference timing` 分别记录请求总时间、服务端接纳等待、OCR 锁等待/推理时间。commit_ms 不包含所有查询时间，不能直接用总时间减去提交时间来认定纯推理耗时。
