---
name: trailsnap-search
description: 逐步检索并理解用户相册，适合回答照片、人物、地点和时间相关问题。
---

# 相册检索

1. 用户条件宽泛时先调用 `search_photos_tool` 获取总量和聚合摘要，不要把样本误当全部结果。
2. 需要可靠细节时，对最多 30 个候选调用 `get_photo_context`。
3. 涉及图片文字时调用 `search_ocr`；涉及出行时联合 `get_trip_tickets` 和 `get_travel_timeline`。
4. 回答中只使用工具确认的信息；无法确认时明确说明。
5. 展示照片使用 `/api/medias/{photo_id}/thumbnail`，绝不泄露服务器原始路径。
