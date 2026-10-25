<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ id: string; path: string; title: string; eager?: boolean; active?: boolean; preload?: boolean }>(), { active: true, eager: false, preload: false })
const origin = 'https://demo.siyuan.ink'
const url = `${origin}${props.path}${props.path.includes('?') ? '&' : '?'}demo=1`
const frame = ref<HTMLIFrameElement>()
const src = ref<string>()
let observer: IntersectionObserver | undefined
let nearViewport = false

function start(force = false) {
  if (src.value) return
  if (!force && (props.active === false || !nearViewport)) return
  src.value = url
}
watch(() => props.active, () => start())
// preload 由首页在 load 后触发，允许在远离视口时提前装载演示页。
watch(() => props.preload, value => { if (value) start(true) })
onMounted(() => {
  if (props.preload) start(true)
  if (props.eager || !('IntersectionObserver' in window)) {
    nearViewport = true
    start()
  } else if (frame.value) {
    observer = new IntersectionObserver(entries => {
      nearViewport = entries.some(entry => entry.isIntersecting)
      if (nearViewport) start()
    }, { rootMargin: '400px 0px' })
    observer.observe(frame.value.parentElement!)
  }
})
onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <iframe ref="frame" :id="id" :src="src" :title="title" :hidden="active === false"
    loading="eager" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
    allow="fullscreen" referrerpolicy="strict-origin-when-cross-origin" />
</template>
