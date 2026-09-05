---
name: travel-album
description: 从一句自然语言需求自动发现或整理旅行照片，同时生成正式相册计划、结构化旅行日志和个性化 HTML 页面。
---

# 一句话旅行相册

1. 提取用户给出的日期、地点、人物、相册名称、期望照片数量和页面风格；缺少日期或地点时先调用 `discover_trips` 返回少量候选，让用户确认范围，不要把候选当成事实。
2. 对已确认范围调用 `get_travel_timeline` 和 `get_trip_tickets`，再用 `search_photos_v2` 获取照片。候选过多时分页读取，但不要超过操作计划的 500 张上限。
3. 用 `select_representative_photos` 选择 6～16 张代表照片；必要时调用 `create_contact_sheet` 做多模态检查。相册可以收录更多候选，但封面必须来自计划内照片。
4. 调用 `create_artifact_draft` 创建 `travel_story` 结构化作品，`content` 必须包含 `summary` 和 `sections`，每个 section 必须使用 `heading`、`body`、`photo_ids` 字段；正文事实必须能回溯到照片或票据 ID。
5. 根据用户指定或默认“旅行杂志”风格调用 `save_artifact_html_page`。正文和真实照片必须预渲染在 HTML 中，默认关闭 Server API 权限。
6. 调用 `propose_album_organization` 创建正式相册计划，并把上一步返回的 `artifact_id` 传入；相册名称、简介、封面和标签应与旅行日志一致。
7. 清楚说明旅行日志草稿已经生成，但正式相册仍未执行。只有用户在计划卡片点击“确认执行”后才创建相册，Agent 不能替用户确认。
8. 全流程不得删除、移动、重命名原始照片，不修改 EXIF；如果任一工具失败，保留已创建的作品并说明未完成阶段。
