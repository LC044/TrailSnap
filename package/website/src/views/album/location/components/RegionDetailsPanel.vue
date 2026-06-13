<template>
  <div class="space-y-4 animate-fade-in">
    <div class="flex items-center justify-between">
      <h2 class="text-xl font-bold text-gray-800 dark:text-white flex items-center gap-2">
        <MapPin class="w-5 h-5 text-primary-500" />
        {{ selectedRegion }}
      </h2>
      <button @click="emit('clear-selection')" class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors">
        <X class="w-5 h-5" />
      </button>
    </div>
    
    <div class="grid grid-cols-2 gap-3">
      <div class="bg-gray-50 dark:bg-gray-800/50 p-3 rounded-xl border border-gray-100 dark:border-gray-700/50">
        <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">照片数量</div>
        <div class="text-xl font-semibold text-gray-800 dark:text-white">{{ selectedRegionCount }}</div>
      </div>
      <div v-if="regionFirstVisit" class="bg-gray-50 dark:bg-gray-800/50 p-3 rounded-xl border border-gray-100 dark:border-gray-700/50">
        <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">首次点亮</div>
        <div class="text-sm font-semibold text-gray-800 dark:text-white mt-1">{{ regionFirstVisit }}</div>
      </div>
    </div>

    <!-- 时间跨度 & 标签 -->
    <div v-if="regionTimeSpan || regionTags.length > 0" class="flex flex-col gap-2 mt-2">
      <div v-if="regionTimeSpan" class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
        <Calendar class="w-3.5 h-3.5" />
        时间跨度: {{ regionTimeSpan }}
      </div>
      <div v-if="regionTags.length > 0" class="flex flex-wrap gap-2">
        <span v-for="tag in regionTags" :key="tag.name" class="px-2.5 py-1 bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 rounded-lg text-xs font-medium border border-primary-100 dark:border-primary-800/30">
          #{{ tag.name }}
        </span>
      </div>
    </div>

    <!-- 区域探索进度 -->
    <div v-if="regionSubLevel && regionTotalCount > 0" class="mt-4 bg-gradient-to-r from-primary-50 to-primary-100 dark:from-primary-900/20 dark:to-primary-900/10 p-4 rounded-xl border border-primary-100 dark:border-primary-800/30">
      <div class="flex justify-between items-end mb-2">
        <div>
          <div class="text-sm font-bold text-gray-800 dark:text-gray-200">{{ selectedRegion }}探索进度</div>
          <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">已点亮 {{ regionExploredCount }} / {{ regionTotalCount }} 个{{ regionSubLevel === 'city' ? '城市' : '区县' }}</div>
        </div>
        <div class="text-lg font-black text-primary-600 dark:text-primary-400">
          {{ regionTotalCount > 0 ? Math.round((regionExploredCount / regionTotalCount) * 100) : 0 }}%
        </div>
      </div>
      <div class="h-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden shadow-inner">
        <div class="h-full rounded-full transition-all duration-1000" :style="{ width: `${regionTotalCount > 0 ? (regionExploredCount / regionTotalCount) * 100 : 0}%`, backgroundColor: currentTheme.primary }"></div>
      </div>
    </div>

    <!-- 区域热门打卡地 -->
    <div v-if="regionSubLevel" class="mt-4">
      <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
        <Trophy class="w-4 h-4 text-yellow-500" /> 热门打卡地
      </h3>
      <div v-if="regionTopSubRegions.length > 0" class="space-y-3">
        <div v-for="(item, index) in regionTopSubRegions" :key="item.name" class="flex items-center gap-3 cursor-pointer group" @click="emit('click-location', item.name, regionSubLevel)">
          <div class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
               :class="index === 0 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-500' :
                       index === 1 ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' :
                       index === 2 ? 'bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-500' :
                       'bg-gray-50 text-gray-500 dark:bg-gray-800/50 dark:text-gray-500'">
            {{ index + 1 }}
          </div>
          <div class="flex-1">
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-700 dark:text-gray-200 group-hover:text-primary-500 transition-colors">{{ item.name }}</span>
              <span class="text-gray-500 dark:text-gray-400">{{ item.count }} 张</span>
            </div>
            <div class="h-1.5 w-full bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all duration-1000"
                   :style="{
                     width: `${(item.count / regionTopSubRegions[0].count) * 100}%`,
                     backgroundColor: currentTheme.primary
                   }">
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="py-2">
        <el-empty description="这里还是一片未知领域，快去探索吧！" :image-size="60" />
      </div>
    </div>

    <!-- 区域最近去过 -->
    <div v-if="regionSubLevel" class="mt-4">
      <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
        <MapPin class="w-4 h-4 text-primary-500" /> 最近去过
      </h3>
      <div v-if="regionRecentVisits.length > 0" class="space-y-2">
        <div v-for="(trip, index) in regionRecentVisits" :key="index" class="flex items-center justify-between bg-white dark:bg-gray-800/50 p-3 rounded-xl border border-gray-100 dark:border-gray-700/50 hover:border-primary-200 dark:hover:border-primary-800/50 cursor-pointer transition-colors" @click="emit('click-location', trip.locationName, regionSubLevel)">
          <div class="flex flex-col">
            <span class="text-sm font-medium text-gray-800 dark:text-white">{{ trip.locationName }}</span>
            <span class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ trip.startDate }}</span>
          </div>
          <div class="flex items-center gap-1.5 text-xs text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20 px-2 py-1 rounded-md">
            <Images class="w-3 h-3" />
            {{ trip.photoCount }}
          </div>
        </div>
      </div>
      <div v-else class="py-2">
        <el-empty description="暂无最近访问记录" :image-size="60" />
      </div>
    </div>

    <!-- 下钻地图按钮 -->
    <div v-if="level === 'province' || level === 'city'" class="pt-2">
      <button @click="emit('change-level', level === 'province' ? 'city' : 'district', { zoom: 0.9, center: [], parentRegion: selectedRegion })" class="w-full py-2.5 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors flex items-center justify-center gap-1.5">
        进入{{ level === 'province' ? '城市' : '区县' }}地图
        <ChevronRight class="w-4 h-4" />
      </button>
    </div>

    <!-- 照片预览墙 -->
    <div v-if="regionPhotos.length > 0" class="space-y-2">
      <div class="flex items-center justify-between">
        <span class="text-sm font-medium text-gray-700 dark:text-gray-300">精彩瞬间</span>
        <button @click="emit('click-location', selectedRegion, undefined)" class="px-3 py-1.5 rounded-lg bg-primary-50 hover:bg-primary-100 dark:bg-primary-900/20 dark:hover:bg-primary-900/40 text-xs text-primary-600 dark:text-primary-400 transition-colors flex items-center gap-1">
          查看全部 <ChevronRight class="w-3.5 h-3.5" />
        </button>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <div 
          v-for="(photo, index) in regionPhotos" 
          :key="photo.id"
          class="aspect-square rounded-lg overflow-hidden group relative shadow-sm"
        >
          <el-image 
            :src="photo.thumbnail || photo.url" 
            :preview-src-list="regionPhotos.map(p => p.url)"
            :initial-index="index"
            fit="cover"
            preview-teleported
            lazy
            class="w-full h-full transition-transform duration-500 group-hover:scale-110 cursor-pointer preview-dark-aware" 
          />
          <div class="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"></div>
        </div>
      </div>
    </div>
    <div v-else class="text-center py-6 text-gray-400 text-sm">
      暂无照片预览
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'
import { MapPin, X, ChevronRight, Trophy, Images, Calendar } from 'lucide-vue-next'
import type { AlbumImage } from '@/types/album'
import type { TimelineNode } from '@/types/location'

