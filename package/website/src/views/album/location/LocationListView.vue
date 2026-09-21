<template>
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
    <div v-else-if="locations.length === 0" class="flex flex-col items-center justify-center h-[50vh] text-gray-500">
      <div class="p-6 rounded-full bg-gray-100 dark:bg-gray-900 mb-4">
        <MapPin class="w-12 h-12 opacity-20" />
      </div>
      <p class="text-lg font-medium">暂无位置信息</p>
    </div>

    <!-- Content Grid -->
    <div v-else class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-12 gap-6">
      <div
        v-for="loc in locations"
        :key="loc.id || loc.name"
        class="group cursor-pointer flex flex-col"
        @click="$emit('click', loc.name, undefined, loc.id)"
      >
        <div class="relative w-full aspect-square rounded-xl overflow-hidden bg-gray-100 dark:bg-gray-800 shadow-sm group-hover:shadow-md transition-all duration-300">
           <div class="absolute top-2 right-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
              <button
                 v-if="level === 'scene' && loc.id"
                 @click.stop="$emit('edit', loc)"
                 class="p-1.5 bg-white/90 rounded-full shadow-sm hover:bg-white transition-all text-gray-600 hover:text-primary-500"
                 title="编辑景区"
              >
                 <Pencil class="w-4 h-4" />
              </button>
              <button
                 v-if="level === 'scene' && loc.id"
                 @click.stop="$emit('delete', loc)"
                 class="p-1.5 bg-white/90 rounded-full shadow-sm hover:bg-white transition-all text-gray-600 hover:text-red-500"
                 title="删除景区"
              >
                 <Trash2 class="w-4 h-4" />
              </button>
           </div>
           <img
             v-if="loc.cover"
             :src="mapPhotoToImage(loc.cover).thumbnail"
             class="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-500"
             loading="lazy"
           />
           <div v-else class="w-full h-full flex items-center justify-center text-gray-300 dark:text-gray-600">
             <MapPin class="w-12 h-12" />
           </div>
           
           <!-- Overlay -->
           <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors"></div>
        </div>

        <div class="mt-2.5 px-1">
          <h3 class="font-semibold text-sm text-gray-900 dark:text-white truncate" :title="loc.name">
            {{ loc.name }}
          </h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {{ loc.count }} 个项目
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { MapPin, Pencil, Trash2 } from 'lucide-vue-next'
import { mapPhotoToImage } from '@/stores/photoStore'
import type { Location } from '@/types/location'

defineProps<{
  locations: Location[]
  loading: boolean
  level: string
}>()

defineEmits<{
  (e: 'click', name: string): void
  (e: 'edit', loc: Location): void
  (e: 'delete', loc: Location): void
}>()
</script>
