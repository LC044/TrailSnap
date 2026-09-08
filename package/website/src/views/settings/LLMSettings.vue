<template>
  <section class="space-y-4 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 sm:p-5">
    <div>
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100">大模型连接与任务配置</h3>
      <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">管理 OpenAI 兼容连接，并为智能分析和 AI 对话选择默认模型。</p>
    </div>

    <div class="space-y-3">
      <article v-for="(conn, index) in aiForm.connections" :key="conn.id" class="flex flex-col gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-600 dark:bg-gray-900 sm:flex-row sm:items-center">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 text-sm font-medium text-gray-800 dark:text-gray-200">
            <span v-if="conn.id === 'builtin'" class="rounded bg-primary-500/10 px-2 py-0.5 text-xs text-primary-600 dark:text-primary-500">内置</span>
            <span class="truncate">{{ conn.provider || 'OpenAI' }}</span>
          </div>
          <p class="mt-1 truncate text-xs text-gray-500 dark:text-gray-400" :title="conn.api_base">{{ conn.api_base || '未设置地址' }}</p>
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">已添加 {{ conn.models?.length || 0 }} 个模型</p>
        </div>
        <div class="flex items-center gap-2">
          <el-switch v-model="conn.enable" :disabled="conn.id === 'builtin'" @change="saveAll" />
          <el-button plain @click="editConnection(index)">编辑</el-button>
        </div>
      </article>
      <el-button type="primary" plain class="w-full" @click="addConnection">+ 添加连接</el-button>
    </div>

    <div class="grid gap-4 border-t border-gray-200 pt-4 dark:border-gray-700 lg:grid-cols-2">
      <div class="rounded-lg border border-gray-200 p-4 dark:border-gray-600">
        <h4 class="font-medium text-gray-800 dark:text-gray-100">大模型智能分析配置</h4>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">请使用支持视觉理解的模型。</p>
        <div class="mt-4 space-y-3">
          <el-select v-model="analysisValue" class="w-full" placeholder="选择分析模型" filterable @change="onAnalysisModelChange">
            <el-option v-for="model in selectableModels" :key="model.value" :label="model.label" :value="model.value" />
          </el-select>
          <el-select v-model="aiForm.analysis_reasoning_effort" class="w-full" placeholder="选择思考等级">
            <el-option v-for="level in selectedReasoningLevels(analysisValue)" :key="level" :label="reasoningLabel(level)" :value="level" />
          </el-select>
        </div>
      </div>
      <div class="rounded-lg border border-gray-200 p-4 dark:border-gray-600">
        <h4 class="font-medium text-gray-800 dark:text-gray-100">AI 对话默认配置</h4>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">对话框内仍可临时切换模型和思考等级。</p>
        <div class="mt-4 space-y-3">
          <el-select v-model="chatValue" class="w-full" placeholder="选择对话模型" filterable @change="onChatModelChange">
            <el-option v-for="model in selectableModels" :key="model.value" :label="model.label" :value="model.value" />
          </el-select>
          <el-select v-model="aiForm.chat_reasoning_effort" class="w-full" placeholder="选择思考等级">
            <el-option v-for="level in selectedReasoningLevels(chatValue)" :key="level" :label="reasoningLabel(level)" :value="level" />
          </el-select>
        </div>
      </div>
    </div>

    <el-collapse>
      <el-collapse-item name="prompts" title="高级提示词设置">
        <div class="space-y-4 pt-2">
          <div>
            <p class="mb-2 text-sm text-gray-700 dark:text-gray-200">图片分析提示词</p>
            <el-input v-model="aiForm.visual_evaluation_prompt" type="textarea" :rows="4" placeholder="用于生成评分和描述的提示词" />
          </div>
          <div>
            <p class="mb-2 text-sm text-gray-700 dark:text-gray-200">朋友圈文案提示词</p>
            <el-input v-model="aiForm.moment_day_caption_prompt" type="textarea" :rows="4" placeholder="用于生成朋友圈日文案的提示词" />
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <div class="flex justify-end">
      <el-button type="primary" :loading="saving" @click="saveAll">保存大模型配置</el-button>
    </div>

    <el-dialog v-model="dialogVisible" :title="editingIndex < 0 ? '添加大模型连接' : '编辑大模型连接'" width="min(94vw, 720px)" destroy-on-close>
      <el-form v-if="draft" label-position="top">
        <el-form-item label="API 提供商">
          <el-select v-model="draft.provider" class="w-full" :disabled="draft.id === 'builtin'">
            <el-option v-if="draft.id === 'builtin'" label="内置 AI" value="Built-in AI" />
            <el-option label="OpenAI 兼容接口" value="OpenAI" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model.trim="draft.api_base" placeholder="https://api.openai.com/v1" :disabled="draft.id === 'builtin'" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="draft.api_key" type="password" show-password placeholder="sk-..." :disabled="draft.id === 'builtin'" />
        </el-form-item>

        <el-form-item label="模型（必填）">
          <div class="w-full space-y-3">
            <div class="flex flex-col gap-2 sm:flex-row">
              <el-button plain :loading="fetchingCandidates" :disabled="!draft.api_base" @click="fetchCandidates">获取模型列表</el-button>
              <el-select v-if="candidateModels.length" v-model="selectedCandidates" multiple collapse-tags filterable class="min-w-0 flex-1" placeholder="选择要添加的模型">
                <el-option v-for="name in availableCandidates" :key="name" :label="name" :value="name" />
              </el-select>
              <el-button v-if="candidateModels.length" type="primary" plain :disabled="!selectedCandidates.length" @click="addSelectedCandidates">添加所选</el-button>
            </div>
            <p v-if="candidateModels.length" class="text-xs text-gray-500 dark:text-gray-400">已获取 {{ candidateModels.length }} 个候选模型，只会添加你选择的模型。</p>

            <div v-for="(model, index) in draft.models" :key="index" class="space-y-3 rounded-lg border border-gray-200 p-3 dark:border-gray-600">
              <div class="grid gap-3 sm:grid-cols-2">
                <el-select v-model="model.model_name" filterable allow-create default-first-option placeholder="输入模型名或从候选列表选择">
                  <el-option v-for="name in candidateModels" :key="name" :label="name" :value="name" />
                </el-select>
                <el-input v-model="model.display_name" placeholder="显示名称（可选）" />
              </div>
              <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                <el-input-number v-model="model.context_window" :min="1024" :step="1024" controls-position="right" class="w-full sm:w-48" />
                <span class="text-xs text-gray-500 dark:text-gray-400">上下文窗口（tokens）</span>
                <el-button type="danger" text class="sm:ml-auto" @click="draft.models.splice(index, 1)">删除</el-button>
              </div>
              <el-checkbox-group v-model="model.reasoning_levels" class="flex flex-wrap gap-x-3">
                <el-checkbox v-for="level in reasoningOptions" :key="level" :label="level" :value="level">{{ reasoningLabel(level) }}</el-checkbox>
              </el-checkbox-group>
            </div>
            <el-button plain class="w-full" @click="addManualModel">+ 手动添加模型</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="flex justify-between gap-3">
          <el-button v-if="editingIndex >= 0 && draft?.id !== 'builtin'" type="danger" plain @click="removeConnection">删除连接</el-button>
          <span v-else></span>
          <div>
            <el-button @click="dialogVisible = false">取消</el-button>
            <el-button type="primary" @click="saveDraft">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingsApi } from '@/api/settings'

