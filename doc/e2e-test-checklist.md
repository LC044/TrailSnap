# TrailSnap 端到端 (E2E) 测试用例清单

> 本文档基于对项目全量代码的扫描，定义 TrailSnap 系统的 E2E 测试用例，作为自动化测试脚本开发的基准路线图。
> 扫描范围：后端 `package/server/app/api/*`（26 个路由模块）、`package/server/app/service/tasks/*`（17 种 TaskType）、`package/server/app/crud/*`（19 个 CRUD 模块）；前端 `package/website/src/router/*`（30+ 路由）、`package/website/src/views/*`、`package/website/src/components/*`、`package/website/src/stores/*`（6 个 Pinia store）；AI 服务 `package/ai/app/routers/*`（8 个域）；CLI `package/trailsnap-cli/`（7 个子命令）；现有 Playwright 测试 `package/website/tests/e2e/specs/{auth,home,album}.spec.ts`。
> **未覆盖缺口**（现有 `auth/home/album` 三个 spec 之外）：toolbox、settings、agent、face、photo 详情、annual-report、ticket、photo 上传、AI 异步任务。

---

## 测试分层约定

| 级别 | 含义 | 触发时机 | 典型耗时 |
|------|------|----------|----------|
| **P0** | 冒烟测试：核心链路拉起 | PR 阶段必跑 | < 5 min |
| **P1** | 核心业务功能 | 每日构建（Nightly）| < 20 min |
| **P2** | 进阶 / AI 能力 | 需 mock-ai 容器 | < 60 min |
| **P3** | 边界 / 异常 | 每周 / 手动 | 不限 |
| **P4** | 跨域 / 集成 | 预发布 | 不限 |

---

## 一、P0 级 - 冒烟测试 (Smoke Tests)

> 目标：验证系统最基础的拉起、登录和主链路可用。已部分实现于 `auth.spec.ts` / `home.spec.ts`。

### 1.1 账号与会话
- [ ] **首次拉起自举**：首次启动，无任何用户时，第一个注册用户自动提升为管理员（验证 `auth.register` 返回的 role=admin）。
- [ ] **登录跳转**：使用管理员账号登录成功，前端 `localStorage.user_token` 写入有效 JWT，路由跳转到 `/`。
- [ ] **登出清理**：点击登出，前端清理 `trailsnap:` / `ticket-` / `trailsnap-location-` 前缀的 localStorage，跳回 `/login`。
- [ ] **路由守卫**：未登录访问受保护路由（如 `/photos`）被拦截至 `/login?redirect=<原路径>`；登录后回跳到 redirect 路径。
- [ ] **白名单放行**：`/login`、`/register`、`/forgot-password`、`/404`、`/annual-report` 无需登录即可访问。
- [ ] **登录态访问 /login 自动跳首页**：已登录用户访问 `/login` 重定向到 `/`。
- [ ] **Token 过期**：篡改/清除 `localStorage.user_token` 后请求 API 返回 401，前端自动跳登录页。
- [ ] **忘记密码两步流程**：第一步验证用户名，第二步回答自定义安全问题后重置成功并可立即登录。

### 1.2 任务拉起与监控
- [ ] **目录扫描入库**：在“外部图库”添加宿主/容器挂载目录后，后台能成功创建 `SCAN_FOLDER` 任务，并自动衍生 `PROCESS_BASIC` 子任务。
- [ ] **任务完成无大面积 FAILED**：所有 `PENDING` / `PROCESSING` 任务最终变为 `COMPLETED` 或 `CANCELLED`，FAILED 任务有清晰错误信息。
- [ ] **任务状态查询**：`GET /api/tasks/` 返回正确的 `PENDING/PROCESSING/COMPLETED/FAILED/CANCELLED` 五态及 `total_items/processed_items` 进度。
- [ ] **worker 进程拉起**：API 进程 lifespan 启动后能看到独立的 worker 子进程（验证 `app.worker.run_worker` 启动成功）。

### 1.3 主链路渲染
- [ ] **首页渲染**：进入 `/`，`OverviewCards` / `HeatmapSection` / `TimeChart` / `FaceSection` / `OnThisDay` 至少 1 个组件成功加载数据。
- [ ] **瀑布流请求**：首页 `loadPhotos` 成功发起请求并渲染导入的测试照片缩略图。
- [ ] **详情查看**：点击照片打开 `PhotoLightbox` / `PhotoMetadataSidebar`，展示“基本信息”等关键元素。
- [ ] **404 兜底**：访问不存在的路由（如 `/foo/bar`）显示 `NotFound.vue`。

### 1.4 系统健康
- [ ] **后端健康**：访问 `/docs`、`/openapi.json` 可用。
- [ ] **AI 服务健康**：`GET http://localhost:8001/health-check` 返回 200。
- [ ] **版本号**：`GET /api/system/version` 返回与 `package.json` 一致的版本字符串。

---

## 二、P1 级 - 核心业务功能 (Core Features)

> 目标：覆盖用户日常管理照片的高频和核心路径。

