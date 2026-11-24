<template>
  <Transition name="bottom-nav-slide">
    <nav
      @focusin="revealDock"
      v-glass-refraction
      v-show="!uiStore.selectionActive"
      class="journal-dock ts-liquid-glass inset-x-[var(--ts-space-3)] bottom-[calc(var(--ts-tabbar-offset)_+_var(--ts-safe-area-bottom))] z-40 md:hidden"
      :class="{ 'is-receding': dockReceding }"
      aria-label="主导航"
    >
      <div class="relative z-10 grid h-14 grid-cols-5 px-1">
        <span
          class="journal-dock-indicator"
          :style="{ transform: `translate3d(${displayedTabIndex * 100}%, 0, 0)` }"
          aria-hidden="true"
        ></span>
        <span class="journal-dock-glow" :style="{ transform: `translate3d(${displayedTabIndex * 100}%, 0, 0)` }" aria-hidden="true"></span>

        <!-- 首页 -->
        <RouterLink
          to="/"
          :class="tabClass(displayedTabIndex === 0)"
          aria-label="首页"
          @pointerdown="previewTab(0)"
          @click="previewTab(0)"
        >
          <Home class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">首页</span>
        </RouterLink>

        <!-- 照片 -->
        <RouterLink
          to="/photos"
          :class="tabClass(displayedTabIndex === 1)"
          aria-label="照片"
          @pointerdown="previewTab(1)"
          @click="previewTab(1)"
        >
          <ImageIcon class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">照片</span>
        </RouterLink>

        <!-- 搜索（居中强调，跳全屏搜索页） -->
        <RouterLink
          to="/mobile-search"
          :class="tabClass(displayedTabIndex === 2)"
          aria-label="搜索"
          @pointerdown="previewTab(2)"
          @click="previewTab(2)"
        >
          <Search class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">搜索</span>
        </RouterLink>

        <!-- 相册 -->
        <RouterLink
          to="/album"
          :class="tabClass(displayedTabIndex === 3)"
          aria-label="相册"
          @pointerdown="previewTab(3)"
          @click="previewTab(3)"
        >
          <Images class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">相册</span>
        </RouterLink>

        <!-- 更多（打开底部 sheet） -->
        <button
          type="button"
          @click="openMoreSheet"
          :class="tabClass(displayedTabIndex === 4)"
          aria-label="更多"
          aria-haspopup="dialog"
          :aria-expanded="moreSheetVisible"
        >
          <Menu class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">更多</span>
        </button>
      </div>
    </nav>
  </Transition>

  <!-- 更多：底部 sheet（el-drawer btt，teleport 到 body，自带 overlay/ESC/滚动锁） -->
  <el-drawer
    v-model="moreSheetVisible"
    direction="btt"
    :with-header="false"
    size="auto"
    :close-on-click-modal="true"
    :close-on-press-escape="true"
    class="more-sheet"
  >
    <div class="px-4 pt-3 pb-[calc(var(--ts-safe-area-bottom)_+_12px)]">
      <div class="relative mb-4 flex items-center justify-between pt-3">
        <div class="absolute left-1/2 top-0 h-1 w-10 -translate-x-1/2 rounded-full bg-slate-300 dark:bg-slate-600" />
        <div>
          <h1 class="text-lg font-bold text-[var(--ts-color-text)]">更多</h1>
          <p class="ts-muted text-xs">探索、整理与应用设置</p>
        </div>
        <button
          type="button"
          class="ts-icon-button ts-button-ghost"
          aria-label="关闭更多导航"
          @click="closeMoreSheet"
        >
          <X class="h-5 w-5" />
        </button>
      </div>

      <!-- 通知（复用 NotificationBell 的 row 变体，自带未读徽标 + 开抽屉） -->
      <NotificationBell variant="row" />

      <!-- 账号快捷入口：移动端无需先进设置页再查找退出。 -->
      <div class="mt-3 flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-slate-800">
        <RouterLink
          to="/settings#profile"
          class="flex min-w-0 flex-1 items-center gap-3 rounded-lg focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click.prevent="navigateFromMore('/settings#profile')"
        >
          <img
            v-if="userStore.userInfo?.avatar"
            :src="toServerUrl(userStore.userInfo.avatar)"
            alt=""
            class="h-9 w-9 shrink-0 rounded-full object-cover"
          />
          <span v-else class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-100 text-sm font-semibold text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
            {{ accountInitial }}
          </span>
          <span class="min-w-0">
            <span class="block truncate text-sm font-medium text-slate-800 dark:text-slate-100">{{ accountName }}</span>
            <span class="ts-muted block truncate text-xs">{{ userStore.userInfo?.username || '个人资料' }}</span>
          </span>
        </RouterLink>
        <button
          v-if="!isTauriApp()"
          type="button"
          class="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-800 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100"
          aria-label="退出登录"
          @click="handleLogout"
        >
          <LogOut class="h-5 w-5" />
        </button>
      </div>

      <!-- 按使用场景分组，避免把所有二级功能铺成一张无层次的九宫格。 -->
      <div class="mt-3 space-y-4">
        <section v-for="section in mobileMoreSections" :key="section.label">
          <h2 class="ts-muted mb-1.5 px-1 text-xs font-semibold">{{ section.label }}</h2>
          <div class="grid grid-cols-3 gap-2">
            <RouterLink
              v-for="item in section.items"
              :key="item.href"
              :to="item.href"
              @click.prevent="navigateFromMore(item.href)"
              class="more-sheet-link flex min-h-16 flex-col items-center justify-center gap-1.5 rounded-xl font-medium transition-colors hover:bg-slate-100 hover:text-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:hover:bg-slate-700/60 dark:hover:text-primary-400"
              :class="isCurrentPath(item.href) ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400' : ''"
            >
              <component :is="item.icon" class="w-5 h-5 shrink-0" />
              <span class="text-xs whitespace-nowrap">{{ item.label }}</span>
            </RouterLink>
          </div>
        </section>
      </div>

      <!-- 快捷访问 -->
      <div v-if="navItemsList.length" class="mt-4 pt-3 border-t border-slate-200 dark:border-slate-700">
        <h2 class="ts-muted mb-2 px-1 text-xs font-semibold">快捷访问</h2>
        <div class="grid grid-cols-3 gap-2 max-h-[40vh] overflow-y-auto">
          <RouterLink
            v-for="item in navItemsList"
            :key="`${item.entity_type}-${item.entity_id}`"
            :to="item.route_path"
            @click.prevent="navigateFromMore(item.route_path)"
            class="flex min-w-0 min-h-16 flex-col items-center justify-center gap-1.5 rounded-xl px-1 py-2 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700/60 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            <div class="w-9 h-9 rounded overflow-hidden shrink-0 bg-slate-200 dark:bg-slate-700 flex items-center justify-center">
              <img v-if="item.cover_photo_id" :src="getThumbnailUrl(item)" alt="" class="w-full h-full object-cover" loading="lazy" />
              <component v-else :is="getNavIcon(item.entity_type)" class="w-4 h-4 text-slate-400" />
            </div>
            <span class="w-full truncate text-center text-xs" :title="item.name">{{ item.name }}</span>
          </RouterLink>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  Home,
  Image as ImageIcon,
  Search,
  Images,
  Menu,
  LogOut,
  X
} from 'lucide-vue-next'
import { injectNavItems, getNavIcon, getThumbnailUrl } from '@/composables/useNavItems'
import NotificationBell from '@/components/NotificationBell.vue'
import { useUiStore } from '@/stores/uiStore'
import { useUserStore } from '@/stores/user'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { mobileMoreSections, type NavGroup } from '@/config/navigation'
import { isTauriApp, toServerUrl } from '@/config/server'

