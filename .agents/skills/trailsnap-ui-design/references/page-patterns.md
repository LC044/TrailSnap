# 页面模式与验收

路径相对于 TrailSnap 根目录；下文 `src/*` 均以 `package/website/` 为前缀。选择最接近的模式和源码，不把所有页面套成同一种卡片网格。

## 布局、滚动和安全区

参考 `src/layouts/MainLayout.vue`、`BlankLayout.vue`、`Sidebar.vue`、`BottomNav.vue`。

- 桌面 ≥768px 展示可折叠侧栏，移动端展示底部五项悬浮玻璃导航。新增业务页通常由路由进入现有布局，不重复创建全局导航。
- html/body/#app 禁止页面级滚动，主滚动区是 `.ts-main-scroll`。粘性标题、弹层和虚拟画廊先确认实际滚动祖先；flex 滚动区域保留 min-h-0，长文本容器保留 min-w-0。
- MainLayout 默认为移动底栏预留 `--ts-tabbar-h + --ts-safe-area-bottom`。需要页内拥有底部留白时用 `AppPage bottom-safe` / `.ts-bottom-safe`；ui.css 的 `:has(.ts-bottom-safe)` 会取消外层留白，不再补第二份 tabbar padding。
- Android 由布局处理顶部安全区，相册 hero 可延伸至状态栏后，其工具栏自行避让一次。遵循 `--ts-safe-area-*` 与 `--ts-content-safe-area-top`，不复制未经验证的平台常数。
- 日记本模式已有专用 flex 布局与滚动覆盖，不随意加 h-screen 或嵌套全高滚动容器。

## 首页与内容发现

参考 `src/views/HomePage.vue`、`src/components/home/MemoryDiscovery.vue`。

- 首页用 wide 内容宽度、大标题与右侧胶囊工具栏，下面按回忆、今日瞬间、统计等业务内容组织。
- 回忆卡片用封面、标题、照片数和地点；横向发现条露出下一项并自然滑动。新增区保持相近信息密度。
- 手机优先照片和回忆，桌面可增加统计与管理模块，沿用当前响应式层级。
- 可选增强模块可参考当前模块的失败降级；核心页面请求失败需明确错误态，不统一静默隐藏所有失败。

## 照片浏览与相册

参考 `src/components/UnifiedPhotoPage.vue`、`PhotoGallery.vue`、`FlatPhotoGallery.vue`、`GalleryChrome.vue`、`SmartAlbumCover.vue`，以及 `src/views/PhotosPage.vue`、`src/views/album/AlbumDetail.vue`、`AlbumList.vue`。

- 网格、瀑布流、朋友圈、日记本、文件夹视图已有统一控制入口；复用其实际属性/插槽及画廊模型，不重写筛选、排序、选择和加载逻辑。
- 使用已有缩略图工具；封面常用 object-cover，原图查看尊重原始比例。保留懒加载、稳定布局、alt 与加载占位。
- 相册库主要为分组横向封面条，不默认改成管理表格。封面主要为正方形，条卡片宽度为 `clamp(140px, 18vw, 220px)`，<640px 为 38%；这是局部模式，不是全局卡片宽度。
- 标题、数量、类型徽标和地点按层级展示。照片上文字配渐变或玻璃背景，按实际照片检查可读性。
- 桌面 hover 操作保留 focus-within 或常驻入口；移动已有长按时沿用，新增操作仍需可发现入口，不能仅依赖 hover。
- 批量选择由 uiStore.selectionActive 隐藏移动主底栏，保留批量工具条与导航切换关系。
- GalleryChrome 提供初始骨架和错误重试；空照片与加载失败分别展示。不把局部动画或任意色值升级为全局规范。

## 设置、表单与工具

参考 `src/views/settings/BasicSettings.vue`、`src/views/settings/sections/AppearanceSettingsSection.vue`、`src/views/toolbox/ToolboxPage.vue`。

- 设置按业务拆分 SettingsSection；保持标题、说明、字段、操作的稳定顺序。普通表单采用 form/content 宽度，工具集合可用 wide。
- 标签对应输入元素，说明放在字段附近；错误与提交状态明确。操作组用 `.ts-form-actions` 或共享按钮，窄屏可换行。
- 工具页可沿用桌面卡片、移动紧凑列表的适配方式，主题色图标与实体表面保持一致。
- Element Plus 控件沿用全局 token，不通过实例 :deep() 覆盖内部底色或建立另一套暗色 palette。
- 主题选择直接使用主题 API，不添加另一份 localStorage 状态。

## 菜单、筛选与弹层

- 简短动作用 AdaptiveMenu，复杂筛选用 FilterSheet，编辑/创建用 ResponsiveDialog。简单菜单默认移动 sheet；当前首页/相册工具栏的 popover 可作为相关场景参考。
- AdaptiveMenu 紧邻触发按钮，保留 aria-expanded/aria-haspopup；沿用定位与路由关闭机制，不写死坐标。
- ResponsiveDialog 已统一 Teleport、动态层级、焦点陷阱和恢复、ESC/返回关闭、滚动锁、手势、visualViewport；通过 props/slots 接入，不平行实现遮罩系统。
- sheet 用于短操作；长编辑场景可用 mobile-mode="fullscreen" 和 mobile-back。有 footer 时内容独立滚动，主要操作留在 footer，保留安全区和软键盘处理。
- 未保存内容可通过 beforeClose 接入业务策略；异步提交期间禁用重复操作。删除等动作沿用业务确认/恢复方式，不仅用颜色表示危险。

## 按改动选择验收

以下为推荐检查点，不要求每个小改动启动所有平台。

| 维度 | 观察点 |
| --- | --- |
| 窄屏 | 320px、390/440px：长标题、工具栏、表单按钮不溢出，输入可读 |
| 断点 | 767/768px：侧栏/底栏、sheet/dialog 切换和留白；涉及 sm 时增加 639/640px |
| 桌面 | 1280px 及宽屏：内容宽度、侧栏折叠、表单行长、菜单锚点 |
| 明暗与主色 | light/dark，至少默认蓝与一种差异较大主题；全局 palette 变更覆盖五色；弹层同样继承 |
| 数据状态 | 加载、空数据、重试、大量数据、长文字、缺少封面 |
| 交互 | 键盘焦点、Enter/Space、禁用/提交中、外部点击、ESC、返回关闭、焦点恢复 |
| 移动弹层 | 长内容滚动、底部操作、软键盘、安全区，触控不依赖 hover |
| 媒体 | 明亮/暗色照片上的文字、裁切、懒加载、布局稳定 |
| 动效 | reduced-motion 下功能可用，不支持玻璃滤镜时实体背景仍可读 |

浏览器检查记录实际视口与结果；仅源码审查时说明未截图验收。构建按 `package/website/README.md`，测试按 `tests/README.md` 使用根目录统一入口，例如前端单元：

```powershell
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component website -Level smoke
```

E2E 先确认套件标签与相关 spec，再通过统一脚本选择范围；环境变量来自 `tests/.env.test`。截图不能替代行为测试，纯 Skill 文档无需运行应用测试。
