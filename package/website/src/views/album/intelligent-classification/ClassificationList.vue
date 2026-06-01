<template>
  <div class="container mx-auto classification-list py-6 px-4 flex flex-col">
    <!-- Header -->
    <div class="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 flex-shrink-0">
      <div class="flex items-center gap-3 w-full md:w-auto bg-white/80 dark:bg-gray-900/80 backdrop-blur-md px-3 py-1.5 rounded-full shadow-sm border border-gray-200/50 dark:border-gray-700/50">
        <button @click="router.back()" class="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors bg-white dark:bg-gray-900">
          <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
        </button>
        <h1 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">智能分类</h1>
      </div>
    </div>

    <!-- Grid View -->
    <div class="flex-1 overflow-y-auto">
      <!-- Loading State -->
      <div v-if="loading" class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-12 gap-6">
        <div v-for="i in 10" :key="i" class="flex flex-col">
          <div class="w-full aspect-square bg-gray-200 dark:bg-gray-800 rounded-xl animate-pulse"></div>
          <div class="mt-3 h-4 bg-gray-200 dark:bg-gray-800 rounded w-2/3 animate-pulse"></div>
          <div class="mt-1 h-3 bg-gray-200 dark:bg-gray-800 rounded w-1/3 animate-pulse"></div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else-if="tags.length === 0" class="flex flex-col items-center justify-center h-[50vh] text-gray-500">
        <div class="p-6 rounded-full bg-gray-100 dark:bg-gray-900 mb-4">
          <Tag class="w-12 h-12 opacity-20" />
        </div>
        <p class="text-lg font-medium">暂无分类信息</p>
      </div>

      <!-- Content Grid -->
      <div v-else class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-12 gap-6">
        <div
          v-for="tag in tags"
          :key="tag.id"
          class="group cursor-pointer flex flex-col"
          @click="goToTag(tag.tag_name)"
        >
          <div class="relative w-full aspect-square rounded-xl overflow-hidden bg-gray-100 dark:bg-gray-800 shadow-sm group-hover:shadow-md transition-all duration-300">
             <img
               v-if="tag.cover"
               :src="mapPhotoToImage(tag.cover).thumbnail"
               class="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-500"
               loading="lazy"
             />
             <div v-else class="w-full h-full flex items-center justify-center text-gray-300 dark:text-gray-600">
               <Tag class="w-12 h-12" />
             </div>
             
             <!-- Overlay -->
             <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors"></div>
          </div>

          <div class="mt-2.5 px-1">
            <h3 class="font-semibold text-gray-900 dark:text-white truncate" :title="tag.tag_name">
              {{ tag.tag_name }}
            </h3>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {{ tag.count }} 个项目
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { classificationService, type TagStats } from '@/api/classification'
import { mapPhotoToImage } from '@/stores/photoStore'
import { ArrowLeft, Tag } from 'lucide-vue-next'

const router = useRouter()
const tags = ref<TagStats[]>([])
const loading = ref(true)

const fetchTags = async () => {
  loading.value = true
  try {
    tags.value = await classificationService.getTags()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const goToTag = (name: string) => {
  router.push({
    name: 'ClassificationDetail',
    params: { name: name }
  })
}

onMounted(() => {
  fetchTags()
})
</script>
