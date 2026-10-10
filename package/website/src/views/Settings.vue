<template>
  <div class="ts-page-background h-full">
    <div class="mx-auto flex h-full w-full max-w-screen-2xl">
      <aside class="ts-settings-nav hidden w-64 lg:w-72 shrink-0 overflow-y-auto border-r px-5 py-6 md:block">
        <h1 class="px-2 text-2xl font-bold">设置</h1>
        <p class="mt-1 px-2 text-sm text-gray-500 dark:text-gray-400">管理账号、图库与系统服务</p>
        <div class="mt-7 space-y-6">
          <section v-for="group in menuGroups" :key="group.label">
            <h2 class="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">{{ group.label }}</h2>
            <div class="ts-surface overflow-hidden">
              <button
                v-for="(item, index) in group.items"
                :key="item.key"
                :data-tab="item.key"
                type="button"
                class="flex w-full items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 dark:hover:bg-gray-700"
                :class="[index > 0 ? 'border-t border-gray-100 dark:border-gray-700' : '', activeTab === item.key ? 'bg-primary-50 text-primary-600 dark:bg-gray-700 dark:text-primary-400' : '']"
                @click="selectItem(item.key)"
              >
                <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400">
                  <component :is="item.icon" class="h-5 w-5" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block text-sm font-medium">{{ item.label }}</span>
                  <span class="mt-0.5 block truncate text-xs text-gray-500 dark:text-gray-400">{{ item.description }}</span>
                </span>
                <ChevronRight class="h-4 w-4 shrink-0 text-gray-300 dark:text-gray-600" />
              </button>
            </div>
          </section>
        </div>
      </aside>

      <div v-if="!activeTab" class="min-w-0 flex-1 overflow-y-auto px-4 pb-8 pt-5 md:hidden">
        <header class="px-1 pb-5"><h1 class="ts-page-title">设置</h1></header>
        <button
          type="button"
          data-tab="profile"
          class="mb-6 flex w-full items-center gap-3 ts-surface p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:ring-offset-gray-900"
          @click="selectItem('profile')"
        >
          <img v-if="userStore.userInfo?.avatar" :src="toServerUrl(userStore.userInfo.avatar)" alt="" class="h-14 w-14 rounded-full object-cover" />
          <span v-else class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xl font-semibold text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">{{ accountInitial }}</span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-lg font-semibold">{{ accountName }}</span>
            <span class="mt-0.5 block truncate text-sm text-gray-500 dark:text-gray-400">账号、头像与个人信息</span>
          </span>
          <ChevronRight class="h-5 w-5 text-gray-300 dark:text-gray-600" />
        </button>

        <div class="space-y-6">
          <section v-for="group in mobileMenuGroups" :key="group.label">
            <h2 class="mb-2 px-3 text-[13px] font-medium text-gray-500 dark:text-gray-400">{{ group.label }}</h2>
            <div class="ts-surface overflow-hidden">
              <button
                v-for="(item, index) in group.items"
                :key="item.key"
                :data-tab="item.key"
                type="button"
                class="flex min-h-14 w-full items-center gap-3 px-4 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
                :class="index > 0 ? 'border-t border-gray-100 dark:border-gray-700' : ''"
                @click="selectItem(item.key)"
              >
                <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400"><component :is="item.icon" class="h-[18px] w-[18px]" /></span>
                <span class="min-w-0 flex-1">
                  <span class="block text-[15px] font-medium">{{ item.label }}</span>
                  <span class="mt-0.5 block truncate text-xs text-gray-500 dark:text-gray-400">{{ item.description }}</span>
                </span>
                <ChevronRight class="h-4 w-4 shrink-0 text-gray-300 dark:text-gray-600" />
              </button>
            </div>
          </section>
        </div>
      </div>

      <main v-else class="min-w-0 flex-1 overflow-y-auto">
        <div v-if="activeTab !== 'mobile-backup'" class="ts-page-header sticky top-0 z-20 flex items-center border-b px-2 md:hidden">
          <BackButton label="返回设置" @click="goBack" />
          <div class="pointer-events-none absolute inset-x-20 truncate text-center text-[15px] font-semibold">{{ activeItem?.label }}</div>
        </div>
        <div ref="contentRef" class="mx-auto w-full max-w-5xl p-4 md:p-8">
          <Transition :name="transitionName" mode="out-in">
            <MobileBackup v-if="activeTab === 'mobile-backup'" :key="activeTab" hosted @request-settings-back="goBack" />
            <component :is="currentComponent" v-else :key="activeTab" />
          </Transition>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Activity, BrainCircuit, ChevronRight, CloudUpload, Database, FolderOpen, Info, Key, List, MessageSquare, Settings as SettingsIcon, Smartphone, User, UserCircle } from 'lucide-vue-next'
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
import DesktopDataDirectory from './settings/DesktopDataDirectory.vue'
import AIModelManagement from './settings/AIModelManagement.vue'
import MobileBackup from './settings/MobileBackup.vue'
import MobileAppConnection from './settings/MobileAppConnection.vue'
import { isMobileApp, isNativeApp, isTauriApp, toServerUrl } from '@/config/server'
import { useUserStore } from '@/stores/user'

type MenuItem = { key: string; label: string; description: string; icon: typeof UserCircle; superuserOnly?: boolean; desktopOnly?: boolean; mobileOnly?: boolean; webOnly?: boolean }
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const isNarrow = ref(typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches)
const activeTab = ref<string | null>(isNarrow.value ? null : 'profile')
const transitionName = ref<'settings-forward' | 'settings-back' | 'settings-none'>('settings-none')
const contentRef = ref<HTMLElement | null>(null)

