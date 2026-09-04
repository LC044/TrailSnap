<template>
  <div class="location-timeline h-full w-full dark:bg-gray-900 overflow-y-auto custom-scrollbar transition-colors duration-300" @scroll="handleScroll">
    <div class="max-w-4xl mx-auto p-4 md:p-8 pb-20 relative">
      <div v-if="loading && !loadingMore" class="flex justify-center items-center py-20">
        <div class="animate-spin rounded-full h-10 w-10 border-4 border-primary-500 border-t-transparent"></div>
      </div>
      
      <div v-else-if="!timelineNodes.length && !loading" class="flex flex-col items-center justify-center py-20 text-gray-400">
        <Map class="w-16 h-16 mb-4 text-gray-300 dark:text-gray-600" />
        <p>暂无地理位置足迹</p>
      </div>
      
      <div v-else class="relative">
        <!-- Vertical Line for all devices (left side) -->
        <div class="absolute left-6 md:left-64 top-4 bottom-0 border-l border-dashed border-gray-300 dark:border-gray-700 w-0 z-0"></div>

        <div v-for="group in groupedNodes" :key="group.id" class="mb-8">
          <!-- Month/Year Header -->
          <div 
            class="flex items-center gap-4 mb-8 cursor-pointer group/header dark:bg-gray-900/90 backdrop-blur-md z-20 py-4 transition-colors duration-300"
            @click="toggleMonth(group.id)"
          >
            <!-- Node dot for header -->
            <div class="absolute left-6 md:left-64 -translate-x-1/2 w-3 h-3 rounded-full border-[1.5px] border-gray-400 bg-[#fcfcfc] dark:bg-[#1a1a1a] z-20"></div>

            <div class="ml-12 md:ml-0 md:pl-72 flex items-center gap-3">
              <h2 class="text-xl font-medium text-gray-600 dark:text-gray-400 tracking-wide">{{ group.label }}</h2>
              <span class="text-xs text-gray-400 dark:text-gray-500 bg-gray-200/50 dark:bg-gray-800/50 px-2 py-0.5 rounded-full">{{ group.nodes.length }} 记录</span>
              <ChevronDown 
                class="w-4 h-4 text-gray-400 transition-transform duration-500 ease-in-out"
                :class="{ '-rotate-90': collapsedMonths[group.id] }"
              />
            </div>
          </div>

          <transition
            enter-active-class="transition-all duration-500 ease-out overflow-hidden"
            enter-from-class="opacity-0 max-h-0"
            enter-to-class="opacity-100 max-h-[5000px]"
            leave-active-class="transition-all duration-500 ease-in overflow-hidden"
            leave-from-class="opacity-100 max-h-[5000px]"
            leave-to-class="opacity-0 max-h-0"
          >
            <div v-show="!collapsedMonths[group.id]" class="space-y-8 mt-4">
              <div v-for="(node, nodeIdx) in group.nodes" :key="nodeIdx" class="relative group timeline-item">

                <div class="flex flex-row relative z-10 w-full">
                  <!-- Node Dot for Item -->
                  <div class="absolute left-6 md:left-64 top-2 -translate-x-1/2 w-2 h-2 rounded-full border-[1.5px] border-gray-400 dark:border-gray-500 bg-[#fcfcfc] dark:bg-[#1a1a1a] group-hover:border-primary-400 group-hover:bg-primary-50 transition-colors duration-300 shadow-[0_0_0_4px_#fcfcfc] dark:shadow-[0_0_0_4px_#1a1a1a]"></div>

                  <div class="flex w-full ml-12 md:ml-0 flex-row">
                    
                    <!-- Left Side: Date & Location -->
                    <div class="w-24 md:w-64 flex-shrink-0 flex flex-col md:pr-8 items-start md:items-end pt-0.5">
                      <span class="text-sm md:text-base font-medium text-primary-600 dark:text-primary-400 tracking-wide">{{ formatNodeDate(node.startDate) }}</span>
                      <div class="mt-1 md:mt-1.5 group/location inline-flex items-start md:items-center justify-start md:justify-end gap-1 cursor-default hover:-translate-y-0.5 transition-transform duration-300 w-full">
                        <MapPin :class="['w-3 h-3 md:w-3.5 md:h-3.5 group-hover/location:text-primary-500 transition-colors flex-shrink-0 mt-0.5 md:mt-0', node.level === 'scene' ? 'text-red-600' : 'text-gray-400 dark:text-gray-500']"  />
                        <span class="text-xs md:text-sm font-medium text-gray-700 dark:text-gray-300 group-hover/location:text-primary-600 dark:group-hover/location:text-primary-400 transition-colors text-left md:text-right break-words">{{ node.locationName }}</span>
                      </div>
                    </div>

                    <!-- Right Side: Photos -->
                    <div class="flex-1 ml-4 md:ml-8 mt-0">
                      <div class="flex pr-4 md:pr-0">
                        <!-- Show cover photo -->
                        <div 
                          v-if="node.coverId"
                          class="w-16 h-16 flex-shrink-0 rounded-lg md:rounded-xl overflow-hidden bg-gray-100 dark:bg-gray-800 relative cursor-pointer group/more shadow-sm hover:shadow-md transition-all duration-500"
                          @click="goToLocationDetail(node)"
                        >
                          <img 
                            :src="getThumbnailUrl(node.coverId)" 
                            class="w-full h-full object-cover transition-transform duration-700 ease-out group-hover/more:scale-[1.03]"
                            loading="lazy"
                          />
                          <!-- More photos indicator -->
                          <div 
                            v-if="node.photoCount > 1"
                            class="absolute inset-0 bg-black/20 opacity-0 group-hover/more:opacity-100 transition-opacity duration-300 flex items-center justify-center"
                          >
                            <span class="text-white font-medium text-md tracking-wider">+{{ node.photoCount - 1 }}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </transition>
        </div>
      </div>
      
      <!-- Loading More Indicator -->
      <div v-if="loadingMore" class="flex justify-center items-center py-8">
        <div class="animate-spin rounded-full h-6 w-6 border-2 border-primary-400 border-t-transparent"></div>
      </div>
      <div v-if="!hasMore && timelineNodes.length > 0" class="text-center text-gray-400 py-8 text-xs tracking-widest">
        · 已经到底啦 ·
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { MapPin, Map, Plane, ChevronDown, ChevronRight } from 'lucide-vue-next'
import { locationService } from '@/api/location'
import type { TimelineNode } from '@/types/location'
import type { Photo } from '@/types/album'
import { toServerUrl } from '@/config/server'
import { thumbnailUrl } from '@/utils/mediaUrl'

