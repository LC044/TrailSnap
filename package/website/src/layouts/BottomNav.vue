<template>
  <!-- 移动端底部 Tab 栏（替代旧版顶部悬浮药丸，根治窄屏挤压）。仅 <768px 显示。 -->
  <Transition name="bottom-nav-slide">
    <nav
      v-show="!uiStore.selectionActive"
      class="fixed bottom-0 inset-x-0 z-40 md:hidden bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border-t border-slate-200 dark:border-slate-800 pb-[env(safe-area-inset-bottom)] transition-colors duration-300"
      aria-label="主导航"
    >
      <div class="grid grid-cols-5 h-14">
        <!-- 首页 -->
        <RouterLink
          to="/"
          :class="tabClass(isGroup('home'))"
          aria-label="首页"
        >
          <span v-if="isGroup('home')" class="absolute top-0 inset-x-3 h-0.5 bg-primary-500 rounded-full" />
          <Home class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">首页</span>
        </RouterLink>

        <!-- 照片 -->
        <RouterLink
          to="/photos"
          :class="tabClass(isGroup('photos'))"
          aria-label="照片"
        >
          <span v-if="isGroup('photos')" class="absolute top-0 inset-x-3 h-0.5 bg-primary-500 rounded-full" />
          <ImageIcon class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">照片</span>
        </RouterLink>

        <!-- 搜索（居中强调，跳全屏搜索页） -->
        <RouterLink
          to="/mobile-search"
          :class="tabClass(isGroup('search'))"
          aria-label="搜索"
        >
          <span v-if="isGroup('search')" class="absolute top-0 inset-x-3 h-0.5 bg-primary-500 rounded-full" />
          <span class="w-7 h-7 rounded-full bg-primary-50 dark:bg-primary-900/30 flex items-center justify-center">
            <Search class="w-4 h-4 shrink-0" />
          </span>
          <span class="text-[10px] leading-none whitespace-nowrap">搜索</span>
        </RouterLink>

        <!-- 相册 -->
        <RouterLink
          to="/album"
          :class="tabClass(isGroup('albums'))"
          aria-label="相册"
        >
          <span v-if="isGroup('albums')" class="absolute top-0 inset-x-3 h-0.5 bg-primary-500 rounded-full" />
          <Images class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">相册</span>
        </RouterLink>

        <!-- 更多（打开底部 sheet） -->
        <button
          type="button"
          @click="moreSheetVisible = true"
          :class="tabClass(moreActive)"
          aria-label="更多"
          aria-haspopup="dialog"
        >
          <span v-if="moreActive" class="absolute top-0 inset-x-3 h-0.5 bg-primary-500 rounded-full" />
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
    class="more-sheet"
  >
    <div class="px-4 pt-3 pb-[calc(env(safe-area-inset-bottom)_+_12px)]">
      <!-- 拖拽手柄 -->
      <div class="mx-auto mb-4 w-10 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600" />

      <!-- 通知（复用 NotificationBell 的 row 变体，自带未读徽标 + 开抽屉） -->
      <NotificationBell variant="row" />

      <!-- 账号快捷入口：移动端无需先进设置页再查找退出。 -->
      <div class="mt-3 flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-slate-800">
        <RouterLink
          to="/settings#profile"
          class="flex min-w-0 flex-1 items-center gap-3 rounded-lg focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="moreSheetVisible = false"
        >
          <img
            v-if="userStore.userInfo?.avatar"
            :src="userStore.userInfo.avatar"
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
              @click="moreSheetVisible = false"
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
            @click="moreSheetVisible = false"
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
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  Home,
  Image as ImageIcon,
  Search,
  Images,
  Menu,
  LogOut
} from 'lucide-vue-next'
import { injectNavItems, getNavIcon, getThumbnailUrl } from '@/composables/useNavItems'
import NotificationBell from '@/components/NotificationBell.vue'
import { useUiStore } from '@/stores/uiStore'
import { useUserStore } from '@/stores/user'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { mobileMoreSections, type NavGroup } from '@/config/navigation'

const route = useRoute()
const uiStore = useUiStore()
const userStore = useUserStore()

const { items: navItemsList } = injectNavItems()

const moreSheetVisible = ref(false)
useOverlayStack(moreSheetVisible, () => { moreSheetVisible.value = false })

const isGroup = (group: NavGroup) => route.meta.navGroup === group
const isCurrentPath = (href: string) => route.path === href || route.path.startsWith(`${href}/`)
const moreActive = computed(() => ['tickets', 'tools', 'more'].includes(String(route.meta.navGroup)))
const accountName = computed(() => userStore.userInfo?.nickname || userStore.userInfo?.username || '我的账号')
const accountInitial = computed(() => accountName.value.trim().charAt(0).toUpperCase() || '我')

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确定要退出当前账号吗？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
    moreSheetVisible.value = false
    await userStore.logout()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') console.error('Logout failed', error)
  }
}

const tabClass = (active: boolean) =>
  [
    'relative flex flex-col items-center justify-center gap-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none',
    active
      ? 'text-primary-600 dark:text-primary-400'
      : 'text-slate-500 dark:text-slate-400 hover:text-primary-600 dark:hover:text-primary-400'
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
}
.more-sheet .el-drawer__body {
  padding: 0;
}
</style>

<style scoped>
.bottom-nav-slide-enter-active,
.bottom-nav-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.bottom-nav-slide-enter-from,
.bottom-nav-slide-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
