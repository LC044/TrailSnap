<template>
  <div class="flex min-w-0 items-center gap-2 px-1" :class="scrolled || overlay ? 'text-white' : 'text-gray-900 dark:text-white'" data-testid="album-detail-title" :data-scrolled="scrolled">
    <button type="button" class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full backdrop-blur-sm transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :class="scrolled ? 'bg-black/60' : overlay ? 'bg-black/35' : 'hover:bg-white dark:hover:bg-gray-800'" :aria-label="backLabel" @click="$emit('back')">
      <ArrowLeft class="h-5 w-5" />
    </button>
    <span v-if="scrolled || overlay" :title="title" class="truncate rounded-full px-3 py-1.5 text-sm font-semibold backdrop-blur-sm transition-colors duration-200 sm:text-base" :class="scrolled ? 'bg-black/60' : 'bg-black/25'">{{ title }}</span>
    <div v-else class="min-w-0 pr-2">
      <h1 :title="title" class="truncate text-sm font-bold leading-tight md:text-lg">{{ title }}</h1>
      <p v-if="subtitle" class="truncate text-xs text-gray-500 dark:text-gray-400">{{ subtitle }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'

defineProps<{ title: string; backLabel: string; scrolled: boolean; overlay?: boolean; subtitle?: string }>()
defineEmits<{ (event: 'back'): void }>()
</script>
