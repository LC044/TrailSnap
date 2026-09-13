<template>
  <article class="panel import-panel">
    <h2>导入管理</h2>
    <div class="import-form">
      <el-input v-model="deviceLabel" placeholder="设备名称，如：办公本 / 家里台式机" style="width: 240px" maxlength="40" />
      <input ref="fileInput" type="file" accept=".sql" class="file-hidden" @change="onFileChange" />
      <el-button type="primary" :icon="Upload" :loading="uploading" :disabled="!deviceLabel.trim()" @click="fileInput?.click()">上传 cc-switch 备份</el-button>
      <span class="import-hint">在 cc-switch「用量统计」页导出 SQLite 备份（.sql）后上传；同设备重复导出会自动去重合并。</span>
    </div>

    <div v-if="importResult" class="import-result">
      <el-alert type="success" :closable="false" show-icon>
        <template #title>
          导入成功：新增明细 {{ importResult.detail_new }} 条（跳过重复 {{ importResult.detail_dup }}、清理过期 {{ importResult.detail_aged_out }}），日聚合 {{ importResult.rollup_rows }} 行，覆盖 {{ importResult.date_min }} ~ {{ importResult.date_max }}
        </template>
      </el-alert>
    </div>

    <div v-if="imports.length" class="imports-table-wrap">
      <table class="trend-table">
        <thead><tr><th>设备</th><th>文件</th><th>明细新增/重复</th><th>日聚合</th><th>数据范围</th><th>导入时间</th><th></th></tr></thead>
        <tbody>
          <tr v-for="row in imports" :key="row.id">
            <td>{{ row.device_label }}</td>
            <td class="file-cell" :title="row.file_name">{{ row.file_name }}</td>
            <td>{{ row.detail_new }} / {{ row.detail_dup }}</td>
            <td>{{ row.rollup_rows }}</td>
            <td>{{ row.date_min }} ~ {{ row.date_max }}</td>
            <td>{{ fmtTime(row.imported_at) }}</td>
            <td><el-button size="small" type="danger" plain @click="removeImport(row)">删除</el-button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="chart-empty">还没有导入记录</p>

    <div v-if="devices.length" class="device-list">
      <span class="device-list-label">按设备删除全部数据：</span>
      <el-tag v-for="device in devices" :key="device.id" closable class="device-tag" @close="removeDevice(device)">{{ device.label }}</el-tag>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { api, type UsageImportRecord, type UsageImportResult } from '../../api'

const emit = defineEmits<{ changed: [] }>()
const imports = ref<UsageImportRecord[]>([])
const deviceLabel = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const importResult = ref<UsageImportResult | null>(null)

const devices = computed(() => {
  const seen = new Map<string, { id: string; label: string }>()
  for (const row of imports.value) seen.set(row.device_id, { id: row.device_id, label: row.device_label })
  return [...seen.values()]
})

function fmtTime(value?: string): string {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

async function loadImports() {
  imports.value = await api.usageImports()
}

function notifyChanged() {
  emit('changed')
  void loadImports()
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void upload(file)
  input.value = ''
}

async function upload(file: File) {
  if (!deviceLabel.value.trim()) return
  uploading.value = true
  importResult.value = null
  try {
    importResult.value = await api.uploadUsageImport(deviceLabel.value.trim(), file)
    ElMessage.success('导入成功')
    notifyChanged()
  } catch (error) {
    if ((error as { response?: { status?: number } })?.response?.status === 409) ElMessage.warning('该文件之前已导入过')
    else ElMessage.error(((error as { response?: { data?: { msg?: string } } })?.response?.data?.msg) || '导入失败，请检查文件格式')
  } finally {
    uploading.value = false
  }
}

async function removeImport(row: UsageImportRecord) {
  try {
    await ElMessageBox.confirm(`删除「${row.file_name}」的 ${row.detail_new} 条明细？日聚合数据保留。`, '删除导入', { type: 'warning' })
  } catch { return }
  try {
    await api.deleteUsageImport(row.id)
    ElMessage.success('已删除')
    notifyChanged()
  } catch (error) { ElMessage.error(String(error)) }
}

async function removeDevice(device: { id: string; label: string }) {
  try {
    await ElMessageBox.confirm(`删除设备「${device.label}」及其全部用量数据？此操作不可恢复。`, '删除设备', { type: 'warning' })
  } catch { return }
  try {
    await api.deleteUsageDevice(device.id)
    ElMessage.success('已删除')
    notifyChanged()
  } catch (error) { ElMessage.error(String(error)) }
}

onMounted(loadImports)
</script>
