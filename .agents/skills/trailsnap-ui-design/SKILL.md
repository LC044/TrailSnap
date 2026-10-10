---
name: trailsnap-ui-design
description: 基于 TrailSnap（行影集）现有设计系统设计、实现和审查前端 UI。适用于 package/website 的新页面、组件、布局、主题、移动端适配与界面改版；纯后端任务和其他项目不适用。
---

# TrailSnap UI 设计

让新增界面自然融入行影集：以照片与回忆为内容中心，中性底色、清晰标题层级、圆角实体内容面板，配合克制的玻璃导航和工具栏。用户明确指定新的视觉方向时按其要求设计，同时保留主题、交互和平台约束。

## 先确认现有实现

- 在当前工作区定位 TrailSnap 根目录，读取适用的 `AGENTS.md`。以下源码路径均相对于根目录，不依赖固定盘符。
- 修改前阅读 `package/website/src/style.css`、`package/website/src/styles/ui.css` 与最接近目标页面的现有组件。以当前源码为准；参考文档中的数值是扫描快照。
- 设计主题或通用控件时读 [设计基础与组件](references/design-system.md)；设计具体页面、媒体浏览或跨端交互时读 [页面模式与验收](references/page-patterns.md)。按任务读取，不全量加载所有页面。
- 先确定用户主要操作、信息层级、布局归属和内容宽度，再实现界面。只改善当前需求相关范围；扫描到旧样式不等于需要顺带改版。

## 核心约束

- Vue 使用 `<script setup lang="ts">`；状态管理使用 Pinia，HTTP 通过 `package/website/src/api/*`。沿用 Vue Router、Tailwind CSS 3、Element Plus 与现有组件。
- 优先复用 `package/website/src/components/ui/` 的页面、卡片、按钮和弹层组件。照片浏览优先接入 `UnifiedPhotoPage` 与现有画廊，避免重复实现虚拟布局、筛选和批量选择。
- 中性色使用 `--ts-color-*` 或共享语义类；主题强调色使用 `primary-*`、`--theme-primary` 和 `--theme-rgb`。不要把默认天空蓝写死为品牌色。
- 每个 `text-gray-*`、`bg-white` 及其变体配套相应的 `dark:` 样式；优先用自动适配明暗的语义 token。Element Plus 继承全局明暗配置，不在实例内覆盖内部颜色。
- 子组件通过 `injectTheme()` 使用根组件提供的主题；不要重复 `provideTheme()` 或创建独立主题状态。图表、Canvas 和动态颜色读取 `currentTheme.value.primary` / `.rgb`，随主题变化更新；明暗相关图表也响应 `isDarkMode`。
- 玻璃材质用于导航、浮动工具栏、菜单、弹层和照片日期标签；照片本体、普通内容卡片、表单阅读区域保持清晰实体表面。直接复用玻璃类，不叠加多道高光边框或大片模糊装饰。
- 桌面侧栏与移动底栏由布局负责。遵守已有滚动容器和安全区归属，避免新增页面再次补齐同一段顶部或底部空间。
- 图标优先使用所在模块已有的 `lucide-vue-next`，保持同组尺寸一致。图标按钮有可理解的 `aria-label`；展开和选择状态提供相应 ARIA 属性。交互卡片支持键盘，触屏操作不只依赖 hover。

## 实施与验收

1. 选取一个相近页面作为布局参考，确认共享组件的实际 props、slots 和 exports 后再使用；不存在的组件或属性不能靠名称猜测。
2. 用 token 与共享组件搭建布局，补齐加载、空数据、错误重试、提交中和禁用等与该功能相关的状态。照片标题、数量和地点服从内容层级，长文本不挤走操作按钮。
3. 检查明暗两种模式和不同主题色；按改动覆盖窄屏、桌面、弹层滚动与必要的软键盘/安全区行为。具体检查见页面模式参考。
4. 涉及行为改动时，按 `tests/README.md` 选择相关现有测试，通过 `tests/scripts/run-tests.ps1` 执行；配置来自 `tests/.env.test`。只有 Skill 文档变更时验证 Skill 与引用，不启动应用测试。
5. 有可用本地环境与浏览器工具时，进行截图或交互检查；需要 Playwright CLI 时遵循可用的 playwright 技能。开发环境账号为 `trailsnap` / `trailsnap`，登录失败向用户询问，不创建账号。未实际运行或截图验收时如实说明。

交付说明修改结果、复用的设计基础、实际检查及剩余限制。用户只要设计方案时提供可落地的页面/组件方案；用户要求实现时完成代码和适当验证。
