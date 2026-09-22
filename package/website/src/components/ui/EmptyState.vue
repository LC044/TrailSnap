<template>
  <div class="flex flex-col items-center justify-center px-6 py-12 text-center md:py-16">
    <div v-if="$slots.icon" class="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500">
      <slot name="icon" />
    </div>
    <h2 class="text-base font-semibold text-gray-900 dark:text-white">{{ title }}</h2>
    <p v-if="description" class="mt-1.5 max-w-sm text-sm leading-6 text-gray-500 dark:text-gray-400">{{ description }}</p>
    <div v-if="$slots.actions" class="mt-5 flex flex-wrap justify-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>
