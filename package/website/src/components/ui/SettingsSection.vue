<template>
  <el-collapse v-model="activeNames" class="mb-8 overflow-hidden rounded-lg border border-gray-100 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
    <el-collapse-item :name="name">
      <template #title><h2 class="px-6 text-lg font-semibold text-gray-900 dark:text-white">{{ title }}</h2></template>
      <slot />
    </el-collapse-item>
  </el-collapse>
</template>
<script setup lang="ts">
defineProps<{ name: string; title: string }>()
const activeNames = defineModel<string[]>({ required: true })
</script>
