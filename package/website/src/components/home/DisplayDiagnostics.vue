<template>
  <section class="ts-surface p-3">
    <button
      type="button"
      class="ts-button ts-button-primary"
      :aria-expanded="expanded"
      aria-controls="display-diagnostics"
      @click="toggle"
    >
      {{ expanded ? '收起显示诊断' : '显示诊断' }}
    </button>
    <div v-if="expanded" id="display-diagnostics" class="mt-3 space-y-3">
      <p ref="bodyTextSample" class="text-sm text-gray-600 dark:text-gray-300">
        在微信、手机浏览器和 App 中分别打开此面板，复制结果或截图比较。
      </p>
      <dl class="space-y-2 text-sm text-gray-800 dark:text-gray-100">
        <div v-for="(value, label) in metrics" :key="label" class="flex flex-wrap justify-between gap-x-3">
          <dt>{{ label }}</dt>
          <dd class="font-mono">{{ value }}</dd>
        </div>
      </dl>
      <div aria-hidden="true" class="flex items-center gap-3">
        <span ref="pixelSample" class="inline-block shrink-0 bg-primary-500" style="width: 20px; height: 20px" />
        <span ref="remSample" class="inline-block shrink-0 bg-primary-500" style="width: 1.25rem; height: 1.25rem" />
        <span ref="textSample" style="font-size: 20px; line-height: 1">Aa</span>
      </div>
      <p ref="smallTextSample" class="text-xs text-gray-500 dark:text-gray-400">固定 20px、1.25rem 色块和 20px 文字是对照样本，保持原尺寸；缩放效果请看正文、图标和页面间距的数值。</p>
      <textarea
        ref="reportField"
        :value="report"
        readonly
        aria-label="显示诊断完整结果，可长按复制"
        class="w-full rounded-lg border border-gray-200 bg-white p-2 font-mono text-xs text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        rows="8"
      />
      <div class="flex flex-wrap gap-2">
        <button type="button" class="ts-button ts-button-ghost" @click="refresh">刷新数值</button>
        <button type="button" class="ts-button ts-button-ghost" @click="copy">复制结果</button>
      </div>
      <p v-if="copyStatus" role="status" class="text-sm text-gray-600 dark:text-gray-300">{{ copyStatus }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Capacitor } from '@capacitor/core'

const expanded = ref(false)
const metrics = ref<Record<string, string | number>>({})
const pixelSample = ref<HTMLElement | null>(null)
const remSample = ref<HTMLElement | null>(null)
const textSample = ref<HTMLElement | null>(null)
const bodyTextSample = ref<HTMLElement | null>(null)
const smallTextSample = ref<HTMLElement | null>(null)
const reportField = ref<HTMLTextAreaElement | null>(null)
const copyStatus = ref('')
const report = computed(() => JSON.stringify({
  ...metrics.value,
  '采集时间': new Date(sampleTime.value).toISOString(),
  'User Agent': navigator.userAgent,
}, null, 2))
const sampleTime = ref(Date.now())
const round = (value: number) => Number(value.toFixed(3))

function refresh() {
  const root = document.documentElement
  const nav = document.querySelector<HTMLElement>('nav[aria-label="主导航"]')
  const icon = nav?.querySelector('svg')
  const navVisible = nav && nav.getClientRects().length > 0
  const rootStyle = getComputedStyle(root)
  const home = document.querySelector('.ts-browse-page')
  const overview = document.querySelector('section[aria-labelledby="photo-overview-title"]')
  const overviewContent = overview?.querySelector(':scope > div')
  const toolbar = document.querySelector('.ts-browse-header .ts-glass-toolbar')
  const styleValue = (element: Element | null | undefined, property: string) =>
    element ? getComputedStyle(element).getPropertyValue(property) : '元素未显示'
  metrics.value = {
    '诊断版本': 'mobile-density-v2',
    '手机缩放样式': rootStyle.getPropertyValue('--ts-spacing-unit').trim() ? '已启用' : '未启用（桌面宽度或旧样式）',
    '运行环境': Capacitor.isNativePlatform() ? `App (${Capacitor.getPlatform()})`
      : /MicroMessenger/i.test(navigator.userAgent) ? '微信' : '浏览器',
    '屏幕宽度 CSS px': screen.width,
    '页面宽度 CSS px': root.clientWidth,
    '窗口宽度 CSS px': window.innerWidth,
    '可视视口宽度 CSS px': window.visualViewport ? round(window.visualViewport.width) : '不可用',
    'DPR': window.devicePixelRatio,
    '可视视口缩放': window.visualViewport ? round(window.visualViewport.scale) : '不可用',
    '根字号': getComputedStyle(root).fontSize,
    '文字自动调整': getComputedStyle(root).getPropertyValue('text-size-adjust')
      || getComputedStyle(root).getPropertyValue('-webkit-text-size-adjust') || '不可用',
    '底栏图标宽度 CSS px': navVisible && icon ? round(icon.getBoundingClientRect().width) : '底栏未显示',
    '底栏图标 CSS 宽度（排除动画）': navVisible ? styleValue(icon, 'width') : '底栏未显示',
    '底栏高度 CSS px': navVisible ? round(nav.getBoundingClientRect().height) : '底栏未显示',
    '正文 text-sm 字号': styleValue(bodyTextSample.value, 'font-size'),
    '辅助 text-xs 字号': styleValue(smallTextSample.value, 'font-size'),
    '首页左右填充': styleValue(home, 'padding-left'),
    '照片概览卡片填充': styleValue(overviewContent, 'padding-left'),
    '照片概览卡片圆角': styleValue(overview, 'border-top-left-radius'),
    '照片概览卡片边框': styleValue(overview, 'border-top-width'),
    '顶部工具栏填充': styleValue(toolbar, 'padding-left'),
    '顶部工具栏间距': styleValue(toolbar, 'column-gap'),
    '底栏距左边缘 CSS px': navVisible ? round(nav.getBoundingClientRect().left) : '底栏未显示',
    '底栏底部偏移': rootStyle.getPropertyValue('--ts-tabbar-offset').trim(),
    '20px 色块实际宽度': pixelSample.value ? round(pixelSample.value.getBoundingClientRect().width) : '不可用',
    '1.25rem 色块实际宽度': remSample.value ? round(remSample.value.getBoundingClientRect().width) : '不可用',
    '20px 文字实际高度': textSample.value ? round(textSample.value.getBoundingClientRect().height) : '不可用',
  }
  sampleTime.value = Date.now()
  copyStatus.value = ''
}

async function toggle() {
  expanded.value = !expanded.value
  if (expanded.value) {
    await nextTick()
    refresh()
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(report.value)
    copyStatus.value = '已复制，可以粘贴到聊天中。'
  } catch {
    reportField.value?.focus()
    reportField.value?.select()
    reportField.value?.setSelectionRange(0, report.value.length)
    copyStatus.value = '请长按上方文本框，选择复制；也可以直接截图。'
  }
}
</script>
