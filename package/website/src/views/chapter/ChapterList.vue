<template>
  <div class="min-h-full bg-gray-50 px-4 py-6 dark:bg-gray-900 md:px-8">
    <div class="mx-auto max-w-7xl">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div><RouterLink to="/memories" class="text-sm text-primary-600 dark:text-primary-400">← 记忆中心</RouterLink><h1 class="mt-4 font-serif text-3xl text-gray-900 dark:text-white">人生章节</h1><p class="mt-2 text-sm text-gray-500 dark:text-gray-400">把数年的照片装订成日记，按天自动整理，慢慢翻阅。</p></div>
        <div class="flex gap-2"><button class="rounded-lg border border-primary-200 px-4 py-2 text-primary-600 disabled:opacity-50 dark:border-primary-800 dark:text-primary-400" :disabled="discovering" @click="discover">{{ discovering ? '正在寻找线索' : '发现章节建议' }}</button><RouterLink to="/chapters/new" class="rounded-lg bg-primary-500 px-4 py-2 text-white">新建章节</RouterLink></div>
      </div>
      <div class="mt-7 flex gap-5 overflow-x-auto border-b border-gray-200 dark:border-gray-700">
        <button v-for="tab in tabs" :key="tab.key" class="shrink-0 border-b-2 px-1 py-3 text-sm" :class="active === tab.key ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 dark:text-gray-400'" @click="choose(tab.key)">{{ tab.name }}</button>
      </div>
      <div v-if="store.loading" class="py-24 text-center text-gray-500 dark:text-gray-400">正在整理章节…</div>
      <div v-else-if="loadError" class="mt-7 rounded-2xl border border-red-200 bg-white px-5 py-16 text-center dark:border-red-900 dark:bg-gray-800"><h2 class="font-serif text-xl text-gray-900 dark:text-white">章节暂时无法加载</h2><p class="mt-2 text-sm text-gray-500 dark:text-gray-400">请稍后重试；已有章节不会因此丢失。</p><button class="mt-5 rounded-lg border border-primary-200 px-4 py-2 text-sm text-primary-600 dark:border-primary-800 dark:text-primary-400" @click="choose(active)">重新加载</button></div>
      <div v-else-if="!store.items.length" class="mt-7 rounded-2xl border border-dashed border-gray-300 bg-white px-5 py-20 text-center dark:border-gray-700 dark:bg-gray-800"><h2 class="font-serif text-xl text-gray-900 dark:text-white">{{ active === 'confirmed' ? '为这些年的照片，写一本日记' : '这里暂时没有章节' }}</h2><p class="mt-2 text-sm text-gray-500 dark:text-gray-400">{{ active === 'confirmed' ? '选一段时光，照片会按天自动汇入，AI 整理成日记，随时可以修改。' : '章节建议根据照片线索生成，是否成立由你确认。' }}</p><div v-if="active === 'confirmed'" class="mt-6 flex flex-wrap justify-center gap-3"><RouterLink to="/chapters/new" class="min-h-11 rounded-lg bg-primary-500 px-5 py-3 text-sm text-white">创建第一本日记</RouterLink><button class="min-h-11 rounded-lg border border-primary-200 px-5 py-3 text-sm text-primary-600 disabled:opacity-50 dark:border-primary-800 dark:text-primary-400" :disabled="discovering" @click="discover">从照片发现章节</button></div></div>
      <div v-else class="mt-7 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <article v-for="item in store.items" :key="item.id" class="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
          <RouterLink :to="`/chapters/${item.id}${store.hidden ? '?manage=1' : ''}`" class="block">
            <div class="relative aspect-[1.5] bg-gray-200 dark:bg-gray-700"><img v-if="item.cover_photo_id && !store.hidden" :src="thumbnailUrl(item.cover_photo_id, 'medium')" :alt="item.title" class="h-full w-full object-cover" loading="lazy" /><span v-if="item.status === 'candidate'" class="absolute left-3 top-3 rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-800">系统建议 · 待确认</span><span v-if="item.is_hidden" class="absolute left-3 top-3 rounded-md bg-gray-800 px-2 py-1 text-xs text-white">已隐藏</span></div>
            <div class="p-5"><h2 class="font-serif text-xl text-gray-900 dark:text-white">{{ store.hidden ? '已隐藏的章节' : item.title }}</h2><template v-if="!store.hidden"><p class="mt-2 text-xs text-gray-500 dark:text-gray-400">{{ item.start_date }} — {{ item.end_date || '至今' }}</p><p class="mt-2 text-xs text-gray-500 dark:text-gray-400">{{ item.photo_count }} 张影像 · {{ item.event_count }} 段事件</p><p v-if="item.status === 'candidate' && item.evidence[0]" class="mt-3 line-clamp-2 text-sm text-gray-600 dark:text-gray-300">{{ item.evidence[0].summary }}</p></template><p v-else class="mt-2 text-sm text-primary-600 dark:text-primary-400">查看与管理 →</p></div>
          </RouterLink>
          <div v-if="item.status !== 'confirmed' || item.is_hidden" class="flex justify-end gap-2 border-t border-gray-100 px-4 py-2 text-sm dark:border-gray-700">
            <button v-if="item.status === 'candidate'" class="text-gray-500 dark:text-gray-400" @click="act(item, 'ignore')">忽略</button>
            <button v-if="item.status === 'ignored'" class="text-primary-600 dark:text-primary-400" @click="act(item, 'restore')">恢复建议</button>
            <RouterLink v-if="item.is_hidden" :to="`/chapters/${item.id}?manage=1`" class="text-primary-600 dark:text-primary-400">查看与管理</RouterLink>
            <RouterLink v-if="item.status === 'candidate'" :to="`/chapters/${item.id}`" class="rounded-md bg-primary-500 px-3 py-1.5 text-white">查看依据并确认</RouterLink>
          </div>
        </article>
      </div>
      <div v-if="store.total > store.items.length" class="mt-5 text-center"><button class="rounded-lg border border-gray-200 bg-white px-5 py-2 text-sm text-primary-600 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800 dark:text-primary-400" :disabled="store.loadingMore" @click="more">{{ store.loadingMore ? '正在加载…' : `加载更多（已显示 ${store.items.length} / ${store.total}）` }}</button></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chapterApi } from '@/api/chapter'