const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()
const userStore = useUserStore()

const { items: navItemsList } = injectNavItems()

const moreSheetVisible = ref(false)
const MORE_HISTORY_KEY = '__trailsnapMoreSheet'
const moreHistoryId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
let historyEntryActive = false
let historyBackPending = false
let closeResolvers: Array<() => void> = []

const isCurrentMoreHistoryEntry = () =>
  window.history.state?.[MORE_HISTORY_KEY] === moreHistoryId

const resolvePendingClose = () => {
  closeResolvers.splice(0).forEach(resolve => resolve())
}

const openMoreSheet = () => {
  if (!historyEntryActive) {
    window.history.pushState(
      { ...(window.history.state ?? {}), [MORE_HISTORY_KEY]: moreHistoryId },
      '',
      window.location.href,
    )
    historyEntryActive = true
  }
  moreSheetVisible.value = true
}

const closeMoreSheet = (): Promise<void> => {
  if (!historyEntryActive) {
    moreSheetVisible.value = false
    return Promise.resolve()
  }

  const closed = new Promise<void>(resolve => closeResolvers.push(resolve))
  if (isCurrentMoreHistoryEntry() && !historyBackPending) {
    historyBackPending = true
    window.history.back()
  } else if (!isCurrentMoreHistoryEntry()) {
    historyEntryActive = false
    moreSheetVisible.value = false
    resolvePendingClose()
  }
  return closed
}