### 2.1 照片流与展示（`/photos`）
- [ ] **无限滚动**：导入照片数超过单页限制时，向下滚动触发 `loadPhotos` 分页加载。
- [ ] **时间轴聚类**：照片按年/月/日正确分组（验证 `AlbumTimeline` 浮动指示器显示正确月份）。
- [ ] **原图加载**：在 `PhotoLightbox` 中能成功请求并渲染高分辨率原图（而非缩略图），缩放/平移流畅。
- [ ] **EXIF 解析显示**：照片详情能正确展示 Make（品牌）、Model（型号）、快门、光圈、ISO 信息（基于标准测试照片）。
- [ ] **视频播放**：导入 `.mp4` / `.mov` 视频，在 `PhotoLightbox` 中能调起 video 播放器。
- [ ] **HEIC 渲染**：导入 `.heic` 文件，前端能通过转码后的 jpeg/webp 正常显示缩略图。
- [ ] **多选操作**：勾选多张照片后，工具栏出现"下载/删除/添加到相册/添加到人物/OCR"操作，全部可点击。
- [ ] **筛选面板**：FilterPanel 支持按来源 / 拍摄时间 / 地点 / 标签 / AI 分类 / 相机品牌型号筛选，结果正确收敛。
- [ ] **筛选条件缓存**：刷新页面后 `selectedFilters` 仍能保留（photoStore 内 24h localStorage 缓存）。

### 2.2 相册管理（`/album`）
- [ ] **创建普通相册**：新建空相册，相册列表正确显示。
- [ ] **创建条件相册**：基于筛选条件（年份/城市/标签）创建，SCAN_ALBUM 任务自动补齐匹配照片。
- [ ] **创建智能相册**：基于人物/分类/地点创建，AI 任务完成后自动归集。
- [ ] **添加照片到相册**：选中单张/多张照片，加入指定相册，相册详情内可见。
- [ ] **移除照片**：从相册内移除某张照片（不删除原文件），相册 `num_photos` 正确减少。
- [ ] **设封面**：在相册详情中点"设为封面"，封面图片正确更新。
- [ ] **删除相册**：删除自定义相册，操作成功且不影响系统内照片总数。
- [ ] **智能相册同步**：条件/智能相册的图片集随相关数据变化（新增照片 / 标签更新）而动态变化。
- [ ] **AlbumSelector 对话框**：在 `PhotoLightbox` 中调起"添加到相册"对话框，支持搜索/新建相册。

### 2.3 智能分类（`/album/classification`）
- [ ] **分类网格**：智能分类列表正确展示 YOLO 模型识别出的所有标签。
- [ ] **分类详情**：进入某个分类（如"风景"），列出所有匹配照片。
- [ ] **设为封面**：分类内照片可设封面。
- [ ] **从分类中移除**：批量操作"从分类中移除"成功（注意：不会删除照片，仅解除 tag 关联）。

### 2.4 人物（`/album/people`）
- [ ] **人物列表**：聚类完成后人物列表展示（已命名 / 未命名 / 隐藏三态可筛选）。
- [ ] **人物详情**：进入某个人物详情，展示其所有照片。
- [ ] **人物编辑**：在 `IdentityEditDialog` 中编辑姓名/描述/标签，保存后正确更新。
- [ ] **设为封面**：为人物设置封面头像（`PersonAvatar` 裁切到人脸位置）。
- [ ] **合并模式**：合并模式下支持合并/隐藏/显示/删除批量操作。
- [ ] **PersonSelector**：在 `PhotoLightbox` 中调起"添加到人物"对话框，支持搜索/新建人物。

### 2.5 位置与地图（`/album/location`）
- [ ] **位置网格**：LocationList 默认 grid 视图正确展示所有地点（按照片数倒序）。
- [ ] **视图切换**：grid / map / timeline / trajectory 四种视图可正常切换。
- [ ] **地图聚类**：`LocationMap.vue` 用天地图 + Supercluster，渲染正确数量的位置标记（Marker）。
- [ ] **下钻**：点击地图 Marker 下钻到 `LocationDetail`，显示该位置下的照片。
- [ ] **轨迹视图**：`LocationTrajectoryView` 显示地图+可折叠时间列表，移动端支持底部抽屉。
- [ ] **时间线视图**：`LocationTimelineView` 按月分组的足迹时间线（节点形式）。
- [ ] **景区管理**：在 `AddSceneDialog` 中新增/编辑/删除景区（基于 polygon 或 radius 匹配）。
- [ ] **按年/范围筛选**：时间筛选（年份/自定义范围）生效。

### 2.6 搜索（`/search` & `/mobile-search`）
- [ ] **基础文件名搜索**：输入文件名片段，正确返回结果。
- [ ] **拍摄时间筛选**：日期选择器筛选特定时间段内照片。
- [ ] **文件类型筛选**：筛选只包含"视频"或"图片"。
- [ ] **AI 语义搜索**（`/api/search/text`）：输入自然语言描述，CLIP 文本向量检索出匹配图片。
- [ ] **搜索建议**：移动端搜索自动补全（人物/地点/标签）。
- [ ] **搜索结果分页**：搜索结果 `FlatPhotoGallery` 无限滚动加载。

### 2.7 回收站（`/recycle-bin`）
- [ ] **移至回收站**：删除某张照片后，主时间轴消失，该照片出现在"回收站"中。
- [ ] **恢复照片**：从回收站恢复，照片重新回到主时间轴的对应时间点。
- [ ] **永久删除**：在回收站中执行彻底删除，数据库记录消失（如果配置允许，物理文件应被标记或处理）。
- [ ] **回收站倒计时**：`RecycleBinPage` 展示剩余天数（基于配置的天数阈值）。
- [ ] **定时清理**：回收站清理调度器按配置时间清理过期 deleted 照片（可在任务管理验证 cron 触发）。

