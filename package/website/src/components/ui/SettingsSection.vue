<template>
  <el-collapse v-model="activeNames" class="ts-surface ts-settings-section mb-8 overflow-hidden">
    <el-collapse-item :name="name">
      <template #title><h2 class="ts-section-title px-4 md:px-6">{{ title }}</h2></template>
      <slot />
    </el-collapse-item>
  </el-collapse>
</template>
<script setup lang="ts">
defineProps<{ name: string; title: string }>()
const activeNames = defineModel<string[]>({ required: true })
</script>