const handleMoreHistoryPopState = () => {
  if (!historyEntryActive) return
  historyEntryActive = false
  historyBackPending = false
  moreSheetVisible.value = false
  resolvePendingClose()
}

const navigateFromMore = async (target: RouteLocationRaw) => {
  await closeMoreSheet()
  await router.push(target)
}

useOverlayStack(moreSheetVisible, closeMoreSheet)

watch(moreSheetVisible, visible => {
  // Drawer modal-click and Escape closes arrive through v-model rather than
  // closeMoreSheet; consume their same-page history entry here as well.
  if (!visible && historyEntryActive && !historyBackPending) void closeMoreSheet()
}, { flush: 'sync' })

let preloadTimer: ReturnType<typeof setTimeout> | undefined

/*
 * 阅读时底栏给照片让位，但必须随时回得来：
 *   · 向上滑动立即回来；
 *   · **停止滑动约 0.4s 后自动回来**（和 Safari 一样，不需要点任何按钮）；
 *   · 滚到页面底部回来；
 *   · 换页时复位，否则新页面一进来就没有底栏。
 * 只响应主内容区向下滚动。
 */
const dockReceding = ref(false)
const scrollPositions = new WeakMap<EventTarget, number>()
let idleRevealTimer: ReturnType<typeof setTimeout> | undefined

const IDLE_REVEAL_DELAY = 420

function cancelIdleReveal() {
  if (idleRevealTimer) clearTimeout(idleRevealTimer)
  idleRevealTimer = undefined
}

function revealDock() {
  cancelIdleReveal()
  dockReceding.value = false
}

/** 停止滑动后把底栏放回来。 */
function scheduleIdleReveal() {
  cancelIdleReveal()
  idleRevealTimer = setTimeout(() => {
    idleRevealTimer = undefined
    dockReceding.value = false
  }, IDLE_REVEAL_DELAY)
}

function onScrollCapture(event: Event) {
  const target = event.target
  if (!(target instanceof HTMLElement) || !target.matches('.ts-main-scroll')) return
  if (target.scrollHeight - target.clientHeight < 64) return
  const top = target.scrollTop
  const previous = scrollPositions.get(target)
  scrollPositions.set(target, top)
  if (previous === undefined) {
    scheduleIdleReveal()
    return
  }
  const delta = top - previous
  if (Math.abs(delta) < 6) return
  const nearBottom = top + target.clientHeight >= target.scrollHeight - 32
  // 大幅跳转（时间轴定位、回到顶部）看不出方向，保持可见。
  if (Math.abs(delta) > 500 || delta < 0 || nearBottom) {
    revealDock()
    return
  }
  dockReceding.value = top > 120
  // 无论是否收起，停止滑动后都要回到可见状态。
  scheduleIdleReveal()
}

