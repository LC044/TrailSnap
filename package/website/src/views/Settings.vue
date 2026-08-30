<template>
  <!-- 禁用滚动条 -->
  <div class="flex flex-col md:flex-row bg-gray-50 dark:bg-gray-900 scrollbar-hide h-full">
    <!-- Sidebar -->
    <div class="w-full md:w-64 bg-white dark:bg-gray-800 border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-700 flex-shrink-0">
      <div class="hidden md:block md:p-6">
        <h1 class="text-xl font-bold text-gray-800 dark:text-white">设置中心</h1>
      </div>
      <nav ref="navRef" class="flex md:block overflow-x-auto md:overflow-visible pb-2 md:pb-0 mt-0 md:mt-2 px-4 md:px-0 scrollbar-hide">
        <a
          v-for="item in menuItems"
          :key="item.key"
          :data-tab="item.key"
          @click="selectTab(item.key)"
          class="flex items-center px-4 md:px-6 py-2 md:py-3 text-sm md:text-base text-gray-600 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition-colors whitespace-nowrap md:whitespace-normal mr-2 md:mr-0 rounded-full md:rounded-none"
          :class="{ 'bg-primary-50 text-primary-500 md:border-r-2 border-primary-500 dark:bg-gray-700 dark:text-primary-400': activeTab === item.key }"
        >
          <component :is="item.icon" class="w-5 h-5 mr-2 md:mr-3" />
          {{ item.label }}
        </a>
      </nav>
    </div>

    <!-- Content Area -->
    <div
      ref="contentRef"
      class="flex-1 overflow-y-auto overflow-x-hidden p-4 md:p-8 max-w-5xl md:mx-auto"
    >
      <div class="relative">
        <Transition :name="transitionName">
          <component :is="currentComponent" :key="activeTab" />
        </Transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, UserCircle, List, Settings, FolderOpen, Info, Key, MessageSquare, Activity, BrainCircuit, Database, CloudUpload, SlidersHorizontal } from 'lucide-vue-next'
import UserManagement from './settings/UserManagement.vue'
import ProfileSettings from './settings/ProfileSettings.vue'
import TaskManagement from './settings/TaskManagement.vue'
import BasicSettings from './settings/BasicSettings.vue'
import ExternalGallery from './settings/ExternalGallery.vue'
import PerformanceTest from './settings/PerformanceTest.vue'
import Tokens from './settings/Tokens.vue'
import AboutPage from './settings/AboutPage.vue'
import FeedbackPage from './settings/FeedbackPage.vue'
import DesktopAIExtensions from './settings/DesktopAIExtensions.vue'
import AIModelManagement from './settings/AIModelManagement.vue'
import MobileBackup from './settings/MobileBackup.vue'
import MobileBackupSettings from './settings/MobileBackupSettings.vue'
import { isMobileApp, isTauriApp } from '@/config/server'
import { useSwipeNavigation } from '@/composables/useSwipeNavigation'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const activeTab = ref('profile')
const baseMenuItems = [
  { key: 'profile', label: '个人资料', icon: UserCircle },
  { key: 'user', label: '用户管理', icon: User, superuserOnly: true },
  { key: 'tasks', label: '任务管理', icon: List },
  { key: 'basic', label: '基础设置', icon: Settings },
  { key: 'ai-extensions', label: 'AI 扩展包', icon: BrainCircuit, desktopOnly: true },
  { key: 'ai-models', label: 'AI 模型管理', icon: Database },
  { key: 'external', label: '外部图库', icon: FolderOpen },
  { key: 'mobile-backup', label: '手机备份', icon: CloudUpload, mobileOnly: true },
  { key: 'mobile-backup-settings', label: '备份设置', icon: SlidersHorizontal, mobileOnly: true },
  { key: 'performance', label: '性能测试', icon: Activity },
  { key: 'tokens', label: '令牌管理', icon: Key },
  { key: 'about', label: '关于行影集', icon: Info },
  { key: 'feedback', label: '问题反馈', icon: MessageSquare },
]
const requestedTab = computed(() => {
  const hash = route.hash ? route.hash.replace('#', '') : ''
  return hash || (typeof route.query.tab === 'string' ? route.query.tab : '')
})
const menuItems = computed(() => baseMenuItems.filter(item =>
  (!item.superuserOnly || userStore.userInfo?.is_superuser)
  && (!item.desktopOnly || isTauriApp() || requestedTab.value === item.key)
  && (!item.mobileOnly || isMobileApp() || requestedTab.value === item.key)
))