type ModelConfig = { model_name: string; display_name: string; context_window: number; reasoning_levels: string[] }
type Connection = { id: string; provider: string; api_base: string; api_key: string; model_names: string[]; models: ModelConfig[]; enable: boolean }
type AIForm = Record<string, any> & {
  connections: Connection[]
  analysis_connection_id: string
  analysis_model_name: string
  analysis_reasoning_effort: string
  chat_connection_id: string
  chat_model_name: string
  chat_reasoning_effort: string
}

const reasoningOptions = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']
const reasoningLabel = (level: string) => ({ none: '关闭', minimal: '最低', low: '低', medium: '中', high: '高', xhigh: '超高', max: '最大' }[level] || level)
const modelTemplate = (name = ''): ModelConfig => ({ model_name: name, display_name: name, context_window: 128000, reasoning_levels: ['none', 'low', 'medium', 'high'] })
const aiForm = ref<AIForm>({ connections: [], analysis_connection_id: '', analysis_model_name: '', analysis_reasoning_effort: 'none', chat_connection_id: '', chat_model_name: '', chat_reasoning_effort: 'none' })
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingIndex = ref(-1)
const draft = ref<Connection | null>(null)
const candidateModels = ref<string[]>([])
const selectedCandidates = ref<string[]>([])
const fetchingCandidates = ref(false)

const selectableModels = computed(() => aiForm.value.connections.filter(conn => conn.enable).flatMap(conn => conn.models.map(model => ({
  value: `${conn.id}|${model.model_name}`,
  label: `${model.display_name || model.model_name} · ${conn.provider}`,
}))))
const analysisValue = computed({
  get: () => aiForm.value.analysis_connection_id && aiForm.value.analysis_model_name ? `${aiForm.value.analysis_connection_id}|${aiForm.value.analysis_model_name}` : '',
  set: value => { [aiForm.value.analysis_connection_id, aiForm.value.analysis_model_name] = value ? value.split('|', 2) : ['', ''] },
})
const chatValue = computed({
  get: () => aiForm.value.chat_connection_id && aiForm.value.chat_model_name ? `${aiForm.value.chat_connection_id}|${aiForm.value.chat_model_name}` : '',
  set: value => { [aiForm.value.chat_connection_id, aiForm.value.chat_model_name] = value ? value.split('|', 2) : ['', ''] },
})
const availableCandidates = computed(() => {
  const existing = new Set(draft.value?.models.map(model => model.model_name) || [])
  return candidateModels.value.filter(name => !existing.has(name))
})

