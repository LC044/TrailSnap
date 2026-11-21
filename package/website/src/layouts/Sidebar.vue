<template>
  <aside
    ref="sidebarRef"
    class="lm-rail shrink-0 z-40"
    :class="{ 'is-open': pinned }"
  >
    <div class="lm-rail-shell">
      <div class="lm-rail-brand">
        <RouterLink to="/" class="lm-rail-logo" aria-label="行影集首页">
          <img src="@/assets/logo.svg" alt="" />
        </RouterLink>
        <span class="lm-rail-word">行影集</span>
      </div>

      <!-- 展开 / 收起：固定在顶部，紧贴品牌下方；两种状态位置完全一致 -->
      <div class="lm-rail-handle">
        <button
          type="button"
          class="lm-rail-toggle"
          :class="{ 'is-hinting': showExploreHint }"
          :aria-expanded="pinned"
          :aria-label="pinned ? '收起导航' : '展开导航'"
          :title="pinned ? '收起导航' : '展开导航'"
          @click="togglePin"
        >
          <ChevronRight v-if="!pinned" class="h-[18px] w-[18px] shrink-0" />
          <ChevronLeft v-else class="h-[18px] w-[18px] shrink-0" />
          <span class="lm-rail-label">{{ pinned ? '收起导航' : '展开导航' }}</span>
        </button>
      </div>

      <!-- 搜索：收起时是一枚图标，展开后即为输入框 -->
      <div class="lm-rail-search">
        <button
          v-show="!panelOpen"
          type="button"
          class="lm-rail-item lm-rail-item--solo"
          aria-label="搜索"
          title="搜索"
          @click="openSearch"
        >
          <Search class="h-[18px] w-[18px] shrink-0" />
        </button>
        <div v-show="panelOpen" class="relative w-full">
          <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--ts-color-text-tertiary)]" />
          <input
            ref="searchInputRef"
            v-model="searchText"
            @input="onInput"
            @keydown.enter="handleSearch"
            @blur="handleBlur"
            @focus="handleFocus"
            type="text"
            placeholder="搜索或描述画面…"
            class="ts-input lm-rail-input w-full !pl-9 !pr-16"
          />
          <button
            v-if="searchText"
            @click="clearSearch"
            class="absolute right-11 top-1/2 -translate-y-1/2 rounded-full p-1 text-[var(--ts-color-text-tertiary)] transition-colors hover:text-[var(--ts-color-text)]"
            aria-label="清空搜索"
          >
            <X class="h-3 w-3" />
          </button>
          <button
            type="button"
            @click="showDropdown = false; router.push('/search/image')"
            class="absolute right-1.5 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full text-[var(--ts-color-text-secondary)] transition-colors hover:bg-[var(--ts-color-surface-muted)] hover:text-[var(--ts-color-text)]"
            aria-label="以图搜图"
            title="以图搜图"
          >
            <Images class="h-4 w-4" />
          </button>

          <!-- 搜索建议下拉框 -->
          <div
            v-if="showDropdown"
            class="lm-rail-dropdown absolute left-0 top-full z-50 mt-2 max-h-72 w-[280px] overflow-y-auto"
          >
            <div v-if="!searchText && suggestions.length === 0" class="px-4 py-3">
              <div class="mb-2 flex items-center gap-2 text-[var(--ts-journal-focus)]">
                <Sparkles class="h-4 w-4" />
                <span class="text-sm font-medium">语义搜索</span>
              </div>
              <p class="text-xs text-[var(--ts-color-text-secondary)]">描述画面内容，就能找到那一张</p>
              <div class="mt-2.5 flex flex-wrap gap-1.5">
                <button
                  v-for="tag in searchHints"
                  :key="tag"
                  type="button"
                  @mousedown.prevent="quickSearch(tag)"
                  class="lm-rail-hint"
                >{{ tag }}</button>
              </div>
            </div>

            <button
              v-if="searchText.trim()" type="button"
              @mousedown.prevent @click="openModelSearch"
              class="lm-rail-suggest"
            >
              <Bot class="h-4 w-4 shrink-0 text-[var(--ts-journal-focus)]" />
              <span class="flex min-w-0 flex-col">
                <span class="font-medium text-[var(--ts-color-text)]">用大模型搜索</span>
                <span class="text-xs text-[var(--ts-color-text-secondary)]">理解时间、地点与人物等组合条件</span>
              </span>
            </button>
            <button
              v-if="searchText"
              type="button"
              @mousedown.prevent="handleSearch"
              class="lm-rail-suggest"
            >
              <Sparkles class="h-4 w-4 shrink-0 text-[var(--ts-journal-focus)]" />
              <span class="flex flex-col text-left">
                <span class="font-medium text-[var(--ts-color-text)]">画面识别 “{{ searchText }}”</span>
                <span class="text-xs text-[var(--ts-color-text-secondary)]">按画面语义检索</span>
              </span>
            </button>

            <button
              v-for="(item, index) in suggestions"
              :key="index"
              type="button"
              @mousedown.prevent="selectSuggestion(item)"
              class="lm-rail-suggest"
            >
              <component :is="getIcon(item.type)" class="h-4 w-4 shrink-0 text-[var(--ts-color-text-tertiary)]" />
              <span class="min-w-0 flex-1">
                <span class="flex items-center justify-between gap-2">
                  <span class="truncate font-medium text-[var(--ts-color-text)]">
                    {{ item.type === 'ocr' ? item.label : item.value }}
                  </span>
                  <span class="lm-rail-tag">{{ getLabel(item.type) }}</span>
                </span>
              </span>
            </button>
          </div>
        </div>
      </div>

      <nav class="lm-rail-nav">
        <!-- One tinted pill travels between destinations instead of blinking. -->
        <span ref="activeGlow" class="lm-rail-glow" aria-hidden="true" />
        <section v-for="(section, sectionIndex) in desktopNavSections" :key="section.label" class="lm-rail-group">
          <div v-if="sectionIndex" class="lm-rail-sep" aria-hidden="true"></div>
          <div class="lm-rail-list">
            <RouterLink
              v-for="item in section.items"
              :key="item.href"
              :to="item.href"
              :aria-label="item.label"
              :title="pinned ? undefined : item.label"
              class="lm-rail-item sidebar-nav-button"
              :class="{ 'is-active': isDesktopNavActive(item), 'sidebar-nav-active': isDesktopNavActive(item) }"
              :aria-current="isDesktopNavActive(item) ? 'page' : undefined"
            >
              <component :is="item.icon" class="h-[18px] w-[18px] shrink-0" />
              <span class="lm-rail-label">{{ item.label }}</span>
            </RouterLink>
          </div>
        </section>

        <div class="lm-rail-sep" aria-hidden="true"></div>

        <!-- 快捷访问 -->
        <div class="lm-rail-quick">
          <div v-if="navItemsList.length" class="lm-rail-list">
            <button
              v-for="item in navItemsList"
              :key="`${item.entity_type}-${item.entity_id}`"
              type="button"
              class="lm-rail-item lm-rail-item--quick"
              :class="{ 'is-active': isActiveRoute(item.route_path) }"
              :aria-label="item.name"
              :title="pinned ? undefined : item.name"
              @click="router.push(item.route_path)"
            >
              <span class="lm-rail-thumb">
                <img v-if="item.cover_photo_id" :src="getThumbnailUrl(item)" alt="" loading="lazy" />
                <component v-else :is="getNavIcon(item.entity_type)" class="h-3.5 w-3.5" />
              </span>
              <span class="lm-rail-label">{{ item.name }}</span>
              <span
                class="lm-rail-remove"
                role="button"
                tabindex="0"
                :aria-label="`移除 ${item.name}`"
                @click.stop="removeNavItem(item.entity_type, item.entity_id)"
                @keydown.enter.stop="removeNavItem(item.entity_type, item.entity_id)"
              ><X class="h-3 w-3" /></span>
            </button>
          </div>
          <!-- 快捷访问的添加入口：有入口时贴在列表末尾，没有时单独一行 -->
          <button
            v-if="pinned || !navItemsList.length"
            type="button"
            class="lm-rail-item lm-rail-item--add"
            :aria-label="navItemsList.length ? '添加快捷访问' : '添加快捷访问'"
            :title="pinned ? undefined : '添加快捷访问'"
            @click="openAddDialog"
          >
            <Plus class="h-[18px] w-[18px] shrink-0" />
            <span class="lm-rail-label">添加快捷访问</span>
          </button>
        </div>
      </nav>

      <div class="lm-rail-foot">
        <button
          type="button"
          class="lm-rail-ai"
          :aria-label="proactiveUnread > 0 ? `AI 助手，${proactiveUnread} 条新消息` : 'AI 助手'"
          :title="pinned ? undefined : 'AI 助手'"
          @click="uiStore.openAgent()"
        >
          <span class="lm-rail-ai-orb">
            <Bot class="h-[15px] w-[15px]" />
            <span v-if="proactiveUnread > 0" class="lm-rail-dot" aria-hidden="true" />
          </span>
          <span class="lm-rail-label">AI 助手</span>
          <Sparkles class="lm-rail-ai-spark h-3.5 w-3.5" />
        </button>

        <SidebarTaskManager :is-collapsed="!pinned" />

        <RouterLink
          v-for="item in desktopSystemNavItems"
          :key="item.href"
          :to="item.href"
          :aria-label="item.label"
          :title="pinned ? undefined : item.label"
          class="lm-rail-item"
          :class="{ 'is-active': route.path === item.href }"
        >
          <component :is="item.icon" class="h-[18px] w-[18px] shrink-0" />
          <span class="lm-rail-label">{{ item.label }}</span>
        </RouterLink>

        <el-dropdown trigger="click" placement="top-start" @command="handleAccountCommand">
          <button
            type="button"
            class="lm-rail-account"
            :aria-label="`账号：${accountName}`"
            :title="pinned ? undefined : accountName"
          >
            <span class="lm-rail-avatar">
              <img v-if="userStore.userInfo?.avatar" :src="toServerUrl(userStore.userInfo.avatar)" :alt="accountName" />
              <span v-else>{{ accountInitial }}</span>
              <span v-if="notificationStore.unreadCount > 0" class="lm-rail-dot" aria-label="有未读通知" />
            </span>
            <span class="lm-rail-label lm-rail-account-copy">
              <span class="lm-rail-account-name">{{ accountName }}</span>
              <span class="lm-rail-account-id">{{ userStore.userInfo?.username }}</span>
            </span>
            <ChevronDown class="lm-rail-account-caret h-3.5 w-3.5" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="notifications">
                <Bell class="mr-2 h-4 w-4" />
                通知
                <span
                  v-if="notificationStore.unreadCount > 0"
                  class="ml-1.5 inline-flex min-w-[16px] items-center justify-center rounded-full bg-primary-500 px-1 text-[10px] font-semibold leading-4 text-white"
                >{{ notificationStore.unreadCount > 99 ? '99+' : notificationStore.unreadCount }}</span>
              </el-dropdown-item>
              <el-dropdown-item command="profile"><UserCircle class="mr-2 h-4 w-4" />个人资料</el-dropdown-item>
              <el-dropdown-item command="settings"><Settings class="mr-2 h-4 w-4" />设置</el-dropdown-item>
              <el-dropdown-item v-if="!isTauriApp()" divided command="logout"><LogOut class="mr-2 h-4 w-4" />退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <NavAddDialog ref="addDialogRef" v-model:visible="showAddNavDialog" />
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Images,
  Search,
  X,
  User,
  MapPin,
  Type,
  Folder,
  FileText,
  Tag,
  Mountain,
  Sparkles,
  Plus,
  Calendar,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  UserCircle,
  Settings,
  LogOut,
  Bot,
  Bell,
} from 'lucide-vue-next'
import { useDebounceFn, useMediaQuery } from '@vueuse/core'
import { usePhotoStore } from '@/stores/photoStore'
import searchService, { type SearchSuggestion } from '@/api/search'
import { injectNavItems, getNavIcon, getThumbnailUrl } from '@/composables/useNavItems'
import NavAddDialog from '@/components/NavAddDialog.vue'
import SidebarTaskManager from '@/components/SidebarTaskManager.vue'
import { useNotificationStore } from '@/stores/notificationStore'
import { parseDateRange } from '@/utils/date'
import { desktopNavSections, systemNavItems } from '@/config/navigation'
import type { AppNavItem } from '@/config/navigation'
import { useUserStore } from '@/stores/user'
import { ElMessageBox } from 'element-plus'
import { useUiStore } from '@/stores/uiStore'
import { isTauriApp, toServerUrl } from '@/config/server'
import { agentApi } from '@/api/agent'