### 2.8 工具箱（`/toolbox`）
- [ ] **低分清理**：基于 `memory_score + quality_score` 升序列出照片，可一键清理。
- [ ] **相似照片清理**：启动 `SIMILAR_PHOTO_CLUSTERING` 任务，进度条实时更新，完成后展示分组（保留最佳）。
- [ ] **重复照片清理**：启动 `FIND_DUPLICATE_PHOTOS` 任务（计算 MD5），完成后按 MD5 分组展示。
- [ ] **图片整理**：启动 `ORGANIZE_PHOTOS` 任务，支持 `time/category/person/location` 四种策略、`move/copy` 两种动作、多种粒度（`ym/ymd`、`province/city/district/...`）。
- [ ] **批量重命名**：启动 `BATCH_RENAME` 任务，按 `prefix + YYYYMMDD_HHMMSS + suffix + ext` 重命名。
- [ ] **从文件名改时间**：启动 `BATCH_TIME_FROM_FILENAME` 任务，解析文件名时间戳并写入 EXIF。
- [ ] **任务状态轮询**：所有工具箱任务通过 `GET /api/toolbox/<task>/tasks/latest` 轮询进度，前端进度条正确更新。
- [ ] **任务失败显示**：任务失败时显示错误信息（不是无限加载）。

### 2.9 车票（`/ticket` & `/statistics`）
- [ ] **车票列表**：火车票/机票合并展示，按 `date_time` 倒序。
- [ ] **筛选/排序**：按 `all/highspeed/normal/flight` 筛选，按 `date/distance/duration/price` 排序。
- [ ] **新增火车票**：通过 `TicketFormModal` 新增火车票，字段（车次、出发/到达、时间、座位、票价）保存成功。
- [ ] **新增机票**：通过 `FlightTicketFormModal` 新增机票。
- [ ] **智能填充**：在表单中上传车票图片，调用 AI 服务 `/tickets/predict` 自动填充字段。
- [ ] **批量删除**：勾选多张车票批量删除。
- [ ] **导入/导出**：通过 `TicketExportModal` 导出车票，导入文件解析成功。
- [ ] **纸质票查看**：`TicketPaperModal` 弹窗展示原图。
- [ ] **车票可视化**：`TrainTicket.vue` 组件导出为图片成功。
- [ ] **旅行足迹报告**：`/statistics` 页面地图+统计卡片正确加载（总时长、总里程、城市数、乘车人统计）。
- [ ] **车票里程计算**：基于 12306 时刻表 API 的里程/经停站计算正确（`/railway/train-schedules` 可用时）。
- [ ] **手动编辑车票**：`/toolbox/ticket-edit` More.vue 表单编辑成功。

### 2.10 上传（`MultiFileUpload`）
- [ ] **拖拽上传**：拖拽多张照片到上传区域，触发后台入库任务。
- [ ] **点击上传**：点击选择文件对话框，多选文件上传。
- [ ] **批量上传到相册**：上传时可选目标相册。
- [ ] **视频上传**：支持 `.mp4` / `.mov` 上传。
- [ ] **HEIC 上传**：支持 `.heic` 上传（后端转码后入库）。
- [ ] **Live Photo 配对**：同名 `.heic + .mov` / `.jpg + .mp4` 被自动识别为实况照片（Apple/Vivo 厂商已注册；Android parser 未注册，预期失败）。

### 2.11 设置中心（`/settings`，7 个 Tab）
- [ ] **用户管理**：管理员可添加用户/重置密码/删除用户，普通用户看不到该 Tab。
- [ ] **任务管理**：按类型分类展示任务，支持启动/暂停/继续/扫描缺失/重新开始/清空；`pause_category` 阻止新任务拉取，`resume_category` 恢复。
- [ ] **基础设置**：安全设置 / 地图提供商+Key / 缩略图策略 / Live Photo 提取视频 / 隐式 EXIF 时区 / 清空数据 / 导入导出配置 全部可保存生效。
- [ ] **外部图库**：添加/扫描/移除目录、配置文件名正则过滤、配置最小大小过滤。
- [ ] **API 令牌管理**：新增/复制/撤销 Agent Token（与用户 JWT 分开，AI 客户端可独立授权）。
- [ ] **关于页面**：项目介绍、功能、版本信息显示正确。
- [ ] **问题反馈**：跳转 GitHub Issues 链接正确。

### 2.12 AI 助手（AgentChat）
- [ ] **打开对话浮层**：点击 AI 助手按钮唤起 `AgentChat.vue`。
- [ ] **新建/切换/置顶/删除会话**：会话侧栏操作全部成功（`/api/agent/sessions*`）。
- [ ] **选择模型**：顶部下拉框可选择不同 LLM 模型。
- [ ] **发送消息**：调用 `search_photos_tool` 搜索照片，工具调用结果在消息中显示。
- [ ] **流式响应**：SSE 流式输出，消息逐字渲染。
- [ ] **中止生成**：点击终止按钮，请求被中断。
- [ ] **编辑/重生成/复制消息**：消息操作菜单功能完整。
- [ ] **批量删除消息**：顶部操作可批量删除。
- [ ] **工具调用**：验证 `search_photos_tool` / `get_photo_locations_tool` / `get_photo_tags_tool` / `get_photo_persons_tool` / `get_photo_details_tool` 至少各 1 次成功调用。

### 2.13 年度回忆录（`/annual-report`）
- [ ] **封面/照片墙/时间统计/高光**：前 4 节（SectionCover / SectionPhotoWall / SectionTime / SectionHighlight）正确渲染。
- [ ] **总结/分类/地点**：SectionAccount / SectionCategory / SectionLocation 数据正确。
- [ ] **最远城市/季节/消费/出行分析**：SectionFarthestCity / SectionSeason / SectionExpense / SectionTransportAnalysis 数据正确。
- [ ] **寄语/彩蛋/结尾**：SectionMessage / SectionEasterEgg / SectionEnd 渲染。
- [ ] **空白布局**：使用 `blank` layout（无左侧导航）。
- [ ] **重看**：刷新或重进页面可重新播放。

