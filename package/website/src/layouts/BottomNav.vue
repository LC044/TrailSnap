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
          :class="tabClass(isActive('/', true))"
          aria-label="首页"
        >
          <span v-if="isActive('/', true)" class="absolute top-0 inset-x-3 h-0.5 bg-primary-500 rounded-full" />
          <Home class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">首页</span>
        </RouterLink>

        <!-- 照片 -->
        <RouterLink
          to="/photos"
          :class="tabClass(isActive('/photos'))"
          aria-label="照片"
        >
          <span v-if="isActive('/photos')" class="absolute top-0 inset-x-3 h-0.5 bg-primary-500 rounded-full" />
          <ImageIcon class="w-5 h-5 shrink-0" />
          <span class="text-[10px] leading-none whitespace-nowrap">照片</span>
        </RouterLink>

        <!-- 搜索（居中强调，跳全屏搜索页） -->
        <RouterLink
          to="/mobile-search"
          class="relative flex flex-col items-center justify-center gap-0.5 text-primary-600 dark:text-primary-400 hover:brightness-110 transition focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          aria-label="搜索"
        >
          <span class="w-7 h-7 rounded-full bg-primary-50 dark:bg-primary-900/30 flex items-center justify-center">
            <Search class="w-4 h-4 shrink-0" />
          </span>
          <span class="text-[10px] leading-none whitespace-nowrap">搜索</span>
        </RouterLink>

        <!-- 相册 -->
        <RouterLink
          to="/album"
          :class="tabClass(isActive('/album'))"
          aria-label="相册"
        >
          <span v-if="isActive('/album')" class="absolute top-0 inset-x-3 h-0.5 bg-primary-500 rounded-full" />
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

      <!-- 二级入口 -->
      <div class="mt-3 grid grid-cols-3 gap-x-2 gap-y-3">
        <RouterLink
          v-for="l in moreLinks"
          :key="l.href"
          :to="l.href"
          @click="moreSheetVisible = false"
          class="flex flex-col items-center gap-1.5 py-2 rounded-xl text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/60 hover:text-primary-600 dark:hover:text-primary-400 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <component :is="l.icon" class="w-5 h-5 shrink-0" />
          <span class="text-xs whitespace-nowrap">{{ l.label }}</span>
        </RouterLink>
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
import {
  Home,
  Image as ImageIcon,
  Search,
  Images,
  Menu,
  Ticket,
  Wrench,
  Layers,
  Trash2,
  Settings
} from 'lucide-vue-next'
import { injectNavItems, getNavIcon, getThumbnailUrl } from '@/composables/useNavItems'
import NotificationBell from '@/components/NotificationBell.vue'
import { useUiStore } from '@/stores/uiStore'

const route = useRoute()
const uiStore = useUiStore()

const moreLinks = [
  { label: '车票', href: '/ticket', icon: Ticket },
  { label: '工具箱', href: '/toolbox', icon: Wrench },
  { label: '断舍离', href: '/swipe-filter', icon: Layers },
  { label: '回收站', href: '/recycle-bin', icon: Trash2 },
  { label: '设置', href: '/settings', icon: Settings },
]

const { items: navItemsList } = injectNavItems()

const moreSheetVisible = ref(false)

const isActive = (href: string, exact = false) =>
  exact ? route.path === href : route.path.startsWith(href)

const moreActive = computed(() => moreLinks.some((l) => route.path.startsWith(l.href)))

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
