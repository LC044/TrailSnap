<template>
  <div class="ts-page-background min-h-full ts-browse-page mx-auto w-full max-w-screen-2xl px-[var(--ts-page-gutter)]">
    <div>
      <header class="ts-browse-header flex items-center justify-between">
        <div class="min-w-0 flex-1">
          <h1 class="ts-page-title text-gray-900 dark:text-white">记忆</h1>
        </div>
        <div class="ts-liquid-glass ts-glass-toolbar" aria-label="记忆操作">
          <button class="ts-glass-button" :disabled="store.discovering" :aria-label="store.discovering ? '正在发现记忆' : '发现记忆'" title="发现记忆" @click="runDiscovery"><RefreshCw class="h-5 w-5" :class="{ 'animate-spin': store.discovering }" /></button>
          <RouterLink to="/memories/new" class="ts-glass-button" aria-label="新建记忆" title="新建记忆"><Plus class="h-5 w-5" /></RouterLink>
          <button class="ts-glass-button" aria-label="更多记忆操作" :aria-expanded="showActions" aria-haspopup="menu" @click="showActions = !showActions"><MoreHorizontal class="h-5 w-5" /></button>
          <AdaptiveMenu v-model="showActions" title="记忆操作" mobile-presentation="popover" glass>
            <button class="ts-action-row" @click="showActions = false; router.push('/daily-frame')"><Film />一日一帧</button>
            <button class="ts-action-row" @click="showActions = false; router.push('/explore/relations')"><Network />关联探索</button>
            <button class="ts-action-row" @click="showActions = false; createWithAgent()"><Bot />和 AI 创建</button>
            <button v-if="store.activeStatus !== 'ignored'" class="ts-action-row" @click="showActions = false; selectMode = !selectMode">{{ selectMode ? '取消批量选择' : '批量合并' }}</button>
          </AdaptiveMenu>
        </div>
      </header>
      <p class="mb-6 text-sm text-gray-500 dark:text-gray-400">把散落的照片，重新连成一段经历</p>

      <ChapterShelf />

      <div class="mt-7 flex flex-col gap-3 border-b border-gray-200 dark:border-gray-700 sm:flex-row sm:items-end sm:justify-between">
        <nav class="-mb-px flex gap-2 overflow-x-auto sm:gap-6" aria-label="记忆状态">
          <button
            v-for="tab in tabs"
            :key="tab.status"
            class="min-h-11 whitespace-nowrap border-b-2 px-1 pb-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 sm:text-sm"
            :class="store.activeStatus === tab.status ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'"
            @click="changeTab(tab.status)"
          >{{ tab.label }} <span class="ml-0.5 rounded-full bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-gray-800 sm:ml-1 sm:px-2">{{ store.counts[tab.status] }}</span></button>
        </nav>
        <div v-if="store.activeStatus !== 'ignored'" class="mb-2 items-center gap-2" :class="selectMode ? 'flex' : 'hidden sm:flex'">
          <button class="min-h-11 text-sm text-gray-500 hover:text-primary-600 dark:text-gray-400" @click="selectMode = !selectMode">
            {{ selectMode ? '取消选择' : '批量合并' }}
          </button>
          <button v-if="selectMode" class="ts-button ts-button-primary min-h-11 bg-primary-500 text-white disabled:opacity-50" :disabled="selectedIds.length < 2" @click="openMerge">合并 {{ selectedIds.length }} 段</button>
        </div>
      </div>

      <div v-if="store.loading" class="flex min-h-[360px] items-center justify-center">
        <LoaderCircle class="h-8 w-8 animate-spin text-primary-500" />
      </div>

      <div v-else-if="store.items.length" class="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
        <MemoryCard
          v-for="memory in store.items"
          :key="memory.id"
          :memory="memory"
          :selectable="selectMode"
          :selected="selectedIds.includes(memory.id)"
          @open="openMemory"
          @confirm="confirmMemory"
          @ignore="ignoreMemory"
          @restore="restoreMemory"
          @toggle-select="toggleSelect"
        />
      </div>

      <div v-if="!store.loading && store.total > 0" class="mt-7 flex flex-col items-center gap-3">
        <p class="text-xs text-gray-500 dark:text-gray-400">当前显示 {{ (store.page - 1) * store.pageSize + 1 }}–{{ Math.min(store.page * store.pageSize, store.total) }}，共 {{ store.total }} 段</p>
        <el-pagination
          v-if="store.total > store.pageSize"
          :current-page="store.page"
          :page-size="store.pageSize"
          :total="store.total"
          layout="prev, pager, next"
          @current-change="changePage"
        />
      </div>

      <div v-else class="ts-surface mt-12 flex min-h-[340px] flex-col items-center justify-center border-dashed px-6 text-center">
        <BookHeart class="h-12 w-12 text-primary-400" />
        <h2 class="ts-section-title mt-4 text-lg font-semibold text-gray-900 dark:text-white">{{ emptyTitle }}</h2>
        <p class="mt-2 max-w-md text-sm text-gray-500 dark:text-gray-400">{{ emptyDescription }}</p>
        <button v-if="store.activeStatus === 'candidate'" class="ts-button ts-button-primary mt-5 bg-primary-500 text-white hover:bg-primary-600" @click="runDiscovery">开始发现</button>
        <RouterLink v-else-if="store.activeStatus === 'confirmed'" to="/memories/new" class="mt-5 rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600">从照片创建</RouterLink>
      </div>
    </div>

    <el-dialog v-model="mergeVisible" title="合并记忆" width="min(92vw, 520px)">
      <p class="text-sm text-gray-500 dark:text-gray-400">合并后会生成一段新记忆，原记忆会保留为历史来源。</p>
      <el-form label-position="top" class="mt-4">
        <el-form-item label="新标题"><el-input v-model="mergeTitle" maxlength="255" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="primary" :loading="merging" @click="mergeSelected">确认合并</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { BookHeart, Bot, Film, LoaderCircle, MoreHorizontal, Network, Plus, RefreshCw } from 'lucide-vue-next'
