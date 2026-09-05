# TrailSnap 相册 Agent P0 设计方案

> 状态：提案
> 目标版本：下一版本
> 范围：P0（只读理解、智能选图、Skill 编排、结构化内容草稿）

## 1. 背景

TrailSnap 已具备照片、位置、人物、标签、OCR、票据、视觉描述、质量评分、回忆评分、向量检索、相似照片聚类和异步任务等数据能力，也已经通过 LangChain/LangGraph 提供流式 Agent 对话。

当前 Agent 实际启用的工具仍以查询为主：搜索照片、查看照片详情、查询位置、标签和人物。已经实现的旅行历史工具尚未注册，照片上下文分散在多个模型和接口中，Agent 也不能按需查看照片画面、进行多样化选图或把结果保存为可继续编辑的作品。因此当前能力更接近“能查询相册的聊天助手”，尚未形成“理解相册并完成任务的相册 Agent”。

P0 将补齐一个安全、可验证、可扩展的只读 Agent 闭环，并以“生成旅行故事册草稿”为首个端到端验收场景。

## 2. 技术决策

P0 沿用现有 Python、LangChain 和 LangGraph，不引入 pi sidecar，不迁移到 Deep Agents，也不接入 MCP。新增轻量 Skill Registry 和受控业务工具，并预留 `AgentBackend` 抽象，避免未来切换运行时需要改动 API 和前端协议。

P0 不为 Agent 提供通用 `read_file`、`write_file` 或 Shell。所需能力拆分为：

- `load_skill`：只读取服务端审核并登记的 Skill；
- `view_photos`：只读取当前用户照片的受控缩略图；
- `create_artifact_draft`：把结构化作品草稿写入数据库；
- 相册和物理文件修改留到后续带确认、审计与撤销能力的阶段。

## 3. P0 目标

1. Agent 能发现并按需加载 TrailSnap 内置 Skills。
2. Agent 能基于时间、地点、人物、标签、OCR、票据和语义描述检索照片。
3. Agent 能一次取得完整、结构化且可追溯的照片上下文。
4. Agent 能按需查看少量照片或联系表，而不接触原始文件路径。
5. Agent 能识别给定时间范围内的旅行时间线。
6. Agent 能从候选照片中去重并选出时间、地点、人物和内容均有代表性的照片。
7. Agent 能生成并持久化结构化旅行故事册草稿。
8. 前端能展示 Agent 当前正在搜索、查看、筛选或生成的步骤。
9. 所有结论和内容均能追溯到照片 ID 或票据 ID。

## 4. 非目标

P0 不包含：

- 自动删除、移动、重命名照片；
- 创建或修改正式相册、标签、人物和元数据；
- 任意文件系统或 Shell 访问；
- 用户安装第三方 Skill；
- MCP Server 或 MCP Client；
- pi Agent Runtime；
- PDF、视频、语音和社交平台发布；
- 完整的自动行程发现。P0 只对用户指定的时间范围进行时间线聚合，自动发现所有历史旅行放到后续阶段。

## 5. 首个端到端场景

用户输入：

> 帮我把去年国庆在云南的照片整理成一篇旅行故事。

Agent 应完成：

1. 解析或追问时间、地点范围；
2. 查询旅行时间线、照片、人物和票据；
3. 获取候选照片的聚合摘要；
4. 相似去重并选择每日代表照片；
5. 必要时查看缩略图联系表进行二次筛选；
6. 生成标题、摘要、每日行程、图文段落和结尾；
7. 保存结构化草稿；
8. 在聊天中返回草稿入口和代表照片；
9. 每一段内容保留对应的 `photo_ids` / `ticket_ids` 作为证据。

## 6. 总体架构

```text
Web AgentChat
    │ 现有 /api/agent/chat + SSE
    ▼
Agent API
    ├── Session / Message / Memory
    ├── AgentBackend（协议边界）
    │     └── LangGraphAgentBackend（P0）
    ├── Skill Registry
    ├── Agent Tool Facade
    │     ├── Search & Aggregate
    │     ├── Timeline & Tickets
    │     ├── Media View
    │     ├── Representative Selection
    │     └── Artifact Draft
    └── Audit / Limits
          │
          ▼
Domain Services + PostgreSQL + AI Service + Task Worker
```

