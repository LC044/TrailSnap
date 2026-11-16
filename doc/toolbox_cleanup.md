# 全量照片清理

工具箱清理通过 `POST /toolbox/plans` 创建后台扫描，所选范围和全库参考按批落入 `cleanup_scope`。清理扫描没有 3000 / 50000 数量上限；其他整理工具保持原来的限制。扫描结果需用户手动选择、确认后才会移入回收站。

## 扫描和缓存

- 状态为 `scan_queued → scanning → preview`，中断为 `scan_stopped` / `scan_failed`，通过 retry 从检查点继续；执行仍使用 `queued → running`。
- 重复扫描按主键批量读取，使用磁盘预算流式计算 MD5；`cleanup_hashes` 记录路径摘要、大小、mtime 和哈希。失败的文件清除旧哈希，不进入重复组。数据库执行哈希分组。
- 相似扫描按用户、数据库、模型隔离磁盘缓存。`image_vectors.content_revision` 在应用写入时更新，复扫仅获取发生变化的向量数据；新增、修改、软删除及模型切换在同步时更新索引。直接通过外部 SQL 修改向量时，也必须更新 content_revision（唯一随机字符串），或删除对应的可再生缓存。
- 缓存为 `DATA_DIR/cleanup-cache` 下的 SQLite manifest 与 HNSW 分片，每片最多 20000 个 512 维 float32 向量。索引文件临时写入后原子替换，文件锁保护同一缓存的更新和查询；分片按内存预算淘汰。
- 快速扫描搜索所有分片，自适应扩展候选并复核相似度，属于近似召回。候选特别密集或 HNSW 无法返回足够结果时精确扫描该分片；完整模式始终执行分块精确比较，时间复杂度仍为 O(N²)，不构建 N×N 矩阵。
- 每组成员均与代表图核验，不通过传递关系合并分组。分组互斥；分组不是完整相似关系图。
- 缺少向量不会自动触发昂贵的模型推理；结果显示缺失数量，完成特征分析后再次扫描。

可选环境变量：

| 配置 | 默认值 | 作用 |
| --- | --- | --- |
| `TS_CLEANUP_CACHE_DIR` | `DATA_DIR/cleanup-cache` | 可再生索引缓存目录 |
| `TS_CLEANUP_INDEX_MEMORY_MB` | `256` | 常驻索引预算估计；最低容纳一个分片，实际进程内存还包含 Python、数据库和单批工作数据 |

## 核对和执行

`cleanup_groups` 和 `cleanup_members` 只保存一次分组关系，参考照片通过 members API 分页加载。选择通过 selection API 保存至 `cleanup_selections`，单次更新最多 500 项，累计可超过 10000 项。执行请求省略 selected_items 时使用服务端已保存的选择。

执行前及执行时检查保留项；重复清理还会重新读取目标与保留文件哈希。按批复用回收站 CRUD，不永久删除文件。失败或停止后的重试保留成功项，重新确认待处理项。CSV 在服务端按主键分页流式输出，浏览器下载 Blob。

## 验证

统一配置来自 `tests/.env.test`：

- `TS_CLEANUP_TEST_PG=1`：在配置的 PostgreSQL 中创建随机隔离 schema，限定测试表和数据在该 schema 内，结束后删除该 schema；不重置原库。
- `TS_CLEANUP_SCALE=100000`：启用十万条照片范围、10002 成员重复组及 3001 成员相似组的规模用例。

```powershell
pwsh tests/scripts/run-tests.ps1 -Layer unit -Component server -Level smoke -Scope toolbox
pwsh tests/scripts/run-tests.ps1 -Layer unit -Component server -Level smoke -Scope cleanup_scale
pwsh tests/scripts/run-tests.ps1 -Layer unit -Component website -Level smoke
```

SQLite 与 PostgreSQL 各有一份 `cleanup_*_0027` Alembic 迁移。开发环境升级前应确认目标库；扫描验收不执行真实图库删除。

2026-11-16 开发环境实测：PostgreSQL 中 72548 张活跃照片使用快速模式完整复扫，耗时 217.23 秒，独立扫描进程峰值 RSS 315.8 MiB（含运行时、索引和工作数据）；缓存更新 0、分片重建 0。结果为 7687 组、22784 条待核对候选，6 张缺少特征。该数据是一次已有索引的完整复扫，不代表首次建索引耗时；测试期间同时运行其他验证任务，不作为跨设备性能保证。

双库清理回归最终 237 项通过，4 个规模用例在独立轮次通过。规模用例已验证十万条范围遍历、10002 成员重复组、10001 项服务端确认与 3001 成员相似组；真实图库只生成预览，删除行为在隔离数据中验证，包含 101 项跨批次回收站执行与保留原件。前端 350 项单元测试和生产构建通过，手机端已核验参考图按需加载、选择保存与无横向溢出。扩展系统检查的 SQLite 从空库升级至 head、重复升级及 schema 对齐通过；8 个 Windows 安装器用例受到注册表或系统临时目录访问权限限制，未通过。