const baseGroups: Array<{ label: string; items: MenuItem[] }> = [
  { label: '账号', items: [
    { key: 'profile', label: '个人资料', description: '头像、昵称与账号信息', icon: UserCircle },
    { key: 'user', label: '用户管理', description: '管理成员和访问权限', icon: User, superuserOnly: true },
    { key: 'tokens', label: '令牌管理', description: '管理 Agent 访问令牌', icon: Key },
  ] },
  { label: '设备与图库', items: [
    { key: 'mobile-app', label: '连接手机 App', description: '下载 App 并连接此服务器', icon: Smartphone, webOnly: true },
    { key: 'mobile-backup', label: '手机备份', description: '查看进度并设置自动备份', icon: CloudUpload, mobileOnly: true },
    { key: 'external', label: '外部图库', description: '管理服务器照片目录', icon: FolderOpen },
    { key: 'data-directory', label: '数据目录', description: '迁移桌面数据、缩略图与模型', icon: Database, desktopOnly: true },
  ] },
  { label: '系统与 AI', items: [
    { key: 'basic', label: '系统设置', description: '安全、地图、扫描与任务选项', icon: SettingsIcon },
    { key: 'tasks', label: '任务管理', description: '查看和控制后台处理任务', icon: List },
    { key: 'ai-extensions', label: 'AI 扩展包', description: '安装桌面 AI 运行能力', icon: BrainCircuit, desktopOnly: true },
    { key: 'ai-models', label: 'AI 模型管理', description: '管理大模型连接与本地模型', icon: Database },
    { key: 'performance', label: '性能测试', description: '检测存储与服务性能', icon: Activity },
  ] },
  { label: '支持', items: [
    { key: 'feedback', label: '需求平台', description: '提交需求、反馈问题并跟进进度', icon: MessageSquare },
    { key: 'about', label: '关于行影集', description: '版本、更新与开源信息', icon: Info },
  ] },
]
const requestedKey = computed(() => {
  const raw = (route.hash ? route.hash.slice(1) : '') || (typeof route.query.tab === 'string' ? route.query.tab : '')
  return raw === 'mobile-backup-settings' ? 'mobile-backup' : raw
})
const isAvailable = (item: MenuItem) => (!item.superuserOnly || userStore.userInfo?.is_superuser)
  && (!item.desktopOnly || isTauriApp() || requestedKey.value === item.key)
  && (!item.mobileOnly || isMobileApp() || requestedKey.value === item.key)
  && (!item.webOnly || !isNativeApp())
const menuGroups = computed(() => baseGroups.map(group => ({ ...group, items: group.items.filter(isAvailable) })).filter(group => group.items.length))
const mobileMenuGroups = computed(() => menuGroups.value.map(group => ({ ...group, items: group.items.filter(item => item.key !== 'profile') })).filter(group => group.items.length))
const allItems = computed(() => menuGroups.value.flatMap(group => group.items))
const activeItem = computed(() => allItems.value.find(item => item.key === activeTab.value))
const tabComponents: Record<string, typeof ProfileSettings> = {
  profile: ProfileSettings, 'mobile-app': MobileAppConnection, user: UserManagement, tasks: TaskManagement,
  basic: BasicSettings, 'data-directory': DesktopDataDirectory, 'ai-extensions': DesktopAIExtensions, 'ai-models': AIModelManagement, external: ExternalGallery,
  'mobile-backup': MobileBackup, performance: PerformanceTest, tokens: Tokens, about: AboutPage, feedback: FeedbackPage,
}
const currentComponent = computed(() => tabComponents[activeTab.value || 'profile'] ?? ProfileSettings)
const accountName = computed(() => userStore.userInfo?.nickname || userStore.userInfo?.username || '我的账号')
const accountInitial = computed(() => accountName.value.trim().charAt(0).toUpperCase() || '我')

const selectItem = (key: string) => {
  if (!allItems.value.some(item => item.key === key)) return
  transitionName.value = isNarrow.value ? 'settings-forward' : 'settings-none'
  activeTab.value = key
  void (isNarrow.value ? router.push({ path: '/settings', hash: `#${key}` }) : router.replace({ path: '/settings', hash: `#${key}` }))
  contentRef.value?.scrollTo({ top: 0 })
}
const goBack = () => { transitionName.value = 'settings-back'; activeTab.value = null; void router.replace({ path: '/settings' }) }
const syncViewport = () => {
  const next = window.matchMedia('(max-width: 767px)').matches
  if (next === isNarrow.value) return
  isNarrow.value = next
  if (!next && !activeTab.value) activeTab.value = requestedKey.value || 'profile'
  if (next && !requestedKey.value) activeTab.value = null
}
watch(() => [route.hash, route.query.tab, allItems.value.length], () => {
  const key = requestedKey.value
  if (key && allItems.value.some(item => item.key === key)) { transitionName.value = 'settings-none'; activeTab.value = key }
  else if (!isNarrow.value && !activeTab.value) activeTab.value = 'profile'
  else if (isNarrow.value && !key) activeTab.value = null
}, { immediate: true })
watch(allItems, items => { if (activeTab.value && !items.some(item => item.key === activeTab.value)) activeTab.value = isNarrow.value ? null : 'profile' })
onMounted(() => window.addEventListener('resize', syncViewport))
onBeforeUnmount(() => window.removeEventListener('resize', syncViewport))
</script>

<style scoped>
.settings-forward-enter-active, .settings-back-enter-active { transition: opacity var(--ts-motion-normal) ease, transform var(--ts-motion-page) var(--ts-ease); }
.settings-forward-enter-from { opacity: 0; transform: translateX(18px); }
.settings-back-enter-from { opacity: 0; transform: translateX(-18px); }
</style>
