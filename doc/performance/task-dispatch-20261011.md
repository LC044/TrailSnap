# 桌面任务调度与 SQLite 空间回收验证

2026-10-11，在配置指向的 `E:\shuaikangzhou\Pictures\data\data\trailsnap.sqlite` 上执行。
迁移前已创建一致性备份；压缩备份保存在同目录的 `backups` 中。

## 调度索引

```sql
CREATE INDEX ix_tasks_type_status_priority_created
ON tasks(type, status, priority DESC, created_at ASC);
CREATE INDEX ix_tasks_status_priority_created
ON tasks(status, priority DESC, created_at ASC);
```

调度器分别查询候选任务类型的队首，再按优先级和创建时间比较，避免多类型
`IN (...)` 查询需要合并排序。批次查询仍限定单一类型。

两条被测查询均包含 `status='pending'`、`type='RECOGNIZE_FACE'`、重试时间过滤，
按 `priority DESC, created_at ASC` 排序，分别取队首和最多 32 条任务。

| 查询 | 迁移前平均耗时 | 迁移后平均耗时 |
| --- | ---: | ---: |
| 取类型队首 | 810.881 ms | 0.865 ms |
| 取 32 条任务 | 1091.170 ms | 0.258 ms |

每条查询重复 5 次，包含首次查询；同时存在本地构建负载，数值仅代表本次测量。

迁移前计划：

```text
SEARCH tasks USING INDEX ix_tasks_status_priority_created (status=?)
USE TEMP B-TREE FOR RIGHT PART OF ORDER BY
```

迁移后两条查询均为：

```text
SEARCH tasks USING INDEX ix_tasks_type_status_priority_created (type=? AND status=?)
```

## 照片关联与空间回收

- SQLite、PostgreSQL 各新增一个迁移，增加 nullable `tasks.photo_id` 外键及其索引。
- ORM 设置 payload 时同步照片关联，覆盖普通插入与 `bulk_save_objects`。
- 外键引用 `photos.id`，物理删除照片时 `ON DELETE CASCADE` 删除关联任务。
- 迁移按主键分页补齐历史关联，规范化 UUID，并移除不存在照片或无效照片 ID 的任务。
  不关联单张照片的扫描、全库任务保留。
- SQLite 一次性执行 `PRAGMA auto_vacuum=FULL; VACUUM`，之后自动回收空闲页。
  这不会删除有效的 EXIF、向量等数据，也不限制有效数据的增长。

本库迁移前后照片数均为 24,706，任务数均为 95,319；这份库未发现需要移除的历史照片任务。
文件从 2,158,350,336 字节缩至 2,106,855,424 字节，迁移后 `auto_vacuum=1`、
`freelist_count=0`，`foreign_key_check` 无错误。

回归测试覆盖历史孤儿清理、UUID 规范化、非照片任务保留、多个状态的级联删除、
批量创建任务的照片关联、查询计划，以及迁移后后续删除仍能自动缩小文件。