const route = useRoute()
const router = useRouter()
const store = usePhotoStore()
const userStore = useUserStore()
const uiStore = useUiStore()
const notificationStore = useNotificationStore()

// 主动式记忆红点：未读的主动消息数量
const proactiveUnread = ref(0)
const refreshProactiveUnread = async () => {
  // 未登录时不请求 agent 接口，避免触发 401 拦截器把未登录页面踢到 /login
  if (!userStore.token) return
  try {
    const res: any = await agentApi.getProactiveMessages()
    proactiveUnread.value = res?.data?.unread ?? 0
  } catch {
    // 静默失败，不影响侧边栏
  }
}
onMounted(refreshProactiveUnread)
// 关闭 Agent 后刷新（用户可能已读了主动消息）
watch(() => uiStore.agentOpen, (open) => {
  if (!open) refreshProactiveUnread()
})
const desktopSystemNavItems = computed(() => systemNavItems.filter(item => item.href === '/recycle-bin'))
const accountName = computed(() => userStore.userInfo?.nickname || userStore.userInfo?.username || '账号')
const accountInitial = computed(() => accountName.value.slice(0, 1).toUpperCase())

const handleAccountCommand = async (command: string) => {
  if (command === 'notifications') {
    notificationStore.openDrawer()
  } else if (command === 'profile') {
    await router.push('/settings#profile')
  } else if (command === 'settings') {
    await router.push('/settings')
  } else if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出当前账号吗？', '退出登录', {
        confirmButtonText: '退出',
        cancelButtonText: '取消',
        type: 'warning',
      })
      await userStore.logout()
    } catch (error) {
      if (error !== 'cancel' && error !== 'close') console.error('Logout failed', error)
    }
  }
}

