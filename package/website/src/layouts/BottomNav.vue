<template>
  <!-- 移动端液体玻璃底栏，仅 <768px 显示。 -->
  <Transition name="bottom-nav-slide">
    <nav
      v-show="!uiStore.selectionActive"
      class="liquid-glass-nav fixed inset-x-3 bottom-[calc(26px_+_env(safe-area-inset-bottom))] z-40 md:hidden"
      :class="{ 'is-flowing': bubbleMoving, 'is-dark': isDarkMode }"
      aria-label="主导航"
    >
      <div class="relative z-10 grid h-14 grid-cols-5 px-1">
        <span
          class="liquid-bubble-track"
          :style="{ transform: `translate3d(${displayedTabIndex * 100}%, 0, 0)` }"
          aria-hidden="true"
        >
          <span
            class="liquid-bubble"
            :class="[
              bubbleMoving ? 'is-moving' : '',
              bubbleDirection === 'right' ? 'moves-right' : 'moves-left',
              displayedTabIndex === 2 ? 'is-search' : '',
            ]"
          />
        </span>

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
    <div class="px-4 pt-3 pb-[calc(env(safe-area-inset-bottom)_+_12px)]">
      <div class="relative mb-4 flex items-center justify-between pt-3">
        <div class="absolute left-1/2 top-0 h-1 w-10 -translate-x-1/2 rounded-full bg-slate-300 dark:bg-slate-600" />
        <div>
          <h1 class="text-lg font-bold text-slate-900 dark:text-slate-100">更多</h1>
          <p class="text-xs text-slate-500 dark:text-slate-400">探索、整理与应用设置</p>
        </div>
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:text-slate-400 dark:hover:bg-slate-700"
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
            <span class="block truncate text-xs text-slate-500 dark:text-slate-400">{{ userStore.userInfo?.username || '个人资料' }}</span>
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
          <h2 class="mb-1.5 px-1 text-xs font-semibold tracking-wide text-slate-400 dark:text-slate-500">{{ section.label }}</h2>
          <div class="grid grid-cols-3 gap-2">
            <RouterLink
              v-for="item in section.items"
              :key="item.href"
              :to="item.href"
              @click.prevent="navigateFromMore(item.href)"
              class="flex min-h-16 flex-col items-center justify-center gap-1.5 rounded-xl text-slate-600 transition-colors hover:bg-slate-100 hover:text-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:text-slate-300 dark:hover:bg-slate-700/60 dark:hover:text-primary-400"
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
        <div class="px-1 mb-2 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">快捷访问</div>
        <div class="space-y-1 max-h-[40vh] overflow-y-auto">
          <RouterLink
            v-for="item in navItemsList"
            :key="`${item.entity_type}-${item.entity_id}`"
            :to="item.route_path"
            @click.prevent="navigateFromMore(item.route_path)"
            class="flex items-center gap-2 px-2 py-2 rounded-lg text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700/60 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            <div class="w-7 h-7 rounded overflow-hidden shrink-0 bg-slate-200 dark:bg-slate-700 flex items-center justify-center">
              <img v-if="item.cover_photo_id" :src="getThumbnailUrl(item)" class="w-full h-full object-cover" loading="lazy" />
              <component v-else :is="getNavIcon(item.entity_type)" class="w-4 h-4 text-slate-400" />
            </div>
            <span class="truncate text-sm">{{ item.name }}</span>
          </RouterLink>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
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
import { injectTheme } from '@/composables/useTheme'

const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()
const userStore = useUserStore()
const { isDarkMode } = injectTheme()

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

onMounted(() => {
  window.addEventListener('popstate', handleMoreHistoryPopState)
  // Warm the four primary route chunks after the initial screen settles. This
  // removes the one-time parse delay on the first visit without competing with
  // initial rendering and API requests.
  preloadTimer = setTimeout(() => {
    void Promise.allSettled([0, 1, 2, 3].map(preloadTab))
  }, 500)
})
onBeforeUnmount(() => {
  window.removeEventListener('popstate', handleMoreHistoryPopState)
  if (historyEntryActive && isCurrentMoreHistoryEntry()) window.history.back()
  if (bubbleTimer) clearTimeout(bubbleTimer)
  if (pendingTabTimer) clearTimeout(pendingTabTimer)
  if (preloadTimer) clearTimeout(preloadTimer)
  resolvePendingClose()
})

