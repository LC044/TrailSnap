<template>
  <header
    :class="[
      mobileOnly && 'md:hidden',
      sticky && 'sticky top-0 z-30',
      bordered && 'border-b border-gray-200/80 dark:border-gray-800/80',
      glass && 'ts-glass',
    ]"
  >
    <div
      class="mx-auto flex min-h-14 w-full items-center gap-2 px-[var(--ts-page-gutter)]"
      :class="widthClass"
    >
      <slot name="leading">
        <IconButton v-if="showBack" label="返回" @click="handleBack">
          <ArrowLeft class="h-5 w-5" />
        </IconButton>
      </slot>

      <div class="min-w-0 flex-1 py-2">
        <div class="flex min-w-0 items-center gap-2">
          <h1
            class="truncate font-bold tracking-tight text-gray-950 dark:text-white"
            :class="large ? 'text-xl md:text-2xl' : 'text-base md:text-lg'"
          >
            {{ title }}
          </h1>
          <slot name="title-extra" />
        </div>
        <p v-if="subtitle" class="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400 md:text-sm">
          {{ subtitle }}
        </p>
      </div>

      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-1.5">
        <slot name="actions" />
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft } from 'lucide-vue-next'
import IconButton from '@/components/ui/IconButton.vue'
import { useAppBack } from '@/composables/useAppBack'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  fallback?: string
  showBack?: boolean
  sticky?: boolean
  glass?: boolean
  bordered?: boolean
  large?: boolean
  mobileOnly?: boolean
  size?: 'full' | 'wide' | 'content' | 'form'
}>(), {
  fallback: '/',
  showBack: false,
  sticky: true,
  glass: true,
  bordered: true,
  large: false,
  mobileOnly: false,
  size: 'content',
})

const emit = defineEmits<{ back: [] }>()
const appBack = useAppBack(props.fallback)

const widthClass = computed(() => ({
  full: 'max-w-none',
  wide: 'max-w-screen-2xl',
  content: 'max-w-7xl',
  form: 'max-w-4xl',
}[props.size]))

const handleBack = async () => {
  emit('back')
  await appBack()
}
</script>
