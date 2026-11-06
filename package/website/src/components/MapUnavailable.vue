<template>
  <div class="flex flex-col items-center justify-center gap-2 p-4 text-center" role="status" style="background: var(--ts-color-surface); color: var(--ts-color-text)">
    <p class="text-sm font-medium">{{ missing ? '尚未配置地图服务' : '地图暂时无法加载' }}</p>
    <p class="ts-muted max-w-sm text-xs leading-5">{{ description }}</p>
    <div class="flex flex-wrap items-center justify-center gap-3 text-sm">
      <RouterLink to="/settings#map" class="primary-text underline underline-offset-4">{{ missing ? '配置地图服务' : '检查地图配置' }}</RouterLink>
      <button v-if="retryable" type="button" class="primary-text underline underline-offset-4" @click="$emit('retry')">重新加载</button>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ error?: string | null; retryable?: boolean }>()
defineEmits<{ retry: [] }>()
const missing = computed(() => props.error === 'MAP_KEY_MISSING')
const description = computed(() => {
  if (missing.value) return '查看地图需要天地图服务密钥，请在「地图与地点」中完成配置。'
  if (props.error === 'UNSUPPORTED_PROVIDER') return '当前地图服务暂不支持，请在「地图与地点」中检查服务选择。'
  if (props.error === 'SETTINGS_ERROR') return '无法获取地图配置，请检查与行影集服务器的连接后重试。'
  return '请检查网络连接，或前往「地图与地点」测试服务密钥是否可用。'
})
</script>
