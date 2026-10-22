<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ id: string; path: string; title: string; eager?: boolean; active?: boolean }>(), { active: true, eager: false })
const origin = 'https://demo.siyuan.ink'
const url = `${origin}${props.path}${props.path.includes('?') ? '&' : '?'}demo=1`
const frame = ref<HTMLIFrameElement>()
const src = ref<string>()
let observer: IntersectionObserver | undefined
let nearViewport = false

function start() {
  if (src.value || props.active === false || !nearViewport) return
  src.value = url
}
watch(() => props.active, () => start())
onMounted(() => {
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
