<template>
  <div class="install-prompt">
    <div class="prompt-heading">
      <Sparkles class="sparkle-icon" :size="30" aria-hidden="true" />
      <div class="prompt-description"><h3>{{ title }}</h3><p>{{ description }}</p></div>
      <button type="button" class="copy-button" @click="onCopy"><component :is="copied ? Check : Copy" :size="15" aria-hidden="true" />{{ copied ? copiedLabel : copyLabel }}</button>
    </div>
    <details :open="expanded" @toggle="expanded = ($event.target as HTMLDetailsElement).open">
      <summary>{{ expanded ? hideLabel : showLabel }} <ChevronDown :size="14" aria-hidden="true" /></summary>
      <pre tabindex="0" :aria-label="title"><code>{{ prompt }}</code></pre>
    </details>
    <p v-if="copyFailed" role="alert" class="copy-error">{{ errorLabel }}</p>
    <span class="sr-only" role="status">{{ copied ? copiedLabel : '' }}</span>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { Check, ChevronDown, Copy, Sparkles } from 'lucide-vue-next'

const props = defineProps<{
  title: string
  description: string
  prompt: string
  copyLabel: string
  copiedLabel: string
  errorLabel: string
  showLabel: string
  hideLabel: string
}>()

const expanded = ref(false)
const copied = ref(false)
const copyFailed = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function fallbackCopy() {
  const textarea = document.createElement('textarea')
  const focusedElement = document.activeElement as HTMLElement | null
  textarea.value = props.prompt
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  try {
    textarea.select()
    return document.execCommand('copy')
  } finally {
    textarea.remove()
    focusedElement?.focus()
  }
}

async function onCopy() {
  copied.value = false
  copyFailed.value = false
  try {
    await navigator.clipboard.writeText(props.prompt)
  } catch {
    try {
      if (!fallbackCopy()) {
        expanded.value = true
        copyFailed.value = true
        return
      }
    } catch {
      expanded.value = true
      copyFailed.value = true
      return
    }
  }
  copied.value = true
  clearTimeout(timer)
  timer = setTimeout(() => { copied.value = false }, 2000)
}

onUnmounted(() => clearTimeout(timer))
</script>

<style scoped>
.install-prompt { min-width: 0; padding: 22px 24px 14px; border: 1px solid var(--vp-c-brand-soft); border-radius: 18px; background: var(--vp-c-brand-soft); }
.prompt-heading { display: flex; align-items: center; gap: 18px; }
.sparkle-icon { flex-shrink: 0; color: var(--vp-c-brand-1); }
.prompt-description { flex: 1; min-width: 0; }
h3 { margin: 0; font-size: 16px; font-weight: 650; line-height: 1.5; color: var(--vp-c-text-1); }
p { margin: 4px 0 0; font-size: 13px; line-height: 1.7; color: var(--vp-c-text-2); }
.copy-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; flex-shrink: 0; border-radius: 9px; background: var(--vp-c-brand-3); color: white; padding: 10px 13px; font-size: 12px; font-weight: 600; cursor: pointer; }
.copy-button:hover { background: var(--vp-c-brand-2); }
summary { display: flex; align-items: center; justify-content: center; gap: 5px; width: fit-content; margin: 10px auto 0; color: var(--vp-c-brand-1); font-size: 12px; cursor: pointer; list-style: none; }
summary::-webkit-details-marker { display: none; }
details[open] summary svg { transform: rotate(180deg); }
pre { margin: 16px 0 4px; max-height: 360px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; border: 1px solid var(--vp-c-divider); border-radius: 12px; padding: 18px; background: var(--vp-c-bg); color: var(--vp-c-text-2); font-size: 13px; line-height: 1.9; }
code { font-family: var(--vp-font-family-mono); }
.copy-error { color: var(--vp-c-danger-1); }
button:focus-visible, summary:focus-visible, pre:focus-visible { outline: 2px solid var(--vp-c-brand-1); outline-offset: 4px; }
@media (max-width: 540px) { .install-prompt { padding: 18px; } .prompt-heading { flex-wrap: wrap; gap: 12px; } .sparkle-icon { width: 24px; } .prompt-description { flex: 1 1 calc(100% - 36px); } .copy-button { margin-left: 36px; max-width: calc(100% - 36px); } }
</style>