Agent 工具只调用领域服务，不在工具函数中继续堆叠 SQL。API、未来 MCP 和其他 Agent Runtime 应复用相同的领域服务与权限校验。

## 7. P0 工具清单

### 7.1 Skill

#### `list_skills`

返回当前可用 Skill 的名称、描述和版本。通常由系统提示直接提供目录，仅用于诊断。

#### `load_skill`

输入 `name`，返回审核过的完整 `SKILL.md` 内容。禁止接收任意路径。

首批内置 Skill：

- `trailsnap-search`：渐进式相册查询；
- `travel-story`：旅行时间线、选图和故事草稿生成；
- `nine-grid-selection`：九宫格代表照片选择，为 #45 提供基础能力。

### 7.2 查询与聚合

#### `search_photos_v2`

保留现有时间、位置、人物、标签、场景、文件夹和文本语义筛选，补充：

- OCR 文本；
- 图片类型；
- 横竖方向；
- 是否有人物；
- 最低质量分与回忆分；
- cursor 分页；
- `fields` 和 `group_by`；
- 全量命中的时间、地点、标签、人物和图片类型摘要。

工具返回受限样本和聚合数据，禁止一次把大量照片明细塞入模型上下文。

#### `get_photo_context`

批量返回照片的统一上下文：

```json
{
  "photo_id": "uuid",
  "photo_time": "ISO-8601",
  "file_type": "image",
  "dimensions": {"width": 0, "height": 0},
  "location": {},
  "scene": null,
  "people": [],
  "albums": [],
  "tags": [],
  "ocr": [],
  "description": null,
  "narrative": null,
  "quality_score": null,
  "memory_score": null,
  "color_emotion": null,
  "thumbnail_url": "/api/medias/{photo_id}/thumbnail"
}
```

单次最多读取 30 张，所有记录强制校验 `owner_id`。

#### `get_travel_timeline`

启用并重构现有旅行历史工具，按天和位置返回：

- 时间范围；
- 城市、区县和景区；
- 照片数量；
- 代表照片候选；
- 人物；
- 相关火车票和飞机票；
- 相邻节点之间的时间间隔和位移。

#### `search_ocr` / `get_trip_tickets`

允许 Agent 用店名、酒店、车站、菜单和票据信息补充旅行语境。响应必须包含来源照片或票据 ID。

### 7.3 媒体查看

#### `view_photos`

向支持视觉输入的模型提供当前用户照片的缩略图，默认最多 9 张，硬上限 16 张；只允许 `small` / `medium`，不返回服务器原始路径。

#### `create_contact_sheet`

把候选照片生成临时联系表供模型比较。联系表：

- 使用临时或缓存存储；
- 带短期 TTL；
- 不写入用户原照片目录；
- 每格标注短 ID，结果能映射回完整 `photo_id`；
- 限制像素、文件大小和单轮生成次数。

### 7.4 代表照片选择

#### `select_representative_photos`

输入候选照片、数量和策略，综合：

- 质量分；
- 回忆分；
- 时间覆盖；
- 地点覆盖；
- 人物覆盖；
- 视觉内容多样性；
- 相似照片惩罚；
- 截图和低质量照片惩罚。

输出选择结果、排序理由、被去重的相似组和评分分解。算法应尽量确定性，LLM 只用于最后少量候选的视觉判断。

### 7.5 作品草稿

#### `create_artifact_draft`

新增统一 `AIArtifact` 数据模型，P0 支持 `travel_story` 类型：

```text
id, user_id, type, title, content_json,
source_photo_ids, source_ticket_ids,
status, version, created_by_session_id,
created_at, updated_at
```

`content_json` 至少包含：

```json
{
  "title": "",
  "summary": "",
  "date_range": ["", ""],
  "locations": [],
  "people": [],
  "cover_photo_id": "",
  "days": [
    {
      "date": "",
      "title": "",
      "story": "",
      "locations": [],
      "photo_ids": [],
      "ticket_ids": []
    }
  ]
}
```

P0 仅保存草稿，不自动发布，不接受 HTML。前端根据结构化数据安全渲染。

## 8. Skill Registry

建议目录：

```text
package/server/app/service/agent/skills/
├── registry.py
├── trailsnap-search/SKILL.md
├── travel-story/SKILL.md
└── nine-grid-selection/SKILL.md
```