const isGroup = (group: NavGroup) => route.meta.navGroup === group
const isCurrentPath = (href: string) => route.path === href || route.path.startsWith(`${href}/`)
const moreActive = computed(() =>
  mobileMoreSections.some(section => section.items.some(item => isCurrentPath(item.href)))
)
const albumsTabActive = computed(() => isGroup('albums') && !moreActive.value)
const routeTabIndex = computed(() => {
  if (moreActive.value) return 4
  if (isGroup('albums')) return 3
  if (isGroup('search')) return 2
  if (isGroup('photos')) return 1
  return 0
})
const activeTabIndex = computed(() => moreSheetVisible.value ? 4 : routeTabIndex.value)
const pendingTabIndex = ref<number | null>(null)
const bubbleMoving = ref(false)
const bubbleDirection = ref<'left' | 'right'>('right')
let bubbleTimer: ReturnType<typeof setTimeout> | undefined
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

watch(displayedTabIndex, async (nextIndex, previousIndex) => {
  bubbleDirection.value = nextIndex >= previousIndex ? 'right' : 'left'
  bubbleMoving.value = false
  await nextTick()
  bubbleMoving.value = true
  if (bubbleTimer) clearTimeout(bubbleTimer)
  bubbleTimer = setTimeout(() => {
    bubbleMoving.value = false
  }, 340)
})

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
    'liquid-tab-item relative isolate my-0.5 flex flex-col items-center justify-center gap-0.5 rounded-full transition-colors duration-200 focus-visible:outline-none',
    active
      ? 'is-active'
      : 'text-slate-600 dark:text-slate-300'
  ].join(' ')

// 路由切换时复位选择模式标志，防止「选择中跳走 → Tab 栏卡在隐藏」残留
watch(() => route.path, () => uiStore.setSelectionActive(false))
</script>

<style>
/* el-drawer teleport 到 body，scoped 样式无法触达面板，用全局样式调整底部 sheet */
.more-sheet {
  border-top-left-radius: 16px;
  border-top-right-radius: 16px;
  overflow: hidden;
  max-height: min(85dvh, 720px);
}
.more-sheet .el-drawer__body {
  padding: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
</style>

<style scoped>
.liquid-glass-nav {
  isolation: isolate;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.68);
  border-radius: 9999px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.58), rgba(248, 250, 252, 0.28));
  box-shadow:
    0 18px 42px rgba(15, 23, 42, 0.16),
    0 3px 10px rgba(15, 23, 42, 0.08),
    inset 0 1.5px 1px rgba(255, 255, 255, 0.92),
    inset 0 -1px 1px rgba(100, 116, 139, 0.16);
  -webkit-backdrop-filter: blur(16px) saturate(175%) contrast(108%);
  backdrop-filter: blur(16px) saturate(175%) contrast(108%);
  transition:
    transform 220ms cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 220ms ease;
}

.liquid-glass-nav.is-flowing {
  transform: scale(1.006);
  box-shadow:
    0 21px 46px rgba(15, 23, 42, 0.19),
    0 4px 12px rgba(15, 23, 42, 0.1),
    inset 0 1.5px 1px rgba(255, 255, 255, 0.96),
    inset 0 -1px 1px rgba(100, 116, 139, 0.18);
}

.liquid-glass-nav::before {
  position: absolute;
  z-index: 0;
  inset: 1px;
  border-radius: inherit;
  background:
    radial-gradient(circle at 12% 0%, rgba(255, 255, 255, 0.72), transparent 24%),
    radial-gradient(circle at 82% 115%, rgba(var(--theme-rgb), 0.1), transparent 34%);
  content: '';
  pointer-events: none;
}

.liquid-glass-nav::after {
  position: absolute;
  z-index: 0;
  inset: 0;
  border-radius: inherit;
  background:
    linear-gradient(105deg, transparent 8%, rgba(255, 255, 255, 0.3) 22%, transparent 38%),
    linear-gradient(to bottom, rgba(255, 255, 255, 0.18), transparent 42%, rgba(15, 23, 42, 0.04));
  content: '';
  pointer-events: none;
}

.liquid-bubble-track {
  position: absolute;
  top: 3px;
  bottom: 3px;
  left: 4px;
  z-index: -1;
  width: calc((100% - 8px) / 5);
  padding: 4px;
  transition: transform 320ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;
}