import MemoryCard from '@/components/memory/MemoryCard.vue'
import ChapterShelf from '@/components/chapter/ChapterShelf.vue'
import { memoryApi } from '@/api/memory'
import { useMemoryStore } from '@/stores/memoryStore'
import { useUiStore } from '@/stores/uiStore'
import type { MemoryItem, MemoryStatus } from '@/types/memory'

const store = useMemoryStore()
const showActions = ref(false)
const router = useRouter()
const uiStore = useUiStore()
const selectMode = ref(false)
const selectedIds = ref<string[]>([])
const mergeVisible = ref(false)
const mergeTitle = ref('')
const merging = ref(false)

const tabs = [
  { status: 'candidate' as const, label: '待确认' },
  { status: 'confirmed' as const, label: '我的记忆' },
  { status: 'ignored' as const, label: '已忽略' },
]

const emptyTitle = computed(() => ({
  candidate: '暂时没有新的候选记忆',
  confirmed: '还没有保存记忆',
  ignored: '没有已忽略的候选',
}[store.activeStatus] || '暂无内容'))
const emptyDescription = computed(() => store.activeStatus === 'candidate'
  ? '系统会根据照片的时间、地点和人物线索寻找经历，你也可以手动创建。'
  : store.activeStatus === 'confirmed' ? '把一次旅行、一场聚会或普通的一天保存下来。' : '被忽略的候选会保留在这里，随时可以恢复。')

function changeTab(status: MemoryStatus) {
  selectedIds.value = []
  selectMode.value = false
  store.fetchList(status, 1)
}
function changePage(page: number) {
  selectedIds.value = []
  store.fetchList(store.activeStatus, page)
}
function createWithAgent() {
  uiStore.openAgentWithPrompt('我想创建一段相册记忆。请先问我这段经历的大概时间、地点、人物或画面线索，再搜索照片并展示候选。在我明确确认标题、照片和地点后，创建正式记忆。', false)
}
function openMemory(memory: MemoryItem) { router.push(`/memories/${memory.id}`) }
function toggleSelect(id: string) {
  selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(item => item !== id) : [...selectedIds.value, id]
}
async function runDiscovery() {
  try {
    const created = await store.discover()
    ElMessage.success(created ? `发现 ${created} 段候选记忆` : '没有发现新的候选记忆')
  } catch (error) { ElMessage.error('发现记忆失败，请稍后重试') }
}
async function confirmMemory(memory: MemoryItem) {
  await store.confirm(memory.id)
  ElMessage.success('已保存为我的记忆')
}
async function ignoreMemory(memory: MemoryItem) {
  await store.ignore(memory.id)
  ElMessage({ message: '已忽略这段候选记忆', type: 'success', duration: 2500 })
}
async function restoreMemory(memory: MemoryItem) {
  await store.restore(memory.id)
  ElMessage.success('已恢复为待确认')
}
function openMerge() {
  const selected = store.items.filter(item => selectedIds.value.includes(item.id))
  mergeTitle.value = selected.map(item => item.title).join(' · ').slice(0, 255)
  mergeVisible.value = true
}
async function mergeSelected() {
  if (selectedIds.value.length < 2 || !mergeTitle.value.trim()) return
  merging.value = true
  try {
    const merged = await memoryApi.merge({ memory_ids: selectedIds.value, title: mergeTitle.value.trim() })
    mergeVisible.value = false
    ElMessage.success('记忆已合并')
    router.push(`/memories/${merged.id}`)
  } finally { merging.value = false }
}

onMounted(async () => {
  try { await Promise.all([store.fetchCounts(), store.fetchList(store.activeStatus)]) }
  catch { ElMessage.error('加载记忆失败') }
})
</script>