### 2.14 首页（`/`）
- [ ] **那年今日**：`OnThisDay.vue` 轮播组件自动播放，全屏查看正常。
- [ ] **统计卡**：OverviewCards 展示照片+视频、今日新增、占用空间。
- [ ] **热力图**：`HeatmapSection` 渲染拍摄热力图。
- [ ] **人物入口**：`FaceSection` 跳转到 `/album/people`。

### 2.15 任务管理（API 层）
- [ ] **任务查询**：`GET /api/tasks/` 支持按状态/类型分页筛选。
- [ ] **任务取消**：取消 PENDING 任务，状态变 `CANCELLED`。
- [ ] **任务重试**：单条重试 `retry_task`、批量重试 `retry_all_failed_tasks`。
- [ ] **Fast Mode**：`set_fast_mode` 切换后非 AI 任务并发数提升。
- [ ] **优先级抢占**：高优先级任务（如 `ORGANIZE_PHOTOS` priority=1000）插队。
- [ ] **Worker 重启恢复**：worker 异常重启后 `PROCESSING` 任务重置为 `PENDING`，`force=True` 任务会清除 force 标记。

### 2.16 媒体接口
- [ ] **缩略图请求**：`/api/medias/<id>?size=small|medium|large` 返回正确尺寸缩略图。
- [ ] **原图流**：`/api/medias/<id>` 返回原图二进制流。
- [ ] **视频流**：视频文件支持 Range 请求边下边播。

### 2.17 CLI（`trailsnap-cli`）
- [ ] **config set**：配置 `API_URL` 和 `Token` 后写入 `.env` 持久化。
- [ ] **photos list**：列出照片（多维筛选：skip/limit/order_by/start-time/end-date/album-id/people-id/tag-id/city/province/scene/make/model）。
- [ ] **photos info**：获取单张照片详情。
- [ ] **photos delete**：删除照片。
- [ ] **tags list** / **albums list** / **locations list/timeline** / **people list** / **folders list**：各子命令正确返回 JSON。
- [ ] **medias get**：下载媒体文件（支持 `format=base64|file|url`，`size=small|medium|large`）。
- [ ] **格式切换**：`--format {json|pretty|table|ndjson|csv}` 输出格式正确。

### 2.18 Railway 子应用（`/railway`）
- [ ] **时刻表数据**：12306 时刻表 `train-schedules` 接口可用。
- [ ] **里程/经停站计算**：基于时刻表的车票里程计算正确（供 `RECOGNIZE_TICKET` 任务使用）。
- [ ] **子应用独立 DB**：`RAILWAY_DB_URL` 配置独立数据库连接成功。

---

## 三、P2 级 - 进阶与 AI 能力 (Advanced & AI Features)

> 目标：验证 TrailSnap 特色的 AI 识别、地理、多模态能力。**需在包含 mock-ai 容器或真实 GPU AI 服务的环境中测试。**

### 3.1 媒体格式兼容性
- [ ] **HEIC 渲染**：（已在 P1 列出，此处补充）验证后端 `pillow_heif` opener 正确注册，EXIF 完整读取。
- [ ] **视频播放**：（已在 P1 列出）支持 `.mp4` / `.mov` 视频元数据（duration/width/height）正确解析。
- [ ] **Live Photo**：
  - Apple 同名 `.heic + .mov` 配对成功（`AppleLivePhotoParser`）。
  - Vivo 同名 `.jpg + .mp4` 配对成功（`VivoLivePhotoParser`）。
  - Android 同名 `.jpg + .mp4` 配对**预期失败**（parser 未在 `LivePhotoService.parsers` 中注册）。
  - 详情页同时展示静态图+视频（Live Photo 联动播放）。
- [ ] **无 EXIF 照片**：导入擦除了元数据的图片，扫描任务不崩溃，时间取文件系统 mtime 或文件名解析。
- [ ] **Google Motion Photo**：检测 XMP `MicroVideoOffset`，自动提取嵌入视频。
- [ ] **截图识别**：iOS/Android 截图（无相机 EXIF）正确归类为 `SCREENSHOT`（`determine_image_type`）。

### 3.2 地点与地图
- [ ] **经纬度解析**：导入包含 GPS 信息的照片，详情页 `PhotoMetadataSidebar` 显示"城市"/"省份"/"国家"。
- [ ] **反向地理编码**：`reverse_geocoder` 提取省/市/区正确。
- [ ] **景区匹配**：`identify_scene` 通过 polygon 或 radius 匹配 `Scene` 记录。
- [ ] **天地图 Key 配置**：`BasicSettings` 填入 Key 后地图正常加载。

### 3.3 AI 识别处理
- [ ] **视觉标签 (YOLO Classification)**：验证系统能提取图像特征并打上基础标签（如"风景"/"猫"）。`/api/ai/image-classification/` 返回 confidence < 0.75 或 `others` 时正确跳过。
- [ ] **OCR 文字识别**：针对包含大段文字的测试图片，调用 `/api/ai/ocr/predict`（120s 超时）返回 `prunedResult.rec_texts/scores/polys`，polygon 坐标正确归一化（0-1），照片详情 OCR 面板展示文本。
- [ ] **人脸识别聚类**：导入包含同一个人多张脸的照片，调用 `/api/ai/face/face-recognition` 提取 embedding，`FaceClusterService` 聚类后在 `/album/people` 聚合出人物档案。
- [ ] **图片向量化**：调用 `/api/ai/embedding/image` 存到 `ImageVector.embedding` 表，用于相似照片搜索。
- [ ] **文本向量化**：调用 `/api/ai/embedding/text` 返回 CLIP 文本向量（用于以文搜图）。
- [ ] **车票识别**：上传车票图片，调用 `/api/ai/tickets/predict`，自动识别为 `TrainTicket` 或 `FlightTicket` 入库。
- [ ] **视觉描述（多模态 LLM）**：调用 `VISUAL_DESCRIPTION` 任务，LLM 返回 description/memory_score/beauty_score/tags/reason/narrative JSON 正确解析并存到 `ImageDescription` 表。
- [ ] **车票自动识别**：YOLO 分类检测到"火车票/机票"时自动调度 `RECOGNIZE_TICKET` 任务（分类 → 车票联动）。

