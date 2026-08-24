import type { Page } from '@playwright/test'

/**
 * 位置相册列表页（LocationList.vue）桌面端控件定位辅助。
 *
 * 背景：LocationList.vue 对 level 切换（区县/城市/省份/景区）和景区过滤
 * （全部/已打卡/未打卡）各渲染了两套按钮——
 *   - 桌面组：带稳定 `data-testid` 的按钮组，桌面视口可见；
 *   - 移动端 dropdown：独立的响应式按钮组（包在 `<div class="py-1">`
 *     里）的同名按钮，桌面视口下 `display:none`。
 * 移动端的按钮在 DOM 中更靠前，因此 `.location-list button:has-text("区县").first()`
 * 会命中隐藏的移动端按钮，导致 toBeVisible 失败 / click 超时。
 *
 * 使用语义化的 `data-testid` 定位桌面组，避免响应式断点从 md 调整为 lg 时
 * E2E 因依赖 Tailwind 实现类而失效。
 */

type LevelLabel = '区县' | '城市' | '省份' | '景区'
type FilterLabel = '全部' | '已打卡' | '未打卡'

/**
 * 网格视图里的位置/景区卡片（LocationListView 内容网格的直接子项）。
 *
 * `.location-list .grid > div` 太宽：LocationMapView 是 v-show 常驻 DOM（网格视图下
 * 隐藏），里面的 GlobalOverviewPanel 也有 `.grid`（子项是 `bg-primary-50` 统计卡），
 * 且它在 DOM 中排在 LocationListView 之前，`.first()` 会命中这些隐藏的统计卡。
 *
 * LocationListView 的内容卡 class 含 `group`（用于 group-hover），用
 * `.grid:has(> div.group)` 锁定「直接子项是 group 卡片」的那个网格——隐藏的统计网格
 * 子项是 `bg-primary-50`，被排除。返回所有卡片，调用方按需 .first()/.count()。
 */
export function locationGridCard(page: Page) {
  return page.locator('.location-list .grid:has(> div.group) > div.group')
}

/** 桌面端 level 切换按钮（区县/城市/省份/景区）。 */
export function desktopLevelButton(page: Page, label: LevelLabel) {
  return page.getByTestId('location-level-desktop').getByRole('button', { name: label, exact: true })
}

/**
 * 桌面端景区过滤按钮（全部/已打卡/未打卡）。仅在 level=scene 时渲染。
 * 用「已打卡」锁定桌面 filter 组，再按 label 取目标按钮，避免「全部」与
 * 年份菜单的「全部时间」撞文本。
 */
export function desktopFilterButton(page: Page, label: FilterLabel) {
  return page.getByTestId('location-filter-desktop').getByRole('button', { name: label, exact: true })
}