import { useChapterStore } from '@/stores/chapterStore'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { ChapterItem, ChapterStatus } from '@/types/chapter'

const store = useChapterStore()
const route = useRoute()
const router = useRouter()
const active = ref<'confirmed' | 'candidate' | 'ignored' | 'hidden'>('confirmed')
const discovering = ref(false)
const loadError = ref(false)
const discoveryTaskId = ref<string | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null
let pollBusy = false
const tabs = [ { key: 'confirmed', name: '我的章节' }, { key: 'candidate', name: '章节建议' }, { key: 'ignored', name: '已忽略' }, { key: 'hidden', name: '已隐藏' } ] as const
async function choose(tab: typeof active.value) {
  active.value = tab
  if (route.query.tab !== tab) void router.replace({ query: { ...route.query, tab } })
  loadError.value = false
  try { await store.load(tab === 'hidden' ? 'confirmed' : tab as ChapterStatus, tab === 'hidden') }
  catch { loadError.value = true; ElMessage.error('加载章节失败') }
}
async function discover() {
  if (discovering.value) return
  discovering.value = true
  try { const task = await chapterApi.discover(); watchDiscovery(task.id); ElMessage.info('正在后台整理照片线索，可离开此页') }
  catch { discovering.value = false; ElMessage.error('启动章节发现失败，请稍后重试') }
}
function stopDiscovery() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  discoveryTaskId.value = null
  discovering.value = false
}
async function pollDiscovery() {
  if (!discoveryTaskId.value || pollBusy) return
  pollBusy = true
  const requestedId = discoveryTaskId.value
  try {
    const task = await chapterApi.discoveryTask(requestedId)
    if (discoveryTaskId.value !== requestedId) return
    if (task.status === 'completed') {
      stopDiscovery()
      ElMessage.success(task.created ? `找到 ${task.created} 条章节建议` : '暂时没有新的章节线索')
      await choose('candidate')
    } else if (task.status === 'failed' || task.status === 'cancelled') {
      stopDiscovery()
      ElMessage.error('章节发现未完成，请重试')
    }
  } catch { if (discoveryTaskId.value === requestedId) { stopDiscovery(); ElMessage.error('查询章节发现状态失败，请刷新重试') } }
  finally { pollBusy = false }
}
function watchDiscovery(id: string) {
  stopDiscovery()
  discoveryTaskId.value = id
  discovering.value = true
  pollTimer = setInterval(() => { void pollDiscovery() }, 2000)
  void pollDiscovery()
}
async function more() {
  try { await store.loadMore() }
  catch { ElMessage.error('加载更多章节失败') }
}
async function act(item: ChapterItem, action: 'confirm' | 'ignore' | 'restore' | 'unhide') {
  try { await chapterApi.action(item.id, action, item.version); await choose(active.value) }
  catch { ElMessage.error('操作失败，请刷新后重试') }
}
onMounted(async () => {
  const tab = tabs.find(item => item.key === route.query.tab)?.key || 'confirmed'
  await choose(tab)
  try { const active = await chapterApi.latestDiscovery(); if (active && !discovering.value) watchDiscovery(active.id) }
  catch { /* The chapter directory remains usable if task status is unavailable. */ }
})
onUnmounted(() => stopDiscovery())
</script>