const normalizeConnection = (connection: any): Connection => ({
  ...connection,
  model_names: connection.model_names || [],
  models: connection.models?.length ? connection.models : (connection.model_names || []).map((name: string) => modelTemplate(name)),
})
const cloneConnection = (connection: Connection): Connection => ({
  ...connection,
  model_names: [...connection.model_names],
  models: connection.models.map(model => ({
    ...model,
    reasoning_levels: [...model.reasoning_levels],
  })),
})
const selectedModel = (value: string) => {
  const [connectionId, modelName] = value.split('|', 2)
  return aiForm.value.connections.find(conn => conn.id === connectionId)?.models.find(model => model.model_name === modelName)
}
const selectedReasoningLevels = (value: string) => {
  const levels = selectedModel(value)?.reasoning_levels
  return levels?.length ? levels : ['none']
}
const ensureReasoning = (value: string, current: string) => {
  const levels = selectedReasoningLevels(value)
  return levels.includes(current) ? current : levels[0]
}
const onAnalysisModelChange = () => { aiForm.value.analysis_reasoning_effort = ensureReasoning(analysisValue.value, aiForm.value.analysis_reasoning_effort) }
const onChatModelChange = () => { aiForm.value.chat_reasoning_effort = ensureReasoning(chatValue.value, aiForm.value.chat_reasoning_effort) }

async function loadSettings() {
  loading.value = true
  try {
    const settings = await settingsApi.getSettings()
    aiForm.value = { ...settings.ai, connections: (settings.ai?.connections || []).map(normalizeConnection) }
  } catch (error: any) {
    ElMessage.error(error.message || '加载大模型配置失败')
  } finally {
    loading.value = false
  }
}

function addConnection() {
  editingIndex.value = -1
  draft.value = { id: `conn_${Date.now()}`, provider: 'OpenAI', api_base: '', api_key: '', model_names: [], models: [], enable: true }
  candidateModels.value = []
  selectedCandidates.value = []
  dialogVisible.value = true
}
function editConnection(index: number) {
  editingIndex.value = index
  draft.value = cloneConnection(aiForm.value.connections[index])
  candidateModels.value = []
  selectedCandidates.value = []
  dialogVisible.value = true
}
function addManualModel() { draft.value?.models.push(modelTemplate()) }
function addSelectedCandidates() {
  if (!draft.value) return
  const existing = new Set(draft.value.models.map(model => model.model_name))
  selectedCandidates.value.forEach(name => { if (!existing.has(name)) draft.value!.models.push(modelTemplate(name)) })
  selectedCandidates.value = []
}
async function fetchCandidates() {
  if (!draft.value?.api_base) return
  fetchingCandidates.value = true
  try {
    const result = await settingsApi.verifyConnection(draft.value.api_base, draft.value.api_key || '')
    if (!result?.success) throw new Error(result?.message || '获取失败')
    candidateModels.value = [...new Set<string>(result.models || [])]
    ElMessage.success(`获取到 ${candidateModels.value.length} 个候选模型`)
  } catch (error: any) {
    ElMessage.error(error.message || '获取模型列表失败')
  } finally {
    fetchingCandidates.value = false
  }
}
async function saveDraft() {
  if (!draft.value) return
  const models = draft.value.models.filter(model => model.model_name.trim()).map(model => ({ ...model, model_name: model.model_name.trim(), display_name: model.display_name.trim(), reasoning_levels: model.reasoning_levels.length ? model.reasoning_levels : ['none'] }))
  if (!draft.value.api_base.trim()) return void ElMessage.warning('请填写 Base URL')
  if (!models.length) return void ElMessage.warning('每个连接必须至少添加一个模型')
  const names = models.map(model => model.model_name)
  if (new Set(names).size !== names.length) return void ElMessage.warning('同一连接中不能添加重复模型')
  const next = { ...draft.value, models, model_names: names }
  if (editingIndex.value < 0) aiForm.value.connections.push(next)
  else aiForm.value.connections[editingIndex.value] = next
  dialogVisible.value = false
  await saveAll()
}
async function removeConnection() {
  if (editingIndex.value < 0) return
  try {
    await ElMessageBox.confirm('确定删除这个大模型连接？', '删除连接', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    const removedId = aiForm.value.connections[editingIndex.value].id
    aiForm.value.connections.splice(editingIndex.value, 1)
    if (aiForm.value.analysis_connection_id === removedId) { aiForm.value.analysis_connection_id = ''; aiForm.value.analysis_model_name = '' }
    if (aiForm.value.chat_connection_id === removedId) { aiForm.value.chat_connection_id = ''; aiForm.value.chat_model_name = '' }
    dialogVisible.value = false
    await saveAll()
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(String(error)) }
}
function ensureSelections() {
  const values = new Set(selectableModels.value.map(model => model.value))
  const fallback = selectableModels.value[0]?.value || ''
  if (!values.has(analysisValue.value)) analysisValue.value = fallback
  if (!values.has(chatValue.value)) chatValue.value = fallback
  onAnalysisModelChange()
  onChatModelChange()
}
async function saveAll() {
  saving.value = true
  try {
    ensureSelections()
    aiForm.value.connections.forEach(conn => { conn.model_names = conn.models.map(model => model.model_name) })
    await settingsApi.updateSettings({ ai: aiForm.value })
    ElMessage.success('大模型配置已保存')
  } catch (error: any) {
    ElMessage.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>
