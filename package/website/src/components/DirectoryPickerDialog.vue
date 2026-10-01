<template>
  <el-dialog v-model="visible" :title="title" width="min(94vw, 500px)" destroy-on-close>
    <DirectoryTree v-if="visible" v-model="draft" />
    <template #footer><div class="flex justify-end gap-3"><el-button @click="visible = false">取消</el-button><el-button type="primary" :disabled="!draft" @click="confirm">确认</el-button></div></template>
  </el-dialog>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import DirectoryTree from './DirectoryTree.vue'
const visible = defineModel<boolean>('visible', { required: true })
const path = defineModel<string>({ required: true })
withDefaults(defineProps<{ title?: string }>(), { title: '选择目标目录' })
const draft = ref('')
watch(visible, open => { if (open) draft.value = path.value }, { immediate: true })
const confirm = () => { path.value = draft.value; visible.value = false }
</script>