启动时：

1. 只扫描配置允许的目录；
2. 解析 `name`、`description`、`version`；
3. 拒绝重复名称、超限文件、非法相对路径和无 frontmatter 的 Skill；
4. 将目录摘要加入系统提示；
5. Agent 匹配任务后调用 `load_skill(name)`；
6. 记录 Skill 名称和版本到消息工具调用及 artifact 元数据。

P0 Skill 只允许仓库内置，不支持运行 Skill 脚本。

## 9. Agent 事件协议

保留现有 `content`、`reasoning`、`title` 和 `[DONE]`，新增兼容事件：

```json
{"type":"tool_start","tool_call_id":"...","tool_name":"search_photos_v2","label":"正在查找照片"}
{"type":"tool_end","tool_call_id":"...","status":"success","summary":"找到 326 张照片"}
{"type":"artifact","artifact_id":"...","artifact_type":"travel_story","title":"云南旅行故事"}
{"type":"warning","code":"INSUFFICIENT_CONTEXT","message":"缺少明确的日期范围"}
```

前端未知事件必须安全忽略，确保向后兼容。工具原始返回不直接推送给前端，只发送脱敏摘要。

## 10. 安全与资源限制

- 所有工具在服务端从运行时上下文取得 `user_id`，不允许模型传入或覆盖；
- 每个查询显式过滤当前用户及未删除照片；
- 不向模型暴露 `file_path`、API Key、Agent Token 和 EXIF 原始敏感字段；
- 单轮最多 20 次工具调用；
- 批量详情最多 30 张，视觉查看最多 16 张；
- 工具统一超时、取消和结果截断；
- Skill 内容、工具调用、来源 ID 和 artifact 版本可审计；
- 外部文本、OCR 和照片描述均按不可信数据处理，不得作为系统指令；
- P0 不提供任何破坏性工具，因此不包含确认执行协议；后续写操作必须先实现 preview/confirm/execute/undo。

## 11. 代码工作包

### WP1：Agent 边界与工具治理

- 定义 `AgentBackend` / `AgentEvent`；
- 将现有实现包装为 `LangGraphAgentBackend`；
- 建立 Tool Registry、公共错误格式、超时和调用限制；
- 移除生产路径中的 `print(chunk, metadata)`。

### WP2：Skill Registry

- Skill 扫描、校验、目录注入和 `load_skill`；
- 编写三个内置 Skill；
- 单元测试匹配、重复名、非法路径和大小限制。

### WP3：相册上下文服务

- 抽取现有工具 SQL 为可复用领域服务；
- 实现 `search_photos_v2` 和 `get_photo_context`；
- 接入 OCR、票据和色彩情绪；
- 统一分页、聚合、字段裁剪与 owner 校验。

### WP4：旅行时间线与智能选图

- 注册并重构旅行时间线；
- 实现相似去重和多样性选图；
- 实现缩略图查看和联系表；
- 为固定数据集增加确定性选择测试。

### WP5：旅行故事草稿

- 新增 `AIArtifact` ORM、Pydantic Schema、CRUD、API 和 Alembic 迁移；
- 支持创建、查看和更新草稿；
- 实现 `travel-story` Skill；
- 页面安全渲染结构化图文内容。

### WP6：流式体验与验证

- 扩展 SSE 工具和 artifact 事件；
- AgentChat 展示可折叠进度；
- 增加后端单元、集成与前端 E2E；
- 增加一套脱敏的旅行故事验收数据。

## 12. 建议里程碑

### M1：Agent 能查全

完成 WP1～WP3。Agent 能稳定回答带证据的时间、地点、人物、OCR 和票据问题。

### M2：Agent 能看和选

完成 WP4。Agent 能从大量候选中去重并选择有代表性的照片。

### M3：Agent 能交付作品

完成 WP5～WP6。用户可以通过自然语言得到可持久化、可编辑的旅行故事草稿。

## 13. 验收标准

### 功能

- [ ] 至少三个内置 Skill 可被发现并按需加载；
- [ ] 旅行历史工具已实际注册；
- [ ] 搜索支持时间、地点、人物、标签、OCR、票据和语义条件；
- [ ] 批量照片上下文不需要 Agent 逐张查询；
- [ ] 能生成最多 16 张照片的受控视觉输入或联系表；
- [ ] 代表照片选择包含相似去重和时间/地点多样性；
- [ ] 能创建并再次打开结构化旅行故事草稿；
- [ ] 聊天页面能展示主要工具阶段和草稿入口；
- [ ] 回答与故事段落保留来源照片或票据 ID。

