<template>
  <section class="ts-surface ts-settings-panel space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h3 class="text-lg font-semibold">Token 用量</h3>
      <div class="flex items-center gap-2">
        <el-select v-model="days" size="small" class="w-28" aria-label="统计时间范围">
          <el-option v-for="period in [7, 30, 90]" :key="period" :label="`近 ${period} 天`" :value="period" />
        </el-select>
        <el-button size="small" plain :loading="loading" @click="loadUsage">刷新</el-button>
      </div>
    </div>

    <p v-if="failed" role="status" class="text-sm text-gray-600 dark:text-gray-300">
      用量加载失败，请点击刷新重试。
    </p>
    <template v-if="report?.totals.requests">
      <dl class="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <div v-for="stat in summary" :key="stat.label" class="min-w-0 rounded-lg border ts-divider px-3 py-2">
          <dt class="text-xs text-gray-500 dark:text-gray-400">{{ stat.label }}</dt>
          <dd class="mt-1 break-all text-lg font-semibold tabular-nums">{{ stat.value }}</dd>
        </div>
      </dl>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        缓存命中计入输入 Token。按 UTC 日期汇总，仅累计服务商返回的用量。
      </p>
      <p v-if="report.totals.reported_requests < report.totals.requests || report.totals.cache_reported_requests < report.totals.requests"
        class="text-xs text-gray-500 dark:text-gray-400">
        {{ format(report.totals.reported_requests) }} 次请求报告了输入和输出用量，{{ format(report.totals.cache_reported_requests) }} 次报告了缓存数据。
      </p>
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <caption class="sr-only">按模型和用途统计的 Token 用量</caption>
          <thead class="text-xs text-gray-500 dark:text-gray-400">
            <tr class="border-b ts-divider">
              <th scope="col" class="p-2">模型</th>
              <th scope="col" class="whitespace-nowrap p-2">用途</th>
              <th scope="col" class="p-2 text-right">请求</th>
              <th scope="col" class="p-2 text-right">输入</th>
              <th scope="col" class="p-2 text-right">输出</th>
              <th scope="col" class="whitespace-nowrap p-2 text-right">缓存命中</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.models" :key="JSON.stringify([row.source, row.connection_id, row.model])"
              class="border-b ts-divider last:border-0">
              <th scope="row" class="min-w-32 break-all p-2 font-medium">
                {{ row.model }}
                <span class="block text-xs font-normal text-gray-500 dark:text-gray-400">
                  {{ row.connection_id === 'builtin' ? '内置' : row.connection_id }}
                </span>
              </th>
              <td class="whitespace-nowrap p-2">{{ sources[row.source] ?? row.source }}</td>
              <td class="p-2 text-right tabular-nums">{{ format(row.requests) }}</td>
              <td class="p-2 text-right tabular-nums">{{ measured(row.input_tokens, row.reported_requests) }}</td>
              <td class="p-2 text-right tabular-nums">{{ measured(row.output_tokens, row.reported_requests) }}</td>
              <td class="p-2 text-right tabular-nums">{{ measured(row.cached_input_tokens, row.cache_reported_requests) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <p v-else-if="!failed" role="status" class="text-sm text-gray-500 dark:text-gray-400">
      {{ loading ? '正在读取用量…' : '这段时间内暂无大模型请求记录。' }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { settingsApi, type LLMUsageReport } from '@/api/settings'

const days = ref(30)
const report = ref<LLMUsageReport | null>(null)
const loading = ref(false)
const failed = ref(false)
let activeRequest: AbortController | undefined

const sources: Record<string, string> = {
  visual_analysis: '智能分析',
  chat: 'AI 对话',
  caption: '朋友圈文案',
  chapter: '章节日记',
  memory: '记忆',
}
const format = new Intl.NumberFormat('zh-CN').format
const measured = (tokens: number, reports: number) => reports ? format(tokens) : '未知'
const summary = computed(() => {
  const totals = report.value?.totals
  if (!totals) return []
  return [
    { label: '输入 Token', value: measured(totals.input_tokens, totals.reported_requests) },
    { label: '输出 Token', value: measured(totals.output_tokens, totals.reported_requests) },
    { label: '缓存命中 Token', value: measured(totals.cached_input_tokens, totals.cache_reported_requests) },
    { label: '完成请求', value: format(totals.requests) },
  ]
})

async function loadUsage() {
  activeRequest?.abort()
  const request = new AbortController()
  activeRequest = request
  loading.value = true
  failed.value = false
  try {
    const data = await settingsApi.getLLMUsage(days.value, request.signal)
    if (!request.signal.aborted) report.value = data
  } catch {
    if (!request.signal.aborted) failed.value = true
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}

watch(days, () => {
  report.value = null
  void loadUsage()
}, { immediate: true })
useIntervalFn(() => {
  if (!loading.value && document.visibilityState === 'visible') void loadUsage()
}, 30_000)
onUnmounted(() => activeRequest?.abort())
</script>
