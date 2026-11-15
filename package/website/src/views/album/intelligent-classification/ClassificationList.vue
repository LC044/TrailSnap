<template>
  <div class="mx-auto w-full max-w-screen-2xl ts-browse-page classification-list px-[var(--ts-page-gutter)] flex flex-col">
    <!-- Header -->
    <div class="ts-browse-header mb-6 flex items-center gap-3 flex-shrink-0">
      <div class="classification-title-group flex items-center gap-3 w-full md:w-auto">
        <h1 class="ts-page-title text-xl md:text-2xl font-bold text-gray-800 dark:text-white">智能分类</h1>
      </div>
      <button class="ts-button ts-button-secondary ml-auto shrink-0" @click="manageRules = true"><Settings2 class="h-4 w-4" />分类规则</button>
    </div>
    <p v-if="error" class="mb-4 text-sm text-red-600 dark:text-red-400" role="alert">{{ error }} <button class="underline" @click="fetchTags">重试</button></p>

    <div class="flex-1 overflow-y-auto">
      <!-- Loading State -->
      <div v-if="loading" class="ts-album-grid">
        <div v-for="i in 8" :key="i" class="flex flex-col">
          <div class="w-full aspect-square bg-gray-200 dark:bg-gray-800 rounded-xl animate-pulse"></div>
          <div class="mt-3 h-4 bg-gray-200 dark:bg-gray-800 rounded w-2/3 animate-pulse"></div>
          <div class="mt-1 h-3 bg-gray-200 dark:bg-gray-800 rounded w-1/3 animate-pulse"></div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else-if="groupCards.length === 0" class="flex flex-col items-center justify-center h-[50vh] text-gray-500 dark:text-gray-400">
        <div class="p-6 rounded-full bg-gray-100 dark:bg-gray-900 mb-4">
          <Tag class="w-12 h-12 opacity-20" />
        </div>
        <p class="text-lg font-medium">暂无分类信息</p>
        <button class="mt-4 ts-button ts-button-secondary" @click="manageRules = true"><Settings2 class="h-4 w-4" />管理分类规则</button>
      </div>

      <!-- Group cards：只显示大组，进入分组详情页后再选择具体类别 -->
      <div v-else class="ts-album-grid" data-testid="classification-group-grid">
        <button
          v-for="group in groupCards"
          :key="group.name"
          type="button"
          class="group cursor-pointer flex flex-col rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 text-left"
          :data-testid="`classification-group-${group.name}`"
          @click="goToGroup(group.name)"
          @keydown.enter="goToGroup(group.name)"
        >
          <div class="relative w-full aspect-square rounded-xl overflow-hidden bg-gray-100 dark:bg-gray-800 shadow-sm group-hover:shadow-md transition-all duration-300">
             <img
               v-if="group.cover"
               :src="mapPhotoToImage(group.cover).thumbnail"
               class="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-500"
               loading="lazy"
               :alt="group.name"
             />
             <div v-else class="w-full h-full flex items-center justify-center text-gray-300 dark:text-gray-600">
               <Tag class="w-12 h-12" />
             </div>

             <!-- Overlay -->
             <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors"></div>
          </div>

          <div class="mt-2.5 px-1">
            <h3 class="ts-card-title font-semibold text-gray-900 dark:text-white truncate" :title="group.name">
              {{ group.name }}
            </h3>
            <p class="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              {{ group.categories.length }} 个类别 · {{ group.count }} 个项目
            </p>
          </div>
        </button>
      </div>
    </div>
    <ClipCategoryManager v-model="manageRules" @updated="fetchTags" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { classificationService, clipClassificationService, type TagStats, type ClipCategory } from '@/api/classification'
import { mapPhotoToImage } from '@/stores/photoStore'
import { Tag, Settings2 } from 'lucide-vue-next'
import ClipCategoryManager from '@/components/ClipCategoryManager.vue'

const YOLO_GROUP = 'YOLO / 自定义分类'

const router = useRouter()
const tags = ref<TagStats[]>([])
const loading = ref(true)
const manageRules = ref(false)
const error = ref('')
const groups = ref<string[]>([])
const categories = ref<ClipCategory[]>([])

const groupCards = computed(() => {
  if (!tags.value.length && !categories.value.length) return []
  const tagMap = new Map(tags.value.map(t => [t.id, t]))
  const result: { name: string; categories: { id: string }[]; count: number; cover: TagStats['cover'] }[] = []
  for (const name of groups.value) {
    const items = categories.value.filter(c => c.groups.includes(name))
    if (!items.length) continue
    const total = items.reduce((sum, c) => sum + c.count, 0)
    if (total === 0) continue
    const coverTag = items.map(c => tagMap.get(c.tag_id)).find(t => t && t.count > 0 && t.cover)
    result.push({ name, categories: items, count: total, cover: coverTag?.cover ?? null })
  }
  const clipTagIds = new Set(categories.value.map(c => c.tag_id))
  const others = tags.value.filter(t => !clipTagIds.has(t.id))
  if (others.length) {
    result.push({
      name: YOLO_GROUP,
      categories: others,
      count: others.reduce((sum, t) => sum + t.count, 0),
      cover: others.find(t => t.cover)?.cover ?? null,
    })
  }
  return result
})

const fetchTags = async () => {
  loading.value = true
  error.value = ''
  try {
    const [tagResult, categoryResult] = await Promise.allSettled([
      classificationService.getTags(),
      clipClassificationService.list(),
    ])
    if (tagResult.status === 'rejected') throw tagResult.reason
    tags.value = tagResult.value
    if (categoryResult.status === 'fulfilled') {
      const data = categoryResult.value
      groups.value = Array.isArray(data?.groups) ? data.groups : []
      categories.value = Array.isArray(data?.categories) ? data.categories : []
    } else { error.value = '分类分组暂不可用，仍可浏览已有标签。' }
  } catch (e) {
    error.value = '分类加载失败，请重试。'
  } finally {
    loading.value = false
  }
}

const goToGroup = (name: string) => {
  router.push({
    name: 'ClassificationGroup',
    params: { group: name }
  })
}

onMounted(() => {
  fetchTags()
})
</script>

<style scoped>
/* 移动端标题组：与位置相册一致，去掉胶囊背景（LocationList.vue .location-title-group 同款） */
.classification-title-group {
  gap: 6px;
  padding: 0;
  border-color: transparent;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}
.classification-back-btn {
  padding: 8px;
  background: transparent;
}
.classification-title-group button { padding: 8px; background: transparent !important; }
</style>