const props = defineProps<{
  level: string
  selectedRegion: string
  selectedRegionCount: number
  regionPhotos: AlbumImage[]
  regionTimeSpan: string
  regionFirstVisit: string
  regionTags: {name: string, count: number}[]
  regionSubLevel: string
  regionExploredCount: number
  regionTotalCount: number
  regionTopSubRegions: { name: string, count: number }[]
  regionRecentVisits: TimelineNode[]
}>()

const emit = defineEmits<{
  (e: 'clear-selection'): void
  (e: 'click-location', name: string, level?: string): void
  (e: 'change-level', level: string, viewState: { zoom: number, center: number[], parentRegion?: string }): void
}>()

const { currentTheme } = useTheme()
</script>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(5px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 适配 Element Plus 图片预览的深色模式 */
:deep(.el-image-viewer__wrapper) {
  .el-image-viewer__btn {
    color: white;
    background-color: rgba(0, 0, 0, 0.5);
    border-color: rgba(255, 255, 255, 0.2);
    
    &:hover {
      background-color: rgba(0, 0, 0, 0.8);
    }
  }
}

html.dark {
  .el-image-viewer__wrapper {
    .el-image-viewer__btn {
      color: #e5e7eb;
      background-color: rgba(31, 41, 55, 0.6);
      border-color: rgba(75, 85, 99, 0.4);
      
      &:hover {
        background-color: rgba(31, 41, 55, 0.9);
      }
    }
    .el-image-viewer__mask {
      background: rgba(15, 23, 42, 0.9);
    }
  }
}
</style>
