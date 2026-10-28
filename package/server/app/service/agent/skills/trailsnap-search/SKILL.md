---
name: trailsnap-search
description: 逐步检索并理解用户相册，适合回答照片、人物、地点和时间相关问题。
---

# 相册检索

1. 先区分意图：用户要找/看照片时优先调用 `search_library_photos(purpose="find")`，由大模型直接拆分时间、地点、人物和画面条件；前端会展示全部匹配照片的分页画廊，不要把样本误当全部结果或重复输出样本图片。人物ID先通过 `lookup_search_people` 查询，关系称呼无法确定时询问用户。
2. 用户要用照片写作、分析或整理时使用 `purpose="context"` 获取候选，再继续相关工作流；中间候选不发布成最终搜索结果。需要全局分布摘要时可用 `search_photos_tool`。
3. 需要可靠细节时，对最多 30 个候选调用 `get_photo_context`。
4. 涉及图片文字可直接传 `ocr_text`；涉及出行分析时联合 `get_trip_tickets` 和 `get_travel_timeline`。
5. 回答中只使用工具确认的信息；无法确认时明确说明。零结果不自动放宽条件。
6. 需要在作品中展示照片时使用工具返回的真实缩略图地址，绝不泄露服务器原始路径。