watch(dockReceding, hidden => {
  if (!hidden) cancelIdleReveal()
})

// 换页后底栏必须是可见的，否则用户在新页面找不到导航。
watch(() => route.path, () => {
  revealDock()
})

onMounted(() => {
  window.addEventListener('popstate', handleMoreHistoryPopState)
  document.addEventListener('scroll', onScrollCapture, { capture: true, passive: true })
  // Warm the four primary route chunks after the initial screen settles. This
  // removes the one-time parse delay on the first visit without competing with
  // initial rendering and API requests.
  preloadTimer = setTimeout(() => {
    void Promise.allSettled([0, 1, 2, 3].map(preloadTab))
  }, 500)
})
onBeforeUnmount(() => {
  window.removeEventListener('popstate', handleMoreHistoryPopState)
  document.removeEventListener('scroll', onScrollCapture, { capture: true })
  if (historyEntryActive && isCurrentMoreHistoryEntry()) window.history.back()
  if (pendingTabTimer) clearTimeout(pendingTabTimer)
  if (preloadTimer) clearTimeout(preloadTimer)
  cancelIdleReveal()
  resolvePendingClose()
})

const isGroup = (group: NavGroup) => route.meta.navGroup === group
const isCurrentPath = (href: string) => route.path === href || route.path.startsWith(`${href}/`)
const moreActive = computed(() =>
  mobileMoreSections.some(section => section.items.some(item => isCurrentPath(item.href)))
)
const routeTabIndex = computed(() => {
  if (moreActive.value) return 4
  if (isGroup('albums')) return 3
  if (isGroup('search') || route.path.startsWith('/search')) return 2
  if (isGroup('photos')) return 1
  return isGroup('home') ? 0 : 4
})
const activeTabIndex = computed(() => moreSheetVisible.value ? 4 : routeTabIndex.value)
const pendingTabIndex = ref<number | null>(null)
let pendingTabTimer: ReturnType<typeof setTimeout> | undefined

const preloadTab = (index: number) => {
  if (index === 0) return import('@/views/HomePage.vue')
  if (index === 1) return import('@/views/PhotosPage.vue')
  if (index === 2) return import('@/views/search/MobileSearch.vue')
  if (index === 3) return import('@/views/album/AlbumList.vue')
  return Promise.resolve()
}

const previewTab = (index: number) => {
  if (index === routeTabIndex.value) return
  pendingTabIndex.value = index
  void preloadTab(index)
  if (pendingTabTimer) clearTimeout(pendingTabTimer)
  // Clear an optimistic state if a navigation guard rejects the route.
  pendingTabTimer = setTimeout(() => {
    pendingTabIndex.value = null
  }, 2000)
}

const displayedTabIndex = computed(() => pendingTabIndex.value ?? activeTabIndex.value)

watch(routeTabIndex, () => {
  pendingTabIndex.value = null
  if (pendingTabTimer) clearTimeout(pendingTabTimer)
})

const accountName = computed(() => userStore.userInfo?.nickname || userStore.userInfo?.username || '我的账号')
const accountInitial = computed(() => accountName.value.trim().charAt(0).toUpperCase() || '我')

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确定要退出当前账号吗？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await closeMoreSheet()
    await userStore.logout()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') console.error('Logout failed', error)
  }
}

const tabClass = (active: boolean) =>
  [
    'journal-dock-tab relative my-0.5 flex flex-col items-center justify-center gap-1 rounded-full transition-colors duration-200',
    active ? 'is-active' : '',
  ].join(' ')

// 路由切换时复位选择模式标志，防止「选择中跳走 → Tab 栏卡在隐藏」残留
watch(() => route.path, () => uiStore.setSelectionActive(false))
</script>