const isDesktopNavActive = (item: AppNavItem) => {
  if (item.excludePaths?.some(path => route.path === path || route.path.startsWith(`${path}/`))) return false
  if (item.activeMatch === 'exact') return route.path === item.href
  if (item.activeMatch === 'path') {
    return route.path === item.href || route.path.startsWith(`${item.href}/`)
  }
  return route.meta.navGroup === item.navGroup
}

/*
 * Sliding active indicator.
 *
 * The pill is one absolutely positioned element; its geometry is measured from
 * the active link after any layout change (route, collapse, section toggle,
 * scroll). Movement is pure transform so it stays on the compositor.
 */
const sidebarRef = ref<HTMLElement | null>(null)
const activeGlow = ref<HTMLElement | null>(null)
let glowFrame = 0

function placeActiveGlow() {
  const sidebar = sidebarRef.value
  const glow = activeGlow.value
  if (!sidebar || !glow) return
  const active = sidebar.querySelector<HTMLElement>('nav .sidebar-nav-button.sidebar-nav-active')
  if (!active || !active.getClientRects().length) {
    glow.style.opacity = '0'
    return
  }
  const base = (glow.offsetParent as HTMLElement | null)?.getBoundingClientRect() ?? sidebar.getBoundingClientRect()
  const rect = active.getBoundingClientRect()
  glow.style.opacity = '1'
  glow.style.height = `${Math.round(rect.height)}px`
  glow.style.transform = `translate3d(0, ${Math.round(rect.top - base.top)}px, 0)`
}

