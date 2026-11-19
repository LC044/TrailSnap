<template>
  <el-popover
    placement="bottom-start"
    trigger="click"
    role="dialog"
    :title="label"
    width="min(360px, calc(100vw - 24px))"
    @before-enter="search = ''"
    @after-enter="focusSearchFromKeyboard"
  >
    <template #reference>
      <button type="button" class="ts-button ts-button-secondary w-full min-w-0 justify-start"
        :aria-label="selectedModel ? `${label}：${selectedModel.name}，思考强度：${reasoningLabel(selectedReasoning)}` : label"
        :disabled="loading || !models.length"
        @pointerdown="keyboardOpening = false"
        @keydown.enter="keyboardOpening = true"
        @keydown.space="keyboardOpening = true">
        <Bot class="size-4 shrink-0 text-primary-500" aria-hidden="true" />
        <span class="min-w-0 flex-1 truncate text-left">
          {{ selectedModel?.name || (loading ? '加载模型…' : models.length ? label : '未配置模型') }}
        </span>
        <span v-if="selectedModel" class="shrink-0 border-l ts-divider pl-2 text-xs">
          {{ reasoningLabel(selectedReasoning) }}
        </span>
        <ChevronDown class="size-4 shrink-0" aria-hidden="true" />
      </button>
    </template>

    <div class="space-y-3">
      <el-input ref="searchInput" v-model="search" placeholder="搜索模型" aria-label="搜索模型" clearable />
      <fieldset class="min-w-0">
        <legend class="sr-only">{{ label }}</legend>
        <div class="max-h-[min(13rem,30dvh)] space-y-0.5 overflow-y-auto">
          <label v-for="model in filteredModels" :key="model.value"
            class="model-choice flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5"
            :class="{ 'is-selected': model.value === modelValue }">
            <input class="sr-only" type="radio" :name="`${id}-model`" :checked="model.value === modelValue"
              @change="emit('update:modelValue', model.value)" />
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium">{{ model.name }}</span>
              <span class="block truncate text-xs text-gray-500 dark:text-gray-400">{{ model.provider }}</span>
            </span>
            <Check v-if="model.value === modelValue" class="size-4 shrink-0 text-primary-500" aria-hidden="true" />
          </label>
          <p v-if="!filteredModels.length" class="px-2 py-1.5 text-sm text-gray-500 dark:text-gray-400">没有匹配的模型</p>
        </div>
      </fieldset>

      <fieldset v-if="selectedModel" class="min-w-0 border-t ts-divider pt-2">
        <legend class="sr-only">思考强度</legend>
        <div class="mb-2 text-xs font-medium" aria-hidden="true">思考强度</div>
        <div class="flex flex-wrap gap-1.5">
          <label v-for="level in levels" :key="level" class="model-choice cursor-pointer rounded-md border ts-divider px-2.5 py-1 text-xs"
            :class="{ 'is-selected': level === selectedReasoning }">
            <input class="sr-only" type="radio" :name="`${id}-reasoning`" :checked="level === selectedReasoning"
              @change="emit('update:reasoning', level)" />
            {{ reasoningLabel(level) }}
          </label>
        </div>
      </fieldset>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import type { InputInstance } from 'element-plus'
import { Bot, Check, ChevronDown } from 'lucide-vue-next'

const props = defineProps<{
  models: { value: string; name: string; provider: string; reasoningLevels: string[] }[]
  modelValue: string
  reasoning: string
  label: string
  reasoningLabel: (level: string) => string
  loading: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:reasoning': [value: string]
}>()

const id = useId()
const search = ref('')
const searchInput = ref<InputInstance>()
let keyboardOpening = false
function focusSearchFromKeyboard() {
  if (keyboardOpening) searchInput.value?.focus()
  keyboardOpening = false
}
const selectedModel = computed(() => props.models.find(model => model.value === props.modelValue))
const levels = computed(() => selectedModel.value?.reasoningLevels ?? ['none'])
const selectedReasoning = computed(() => levels.value.includes(props.reasoning) ? props.reasoning : levels.value[0])
const filteredModels = computed(() => {
  const query = search.value.trim().toLowerCase()
  return props.models.filter(model => `${model.name} ${model.provider}`.toLowerCase().includes(query))
})
</script>

<style scoped>
.model-choice:hover {
  background: var(--ts-color-surface-muted);
}

.model-choice.is-selected {
  background: rgba(var(--theme-rgb), .1);
}

.model-choice:focus-within {
  outline: 2px solid var(--theme-primary);
  outline-offset: -2px;
}
</style>