<style>
/* el-drawer teleport 到 body，scoped 样式无法触达面板，用全局样式调整底部 sheet */
.more-sheet {
  border-top-left-radius: var(--ts-radius-dialog);
  border-top-right-radius: var(--ts-radius-dialog);
  overflow: hidden;
  max-height: min(85dvh, 720px);
}
.more-sheet .el-drawer__body {
  padding: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.more-sheet-link { color: var(--ts-color-text); }
.more-sheet-link.router-link-exact-active { color: var(--ts-journal-accent-text); }
/* Shortcuts cascade into the sheet instead of appearing all at once. */
.more-sheet .more-sheet-link {
  animation: ts-rise 420ms var(--ts-ease-enter) backwards;
}
.more-sheet .more-sheet-link:nth-child(1) { animation-delay: 40ms; }
.more-sheet .more-sheet-link:nth-child(2) { animation-delay: 80ms; }
.more-sheet .more-sheet-link:nth-child(3) { animation-delay: 120ms; }
.more-sheet .more-sheet-link:nth-child(4) { animation-delay: 160ms; }
.more-sheet .more-sheet-link:nth-child(5) { animation-delay: 200ms; }
.more-sheet .more-sheet-link:nth-child(6) { animation-delay: 240ms; }
</style>

<style scoped>
.journal-dock {
  --glass-tint: var(--ts-glass-control);
  position: fixed;
  border-radius: var(--ts-radius-pill);
  color: var(--ts-color-text);
  box-shadow: var(--ts-shadow-floating);
  /* `translate` composes with the enter/leave `transform`, so hiding the dock
     never fights the route transition. */
  transition: translate 460ms var(--ts-ease-paper), opacity 320ms ease;
}
.journal-dock.is-receding { translate: 0 calc(100% + 44px); opacity: 0; }

/* 选中项背后的胶囊：绝对定位，不参与 5 列网格的排布 */
.journal-dock-indicator {
  position: absolute;
  z-index: -1;
  inset: 5px auto 5px 4px;
  width: calc((100% - 8px) / 5);
  border-radius: var(--ts-radius-pill);
  background: var(--ts-journal-active);
  transition: transform 460ms var(--ts-ease-spring);
}

/* A soft halo under the active tab, as if the dock were lit from within. */
.journal-dock-glow {
  position: absolute;
  z-index: -2;
  inset: 0 auto 0 4px;
  width: calc((100% - 8px) / 5);
  border-radius: 9999px;
  background: radial-gradient(circle at 50% 70%, rgba(var(--theme-rgb), .3), transparent 66%);
  filter: blur(7px);
  transition: transform 620ms var(--ts-ease-spring), opacity 240ms ease;
  pointer-events: none;
}
.journal-dock-tab {
  font-weight: 600;
  text-shadow: var(--ts-glass-label-shadow);
}
.journal-dock-tab > svg { filter: drop-shadow(var(--ts-glass-label-shadow)); }
.journal-dock-tab.is-active { color: var(--ts-journal-accent-text); font-weight: 700; }
.journal-dock-tab.is-active > svg { animation: ts-tab-bloom 560ms var(--ts-ease-spring) both; }
.journal-dock-tab.is-active > span { animation: ts-fade-in 320ms ease both; }
.journal-dock-tab:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: -2px; }
.journal-dock-tab svg { transition: transform 240ms var(--ts-ease-spring); }
.journal-dock-tab:active svg { transform: scale(.88); }
.bottom-nav-slide-enter-active, .bottom-nav-slide-leave-active {
  transition: transform var(--ts-motion-page) var(--ts-ease), opacity var(--ts-motion-normal) ease;
}
.bottom-nav-slide-enter-from, .bottom-nav-slide-leave-to {
  transform: translateY(calc(100% + 24px));
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .journal-dock, .journal-dock-indicator, .journal-dock-tab, .journal-dock-tab svg { transition-duration: 0s !important; }
}
</style>
