<template>
  <section class="ts-surface space-y-4 p-5 text-left" aria-labelledby="desktop-port-heading">
    <h3 id="desktop-port-heading" class="font-semibold">手机连接端口</h3>
    <p v-if="store.loading" class="ts-muted" role="status">正在读取端口配置…</p>
    <template v-if="store.config">
      <p class="ts-muted text-sm">{{ recovery ? '可在这里修改端口并重新启动，无需先进入程序。' : `当前监听端口：${store.config.activePort || '尚未启动'}` }}</p>
      <label class="block space-y-2">
        <span class="block text-sm">端口选择方式</span>
        <select v-model="store.fixed" class="ts-surface w-full p-3" :disabled="locked">
          <option :value="false">自动选择（推荐）</option>
          <option :value="true">自定义端口</option>
        </select>
      </label>
      <label v-if="store.fixed" class="block space-y-2">
        <span class="block text-sm">自定义端口（1–65535）</span>
        <input v-model.trim="store.port" class="ts-surface w-full p-3" type="text" inputmode="numeric" autocomplete="off" :disabled="locked" />
      </label>
      <p class="ts-muted text-sm">自动模式优先沿用上次端口，不可用时自动更换。修改后需重启，手机请重新扫码连接。</p>
      <p v-if="!recovery" class="ts-muted text-sm">重启前会等待上传和后台任务结束。</p>
    </template>
    <p v-if="store.error" role="alert" class="ts-muted break-words text-sm">{{ store.error }}</p>
    <button v-if="store.config" class="ts-button ts-button-primary" :disabled="store.loading || store.saving" @click="store.saveAndRestart">
      {{ store.saving ? '正在处理…' : store.waiting ? '继续等待并重启' : store.needsRestart ? '重试重启' : '保存并重启' }}
    </button>
    <button v-else-if="!store.loading" class="ts-button ts-button-secondary" @click="store.load">重新读取</button>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useDesktopPortStore } from '@/stores/desktopPort'
defineProps<{ recovery?: boolean }>()
const store = useDesktopPortStore()
const locked = computed(() => store.saving || store.needsRestart)
onMounted(() => { void store.load() })
</script>
