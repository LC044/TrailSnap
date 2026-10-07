<template>
  <div class="flex min-w-0 items-center gap-2 px-1" :class="scrolled || overlay ? 'text-white' : 'text-gray-900 dark:text-white'" data-testid="album-detail-title" :data-scrolled="scrolled">
    <BackButton :label="backLabel" @click="$emit('back')" />
    <span v-if="scrolled || overlay" :title="title" class="truncate rounded-full px-3 py-1.5 text-sm font-semibold backdrop-blur-sm transition-colors duration-200 sm:text-base" :class="scrolled ? 'bg-black/60' : 'bg-black/25'">{{ title }}</span>
    <div v-else class="min-w-0 pr-2">
      <h1 :title="title" class="truncate text-sm font-bold leading-tight md:text-lg">{{ title }}</h1>
      <p v-if="subtitle" class="truncate text-xs text-gray-500 dark:text-gray-400">{{ subtitle }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'

defineProps<{ title: string; backLabel: string; scrolled: boolean; overlay?: boolean; subtitle?: string }>()
defineEmits<{ (event: 'back'): void }>()
</script>
