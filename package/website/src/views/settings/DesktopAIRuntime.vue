<template>
  <section v-if="isTauriApp()" class="ts-surface ts-settings-panel space-y-4" aria-label="AI 推理设备">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="ts-section-title">推理设备</h3>
        <p class="mt-1 text-sm ts-muted" role="status" aria-live="polite">
          当前设备：{{ store.status?.runtime.deviceName || '正在读取…' }}
          <span v-if="store.status?.runtime.backend"> · {{ labels[store.status.runtime.backend] }}</span>
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button class="ts-button ts-button-secondary" :disabled="store.busy" @click="store.refresh()">刷新设备</button>
        <button v-if="store.status?.supported" class="ts-button ts-button-primary" :disabled="store.busy" @click="store.autoSelect()">自动配置</button>
      </div>
    </div>
    <p class="text-sm ts-muted">CPU 已内置。可按需下载加速包，用于人脸、文字识别、分类和图片特征计算。</p>
    <p v-if="store.status && !store.status.supported" class="text-sm ts-muted">加速包目前支持 Windows x64，当前平台使用内置运行时。</p>
    <div v-if="store.status" class="grid gap-3 md:grid-cols-3">
      <article v-for="backend in backends" :key="backend" class="rounded-lg border p-4" :class="store.status.selected === backend ? 'border-primary-500 bg-primary-500/5' : 'ts-divider'">
        <div class="flex flex-wrap items-center gap-2">
          <h4 class="font-medium">{{ labels[backend] }}</h4>
          <span v-if="store.status.runtime.backend === backend" class="text-xs text-primary-600 dark:text-primary-400">正在使用</span>
          <span v-else-if="store.status.selected === backend" class="text-xs ts-muted">已选择</span>
        </div>
        <p class="mt-1 text-xs ts-muted">{{ hints[backend] }}</p>
        <div v-if="backend === 'openvino' && installed(backend)" class="mt-3">
          <label for="openvino-device" class="block text-sm ts-muted">设备</label>
          <select id="openvino-device" v-model="device" class="ts-input mt-1 w-full" :disabled="store.busy">
            <option v-for="item in devices" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
        </div>
        <button class="ts-button ts-button-secondary mt-3" :disabled="store.busy || (backend !== 'cpu' && !store.status.supported)" @click="store.act(backend, device, !installed(backend))">
          {{ store.busy && store.progress?.backend === backend ? phases[store.progress.phase] : installed(backend) ? (store.status.runtime.backend === backend && (backend !== 'openvino' || store.status.device === device) ? '重新验证' : '使用此设备') : '下载加速包' }}
        </button>
      </article>
    </div>
    <div v-if="store.busy && store.progress" class="space-y-2" role="status" aria-live="polite">
      <p class="text-sm ts-muted">{{ store.progress.phase === 'detecting' ? phases.detecting : labels[store.progress.backend] + ' · ' + phases[store.progress.phase] }}</p>
      <template v-if="store.progress.size">
        <progress class="w-full accent-[var(--theme-primary)]" :value="store.progress.downloaded" :max="store.progress.size" aria-label="加速包下载进度" />
        <p class="text-xs ts-muted">{{ bytes(store.progress.downloaded) }} / {{ bytes(store.progress.size) }}</p>
      </template>
      <p v-if="store.progress.phase === 'switching'" class="text-xs ts-muted">正在等待 AI 请求和模型下载结束，随后验证并切换设备。</p>
    </div>
    <p v-if="message" class="break-words text-sm text-amber-700 dark:text-amber-400" role="alert">{{ message }}</p>
    <details v-if="Object.keys(store.status?.runtime.models || {}).length" class="text-xs ts-muted">
      <summary class="cursor-pointer">各模型运行状态</summary>
      <p v-for="(model, name) in store.status?.runtime.models" :key="name" class="mt-2 break-words">{{ name }}：{{ model.providers.join(' → ') }}<span v-if="model.error"> · {{ model.error }}</span></p>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { isTauriApp } from '@/config/server'
import { useDesktopAIRuntimeStore } from '@/stores/desktopAIRuntime'
import type { AIBackend } from '@/api/desktopAIRuntime'

const store = useDesktopAIRuntimeStore()
const device = ref('CPU')
watch(() => store.status?.device, value => { if (value) device.value = value })
const backends: AIBackend[] = ['cpu', 'cuda', 'openvino']
const labels = { cpu: 'CPU', cuda: 'NVIDIA CUDA', openvino: 'Intel OpenVINO' }
const hints = { cpu: '无需下载，适用于所有设备', cuda: '需要兼容的 NVIDIA 显卡和驱动', openvino: '支持 Intel CPU、核显和 NPU，依设备与驱动而定' }
const phases = { detecting: '正在检测本机推理设备…', checking: '正在检查加速包…', downloading: '正在下载…', verifying: '正在校验…', installing: '正在安装…', switching: '正在切换设备…', ready: '已准备好', error: '操作失败，可重试' }
const message = computed(() => store.error || store.readError || store.status?.error || store.status?.runtime.error || store.progress?.error)
const devices = computed(() => {
  const detected = store.status?.runtime.devices || []
  return detected.length ? detected : ['CPU', 'GPU', 'NPU'].map(id => ({ id, name: id }))
})
const installed = (backend: AIBackend) => backend === 'cpu' || !!store.status?.packages.find(p => p.backend === backend)?.installed
const bytes = (value: number) => `${(value / 1024 / 1024).toFixed(1)} MB`
let timer: ReturnType<typeof setInterval> | undefined
onMounted(async () => {
  if (!isTauriApp()) return
  try { await store.subscribe() } catch (cause) { store.error = String(cause) }
  timer = setInterval(() => void store.refresh(), 2500)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