function scheduleActiveGlow() {
  if (glowFrame) return
  glowFrame = requestAnimationFrame(() => {
    glowFrame = 0
    placeActiveGlow()
  })
}

// 路由激活状态判断：完全匹配，避免首页（/）一直处于激活状态
const isActiveRoute = (path: string) => {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}

/* ---------------------------------------------------------------------------
 * Rail behaviour.
 *
 * 桌面导航默认是一条窄的玻璃轨道（只有图标）。顶部的「展开导航」把它展开成
 * 带文字的完整面板，再次点击收起。开关固定在品牌下方，两种状态位置一致；
 * 展开时内容整体让位，不做覆盖式弹层。
 * ------------------------------------------------------------------------- */
const PIN_KEY = 'trailsnap_expanded'
const pinned = ref(false)
try { pinned.value = localStorage.getItem(PIN_KEY) === '1' } catch { pinned.value = false }

const panelOpen = computed(() => pinned.value)

/* 首次使用的一次性提示：只在从未展开过导航时出现几秒。 */
const HINT_KEY = 'trailsnap_rail_hint'
const showExploreHint = ref(false)
let hintTimer: ReturnType<typeof setTimeout> | undefined
function dismissHint() {
  showExploreHint.value = false
  if (hintTimer) clearTimeout(hintTimer)
  hintTimer = undefined
  try { localStorage.setItem(HINT_KEY, '1') } catch {}
}

function togglePin() {
  pinned.value = !pinned.value
  try { localStorage.setItem(PIN_KEY, pinned.value ? '1' : '0') } catch {}
  if (pinned.value) dismissHint()
}