### 安全

- [ ] 跨用户 photo/artifact ID 均返回无权限或不存在；
- [ ] Agent 与模型响应中不出现服务器原始文件路径和凭证；
- [ ] Skill 不能读取登记目录之外的文件；
- [ ] 所有批量工具具备数量上限、超时和取消；
- [ ] P0 不存在删除、移动、重命名或任意写文件工具。

### 质量

- [ ] 预置旅行数据集可以稳定生成按天组织的故事；
- [ ] 选出的照片不存在明显重复连拍，并覆盖主要日期或地点；
- [ ] 地点、人物、日期等事实可以从来源数据验证；
- [ ] 单个工具失败时 Agent 能说明失败并保留已有结果；
- [ ] 现有会话、记忆、终止和标题功能无回归。

## 14. 观测指标

P0 上线后记录：

- 旅行故事生成成功率；
- 平均工具调用次数和总耗时；
- 每类工具失败率；
- 平均输入/输出 token；
- 生成后用户保存、编辑或放弃草稿的比例；
- 用户替换封面和代表照片的比例；
- 无来源事实与错误来源 ID 的数量；
- 跨用户权限测试失败数（必须为 0）。

## 15. 与现有 Issue 的关系

- #44 自动旅行日志：P0 的首个上层产品场景；
- #45 朋友圈九宫格：复用 P0 的代表照片选择、联系表和文案上下文；
- #48 智能相册推荐：未来复用旅行/事件聚合与代表照片选择；
- #49 2026 路线图：本方案把多个独立 AI 功能收敛到共同的相册 Agent 基础设施。

P0 完成后，#44 和 #45 仍可分别跟踪页面、模板、拼图、导出和发布体验，不由本方案自动关闭。

## 16. 后续阶段

- P1：创建相册、标签和元数据修正；preview/confirm/execute/undo；完整审计；
- P2：自动旅行发现、人物时光机、相册医生、回忆侦探和主动回忆；
- P3：TrailSnap MCP Server、外部 MCP Client、第三方 Skills、可选 pi Runtime；
- P4：PDF、长图、视频、语音和外部平台发布。

## 17. P0 实施记录（2026-09-04）

P0 已按本文方案落地，采用现有 LangGraph Runtime，没有引入 pi 或 Deep Agents：

- 内置 `trailsnap-search`、`travel-story`、`nine-grid-selection` 三个 Skill，并通过白名单注册表按需加载；
- 新增高级搜索、统一照片上下文、OCR、票据、旅行时间线、批量查看、联系表、代表照片选择和作品草稿工具；
- 代表选图复用 CLIP embedding 聚类去重，并以质量、回忆价值、时间、地点和人物覆盖做确定性选择；
- 联系表在内存中生成压缩 JPEG，以多模态 tool message 直接交给模型，不暴露原图路径，也不持久化临时图片；
- 新增 `AIArtifact`、PostgreSQL/SQLite 迁移、owner-scoped CRUD/API，以及可查看、编辑和保存的旅行日志页面；
- SSE 新增 `tool_start`、`tool_end`、`artifact` 事件，前端显示执行进度和可点击作品卡片；
- MiniMax 风格的 `<think>` 流被拆分到 reasoning 通道，正文不会再显示原始思考标签；外部占位图片 URL 会被拦截；
- 所有 P0 写操作仅限创建/更新 AI 草稿，没有照片删除、移动、重命名或任意文件写入能力。

验收使用已部署 PostgreSQL 环境和 MiniMax-M3 完成：模型加载 `travel-story` Skill，读取 2026-07-25 的 83 张照片时间线，查看真实联系表，选出 9 张代表照片，生成 6 个章节并保存、打开和编辑草稿。统一 smoke 测试结果为 server 2333 passed、AI 411 passed、CLI 13 passed；前端生产构建通过，浏览器作品页与编辑态均为 0 console errors。

## 18. 个性化 HTML 作品（2026-09-04）

