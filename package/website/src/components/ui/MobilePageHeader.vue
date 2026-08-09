<template>
  <header
    class="md:hidden border-b border-gray-200 bg-white/95 px-3 py-2 backdrop-blur dark:border-gray-800 dark:bg-gray-900/95"
    :class="sticky ? 'sticky top-0 z-30' : ''"
  >
    <div class="flex min-h-10 items-center gap-2">
      <slot name="leading">
        <IconButton v-if="showBack" label="返回" @click="handleBack">
          <ArrowLeft class="h-5 w-5" />
        </IconButton>
      </slot>
      <div class="min-w-0 flex-1">
        <h1 class="truncate text-base font-semibold text-gray-900 dark:text-white">{{ title }}</h1>
        <p v-if="subtitle" class="truncate text-xs text-gray-500 dark:text-gray-400">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-1">
        <slot name="actions" />
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import IconButton from '@/components/ui/IconButton.vue'
import { useAppBack } from '@/composables/useAppBack'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  fallback?: string
  showBack?: boolean
  sticky?: boolean
}>(), {
  fallback: '/',
  showBack: true,
  sticky: true,
})

const emit = defineEmits<{ back: [] }>()
const appBack = useAppBack(props.fallback)

const handleBack = async () => {
  emit('back')
  await appBack()
}
</script>
