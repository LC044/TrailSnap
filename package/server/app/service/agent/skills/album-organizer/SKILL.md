---
name: album-organizer
description: 安全地把照片整理成正式相册，通过预览、用户确认、执行和撤销完成写操作。
---

# 相册整理

1. 先理解用户给出的时间、地点、人物、事件和期望数量；信息不足时追问，不要扩大范围。
2. 用 `search_photos_v2`、`get_travel_timeline` 或其他只读工具找到候选照片，再用 `select_representative_photos` 去除相似连拍并保证时间、地点和人物覆盖。
3. 必要时调用 `get_photo_context` 或 `create_contact_sheet` 检查封面和候选照片。
4. 向用户说明候选总量、建议收录量、相册名、简介、封面和标签，然后调用 `propose_album_organization` 创建操作计划。
5. `propose_album_organization` 只生成预览，绝不代表已经修改相册。必须让用户在计划卡片中点击确认，Agent 不得代替用户执行。
6. P1 只创建或更新普通相册关系、封面、简介和标签，不删除、移动、重命名原始照片，不修改 EXIF。
7. 执行成功后用户可以在同一计划卡片中撤销；不要引导用户用自然语言绕过确认步骤。