### 3.4 LLM Agent 工具调用
- [ ] **search_photos_tool**：按多维筛选（日期/地点/省/市/区/景区/标签/人物/CLIP 描述/排序）返回正确结果。
- [ ] **get_photo_locations_tool**：返回照片足迹时间轴，支持 provinces/cities/districts/scenes 维度。
- [ ] **get_photo_tags_tool**：返回照片分类标签（去重）。
- [ ] **get_photo_persons_tool**：返回照片中的人物/身份标签（去重）。
- [ ] **get_photo_details_tool**：返回照片详细描述/标签/旁白。

### 3.5 LLM 子进程管理
- [ ] **LLM 启动**：`llm_manager.py` 自动启动 llama.cpp 子进程（端口 8002）。
- [ ] **LLM 空闲退出**：默认 5 分钟空闲后子进程自动退出，释放显存。
- [ ] **AI 服务空闲退出**：非 Windows 平台 600 秒（`IDLE_TIMEOUT`）空闲后 `sys.exit(0)`，由容器编排器重启。
- [ ] **OpenAI 兼容 API**：`/v1/chat/completions` 透传 LLM 子进程，支持流式。

### 3.6 任务调度核心
- [ ] **优先级队列**：`asyncio.PriorityQueue` × 3（CPU/IO/AI）按 `(-priority, count, batch)` 入队。
- [ ] **块大小**：`get_chunk_size` 决定批大小（VISUAL_DESCRIPTION: 2, PROCESS_BASIC/EXTRACT_METADATA: 16, CLASSIFY_IMAGE/IMAGE_EMBEDDING: 8）。
- [ ] **AI 降级 IO**：用户配置 `ai.analysis_connection_id == 'builtin'` 时，AI 任务被降级到 IO 队列。
- [ ] **定时扫描**：interval 模式（按分钟间隔）、weekly 模式（周几定时）触发 `SCAN_FOLDER` 任务。
- [ ] **回收站定时清理**：每天固定时间清理 `is_deleted=True` 且超期照片。
- [ ] **任务结果回写**：`result_loop` 批量回写结果（50 条/批或 1 秒间隔）。

### 3.7 性能指标（Soft 指标，不强制）
- [ ] **入库吞吐**：1000 张照片在 1 小时内完成 SCAN + PROCESS_BASIC + 7 项 AI 任务。
- [ ] **人脸聚类**：1000 张含人脸照片在 10 分钟内完成聚类（依赖 AI 服务吞吐）。
- [ ] **相似照片**：1 万张照片 `SIMILAR_PHOTO_CLUSTERING` 在 1 小时内完成。
- [ ] **MD5 去重**：1 万张照片 `FIND_DUPLICATE_PHOTOS` 在 1 小时内完成。
- [ ] **首页加载**：1000 张照片场景下首页首屏 < 2s。
- [ ] **详情加载**：单张照片详情页 < 1s（缩略图命中缓存）。

---

## 四、P3 级 - 边界与异常测试 (Edge Cases & Exceptions)

> 目标：验证系统的健壮性与边界处理。

### 4.1 文件级异常
- [ ] **损坏文件**：放入 0 字节 jpg 或文件头损坏的 jpg，扫描任务标记为 FAILED 而不阻塞其他文件入库。
- [ ] **重复导入（MD5 相同）**：配置相同照片目录或放入 md5 相同文件，验证防重机制不产生重复 `Photo` 行（按 `md5` 唯一键去重）。
- [ ] **超大文件/分辨率**：放入 200MB TIFF 全景图，缩略图生成不导致后端 OOM（应有 `min_width/min_height` 过滤或流式处理）。
- [ ] **极小文件**：放入 1x1 px 图片，缩略图生成成功。
- [ ] **非图片后缀伪装**：将 jpg 改名为 `.txt` 放入目录，验证文件名正则过滤是否正确拦截。
- [ ] **超长文件名**：放入文件名 200+ 字符的图片，验证文件系统兼容性（Linux ext4: 255 字符上限）。
- [ ] **特殊字符文件名**：包含 `:*?"<>|` 的文件名，验证 `ORGANIZE_PHOTOS` 非法字符过滤生效。
- [ ] **同名冲突**：目录内存在两个同名文件，验证入库不会丢失。
- [ ] **文件名时间戳提取**：`extract_datetime_from_filename` 识别多种日期格式（`YYYYMMDD_HHMMSS` / `YYYY-MM-DD HH.MM.SS` / `IMG_20240101` 等）。

