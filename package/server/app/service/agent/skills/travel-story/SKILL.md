---
name: travel-story
description: 从照片时间线、地点、票据与代表照片生成结构化旅行日志和个性化 HTML 页面。
---

# 旅行日志

1. 先用 `get_travel_timeline` 确认日期、地点段和票据；不确定范围时向用户确认。
2. 用 `select_representative_photos` 选 6–12 张代表照片，再用 `get_photo_context` 获取证据。
3. 标题、摘要、章节和图注必须对应真实照片/票据信息，不臆造同行人或事件。
4. 调用 `create_artifact_draft` 保存结构化草稿。内容结构应包含 `summary`、`sections`；每个 section 包含 `heading`、`body`、`photo_ids`。
5. 使用工具返回的 artifact id 调用 `save_artifact_html_page`，生成完整 HTML 文档。若用户要求为已有作品生成或重新设计页面，先调用 `get_artifact_context`。遵循用户选择的预设或自定义风格；使用响应式布局，兼顾手机与桌面。主要正文、章节和照片必须直接预渲染在 DOM 中，不得依赖 JavaScript 生成；JavaScript 只做渐进增强。
6. HTML 中的照片必须使用 `/api/medias/{user_id}/{photo_id}/thumbnail?size=medium` 真实地址。允许动态数据时只使用 `TrailSnap.request('/api/...')`，可用路径包括 `/api/stats/timeline?years=2026`、`/api/stats/dashboard`、`/api/albums`、`/api/photos`；不得嵌入登录令牌、密码、外部追踪或占位图片。
7. 默认不开放 Server API；只有用户明确开启时才把 `server_api_access` 设为 true。告知用户结构化内容和 HTML 页面都可继续编辑，并附作品卡片。