`AIArtifact` 同时保留结构化 JSON 与 Agent 生成的完整 HTML：JSON 负责可编辑、可检索和后续导出，HTML 负责个性化视觉、交互和动态数据展示。用户可选择旅行杂志、电影叙事、手账拼贴、地图足迹、极简画册，或直接用自然语言定义风格。

HTML 在独立 sandbox iframe 内运行，默认无 Server API 权限。用户明确开启后，页面可通过 `TrailSnap.request('/api/...')` 由父页代理只读请求；生成代码不会获得 JWT，登录、用户、设置、Token、系统与 Agent 对话接口被禁止，CSP 也限制外部网络资源。

## 19. P1 实施记录（2026-09-05）

P1 首批写能力已落地为受控的相册整理事务，完整流程为 `preview → confirm → execute → undo`：

- 新增内置 `album-organizer` Skill 和 `propose_album_organization` 工具。Agent 只能创建操作计划，不能替用户确认或直接执行；
- 首批操作支持创建普通相册，或向用户已有的普通相册添加照片，同时设置名称、简介、封面和自定义标签；
- 执行入口是登录用户专用 REST API，不暴露给模型工具；计划、执行和撤销均做 owner 校验；
- 新增 `AgentActionPlan` 持久化模型，保存不可变预览、待执行操作、执行结果和精确撤销数据，并记录 proposed、executed、undone 状态与时间；
- 执行和撤销使用事务与行锁，阻止重复执行、重复撤销和并发确认；单次计划最多 500 张照片、10 个标签，且封面必须属于候选照片；
- 创建相册的撤销会删除该相册；更新已有相册的撤销只移除本次新增关系，并恢复原名称、简介、封面和标签关系；
- 前端聊天消息新增计划卡片，展示操作类型、照片数、标签、样图和原文件安全提示；用户须在二次确认弹窗中执行，执行后可打开相册或撤销；
- 会话历史保存计划引用，重新进入会话时从服务端刷新状态，避免卡片显示过期的 proposed/executed 状态；
- P1 仍不允许删除、移动或重命名原始照片，不修改 EXIF，也不提供任意文件写入工具。

已使用部署中的 PostgreSQL、账号数据和 MiniMax-M3 完成真实验收：模型加载 Skill 并生成 3 张照片的计划，页面二次确认后创建相册且显示 3 个项目，随后从同一卡片撤销，接口确认相册已不存在。验收同时覆盖了 MiniMax ToolMessage 不携带工具名的兼容情况：服务端会通过 `tool_call_id` 恢复工具名，确保计划事件和会话 `content_ext` 不丢失。

## 20. P1.1 加固与 P2 旅行相册 MVP（2026-09-05）

P1.1 把“能执行”补齐为“可长期运行和审计”：

- 操作计划默认 7 天过期，服务端持久化 `expired` 终态，防止用户执行已严重脱离当前相册状态的旧计划；
- 增加 `failed` 终态、尝试次数、失败原因和失败时间，执行变更回滚后单独保存审计信息；
- 新增用户隔离的操作记录页，可按待确认、已执行、已撤销、失败和过期过滤，并可从记录重新打开相册或旅行日志；
- 相册计划可绑定当前用户的 `AIArtifact`，跨用户 artifact ID 会在生成计划时被拒绝；
- 补齐过期、失败、artifact owner 隔离单测，以及“历史加载 → 确认执行 → 撤销”前端 E2E。

P2 本次先交付有明确产品闭环的“一句话旅行相册” MVP：

- 新增 `discover_trips` 工具，在 owner 隔离、有时间和地点的照片上，按连续拍摄日期聚合最多 12 个候选旅行，同时关联区间内火车票和机票；
- 候选仅是可解释的建议，返回日期、地点、拍摄日数、照片数、来源 ID 和命中原因，Agent 必须让用户确认范围；
- 新增复合 `travel-album` Skill，串联旅行发现、时间线、票据、代表照片选择、结构化旅行日志、个性化 HTML 和待确认相册计划；
- 作品与相册计划通过 `artifact_id` 关联：日志先持久化，相册仍需用户二次确认，确认前不修改相册；
- 相册页新增“AI 整理旅行”入口，会打开 Agent 并启动上述复合 Skill；同页也可进入操作记录。

本次旅行相册 MVP 不包括原路线中的人物时光机、回忆侦探和主动回忆；这些场景复用本次的候选发现、作品关联和操作审计基础，后续独立交付。