onMounted(() => {
  let seen = false
  try { seen = localStorage.getItem(HINT_KEY) === '1' || localStorage.getItem(PIN_KEY) === '1' } catch {}
  if (seen || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  showExploreHint.value = true
  hintTimer = setTimeout(dismissHint, 7000)
})

// 兼容旧实现：模板已改为窄轨道，这里保留 isCollapsed 供子组件判断展开状态。
const isCollapsed = computed(() => !panelOpen.value)

// 搜索相关状态和逻辑
const searchText = ref('')
const openModelSearch = () => {
  const query = searchText.value.trim()
  if (!query) return
  uiStore.openAgentWithPrompt(query, true, 'search')
  showDropdown.value = false
}
const showDropdown = ref(false)
const searchInputRef = ref<HTMLInputElement | null>(null)
const suggestions = ref<SearchSuggestion[]>([])
const searchHints = ['海边日落', '猫咪', '雪景', '花园', '城市夜景']

// AI 微服务预热标记（会话级，仅触发一次，避免后续真正搜索时模型冷启动延迟）
let aiWarmupTriggered = false
const triggerAiWarmup = () => {
  if (aiWarmupTriggered) return
  aiWarmupTriggered = true
  // fire-and-forget：发送一次极简语义搜索请求，激活后端的 embedding 调用链以预热 AI 微服务
  searchService
    .searchByText({ text: 'warmup', limit: 1 })
    .catch((e) => {
      // 预热失败不影响后续使用，重置标记以便下次 focus 再试一次
      aiWarmupTriggered = false
      console.warn('AI warmup failed:', e)
    })
}

// 自定义导航项
const { items: navItemsList, removeItem: removeNavItem, addItem: addNavItem } = injectNavItems()
const showAddNavDialog = ref(false)
const addDialogRef = ref<InstanceType<typeof NavAddDialog> | null>(null)

const openAddDialog = () => {
  showAddNavDialog.value = true
  nextTick(() => {
    addDialogRef.value?.fetchData()
  })
}

watch(() => store.currentContext, (ctx) => {
  if (ctx.type === 'search' && ctx.id) {
    searchText.value = ctx.id
  } else if (ctx.type !== 'search') {
    searchText.value = ''
    suggestions.value = []
  }
})

const openSearch = () => {
  pinned.value = true
  nextTick(() => {
    if (searchInputRef.value) {
      searchInputRef.value.focus()
    }
  })
}

const handleBlur = () => {
  setTimeout(() => {
    showDropdown.value = false
    suggestions.value = []
  }, 200)
}

const handleFocus = () => {
  showDropdown.value = true
  // 点击搜索框时预热 AI 微服务，避免后续真正搜索时模型冷启动造成卡顿
  triggerAiWarmup()
  if (searchText.value) {
    fetchSuggestions(searchText.value)
  }
}

const handleSearch = () => {
  if (searchText.value.trim()) {
    showDropdown.value = false
    suggestions.value = []
    
    const dateRange = parseDateRange(searchText.value)
    if (dateRange) {
      router.push({ path: '/search', query: { q: searchText.value, type: 'date' } })
    } else {
      router.push({ path: '/search', query: { q: searchText.value } })
    }
    
    searchInputRef.value?.blur()
  }
}

const clearSearch = () => {
  searchText.value = ''
  suggestions.value = []
  store.loadPhotos(true)
  searchInputRef.value?.focus()
}

const quickSearch = (text: string) => {
  searchText.value = text
  handleSearch()
}

const fetchSuggestions = useDebounceFn(async (q: string) => {
  if (!q.trim()) {
    suggestions.value = []
    return
  }
  try {
    const res = await searchService.getSuggestions(q)
    const processedSuggestions: SearchSuggestion[] = []
    let hasOcr = false
    
    for (const item of res) {
      if (item.type === 'ocr') {
        hasOcr = true
      } else {
        processedSuggestions.push(item)
      }
    }
    
    if (hasOcr) {
      processedSuggestions.push({
        type: 'ocr',
        value: q,
        label: `图片中包含文字：${q}`
      } as SearchSuggestion)
    }

    const dateRange = parseDateRange(q)
    if (dateRange) {
      processedSuggestions.unshift({
        type: 'date',
        value: q,
        label: `按日期搜索：${dateRange.label}`
      } as SearchSuggestion)
    }
    
    suggestions.value = processedSuggestions
  } catch (e) {
    console.error("Failed to fetch suggestions", e)
  }
}, 300)

const onInput = () => {
  showDropdown.value = true
  fetchSuggestions(searchText.value)
}

const selectSuggestion = (item: SearchSuggestion) => {
  searchText.value = item.value
  showDropdown.value = false
  suggestions.value = []
  router.push({ 
    path: '/search', 
    query: { 
      q: item.value, 
      type: item.type 
    } 
  })
  searchInputRef.value?.blur()
}

const getLabel = (type: string) => {
  const map: Record<string, string> = {
    'person': '人物',
    'location': '地点',
    'ocr': '文字',
    'album': '相册',
    'folder': '文件夹',
    'filename': '文件',
    'tag': '标签',
    'scene': '景区',
    'date': '日期'
  }
  return map[type] || type
}

const getIcon = (type: string) => {
  const map: Record<string, any> = {
    'person': User,
    'location': MapPin,
    'ocr': Type,
    'album': Images,
    'folder': Folder,
    'filename': FileText,
    'tag': Tag,
    'scene': Mountain,
    'date': Calendar
  }
  return map[type] || Search
}

/* The indicator needs every nav list resolved, so it is wired at the end. */
let sidebarObserver: ResizeObserver | undefined
let glowScrollTarget: HTMLElement | null = null

onMounted(() => {
  void nextTick(scheduleActiveGlow)
  const sidebar = sidebarRef.value
  if (!sidebar) return
  sidebarObserver = new ResizeObserver(scheduleActiveGlow)
  sidebarObserver.observe(sidebar)
  glowScrollTarget = sidebar.querySelector('nav')
  glowScrollTarget?.addEventListener('scroll', scheduleActiveGlow, { passive: true })
})

onBeforeUnmount(() => {
  if (glowFrame) cancelAnimationFrame(glowFrame)
  sidebarObserver?.disconnect()
  glowScrollTarget?.removeEventListener('scroll', scheduleActiveGlow)
  if (hintTimer) clearTimeout(hintTimer)
})

watch(
  [() => route.path, isCollapsed, () => navItemsList.value.length],
  () => void nextTick(scheduleActiveGlow),
  { flush: 'post' },
)
</script>

<style scoped>
/* ===========================================================================
 * 桌面导航轨道（Lumen rail）
 *
 * 收起：一条 64px 的玻璃竖条，只有图标；所有图标共用同一条中轴线。
 * 展开：面板加宽到 236px，画布整体让位；图标原位不动，文字从右侧淡入。
 * 开关固定在底部同一行，两种状态下位置完全一致。
 * ========================================================================= */

.lm-rail {
  --rail-icon: 22px;
  --rail-pad: 12px;
  --rail-gap: 12px;
  position: relative;
  width: 92px;
  padding: 14px 0 14px 14px;
  background: transparent;
  transition: width 320ms var(--lm-ease);
}

.lm-rail.is-open { width: 252px; }

.lm-rail-shell {
  display: flex;
  height: 100%;
  width: 64px;
  flex-direction: column;
  gap: 4px;
  padding: 10px 8px 12px;
  overflow: hidden;
  border: 1px solid var(--ts-glass-border);
  border-radius: 30px;
  background: var(--ts-glass-bg);
  box-shadow: var(--ts-shadow-glass);
  -webkit-backdrop-filter: blur(26px) saturate(var(--ts-glass-saturation));
  backdrop-filter: blur(26px) saturate(var(--ts-glass-saturation));
  transition: width 380ms var(--lm-ease), box-shadow 320ms var(--lm-ease), border-radius 320ms var(--lm-ease);
}

/* 玻璃内侧的一束顶部光，让轨道不再像一块白板。 */
.lm-rail-shell::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background: var(--ts-glass-sheen);
  opacity: .8;
}

