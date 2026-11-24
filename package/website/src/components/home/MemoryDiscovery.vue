<template>
  <section v-if="items.length" class="lm-discovery" aria-labelledby="lm-discovery-title">
    <div class="lm-section-head">
      <div>
        <p class="lm-eyebrow">待确认</p>
        <h2 id="lm-discovery-title" class="lm-title">发现新的记忆</h2>
      </div>
      <RouterLink to="/memories" class="lm-more">全部查看 <ArrowRight /></RouterLink>
    </div>
    <div class="lm-discovery-rail">
      <RouterLink
        v-for="memory in items"
        :key="memory.id"
        :to="`/memories/${memory.id}`"
        class="lm-discovery-card"
      >
        <span class="lm-frame lm-discovery-cover">
          <img v-if="memory.cover_photo_id" :src="thumbnailUrl(memory.cover_photo_id, 'small')" :alt="memory.title" loading="lazy" />
          <span v-else class="lm-discovery-blank"><Sparkles class="h-5 w-5" /></span>
          <span class="lm-discovery-badge">{{ memory.photo_count }} 帧</span>
        </span>
        <span class="lm-discovery-copy">
          <strong>{{ memory.title }}</strong>
          <span v-if="memory.places[0]">{{ memory.places[0].name }}</span>
          <span v-else>{{ total }} 段经历等待你确认</span>
        </span>
      </RouterLink>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowRight, Sparkles } from 'lucide-vue-next'
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