// Map each tab key to its component so the content area can render a single
// keyed <component>, which lets <Transition> animate the tab swap.
const tabComponents: Record<string, typeof ProfileSettings> = {
  profile: ProfileSettings,
  user: UserManagement,
  tasks: TaskManagement,
  basic: BasicSettings,
  'ai-extensions': DesktopAIExtensions,
  'ai-models': AIModelManagement,
  external: ExternalGallery,
  'mobile-backup': MobileBackup,
  'mobile-backup-settings': MobileBackupSettings,
  performance: PerformanceTest,
  tokens: Tokens,
  about: AboutPage,
  feedback: FeedbackPage,
}
const currentComponent = computed(() => tabComponents[activeTab.value] ?? ProfileSettings)

// Direction of the slide transition: swipe left → next slides in from the
// right; swipe right → previous slides in from the left.
const transitionName = ref<'slide-left' | 'slide-right' | 'slide-none'>('slide-none')

const goNext = () => {
  const i = menuItems.value.findIndex(item => item.key === activeTab.value)
  if (i >= 0 && i < menuItems.value.length - 1) {
    transitionName.value = 'slide-left'
    activeTab.value = menuItems.value[i + 1].key
  }
}
const goPrev = () => {
  const i = menuItems.value.findIndex(item => item.key === activeTab.value)
  if (i > 0) {
    transitionName.value = 'slide-right'
    activeTab.value = menuItems.value[i - 1].key
  }
}

// Selecting a tab from the sidebar. The slide animation is mobile-only — on
// desktop switching is instant (slide-none) since the slide feels out of place
// alongside the vertical sidebar layout.
const selectTab = (key: string) => {
  if (key === activeTab.value) return
  const isMobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches
  if (isMobile) {
    const cur = menuItems.value.findIndex(item => item.key === activeTab.value)
    const next = menuItems.value.findIndex(item => item.key === key)
    transitionName.value = next > cur ? 'slide-left' : 'slide-right'
  } else {
    transitionName.value = 'slide-none'
  }
  activeTab.value = key
}

// Horizontal swipe to switch tabs — mobile only (below the md breakpoint,
// where the sidebar collapses into horizontal pills).
const contentRef = ref<HTMLElement | null>(null)
useSwipeNavigation(contentRef, {
  onSwipeLeft: goNext,
  onSwipeRight: goPrev,
  enabled: () => typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches,
})

// Handle URL hash / query-param navigation. Both /settings#tasks and
// /settings?tab=tasks activate the "任务管理" tab so that the TaskBell
// can deep-link into a specific category.
watch(
  () => [route.hash, route.query.tab],
  ([newHash, queryTab]) => {
    const key = (newHash ? String(newHash).replace('#', '') : '') || (queryTab ? String(queryTab) : '')
    if (key && menuItems.value.some(item => item.key === key)) {
      transitionName.value = 'slide-none'
      activeTab.value = key
    }
  },
  { immediate: true }
)

watch(menuItems, (items) => {
  if (!items.some(item => item.key === activeTab.value)) activeTab.value = 'profile'
})

watch(activeTab, (newTab) => {
  router.replace({ hash: `#${newTab}` })
})

const navRef = ref<HTMLElement | null>(null)
// Keep the active pill inside the horizontal scroll strip on mobile — after a
// swipe switches to an off-screen tab, scroll its pill into view (centered).
watch(
  activeTab,
  () => {
    if (typeof window === 'undefined' || !window.matchMedia('(max-width: 767px)').matches) return
    const el = navRef.value?.querySelector<HTMLElement>(`[data-tab="${activeTab.value}"]`)
    el?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  },
  { flush: 'post' }
)
</script>

<style scoped>
/* Hide scrollbars on the horizontal nav strip (and root) while keeping it
   scrollable — matches the local .scrollbar-hide used in other components. */
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}
.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

/* Tab slide transitions. The leaving panel is absolutely positioned so it can
   slide out while the entering panel takes its place in normal flow — the
   container keeps the entering panel's height throughout. */
.slide-left-enter-active,
.slide-left-leave-active,
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
.slide-left-leave-active,
.slide-right-leave-active {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
}
.slide-left-enter-from {
  transform: translateX(100%);
}
.slide-left-leave-to {
  transform: translateX(-100%);
}
.slide-right-enter-from {
  transform: translateX(-100%);
}
.slide-right-leave-to {
  transform: translateX(100%);
}
</style>
