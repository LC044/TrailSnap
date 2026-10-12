# 桌面启动优化与本机实测（2026-10-11）

本轮实现了小幅提速，尚未实现一秒内首页可用。最终交替测试的首页主数据渲染中位数从 3.054 秒降至 2.869 秒，约降低 6.1%。后端健康检查就绪仍约 2.46 秒，是剩余启动链路的主要成本。

## 实现

- 数据库 UUID / Vector 类型仅在 PostgreSQL 方言实际使用时导入对应依赖，SQLite 启动不加载 pgvector。
- 人脸、相册、年度报告、向量搜索、地点相似度、关联探索、朋友圈精选中的 NumPy 改为用时导入，切断全部已发现的普通 API 启动导入路径。
- 朋友圈文案生成用到的 LangChain 消息类型推迟到生成时导入；查询既有文案不加载 LLM 依赖。
- zeroconf 推迟到后台服务发现实际执行时导入。
- 桌面健康检查禁止代理，连接超时为 100 毫秒，轮询间隔为 50 毫秒；响应超时保留 1200 毫秒，启动总超时保留 60 秒。
- 首页路由代码在等待后端期间预加载，仍完成标准桌面 JWT 登录和用户信息获取后挂载主界面。
- 测速脚本通过 WebView2 DevTools 检查真实页面状态，输出 JSON 和截图，使用独立数据目录，不删除或依赖用户访问日志。

本机对未监听的 localhost 端口执行三次 TCP 连接，失败耗时分别约为 2034、2054、2050 毫秒。连接超时与响应超时分别控制，避免后端尚未监听时的连接等待占据整次健康检查请求。

数据库列定义与存储格式保持一致，本轮只调整类型依赖的加载时机。

## 测量方法与边界

- Windows 本机，Rust release / PyInstaller 目录模式 / Vue production 构建。
- 基线为当前代码修改前的重新构建版本，基线 Python Sidecar 单独保留；优化版重新构建 Python、前端和 Rust。
- 首先进行各五次连续启动，再执行交替对比。早期复测发现系统负载波动，随后增加了连接超时优化；下表只使用最终代码的五组交替结果，不剔除异常值。
- 同一隔离空图库、同一 WebView2 用户目录、相同调试开关。测量起点为创建桌面进程之前，结束标记由页面和原生运行状态实际观测。
- `backendReadyMs`：外部探针首次检测到健康检查成功；`runtimeReadyMs`：原生运行状态首次 ready；`homeShellMs`：启动屏消失且首页标题已出现；`homeDataMs`：首页主数据内容出现且主加载状态消失。后三项通过 DevTools 采样，因此是观测时间，存在采样与 IPC 开销。
- “首页主数据渲染”不表示所有次级异步卡片、照片缩略图或 AI 功能同时就绪。
- 保留操作系统磁盘缓存，没有通过重启机器测量真正的系统冷启动。基线第一个最终样本明显较慢，完整保留。
- 测试期间本机另有用户安装版进程运行，无法完全控制外部负载；因此这是本机观察结果，不作为跨设备性能保证。
- 整理结果时发现其他任务并发修改了 `app/db/types.py`（新增向量类型 `hashable = False`）并增加年度报告 SQLite 向量测试，均已保留。上述启动测试构建生成于该并发修改之前，启动数据对应本轮的启动优化快照；不能把测试可执行文件当作包含随后所有工作区修改的安装包。
- 基础安装、数据库迁移、图库规模、待恢复任务、杀毒软件与磁盘状态均可能影响结果。此空图库数据不能代表用户已有的大型照片库。

## 最终结果

以下均为从启动桌面进程开始计时，单位秒。

| 指标 | 基线中位数 | 优化中位数 | 基线范围 | 优化范围 |
|---|---:|---:|---:|---:|
| 后端健康检查成功 | 2.466 | 2.458 | 2.321–4.135 | 2.281–2.550 |
| 原生运行状态 ready | 2.616 | 2.469 | 2.591–4.548 | 2.302–2.652 |
| 首页布局出现 | 2.800 | 2.586 | 2.717–4.675 | 2.423–2.774 |
| 首页主数据渲染 | 3.054 | 2.869 | 2.973–4.942 | 2.711–3.060 |

| 交替测试组 | 基线首页主数据渲染 | 优化首页主数据渲染 |
|---|---:|---:|
| 1 | 4.942 | 3.060 |
| 2 | 2.973 | 2.852 |
| 3 | 2.980 | 2.869 |
| 4 | 3.133 | 2.998 |
| 5 | 3.054 | 2.711 |

原始 JSON、截图与汇总保留在本机 `output/performance/startup-20261011/`，其中 `baseline-final-1.json` 至 `baseline-final-5.json`、`optimized-final-1.json` 至 `optimized-final-5.json` 对应上述最终样本。早期 `baseline.json`、`optimized.json`、`*-pair-*.json` 保留用于查看测量过程，不能与最终版混合统计。

## 验证

- `pwsh tests/scripts/run-tests.ps1 -Layer unit -Component server -Level smoke`：2825 passed，48 deselected。
- `pwsh tests/scripts/run-tests.ps1 -Layer unit -Component website -Level smoke`：69 passed。
- 工作区并发修改后，通过统一入口补跑年度报告 SQLite 向量、SQLite 后端、PostgreSQL 距离表达式和桌面冷导入检查：12 passed。
- Vue production 构建、PyInstaller Sidecar 构建、Tauri release 构建通过。
- 新增独立解释器检查：导入桌面 API 应用不加载 NumPy、OpenCV、pgvector、LangChain、zeroconf、MCP，且桌面会话 API 保留。
- 五次最终优化版运行均完成桌面会话、用户信息获取和首页主数据渲染；检查了最终首页截图。
- 最终桌面构建直接使用其资源目录内的优化 Sidecar，确认该可执行文件与优化版打包结果的 SHA-256 相同。

## 复测

需要 Node.js 22+、桌面构建与配套资源：

```powershell
pwsh package/desktop/scripts/measure-startup.ps1 `
  -ExePath package/desktop/src-tauri/target/release/trailsnap-desktop.exe `
  -Runs 5 `
  -OutputPath output/performance/startup-local.json
```

默认创建独立临时图库。第 0 次为预热，汇总只统计后五次。`-DataRoot` 可指定同一隔离目录做前后对比，`-ServerBinary` 可明确选择待比较的 Sidecar。脚本只结束其启动的桌面进程树，数据目录保留以便复查。

若目标是一秒内显示主界面，需要把主布局显示与后端就绪解耦；若目标是一秒内真实图库可用，则需要进一步拆分后端核心服务与非首屏业务初始化。当前完整 FastAPI 应用的启动路径仍超过一秒，单纯继续移动几个 import 的收益有限。