### 4.2 任务级异常
- [ ] **AI 服务 5xx 错误**：模拟 AI 服务不可用，相关任务（RECOGNIZE_FACE / OCR / CLASSIFY_IMAGE / VISUAL_DESCRIPTION）正确标记 FAILED，前端展示错误信息。
- [ ] **AI 服务超时**：OCR 任务 120 秒超时、VISUAL_DESCRIPTION API 60 秒超时正确触发。
- [ ] **AI 服务返回空结果**：embedding 为空 / OCR 文本为空 时任务优雅处理不崩溃。
- [ ] **Task worker 崩溃**：模拟 worker 进程被 kill，API 进程能自动 `restart_worker`。
- [ ] **数据库连接中断**：DB 不可用时 API 返回 5xx 而非挂起。
- [ ] **任务队列溢出**：PENDING 任务超过 50 条时只接受更高优先级任务（验证背压）。
- [ ] **PROCESSING 任务恢复**：worker 启动时 `_recover_unfinished_tasks` 将所有 PROCESSING 任务重置为 PENDING。
- [ ] **force 标记清除**：PROCESSING 中断后，force=True 任务的 force 标记被清除（避免无限强制重试）。
- [ ] **大文件去重 OOM**：1 万张照片 `FIND_DUPLICATE_PHOTOS` 异步并发（batch=20）不导致 OOM。

### 4.3 权限与并发
- [ ] **目录权限不足**：放入无读权限的子目录，`SCAN_FOLDER` 任务 `OSError` 捕获后继续扫描其他目录。
- [ ] **磁盘空间不足**：ORGANIZE_PHOTOS `move` 时磁盘满，正确处理失败文件。
- [ ] **并发编辑相册**：两个客户端同时编辑同一相册，后提交者覆盖前提交者（基于最后写入获胜，可接受）。
- [ ] **并发删除照片**：两个客户端同时删除同一张照片，其中一个返回 404，另一个成功。

### 4.4 安全与认证
- [ ] **越权访问**：普通用户访问 `/api/users/*`（管理员接口）返回 403。
- [ ] **Agent Token 越权**：使用一个用户的 Agent Token 访问另一个用户的照片返回 403。
- [ ] **JWT 过期**：超过 JWT 过期时间后请求返回 401。
- [ ] **密码哈希**：数据库中存储的密码是 bcrypt 等不可逆哈希，不是明文。
- [ ] **SQL 注入**：参数化查询正确（不应出现 `f"SELECT * FROM photo WHERE id = {id}"` 这类拼接）。
- [ ] **路径穿越**：上传文件名包含 `../../etc/passwd` 时被清洗为合法文件名。
- [ ] **CORS**：开发环境跨域请求正常放行，生产环境按预期限制来源。

### 4.5 多端兼容
- [ ] **桌面浏览器**：Chrome / Edge / Firefox 最新版可正常打开。
- [ ] **移动浏览器**：移动端布局正常，触摸交互（缩放、滑动）有效。
- [ ] **深色模式**：所有页面在 `html.dark` 模式下颜色正确（`el-dialog` / `el-select` / `el-slider` 等组件继承 `--el-bg-color: #111827`）。
- [ ] **主题色切换**：5 种主题（sky / emerald / violet / rose / amber）切换后所有 `primary-*` 工具类颜色联动，`injectTheme()` 调用的 JS 绘图（地图、图表）也重新执行。
- [ ] **键盘可达性**：所有交互元素有 `focus-visible:ring-2 focus-visible:ring-primary-500` 焦点环。

---

## 五、P4 级 - 跨域与集成测试 (Integration & Cross-Domain)

> 目标：覆盖多服务协作、CI/CD、CLI 等横切关注点。

### 5.1 多服务集成
- [ ] **完整入库链路**：SCAN_FOLDER → PROCESS_BASIC → {EXTRACT_METADATA, RECOGNIZE_FACE, OCR, CLASSIFY_IMAGE, VISUAL_DESCRIPTION, IMAGE_EMBEDDING} 整条链路在真实 AI 容器下端到端跑通。
- [ ] **分类 → 车票联动**：YOLO 分类识别出"火车票"后，`RECOGNIZE_TICKET` 任务被自动调度并成功入库。
- [ ] **EXIF → 条件相册**：`EXTRACT_METADATA` 完成后，条件相册（如"今年夏天的照片"）自动更新。
- [ ] **人脸聚类 → 条件相册**：`RECOGNIZE_FACE` 完成后，条件相册（如"所有包含 A 的照片"）自动更新。
- [ ] **批量改时间 → 条件相册**：`BATCH_TIME_FROM_FILENAME` 完成后触发条件相册更新。

### 5.2 Docker / CI
- [ ] **docker-compose 拉起**：`docker-compose up` 一次性拉起 postgres(pgvector) / server / ai / frontend(nginx) 四个服务。
- [ ] **后端 Docker 构建**：commit 含 "构建后端" 触发 `.github/workflows/docker-build-push-server.yml`，镜像推送到 Docker Hub。
- [ ] **前端 Docker 构建**：commit 含 "构建前端" 触发 `docker-build-push-frontend.yml`。
- [ ] **AI Docker 构建**：commit 含 "构建ai" / "构建AI" 触发 `docker-build-push-ai.yml`（matrix: CPU/GPU）。
- [ ] **CLI 构建**：commit 含 "构建cli" 触发 `build-publish-cli.yml`，产物保留在 Actions Artifacts；推送 `v*.*.*` 标签时才发布到 Release、npm 和 PyPI。
- [ ] **E2E CI**：commit 含 "执行测试" 触发 `e2e-system-tests.yml`，Playwright 20min timeout。
- [ ] **Tag 触发**：push `v*.*.*` tag 触发所有构建/发布流水线。
- [ ] **AI GPU 镜像**：`Dockerfile.gpu`（CUDA 12.8）正确构建并启动。