.liquid-bubble {
  display: block;
  width: 100%;
  height: 100%;
  border: 1px solid rgba(255, 255, 255, 0.64);
  border-radius: 9999px;
  background:
    radial-gradient(circle at 28% 18%, rgba(255, 255, 255, 0.74), transparent 38%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.4), rgba(var(--theme-rgb), 0.13));
  box-shadow:
    0 7px 18px rgba(var(--theme-rgb), 0.16),
    inset 0 1.5px 1px rgba(255, 255, 255, 0.88),
    inset 0 -1px 1px rgba(var(--theme-rgb), 0.1);
  -webkit-backdrop-filter: blur(7px) saturate(190%);
  backdrop-filter: blur(7px) saturate(190%);
  transition: transform 180ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;
}

.liquid-bubble.is-search:not(.is-moving) {
  transform: scaleX(1.12);
}

.liquid-bubble.is-moving.moves-right {
  transform-origin: right center;
  animation: liquid-stretch-right 320ms cubic-bezier(0.22, 1, 0.36, 1);
}

.liquid-bubble.is-moving.moves-left {
  transform-origin: left center;
  animation: liquid-stretch-left 320ms cubic-bezier(0.22, 1, 0.36, 1);
}

.liquid-tab-item :deep(svg) {
  transition: transform 100ms ease, filter 200ms ease;
}

.liquid-tab-item:hover,
.liquid-tab-item.is-active {
  color: var(--theme-primary);
}

.liquid-tab-item:focus-visible {
  box-shadow:
    0 0 0 2px rgba(var(--theme-rgb), 0.7),
    0 0 0 4px rgba(255, 255, 255, 0.7);
}

.liquid-tab-item:active :deep(svg) {
  transform: scale(0.9);
}

.liquid-tab-item.is-active :deep(svg) {
  animation: liquid-icon-pop 260ms cubic-bezier(0.22, 1, 0.36, 1);
  filter: drop-shadow(0 2px 4px rgba(var(--theme-rgb), 0.24));
}

.liquid-glass-nav.is-dark {
  border-color: rgba(255, 255, 255, 0.2);
  background: linear-gradient(145deg, rgba(30, 41, 59, 0.62), rgba(15, 23, 42, 0.38));
  box-shadow:
    0 16px 38px rgba(0, 0, 0, 0.42),
    inset 0 1.5px 1px rgba(255, 255, 255, 0.2),
    inset 0 -1px 1px rgba(0, 0, 0, 0.3);
}

.liquid-glass-nav.is-dark::before {
  background:
    radial-gradient(circle at 12% 0%, rgba(255, 255, 255, 0.2), transparent 25%),
    radial-gradient(circle at 82% 115%, rgba(var(--theme-rgb), 0.16), transparent 36%);
}

.liquid-glass-nav.is-dark::after {
  background:
    linear-gradient(105deg, transparent 8%, rgba(255, 255, 255, 0.11) 22%, transparent 38%),
    linear-gradient(to bottom, rgba(255, 255, 255, 0.06), transparent 45%, rgba(0, 0, 0, 0.1));
}

.liquid-glass-nav.is-dark .liquid-bubble {
  border-color: rgba(255, 255, 255, 0.22);
  background:
    radial-gradient(circle at 28% 18%, rgba(255, 255, 255, 0.18), transparent 40%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.08), rgba(var(--theme-rgb), 0.2));
  box-shadow:
    0 5px 16px rgba(var(--theme-rgb), 0.18),
    inset 0 1.5px 1px rgba(255, 255, 255, 0.2),
    inset 0 -1px 1px rgba(0, 0, 0, 0.12);
}

@keyframes liquid-stretch-right {
  0% { transform: scaleX(1); }
  34% { transform: scaleX(1.34) scaleY(0.96); }
  72% { transform: scaleX(0.96) scaleY(1.03); }
  100% { transform: scaleX(1); }
}

@keyframes liquid-stretch-left {
  0% { transform: scaleX(1); }
  34% { transform: scaleX(1.34) scaleY(0.96); }
  72% { transform: scaleX(0.96) scaleY(1.03); }
  100% { transform: scaleX(1); }
}

@keyframes liquid-icon-pop {
  0% { transform: scale(0.9) translateY(1px); }
  58% { transform: scale(1.08) translateY(-1px); }
  100% { transform: scale(1) translateY(0); }
}

.bottom-nav-slide-enter-active,
.bottom-nav-slide-leave-active {
  transition: transform 0.3s ease, opacity 0.25s ease;
}
.bottom-nav-slide-enter-from,
.bottom-nav-slide-leave-to {
  transform: translateY(calc(100% + 24px)) scale(0.96);
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .liquid-glass-nav,
  .liquid-bubble-track,
  .liquid-bubble,
  .liquid-tab-item :deep(svg) {
    animation: none !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
