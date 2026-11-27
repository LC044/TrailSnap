<template>
  <ResponsiveDialog :model-value="true" title="计划列表" max-width="40rem" mobile-mode="fullscreen" mobile-back
    :before-close="() => !deleting" @update:model-value="value => !value && emit('close')">
    <ul>
      <li v-for="plan in plans" :key="plan.id" class="ts-divider flex flex-wrap items-center justify-between gap-3 border-b py-3 last:border-b-0">
        <div class="min-w-0 text-sm">
          <time :datetime="plan.created_at">{{ dateLabel(plan.created_at) }}</time>
          <p class="ts-muted mt-1">{{ labels[plan.status] || plan.status }} · {{ plan.summary.total || 0 }} 项</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <el-button v-if="!isActive(plan)" :disabled="deleting" @click="pendingDelete = plan">删除计划</el-button>
          <el-button type="primary" :disabled="deleting" @click="emit('open', plan.id)">{{ actionLabel(plan) }}</el-button>
        </div>
      </li>
    </ul>
    <p v-if="loading" role="status" class="ts-muted py-4 text-center text-sm">正在加载计划…</p>
    <p v-else-if="loadError" role="alert" class="py-4 text-center text-sm text-red-600 dark:text-red-400">
      {{ loadError }} <el-button @click="load">重试</el-button>
    </p>
    <p v-else-if="!plans.length" class="ts-muted py-6 text-center text-sm">暂无计划</p>
    <AutoLoadSentinel v-else-if="hasMore && !deleting" @load="load" />
  </ResponsiveDialog>
  <ConfirmDialog :visible="!!pendingDelete" title="删除计划"
    :message="deletePlanMessage"
    confirm-text="删除计划" @cancel="pendingDelete = null" @confirm="remove" />
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import AutoLoadSentinel from '@/components/ui/AutoLoadSentinel.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { dateLabel, isActive, actionLabel, labels, deletePlanMessage } from './toolPlanDisplay'
import { workflowApi, type PlanFilter, type ToolPlan } from '@/api/toolboxWorkflows'

const props = defineProps<{ filter: PlanFilter }>()
const emit = defineEmits<{ close: []; open: [id: string]; deleted: [id: string] }>()
const plans = ref<ToolPlan[]>([])
const loading = ref(false)
const hasMore = ref(true)
const loadError = ref('')
const deleting = ref(false)
const pendingDelete = ref<ToolPlan | null>(null)
const pageSize = 20
let offset = 0
let loadVersion = 0

const load = async () => {
  if (loading.value || !hasMore.value) return
  const version = loadVersion
  loading.value = true
  loadError.value = ''
  try {
    const rows = await workflowApi.history(offset, pageSize, false, props.filter)
    if (version !== loadVersion) return
    const known = new Set(plans.value.map(plan => plan.id))
    plans.value.push(...rows.filter(plan => !known.has(plan.id)))
    offset += rows.length
    hasMore.value = rows.length === pageSize
  } catch {
    if (version === loadVersion) loadError.value = '计划加载失败'
  } finally {
    if (version === loadVersion) loading.value = false
  }
}
const remove = async () => {
  const plan = pendingDelete.value
  pendingDelete.value = null
  if (!plan || deleting.value) return
  deleting.value = true
  try {
    await workflowApi.deletePlan(plan.id)
    loadVersion++
    plans.value = []
    offset = 0
    loading.value = false
    hasMore.value = true
    void load()
    emit('deleted', plan.id)
    ElMessage.success('计划已删除')
  } catch {
    // The request layer displays the server's reason.
  } finally {
    deleting.value = false
  }
}
onMounted(load)
</script>
