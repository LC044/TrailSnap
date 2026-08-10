<template>
  <el-dialog
    :model-value="visible"
    title="编辑人物信息"
    :width="dialogWidth"
    class="rounded-xl"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form label-position="top">
      <el-form-item label="姓名">
        <el-input v-model="form.identity_name" placeholder="输入姓名..." />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="输入描述..." />
      </el-form-item>
      <el-form-item label="标签">
        <el-select
          v-model="form.tags"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="选择或输入标签"
          class="w-full"
        >
          <el-option v-for="tag in defaultTags" :key="tag" :label="tag" :value="tag" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="flex gap-2 justify-end">
        <el-button @click="$emit('update:visible', false)">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { FaceIdentity } from '@/types/album'
import { faceApi } from '@/api/face'
import { ElMessage } from 'element-plus'
import { useWindowSize } from '@vueuse/core'

const props = defineProps<{
  visible: boolean
  identity: FaceIdentity | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', identity: FaceIdentity): void
}>()

const { width } = useWindowSize()
const dialogWidth = computed(() => width.value < 640 ? '90%' : '400px')

const visibleRef = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const form = ref({
  identity_name: '',
  description: '',
  tags: [] as string[]
})
const saving = ref(false)

const defaultTags = ["自己", "朋友", "家人", "同事", "女朋友", "男朋友", "同学"]

watch(() => props.identity, (newVal) => {
  if (newVal) {
    form.value = {
      identity_name: newVal.identity_name || '',
      description: newVal.description || '',
      tags: newVal.tags || []
    }
  }
}, { immediate: true })

const submit = async () => {
  if (!props.identity) return
  saving.value = true
  try {
    const updated = await faceApi.updateIdentity(props.identity.id, form.value)
    ElMessage.success('保存成功')
    emit('saved', updated)
    emit('update:visible', false)
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>