.lm-rail-shell::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  border-radius: inherit;
  background:
    radial-gradient(120px 64px at 50% 0%, rgba(var(--theme-rgb), .14), transparent 72%),
    radial-gradient(140px 90px at 50% 100%, rgba(var(--theme-rgb), .08), transparent 76%);
}

.lm-rail.is-open .lm-rail-shell {
  width: 236px;
  border-radius: 28px;
  background: var(--ts-glass-panel);
  box-shadow: var(--ts-shadow-floating);
}

/* ——— 品牌 ——— */
.lm-rail-brand {
  position: relative;
  z-index: 1;
  display: flex;
  height: 44px;
  flex-shrink: 0;
  align-items: center;
  gap: 10px;
  padding: 0 5px;
}

.lm-rail-logo {
  display: grid;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 10px;
  transition: transform 320ms var(--ts-ease-spring);
}
.lm-rail-logo img { width: 100%; height: 100%; border-radius: inherit; }
.lm-rail-logo:hover { transform: rotate(-5deg) scale(1.05); }
.lm-rail-logo:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: 3px; }

.lm-rail-word {
  max-width: 0;
  overflow: hidden;
  opacity: 0;
  color: var(--ts-color-text);
  font-family: var(--lm-font-display);
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -.05em;
  white-space: nowrap;
  transition: max-width 320ms var(--lm-ease), opacity 220ms ease;
}
.lm-rail.is-open .lm-rail-word { max-width: 120px; opacity: 1; }

/* ——— 搜索 ——— */
.lm-rail-search { position: relative; z-index: 3; display: flex; padding: 2px 0 4px; }
.lm-rail-input { height: 38px; min-height: 38px; border-radius: 12px; background: color-mix(in srgb, var(--ts-color-surface) 72%, transparent); font-size: 13px; }

.lm-rail-dropdown {
  border: 1px solid var(--ts-color-border);
  border-radius: 18px;
  background: var(--ts-color-surface);
  box-shadow: var(--ts-shadow-floating);
  overflow: hidden;
}
.lm-rail-hint {
  border-radius: 999px;
  background: var(--ts-color-surface-muted);
  padding: 4px 10px;
  color: var(--ts-color-text-secondary);
  font-size: 11px;
  font-weight: 600;
  transition: background-color 160ms ease, color 160ms ease;
}
.lm-rail-hint:hover { background: var(--ts-journal-active); color: var(--ts-color-text); }
.lm-rail-suggest {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  border-top: 1px solid var(--ts-color-divider);
  padding: 9px 14px;
  text-align: left;
  font-size: 13px;
  transition: background-color 140ms ease;
}
.lm-rail-suggest:hover { background: var(--ts-color-surface-muted); }
.lm-rail-tag {
  flex-shrink: 0;
  border-radius: 6px;
  background: var(--ts-color-surface-muted);
  padding: 1px 6px;
  color: var(--ts-color-text-secondary);
  font-size: 10px;
  font-weight: 600;
}