### 5.3 数据库迁移
- [ ] **Alembic 升级**：`alembic upgrade head` 在干净 DB 上正确执行。
- [ ] **Alembic 降级**：`alembic downgrade -1` 平滑回滚。
- [ ] **Alembic 自动生成**：修改 ORM 后 `alembic revision --autogenerate -m "..."` 生成的迁移文件无遗漏。
- [ ] **不删字段**：迁移文件中不直接 `drop_column`（必须有数据迁移步骤）。
- [ ] **pgvector 扩展**：首次启动自动 `CREATE EXTENSION IF NOT EXISTS vector`。
- [ ] **Railway 独立 DB**：`RAILWAY_DB_URL` 指向独立 Postgres，railway 子应用迁移独立执行。

### 5.4 CLI 集成
- [ ] **AI Agent 调用 CLI**：在 Claude Code / OpenClaw 环境中通过 `trailsnap-cli` 技能查询照片元数据（验证 `skills/trailsnap-cli/` 可用）。
- [ ] **多种输出格式**：`--format {json|pretty|table|ndjson|csv}` 全部可用，编码（UTF-8）正确。
- [ ] **跨平台二进制**：ubuntu-latest / windows-latest / macos-14 三平台 CLI 二进制均可运行。

### 5.5 备份与恢复
- [ ] **配置导入导出**：通过 `BasicSettings` 导出配置 JSON，再导入恢复。
- [ ] **数据清空**：`BasicSettings` 的"清空数据"按钮二次确认后正确清空（按预期清空哪些数据需验证）。
- [ ] **照片物理文件**：删除照片后物理文件是否保留（取决于 `delete_strategy` 配置）行为可预期。

---

## 六、API 端点覆盖矩阵（按后端路由模块）

> 以下矩阵基于扫描结果，确保每个 API 域至少有一条测试用例。

