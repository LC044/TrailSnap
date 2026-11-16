# 设计基础与组件

基于 2026-10-09 的源码扫描，不代表已完成浏览器视觉验收。路径均相对于 TrailSnap 仓库根目录；后续实现重新读取相关源码，避免把快照当成永久常量。

## 设计来源与优先级

| 来源 | 用途 |
| --- | --- |
| `package/website/src/style.css` | 明暗语义 token、字体、主题工具类、玻璃、标题、原生安全区 |
| `package/website/src/styles/ui.css` | 共享 surface、按钮、输入、表单、Element Plus 全局适配 |
| `package/website/tailwind.config.js` | 动态 primary 色阶、中性色合并、移动间距缩放 |
| `package/website/src/composables/useTheme.ts` | 五色主题、light/auto/dark、全局 CSS 变量同步 |
| `package/website/src/main.ts`、`package/website/src/App.vue` | 样式加载顺序、Element Plus 暗色变量、根主题 provider |

`main.ts` 先加载 `style.css`，再加载 `styles/ui.css`；判断颜色和控件效果时查看最终级联。`src/main.css` 只有 Tailwind 指令，不是当前设计 token 的入口。旧页中局部硬编码、旧字体或特殊配色不能直接升级为通用规范。

## 视觉语言

- 照片、相册封面和回忆是视觉中心。普通页面以低饱和中性背景衬托，主色突出选择、链接和主要操作。
- 内容表面用细边框、柔和阴影和圆角组织；玻璃作为悬浮控制层，避免把媒体放在模糊滤镜中。
- 主色与危险色分开：删除等操作使用 `--ts-color-danger`、danger 按钮或动作行，不因主题变色失去语义。
- 系统字体栈包含 Inter、Segoe UI、苹方和微软雅黑；默认继承 `--ts-font-sans`，不为普通页面引入装饰字体。年度报告、日记本等已有专用视觉场景可沿用自身样式。

## 样式入口

使用变量与共享类，不复制扫描时的色值和尺寸。按用途查阅当前 CSS：

| 用途 | 入口 |
| --- | --- |
| 背景、正文、边框与分隔线 | `--ts-color-*` |
| 间距、圆角与控件高度 | `--ts-space-*`、`--ts-radius-*`、`--ts-control-*` |
| 页面边距与区块间距 | `--ts-page-gutter`、`--ts-section-gap` |
| 标题层级 | `.ts-page-title`、`.ts-section-title`、`.ts-card-title` |
| 动效 | `--ts-motion-*`、`--ts-ease` |
| 玻璃控制层 | `.ts-liquid-glass`、`.ts-glass-toolbar`、`.ts-glass-button` |

移动间距已由共享样式适配，不缩放根字号或整页 transform。控件沿用共享命中尺寸，不为压缩界面缩小触控区域。

## 主题接入

天空蓝、森系绿、梦幻紫、落日红、复古橘由 `useTheme.ts` 定义。默认蓝色值与 `style.css` 的 fallback 不完全相同，因此不要复制 fallback 来代表实际主题。

```ts
import { watch } from 'vue'
import { injectTheme } from '@/composables/useTheme'

const { currentTheme, isDarkMode } = injectTheme()
// updateChart 为当前组件自己的更新函数，需在图表初始化后执行。
watch([currentTheme, isDarkMode], () => {
  updateChart(currentTheme.value.primary, currentTheme.value.rgb, isDarkMode.value)
})
```

CSS 使用 `text-primary-500`、`bg-primary-50`、`border-primary-500` 等。低档 primary 常表示透明底色，不当作正文色阶；深色主色文字已由 `ui.css` 调亮。RGBA 写作 `rgba(var(--theme-rgb), .1)`。动态 Tailwind 类必须能被扫描发现，优先静态映射或 CSS 变量。

主题变量写到 `document.documentElement`，Teleport 到 body 的菜单/弹层也应继承；不要给弹层另建主题 provider。照片遮罩的固定黑白色可以表达媒体对比度；普通面板使用明暗 token。

## 组件选择

目录为 `package/website/src/components/ui/`。以下为接口摘要，使用前读当前组件。

| 组件/类 | 适用方式 |
| --- | --- |
| `AppPage` | `size=full/wide/content/form` 对应无上限/1536/1280/896px；padded 默认 true；bottomSafe 默认 false |
| `PageHeader` | title、subtitle、leading/actions/title-extra；默认 compact、sticky、glass、bordered；large 展示大标题；size 与页面保持一致 |
| `MobilePageHeader` | 仅移动显示；通过 useAppBack 返回，默认 showBack |
| `SectionHeader` | 区块标题与描述，icon/actions 插槽 |
| `SurfaceCard` | padding=none/sm/md/lg、radius=control/card/dialog、as、elevated、interactive；interactive 是视觉行为，不自动提供键盘语义 |
| `PrimaryButton` | variant=primary/secondary/ghost/danger、size、block、loading、disabled；leading/trailing 插槽 |
| `IconButton` | 必填 label，title 默认等于 label；ghost/primary/danger；共享命中尺寸 |
| `EmptyState` | title、description、icon/actions 插槽；与失败态区分 |
| `SettingsSection` | name、title；v-model 为展开项名称数组；折叠分组 |
| `ResponsiveDialog` | v-model、title、description、maxWidth；mobileMode=sheet/fullscreen、mobileBack、footer、beforeClose、placement；默认 glass=true |
| `AdaptiveMenu` | 默认桌面 popover、移动 sheet；mobilePresentation=popover 可保留移动悬浮菜单；closeOnAction 默认 false；相邻触发按钮供定位和动画使用 |
| `FilterSheet` | reset/apply 事件，loading、resultCount；默认 42rem 宽 |
| `UnifiedDatePicker` | 统一日期交互；修改前读其与 DateWheelColumn 的接口 |
| `.ts-input` | 原生 input/textarea 的主题和尺寸基础 |
| `.ts-section-stack` / `.ts-form-actions` | 区块纵向间距 / 可换行操作组 |
| `.ts-liquid-glass` + `.ts-glass-toolbar` | 胶囊玻璃工具栏；按钮用 `.ts-glass-button` |
| `.ts-action-row` | 图标与文字菜单行动作；危险项加 `.danger` |

AdaptiveMenu、SettingsSection、MobilePageHeader 等未在 `ui/index.ts` 导出；使用具体路径，不假设 barrel 已导出所有组件。

## 下拉选择

- 普通业务选择框默认使用 `el-select` / `el-option`，继承 `src/styles/ui.css`，不另用原生 `<select>` 搭配 `.ts-input` 建立一套样式。动作菜单接入见页面模式文档。
- 选项多时限高滚动，长文本不撑破窄屏布局。沿用组件的 Teleport 配置，检查祖先裁切与弹层层级；不要不分场景强制修改挂载目标。
- 替换选择器时保留值类型、选中态与联动行为，并检查展开后的明暗及窄屏效果。参考 `src/views/settings/sections/MapSettingsSection.vue`、`src/views/album/location/stats/StatsAnnualTrendCard.vue`（均相对于 `package/website/`）。