/* ——— 导航 ——— */
.lm-rail-nav {
  position: relative;
  z-index: 1;
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 1px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
  mask-image: linear-gradient(to bottom, #000 calc(100% - 20px), transparent);
  -webkit-mask-image: linear-gradient(to bottom, #000 calc(100% - 20px), transparent);
}
.lm-rail-nav::-webkit-scrollbar { display: none; }
.lm-rail-nav > * { flex-shrink: 0; }

/* 选中项背后的滑块：放在 nav 内，跟随列表一起滚动 */
.lm-rail-glow {
  position: absolute;
  z-index: 0;
  top: 0;
  left: 4px;
  right: 4px;
  border-radius: 13px;
  background: var(--ts-journal-active);
  opacity: 0;
  pointer-events: none;
  will-change: transform;
  transition: transform 420ms var(--ts-ease-spring), height 200ms var(--ts-ease-paper), opacity 200ms ease;
}

.lm-rail-sep {
  height: 1px;
  margin: 6px 10px;
  background: linear-gradient(to right, var(--ts-color-divider), transparent);
}

.lm-rail-list { display: flex; flex-direction: column; gap: 1px; }

/* 所有行共用的骨架：同样的高度、同样的左内边距、同样的图标槽 */
.lm-rail-item,
.lm-rail-ai,
.lm-rail-account {
  position: relative;
  z-index: 1;
  display: flex;
  width: 100%;
  min-width: 0;
  height: 38px;
  align-items: center;
  gap: var(--rail-gap);
  border-radius: 13px;
  padding: 0 var(--rail-pad);
  color: var(--ts-color-text-secondary);
  font-size: 13.5px;
  font-weight: 550;
  line-height: 1.2;
  white-space: nowrap;
  transition: color 180ms ease, background-color 180ms ease, transform 120ms ease;
}

/* 收起时：零内边距、零间距，图标严格居中在同一条中轴线上 */
.lm-rail:not(.is-open) :is(.lm-rail-item, .lm-rail-ai, .lm-rail-account) {
  justify-content: center;
  gap: 0;
  padding: 0;
}

.lm-rail-item:hover,
.lm-rail-ai:hover,
.lm-rail-account:hover { color: var(--ts-color-text); background: color-mix(in srgb, var(--ts-color-surface-muted) 72%, transparent); }
.lm-rail-item:active,
.lm-rail-ai:active,
.lm-rail-account:active { transform: scale(.97); }
.lm-rail-item:focus-visible,
.lm-rail-ai:focus-visible,
.lm-rail-account:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: -2px; }

.lm-rail-item.is-active {
  color: var(--ts-journal-accent-text);
  font-weight: 650;
  background: transparent;
}
/* 激活项左侧的一枚光点，收起状态下也能看见当前位置 */
.lm-rail-item.is-active::before {
  content: '';
  position: absolute;
  left: 2px;
  width: 3px;
  height: 15px;
  border-radius: 999px;
  background: var(--ts-journal-focus);
  box-shadow: 0 0 10px rgba(var(--theme-rgb), .55);
}

/* 图标统一占 22px 的槽位，与缩略图、AI 光球、头像落在同一条中轴线 */
.lm-rail-item > svg { margin-inline: 2px; transition: transform 380ms var(--ts-ease-spring); }
.lm-rail-item:hover > svg { transform: translate3d(0, -1px, 0) scale(1.07); }

.lm-rail-label {
  max-width: 0;
  overflow: hidden;
  opacity: 0;
  text-overflow: ellipsis;
  transition: max-width 300ms var(--lm-ease), opacity 200ms ease;
}
.lm-rail.is-open .lm-rail-label { max-width: 150px; opacity: 1; }

/* 快捷访问 */
.lm-rail-thumb {
  display: grid;
  width: var(--rail-icon);
  height: var(--rail-icon);
  flex-shrink: 0;
  place-items: center;
  overflow: hidden;
  border-radius: 7px;
  background: var(--ts-color-surface-muted);
  color: var(--ts-color-text-tertiary);
}
.lm-rail-thumb img { width: 100%; height: 100%; object-fit: cover; }

.lm-rail-remove {
  position: absolute;
  right: 8px;
  display: grid;
  width: 20px;
  height: 20px;
  place-items: center;
  border-radius: 6px;
  color: var(--ts-color-text-tertiary);
  opacity: 0;
  cursor: pointer;
  transition: opacity 160ms ease, color 160ms ease, background-color 160ms ease;
}
.lm-rail:not(.is-open) .lm-rail-remove { display: none; }
.lm-rail-item--quick:hover .lm-rail-remove { opacity: 1; }
.lm-rail-remove:hover { background: var(--ts-color-surface-muted); color: var(--ts-color-danger); }

.lm-rail-item--add { color: var(--ts-color-text-tertiary); font-size: 12.5px; font-weight: 550; }
.lm-rail-item--add:hover { color: var(--ts-color-text); }

/* ——— 底部 ——— */
.lm-rail-foot {
  position: relative;
  z-index: 2;
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  gap: 1px;
  padding-top: 4px;
}
.lm-rail-foot::before {
  content: '';
  height: 1px;
  margin: 2px 10px 5px;
  background: linear-gradient(to right, var(--ts-color-border), transparent);
}

/* ——— 展开 / 收起：贴在品牌下方 ——— */
.lm-rail-handle {
  position: relative;
  z-index: 2;
  display: flex;
  flex-shrink: 0;
  padding-bottom: 2px;
}

.lm-rail-toggle {
  display: flex;
  width: 100%;
  height: 32px;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-radius: 10px;
  color: var(--ts-color-text-tertiary);
  font-size: 12px;
  font-weight: 600;
  transition: color 180ms ease, background-color 180ms ease;
}
.lm-rail-toggle > svg { margin-inline: 2px; opacity: .85; transition: transform 320ms var(--ts-ease-spring); }
.lm-rail.is-open .lm-rail-toggle { justify-content: flex-start; padding: 0 var(--rail-pad); }
.lm-rail-toggle:hover { color: var(--ts-color-text); background: color-mix(in srgb, var(--ts-color-surface-muted) 72%, transparent); }
.lm-rail-toggle:hover > svg { opacity: 1; }
.lm-rail.is-open .lm-rail-toggle:hover > svg { transform: translateX(-2px); }
.lm-rail-toggle:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: -2px; }

