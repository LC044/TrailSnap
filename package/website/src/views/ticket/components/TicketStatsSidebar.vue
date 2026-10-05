<template>
  <aside class="w-full xl:w-[320px] shrink-0 space-y-4">
    <div class="hidden md:block lg:hidden mb-4">
      <input
        :value="searchQuery"
        @input="handleSearchInput"
        type="text"
        placeholder="搜索车票 / 乘车人..."
        class="ts-input w-full"
      />
    </div>

    <div class="grid grid-cols-3 xl:grid-cols-1 gap-2 sm:gap-4">
      <StatsCard 
        compact
        label="点击查看足迹地图" 
        :icon="MapPin" 
        clickable 
        @click="$emit('show-city-modal')"
      >
        <template #value>
          <span class="text-3xl font-bold text-slate-800 dark:text-white">{{ uniqueCities.length }}</span>
          <span class="text-xs text-slate-500 dark:text-slate-400">座城市</span>
        </template>
      </StatsCard>

      <StatsCard compact label="总时长" :icon="Clock">
        <template #value>
          <div v-if="loading && tickets.length > 0 && !statsMap" class="flex items-center gap-2">
            <div class="w-4 h-4 border-2 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
            <span class="text-sm text-slate-400">计算中...</span>
          </div>
          <div v-else>
            <span class="text-3xl font-bold text-slate-800 dark:text-white">{{ totalDuration.hours }}<span class="text-sm font-normal text-slate-500 ml-0.5">小时</span></span>
            <span class="text-lg font-semibold text-slate-600 dark:text-slate-300">{{ totalDuration.minutes }}<span class="text-xs font-normal text-slate-500 ml-0.5">分钟</span></span>
          </div>
        </template>
      </StatsCard>

      <StatsCard compact label="总里程" :icon="Route">
        <template #value>
          <div v-if="loading && tickets.length > 0 && !statsMap" class="flex items-center gap-2">
            <div class="w-4 h-4 border-2 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
            <span class="text-sm text-slate-400">计算中...</span>
          </div>
          <div v-else>
            <span class="text-3xl font-bold text-slate-800 dark:text-white">{{ totalDistance.toLocaleString() }}</span>
            <span class="text-xs text-slate-500 dark:text-slate-400">km</span>
          </div>
        </template>
      </StatsCard>
    </div>

    <details class="ts-surface p-4" :open="wide">
      <summary class="min-h-11 text-sm font-semibold cursor-pointer flex items-center gap-2">
        <User class="w-4 h-4 text-primary-600 dark:text-primary-400" />
        乘车人筛选
      </summary>
      <div class="mt-3 flex flex-wrap gap-2 max-h-[200px] overflow-y-auto">
        <button
          type="button"
          v-for="passenger in uniquePassengers" 
          :key="passenger"
          @click="$emit('filter-by-passenger', passenger)"
          class="ts-button ts-button-sm ts-button-ghost"
          :aria-pressed="selectedPassenger === passenger"
          :class="selectedPassenger === passenger ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400' : ''"
        >
          {{ passenger }}
        </button>
        <button
          type="button"
          @click="$emit('clear-passenger-filter')"
          class="ts-button ts-button-sm ts-button-secondary"
        >
          全部
        </button>
      </div>
    </details>
  </aside>
</template>

<script setup lang="ts">
import { MapPin, Clock, Route, User } from 'lucide-vue-next';
import StatsCard from '@/components/StatsCard.vue';
import { useMediaQuery } from '@vueuse/core';
const wide = useMediaQuery('(min-width: 1280px)');

defineProps<{
  searchQuery: string;
  uniqueCities: string[];
  totalDuration: { hours: number; minutes: number };
  totalDistance: number;
  uniquePassengers: string[];
  selectedPassenger: string;
  loading: boolean;
  tickets: any[];
  statsMap: any;
}>();

const emit = defineEmits<{
  (e: 'update:searchQuery', value: string): void;
  (e: 'show-city-modal'): void;
  (e: 'filter-by-passenger', passenger: string): void;
  (e: 'clear-passenger-filter'): void;
}>();

const handleSearchInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit('update:searchQuery', target.value);
};
</script>