const props = defineProps<{
  startDate?: string
  endDate?: string
  level: string
}>()

const emit = defineEmits<{
  (e: 'click-photo', photo: Photo, contextPhotos: Photo[]): void
}>()

const router = useRouter()

const loading = ref(false)
const loadingMore = ref(false)
const hasMore = ref(true)
const skip = ref(0)
const limit = 100

const timelineNodes = ref<TimelineNode[]>([])
const collapsedMonths = ref<Record<string, boolean>>({})

interface MonthGroup {
  id: string
  label: string
  nodes: TimelineNode[]
}

const groupedNodes = computed(() => {
  const groups: MonthGroup[] = []
  let currentGroup: MonthGroup | null = null

  timelineNodes.value.forEach((node, index) => {
    const dateStr = node.endDate
    const date = new Date(dateStr)
    const monthId = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}`
    const monthLabel = `${date.getFullYear()} · ${(date.getMonth() + 1).toString().padStart(2, '0')}`

    if (!currentGroup || currentGroup.id !== monthId) {
      currentGroup = {
        id: monthId,
        label: monthLabel,
        nodes: []
      }
      groups.push(currentGroup)
    }
    currentGroup.nodes.push(node)
  })

  return groups
})

const fetchTimelineData = async (isLoadMore = false) => {
  if (loading.value || loadingMore.value || (!hasMore.value && isLoadMore)) return

  if (isLoadMore) {
    loadingMore.value = true
  } else {
    loading.value = true
    skip.value = 0
    hasMore.value = true
  }

  try {
    const res = await locationService.getTimelineNodes(skip.value, limit, props.startDate, props.endDate, props.level)
    const newNodes = res.nodes
    
    if (newNodes.length < limit) {
      hasMore.value = false
    }

    if (isLoadMore) {
      timelineNodes.value.push(...newNodes)
    } else {
      timelineNodes.value = newNodes
      collapsedMonths.value = {}
    }

    skip.value += limit
  } catch (e) {
    console.error('Failed to fetch timeline nodes', e)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

const handleScroll = (e: Event) => {
  const target = e.target as HTMLElement
  if (target.scrollHeight - target.scrollTop <= target.clientHeight + 200) {
    fetchTimelineData(true)
  }
}

const toggleMonth = (monthId: string) => {
  collapsedMonths.value[monthId] = !collapsedMonths.value[monthId]
}

const formatNodeDate = (dateStr: string) => {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return `${date.getFullYear()}.${(date.getMonth() + 1).toString().padStart(2, '0')}.${date.getDate().toString().padStart(2, '0')}`;
}

const getThumbnailUrl = (photoId: string) => {
  // console.log(photoId)
  return thumbnailUrl(photoId)
}

const goToLocationDetail = (node: TimelineNode) => {
  router.push({
    name: 'LocationDetail',
    params: { name: node.locationName },
    query: { 
      level: node.level || 'city', 
      startDate: node.startDate,
      endDate: node.endDate
    }
  })
}

watch([() => props.startDate, () => props.endDate, () => props.level], () => {
  fetchTimelineData()
})

onMounted(() => {
  fetchTimelineData()
})
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.5);
  border-radius: 20px;
}
.dark .custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(75, 85, 99, 0.5);
}
</style>