/* 收起时做成一颗带描边的按钮，和导航图标区分开；高度与展开时保持一致，
   这样上下两块内容不会因为开关形态变化而位移。 */
.lm-rail:not(.is-open) .lm-rail-toggle {
  width: min(44px, 100%);
  margin-inline: auto;
  border: 1px solid var(--ts-color-border);
  border-radius: 9px;
  background: color-mix(in srgb, var(--ts-color-surface) 58%, transparent);
  color: var(--ts-color-text-secondary);
}
.lm-rail:not(.is-open) .lm-rail-toggle .lm-rail-label { display: none; }
.lm-rail:not(.is-open) .lm-rail-toggle:hover {
  border-color: color-mix(in srgb, var(--ts-color-border) 45%, var(--ts-color-text-tertiary));
  color: var(--ts-color-text);
}

/* 首次使用提示：不弹气泡（会压住页面标题），改成让开关自己「呼吸」三下 */
@keyframes lm-handle-nudge {
  0%, 100% { transform: translateX(0); box-shadow: 0 0 0 0 rgba(var(--theme-rgb), 0); }
  35% { transform: translateX(2px); box-shadow: 0 0 0 4px rgba(var(--theme-rgb), .16); }
  70% { transform: translateX(0); box-shadow: 0 0 0 0 rgba(var(--theme-rgb), 0); }
}
.lm-rail-toggle.is-hinting {
  border-color: color-mix(in srgb, var(--ts-color-border) 30%, var(--ts-journal-focus));
  color: var(--ts-journal-accent-text);
  animation: lm-handle-nudge 1.6s var(--ts-ease-breathe) 400ms 3;
}
@media (prefers-reduced-motion: reduce) {
  .lm-rail-toggle.is-hinting { animation: none; }
}

/* 展开时在开关下加一条发丝线，和搜索分开；用阴影画，不占高度 */
.lm-rail.is-open .lm-rail-handle { box-shadow: inset 0 -1px 0 var(--ts-color-divider); }

.lm-rail-ai { color: var(--ts-color-text); font-weight: 600; }

.lm-rail-ai-orb {
  position: relative;
  display: grid;
  width: var(--rail-icon);
  height: var(--rail-icon);
  flex-shrink: 0;
  place-items: center;
  border-radius: 8px;
  color: var(--ts-journal-focus);
  background:
    radial-gradient(circle at 30% 20%, rgba(var(--theme-rgb), .34), transparent 70%),
    color-mix(in srgb, var(--ts-color-surface) 70%, transparent);
  box-shadow: inset 0 0 0 1px rgba(var(--theme-rgb), .26);
}
.lm-rail-ai-spark { margin-left: auto; color: var(--ts-journal-focus); opacity: 0; transition: opacity 220ms ease; }
.lm-rail:not(.is-open) .lm-rail-ai-spark { display: none; }
.lm-rail.is-open .lm-rail-ai-spark { opacity: .8; animation: ts-twinkle 5.2s var(--ts-ease-breathe) infinite; }

.lm-rail-dot {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #f43f5e;
  box-shadow: 0 0 0 2px var(--ts-color-page);
}

.lm-rail-account { text-align: left; }

.lm-rail-avatar {
  position: relative;
  display: grid;
  width: var(--rail-icon);
  height: var(--rail-icon);
  flex-shrink: 0;
  place-items: center;
  border-radius: 999px;
  background: rgba(var(--theme-rgb), .16);
  color: var(--ts-journal-accent-text);
  font-size: 10px;
  font-weight: 700;
}
.lm-rail-avatar img { width: 100%; height: 100%; border-radius: 999px; object-fit: cover; }

.lm-rail-account-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 1px;
  line-height: 1.2;
}
.lm-rail.is-open .lm-rail-account-copy { max-width: 130px; }
.lm-rail-account-name { overflow: hidden; text-overflow: ellipsis; font-size: 13px; font-weight: 600; color: var(--ts-color-text); }
.lm-rail-account-id { overflow: hidden; text-overflow: ellipsis; font-size: 11px; color: var(--ts-color-text-tertiary); }
.lm-rail-account-caret { margin-left: auto; color: var(--ts-color-text-tertiary); opacity: 0; transition: opacity 200ms ease; }
.lm-rail:not(.is-open) .lm-rail-account-caret { display: none; }
.lm-rail.is-open .lm-rail-account-caret { opacity: 1; }

.lm-rail-foot :deep(.el-dropdown) { width: 100%; }

@media (prefers-reduced-motion: reduce) {
  .lm-rail, .lm-rail-shell, .lm-rail-word, .lm-rail-label,
  .lm-rail-item, .lm-rail-glow, .lm-rail-ai-spark { transition-duration: 0s !important; animation: none !important; }
}
</style>
