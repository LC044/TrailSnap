<template>
  <section v-if="items.length" class="mx-4 rounded-2xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-800">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="flex items-center gap-2 font-bold text-gray-900 dark:text-white"><Sparkles class="h-4 w-4 text-amber-500" />发现新的记忆</h2>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">有 {{ total }} 段经历等待你确认</p>
      </div>
      <RouterLink to="/memories" class="rounded-lg px-2 py-1 text-sm text-primary-600 hover:bg-primary-50 dark:text-primary-400 dark:hover:bg-primary-900/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500">全部查看</RouterLink>
    </div>
    <div class="memory-scrollbar mt-4 flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1">
      <RouterLink
        v-for="memory in items"
        :key="memory.id"
        :to="`/memories/${memory.id}`"
        class="min-w-[230px] flex-1 snap-start overflow-hidden rounded-xl border border-gray-200 bg-gray-50 transition hover:border-primary-300 hover:shadow-sm dark:border-gray-700 dark:bg-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
      >
        <img v-if="memory.cover_photo_id" :src="thumbnailUrl(memory.cover_photo_id, 'small')" :alt="memory.title" class="h-28 w-full object-cover" loading="lazy" />
        <div class="p-3">
          <h3 class="line-clamp-1 text-sm font-semibold text-gray-900 dark:text-white">{{ memory.title }}</h3>
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ memory.photo_count }} 张照片<span v-if="memory.places[0]"> · {{ memory.places[0].name }}</span></p>
        </div>
      </RouterLink>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Sparkles } from 'lucide-vue-next'
import { memoryApi } from '@/api/memory'
import type { MemoryItem } from '@/types/memory'
import { thumbnailUrl } from '@/utils/mediaUrl'

const items = ref<MemoryItem[]>([])
const total = ref(0)

onMounted(async () => {
  try {
    const data = await memoryApi.list('candidate', 0, 3)
    items.value = data.items
    total.value = data.total
  } catch {
    // 首页模块是增强内容，失败时静默隐藏，不影响首页主数据。
  }
})
</script>

<style scoped>
.memory-scrollbar {
  scrollbar-width: none;
}

.memory-scrollbar::-webkit-scrollbar {
  display: none;
}
</style>