| 模块 | 端点抽样 | 建议测试覆盖 |
|------|----------|--------------|
| `auth.py` | POST /auth/login, /auth/register, /auth/me | P0 登录、P0 首次自举 |
| `user.py` | /users/* CRUD | P1 用户管理、P3 越权 |
| `login.py` | 登录辅助 | P0 |
| `photo.py` | /photos/* CRUD, batch | P1 照片流、P3 批量删除 |
| `metadata.py` | /photo-metadata/* | P1 EXIF |
| `album.py` | /albums/*, /conditional-albums/* | P1 相册、P2 条件相册 |
| `face.py` | /faces/identities/*, /faces/clusters/* | P1 人物、P2 人脸聚类 |
| `ocr.py` | /ocr/* | P2 OCR |
| `classification.py` | /tags/*, /classification/* | P1 智能分类、P2 YOLO |
| `location.py` | /locations/*, /scenes/* | P1 位置、P2 景区匹配 |
| `scene.py` | /scenes/* | P2 景区管理 |
| `train_ticket.py` | /train-ticket/* | P1 车票 |
| `flight_ticket.py` | /flight-ticket/* | P1 车票 |
| `annual_report.py` | /annual-report/* | P1 年度报告 |
| `tasks.py` | /tasks/*, /task-categories/* | P0 任务监控、P1 任务管理 |
| `system.py` | /system/*, /health | P0 |
| `media.py` | /medias/* | P1 媒体接口 |
| `metadata.py` | /metadata/* | P1 EXIF |
| `index.py` | /index/rebuild, /index/status | P1 索引重建 |
| `search.py` | /search/text | P1 搜索 |
| `toolbox.py` | /toolbox/* | P1 工具箱 |
| `settings.py` | /settings/* | P1 设置中心 |
| `stats.py` | /stats/*, /statistics/* | P1 旅行足迹 |
| `agent.py` | /agent/sessions/*, /agent/chat/* | P1 AI 助手 |
| `agent_token.py` | /tokens/* | P1 令牌管理 |
| `nav.py` | /nav/items* | P1 导航 |
| `railway/api.py` | /railway/* | P1 Railway 子应用 |

### AI 服务端点
| 模块 | 端点 | 建议测试 |
|------|------|----------|
| `face.py` | POST /face/face-recognition | P2 人脸 |
| `ocr.py` | POST /ocr/predict | P2 OCR |
| `tickets.py` | POST /tickets/predict | P2 车票 |
| `image_classification.py` | POST / | P2 YOLO |
| `embedding.py` | POST /text, /image | P2 向量化 |
| `llm.py` | /v1/* (OpenAI 兼容) | P2 LLM |
| `ai_config.py` | GET /config, POST /config/model | P2 模型切换 |
| `system.py` | GET /health-check, /version | P0 |

---

## 七、测试数据准备

### 7.1 必需数据集
- **基础照片集**：100 张含 EXIF（带 GPS）的 JPG，覆盖多个城市、年份、相机品牌。
- **HEIC 照片**：至少 5 张 iPhone `.heic` 原图。
- **视频**：至少 5 个 `.mp4` / `.mov`，含 H.264/H.265 编码。
- **Live Photo**：1 套 Apple（.heic + .mov）、1 套 Vivo（.jpg + .mp4）。
- **Motion Photo**：1 张 Google Motion Photo（含嵌入视频）。
- **含文字图片**：3 张含大段中英文的截图/文档照片（用于 OCR）。
- **含人脸照片**：10 张包含 2-3 个不同人脸的照片（用于聚类）。
- **截图**：2 张 iOS/Android 截图（无 EXIF）。
- **损坏文件**：1 个 0 字节 jpg、1 个文件头损坏 jpg。
- **重复文件**：2 个 MD5 相同的照片（不同文件名）。
- **车票图**：2 张火车票、2 张机票（用于车票识别）。
- **超大文件**：1 张 200MB TIFF（用于内存压力测试）。

### 7.2 Mock 与 Stub
- **mock-ai 容器**：在 CI 中提供 mock AI 服务（FastAPI 桩）以避免对真实 GPU 依赖。
- **LLM Mock**：`/v1/chat/completions` 返回固定 JSON（description + scores + tags）。
- **12306 Mock**：`/railway/train-schedules` 返回固定时刻表数据。

---

## 八、自动化测试执行建议

| 场景 | 覆盖级别 | 触发条件 | 预计耗时 | 备注 |
|------|----------|----------|----------|------|
| **PR Smoke** | P0 | 每个 PR | < 5 min | 仅跑 auth/home/smoke 三个 spec |
| **每日构建 (Nightly)** | P0 + P1 | cron daily | < 20 min | + 全部 spec（mock-ai） |
| **AI 集成 (Weekly)** | P0 + P1 + P2 | weekly | < 60 min | + 真实 AI 服务（GPU runner） |
| **发布前回归 (Release)** | P0 + P1 + P2 + P3 | tag 推送前 | 2-4 hours | 完整数据集 + 人工验收 |
| **跨域集成 (Manual)** | P4 | 发布前 | 不限 | docker-compose + 真实环境 |

### Playwright 测试目录建议扩展

`package/website/tests/e2e/specs/` 当前缺失：
- `toolbox.spec.ts`（6 个工具子页面）
- `settings.spec.ts`（7 个 Tab）
- `agent.spec.ts`（AI 助手）
- `face.spec.ts`（人物详情、合并模式）
- `photo-detail.spec.ts`（PhotoLightbox、PhotoEditor、PhotoOCRPanel）
- `annual-report.spec.ts`（13 个 Section）
- `ticket.spec.ts`（火车/机票 CRUD、智能填充、统计）
- `upload.spec.ts`（MultiFileUpload、Live Photo 配对）
- `search.spec.ts`（基础搜索、AI 语义搜索）
- `theme.spec.ts`（5 种主题 + 暗色模式）
- `recycle-bin.spec.ts`（恢复/永久删除）
- `task-mgmt.spec.ts`（任务监控、暂停/恢复、Fast Mode）

### 服务端集成测试

`package/server/tests/` 现有 `test_api_integration.py`，建议扩展：
- `test_tasks_lifecycle.py`（任务创建→执行→完成/失败/重试）
- `test_scan_folder.py`（目录扫描、Live Photo 配对）
- `test_album_sync.py`（条件相册动态更新）
- `test_worker_recovery.py`（worker 崩溃恢复）
- `test_auth_security.py`（越权、JWT、密码哈希）
- `test_storage_limits.py`（超大文件、磁盘空间）

---

## 九、附录：模块到测试用例的索引

| 测试模块 | 章节 | 关键路径 |
|----------|------|----------|
| 账号会话 | §1.1, §2.11, §4.4 | `auth.py`, `login.py`, `user.py`, `views/login/*` |
| 任务系统 | §1.2, §2.15, §3.6, §4.2 | `service/tasks/*`, `task_manager.py`, `task_worker.py`, `worker.py` |
| 照片流 | §2.1, §2.10, §4.1 | `api/photo.py`, `views/PhotosPage.vue`, `MultiFileUpload.vue` |
| 相册 | §2.2 | `api/album.py`, `views/album/*`, `crud/album.py` |
| 分类 | §2.3 | `api/classification.py`, `views/album/intelligent-classification/*` |
| 人物 | §2.4 | `api/face.py`, `views/album/people/*`, `service/face_cluster.py` |
| 位置 | §2.5, §3.2 | `api/location.py`, `views/album/location/*` |
| 搜索 | §2.6 | `api/search.py`, `views/search/*`, `crud/search_vector.py` |
| 回收站 | §2.7 | `RecycleBinPage.vue`, 任务调度清理 |
| 工具箱 | §2.8 | `api/toolbox.py`, `views/toolbox/*`, `tasks/{organize,rename,similar,duplicate,time_from_filename}.py` |
| 车票 | §2.9, §3.1 | `api/{train_ticket,flight_ticket}.py`, `views/ticket/*`, `tasks/tickets.py` |
| 设置 | §2.11 | `views/settings/*`, `api/settings.py` |
| AI 助手 | §2.12, §3.4 | `api/agent.py`, `views/agent/*`, `service/agent/*` |
| 年度报告 | §2.13 | `api/annual_report.py`, `views/annual-report/*` |
| 首页 | §2.14 | `HomePage.vue`, `components/home/*` |
| 媒体 | §2.16 | `api/media.py`, `service/storage.py` |
| CLI | §2.17, §5.4 | `package/trailsnap-cli/`, `skills/trailsnap-cli/` |
| Railway | §2.18 | `app/railway/*` |
| AI 能力 | §3.1, §3.3, §3.5 | `package/ai/app/*` |
| 安全 | §4.4 | `api/auth.py`, `api/agent_token.py` |
| 集成 | §5.1, §5.2 | `docker-compose.yml`, `.github/workflows/*` |
| 迁移 | §5.3 | `alembic/`, `db/models/*` |

---

## 十、与现有实现的对应

| 现有 E2E spec | 覆盖章节 |
|---------------|----------|
| `auth.spec.ts` | §1.1 登录/注册 |
| `home.spec.ts` | §1.3 首页渲染 |
| `album.spec.ts` | §2.2 / §2.3 / §2.4 / §2.5 路由可访问性 |

**未覆盖缺口**：toolbox / settings / agent / face 详情 / photo 详情 / annual-report / ticket / upload / search / theme / recycle-bin / task-mgmt 等所有 spec 均待编写。