真实验收使用已部署的 PostgreSQL、`zhousk` 账号与 MiniMax-M3：先从 8416 张带地点照片中返回候选，再对 2026-01-17 西安范围的 14 张照片选出 6 张代表照片，成功生成结构化日志、7908 字符 HTML 和一个关联作品的 `proposed` 计划。验收过程发现并修复 PostgreSQL `SELECT DISTINCT` 排序兼容问题；同时增加结构化章节字段归一化，兼容模型输出的 `title/narrative/photo_id` 别名。作品页的结构化视图和 sandbox HTML 视图、操作历史页、相册入口在真实浏览器中均为 0 console errors。

## 21. P2.1 只读相册医生（2026-09-05）

相册医生把 Agent 从“按指令生成作品”扩展为“主动发现相册数据问题”，但本阶段坚持只读诊断：

- 新增内置 `album-doctor` Skill 和 `inspect_album_health` 工具，可体检整个照片库或用户拥有的指定相册；
- 统一检查缺少拍摄时间、地点、视觉描述和文件哈希的照片，以及未归档照片、完全重复照片组、空相册、相册计数不一致和封面缺失；
- 返回健康分、按优先级排列的问题、样本照片 ID、相册问题和可执行建议，所有查询都经过 owner 隔离；
- 相册页新增“AI 相册体检”入口，自动启动明确标注为只读的对话流程；
- Agent 只能解释诊断结果和建议下一步，不能删除照片、修改元数据或声称问题已经修复。重复照片继续引导用户到现有工具箱复核；未归档照片只有在用户选定范围后，才可转入 P1 的待确认相册计划。

真实数据验收覆盖 39098 张照片，查询耗时约 0.24 秒，得到健康分 54：缺地点 30682 张、缺视觉描述 6571 张、缺哈希 15248 张、未归档 35460 张、完全重复额外副本 1277 张（1194 组），没有发现空相册、计数不一致或封面缺失。MiniMax-M3 能正确加载 Skill、调用体检工具并区分“发现问题”和“已经修复”，对话结束后没有创建作品或操作计划，也没有修改或删除照片。

## 22. P2.2 回忆侦探（2026-09-05）

回忆侦探面向“我记得有一次……”这类无法用单一筛选条件表达的搜索，通过多线索召回、证据解释和视觉复核找回可能的照片事件：

- 新增内置 `memory-detective` Skill 和 `investigate_memory` 工具；Agent 先从自然语言中提取时间、地点、同行人、画面和照片文字，必要时一次只追问一个最有区分度的问题；
- 先用语义搜索召回画面相近的照片，再把地点、人物、描述、OCR 和语义照片 ID 做并集召回，避免因模糊记忆中的一条错误线索漏掉正确事件；
- 每张候选照片保留命中类型、命中词、得分、地点、人物、描述、OCR 样本和来源 ID；事件置信度来自独立证据类型数量，不把语义相似或地理 POI 直接当作事实；
- 有日期范围时仅在范围内检索；候选事件最长连续 7 天，同一天相邻照片间隔超过 6 小时会拆成不同经历，防止凌晨和中午的照片被错误合并；
- 单次最多载入 1000 张候选并明确返回总命中数和截断状态，提示 Agent 在范围过宽时继续追问，而不是在不完整结果上给出确定结论；
- Agent 最多给出 3 个候选，通过批量看图或联系表做视觉确认。用户确认后才可生成 `memory_story` 结构化作品及可选 HTML，侦查过程本身不创建相册、不修改或删除照片；
- 相册页新增“回忆侦探”入口，自动打开对话并加载对应 Skill；照片展示必须使用工具返回的 `thumbnail_url`，禁止模型自行拼接媒体地址。

真实验收使用已部署 PostgreSQL、`zhousk` 账号和 MiniMax-M3：模型依次加载 Skill、执行语义搜索、地点检索、证据融合和批量看图。对 2026-01-17 西安线索共召回 14 张照片；虽然照片 POI 为“西安城墙·碑林历史文化景区”，视觉描述实际是书桌和办公场景，模型正确拒绝把 POI 匹配解释成“游览古城”，明确区分了已确认事实与推测，并建议放宽日期继续查找。全过程没有创建作品、操作计划或相册，也没有修改照片。
