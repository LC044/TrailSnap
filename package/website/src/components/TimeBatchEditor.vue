<template>
  <ResponsiveDialog
    :model-value="modelValue"
    title="批量修改时间"
    :description="`已选 ${photoIds.length} 项，将统一设置为以下拍摄时间`"
    :before-close="() => !submitting"
    :close-on-backdrop="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="space-y-4">
      <div class="space-y-2">
        <label for="batch-photo-time" class="text-sm font-medium text-[var(--ts-color-text)]">拍摄时间</label>
        <UnifiedDatePicker
          id="batch-photo-time"
          v-model="photoTime"
          type="datetime"
          placeholder="选择拍摄时间"
          format="YYYY-MM-DD HH:mm:ss"
          value-format="YYYY-MM-DD HH:mm:ss"
          class="!w-full"
          :disabled="submitting"
        />
      </div>
      <div>
        <el-checkbox v-model="modifyOriginalFile" :disabled="submitting">同步修改原文件</el-checkbox>
        <p class="text-xs text-[var(--ts-color-text-secondary)]">开启后同步修改原文件的系统修改时间（EXIF 拍摄时间暂不支持修改）。</p>
      </div>
      <p v-if="submitting" role="status" class="text-sm text-[var(--ts-color-text-secondary)]">正在修改 {{ completed }} / {{ total }} 项</p>
      <p v-if="failedIds.length" role="alert" class="text-sm text-[var(--ts-color-danger)]">{{ failedIds.length }} 项修改失败，可重试失败项，或关闭后重新选择。</p>
    </div>
    <template #footer>
      <div class="flex justify-end gap-2">
        <el-button :disabled="submitting" @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :loading="submitting" :disabled="!photoTime || !photoIds.length" @click="handleApply">
          {{ failedIds.length ? `重试失败项 (${failedIds.length})` : `应用到全部 (${photoIds.length})` }}
        </el-button>
      </div>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { albumService } from '@/api/album'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'

const props = defineProps<{ modelValue: boolean; photoIds: string[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; updated: []; success: [] }>()
const photoTime = ref('')
const modifyOriginalFile = ref(true)
const submitting = ref(false)
const completed = ref(0)
const total = ref(0)
const failedIds = ref<string[]>([])

watch(() => props.modelValue, visible => {
  if (!visible) return
  photoTime.value = ''
  modifyOriginalFile.value = true
  failedIds.value = []
  completed.value = 0
}, { immediate: true })

const handleApply = async () => {
  if (submitting.value || !photoTime.value || !props.photoIds.length) return
  const ids = [...new Set(failedIds.value.length ? failedIds.value : props.photoIds)]
  const updates = { photo_time: photoTime.value, modify_original_file: modifyOriginalFile.value }
  submitting.value = true
  completed.value = 0
  total.value = ids.length
  const failures: string[] = []
  try {
    for (const id of ids) {
      try {
        await albumService.updatePhoto(id, updates)
      } catch {
        failures.push(id)
      }
      completed.value++
    }
    failedIds.value = failures
    const succeeded = ids.length - failures.length
    if (succeeded) emit('updated')
    if (failures.length) {
      ElMessage.warning(`已修改 ${succeeded} 项，${failures.length} 项失败`)
    } else {
      ElMessage.success(`已修改 ${succeeded} 项的拍摄时间`)
      emit('update:modelValue', false)
      emit('success')
    }
  } finally {
    submitting.value = false
  }
}
</script>
