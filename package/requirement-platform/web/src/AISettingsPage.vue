<template>
  <section>
    <div class="page-head">
      <div class="page-head-left">
        <div><h1>AI 模型设置</h1><p class="sub">集中管理模型连接，并按任务配置主模型与备用模型。</p></div>
      </div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-alert v-if="settings?.legacy_environment_configured" type="info" :closable="false" show-icon title="检测到环境变量兼容配置">
      未保存任务路由时，提交前分析和需求分诊仍使用 RP_AI_API_URL / RP_AI_MODEL。保存路由后以页面配置为准。
    </el-alert>

    <article class="panel settings-block">
      <h2>添加模型连接</h2>
      <el-form label-position="top" @submit.prevent="createConnection">
        <div class="connection-grid">
          <el-form-item label="连接名称"><el-input v-model="newConnection.name" placeholder="例如 OpenAI 主连接" /></el-form-item>
          <el-form-item label="接口地址"><el-input v-model="newConnection.api_base" placeholder="https://api.openai.com/v1" /></el-form-item>
          <el-form-item label="API Key"><el-input v-model="newConnection.api_key" type="password" show-password autocomplete="new-password" placeholder="本地模型可留空" /></el-form-item>
          <el-form-item label="超时（秒）"><el-input-number v-model="newConnection.timeout_seconds" :min="3" :max="180" /></el-form-item>
        </div>
        <el-button type="primary" native-type="submit" :loading="saving">添加连接</el-button>
      </el-form>
    </article>

    <div class="connection-list">
      <article v-for="connection in settings?.connections || []" :key="connection.id" class="panel settings-block">
        <div class="block-head">
          <div><h2>{{ connection.name }}</h2><p>{{ connection.provider }} · {{ connection.models.length }} 个模型</p></div>
          <el-switch v-model="connection.enabled" active-text="启用" @change="saveConnection(connection)" />
        </div>
        <div class="connection-grid">
          <el-form-item label="连接名称"><el-input v-model="connection.name" /></el-form-item>
          <el-form-item label="接口地址"><el-input v-model="connection.api_base" /></el-form-item>
          <el-form-item :label="`API Key ${connection.api_key_hint || '未设置'}`">
            <el-input v-model="connectionKeys[connection.id]" type="password" show-password autocomplete="new-password" placeholder="留空表示不修改" />
          </el-form-item>
          <el-form-item label="超时（秒）"><el-input-number v-model="connection.timeout_seconds" :min="3" :max="180" /></el-form-item>
        </div>
        <div class="actions">
          <el-button :loading="saving" @click="saveConnection(connection)">保存连接</el-button>
          <el-button :disabled="!connection.models.length" @click="testConnection(connection)">测试连接</el-button>
          <el-button v-if="connection.has_api_key" @click="clearConnectionKey(connection)">清除密钥</el-button>
          <el-button type="danger" plain @click="removeConnection(connection)">删除</el-button>
        </div>

        <div class="models">
          <div class="models-head"><h3>模型</h3><span>关闭 JSON Mode 可兼容不支持 response_format 的服务。</span></div>
          <div v-for="model in connection.models" :key="model.id" class="model-row">
            <el-input v-model="model.display_name" placeholder="显示名称" />
            <el-input v-model="model.model_name" placeholder="上游模型名" />
            <el-input-number v-model="model.context_window" :min="1024" :max="10000000" placeholder="上下文" />
            <el-checkbox v-model="model.supports_json_mode">JSON Mode</el-checkbox>
            <el-switch v-model="model.enabled" active-text="启用" />
            <div class="row-actions"><el-button size="small" @click="saveModel(model)">保存</el-button><el-button size="small" type="danger" link @click="removeModel(model)">删除</el-button></div>
          </div>
          <div class="model-row add-model">
            <el-input v-model="modelDraft(connection.id).display_name" placeholder="显示名称" />
            <el-input v-model="modelDraft(connection.id).model_name" placeholder="模型名，例如 gpt-5-mini" />
            <el-input-number v-model="modelDraft(connection.id).context_window" :min="1024" :max="10000000" placeholder="上下文" />
            <el-checkbox v-model="modelDraft(connection.id).supports_json_mode">JSON Mode</el-checkbox>
            <span></span>
            <el-button type="primary" plain @click="addModel(connection.id)">添加模型</el-button>
          </div>
        </div>
      </article>
    </div>

    <article class="panel settings-block">
      <h2>任务模型路由</h2>
      <p class="route-help">列表中的第一个模型是主模型，其余模型按顺序作为失败兜底。禁用路由会明确关闭该任务的 AI。</p>
      <div v-for="route in settings?.routes || []" :key="route.task_type" class="route-row">
        <div><strong>{{ route.label }}</strong><p>{{ route.description }}<span v-if="route.source === 'environment'"> · 当前使用环境变量</span></p></div>
        <el-switch v-model="route.enabled" />
        <el-select v-model="route.model_ids" multiple filterable placeholder="依次选择主模型和备用模型">
          <el-option v-for="option in modelOptions" :key="option.id" :label="option.label" :value="option.id" :disabled="!option.enabled" />
        </el-select>
        <el-button @click="saveRoute(route)">保存路由</el-button>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type AIConnection, type AIModel, type AISettings, type AITaskRoute } from './api'

const loading = ref(false), saving = ref(false)
const settings = ref<AISettings | null>(null)
const connectionKeys = reactive<Record<string, string>>({})
const modelDrafts = reactive<Record<string, { model_name: string; display_name: string; context_window?: number; supports_json_mode: boolean }>>({})
const newConnection = reactive({ name: '', api_base: '', api_key: '', timeout_seconds: 45 })
const emptyModel = () => ({ model_name: '', display_name: '', context_window: 128000, supports_json_mode: true })
function modelDraft(connectionId: string) { return modelDrafts[connectionId] ||= emptyModel() }
const modelOptions = computed(() => (settings.value?.connections || []).flatMap(connection => connection.models.map(model => ({
  id: model.id, label: `${connection.name} / ${model.display_name || model.model_name}`,
  enabled: connection.enabled && model.enabled,
}))))

function message(error: any) { return error?.response?.data?.msg || error?.response?.data?.detail || '操作失败' }
async function load() {
  loading.value = true
  try {
    settings.value = await api.aiSettings()
    for (const connection of settings.value.connections) {
      connectionKeys[connection.id] = ''
      modelDrafts[connection.id] ||= emptyModel()
    }
  } catch (error) { ElMessage.error(message(error)) } finally { loading.value = false }
}
async function createConnection() {
  saving.value = true
  try {
    await api.createAIConnection({ ...newConnection, provider: 'openai_compatible', enabled: true, priority: 100 })
    Object.assign(newConnection, { name: '', api_base: '', api_key: '', timeout_seconds: 45 })
    ElMessage.success('模型连接已添加'); await load()
  } catch (error) { ElMessage.error(message(error)) } finally { saving.value = false }
}
async function saveConnection(connection: AIConnection) {
  saving.value = true
  try {
    await api.updateAIConnection(connection.id, { name: connection.name, api_base: connection.api_base,
      api_key: connectionKeys[connection.id] || undefined, enabled: connection.enabled,
      timeout_seconds: connection.timeout_seconds, priority: connection.priority })
    connectionKeys[connection.id] = ''; ElMessage.success('连接已保存'); await load()
  } catch (error) { ElMessage.error(message(error)) } finally { saving.value = false }
}
async function removeConnection(connection: AIConnection) {
  try { await ElMessageBox.confirm(`删除连接“${connection.name}”及其全部模型？相关任务路由会自动清理。`, '删除模型连接'); await api.deleteAIConnection(connection.id); await load() }
  catch (error) { if (error !== 'cancel') ElMessage.error(message(error)) }
}
async function clearConnectionKey(connection: AIConnection) {
  try { await ElMessageBox.confirm('清除后，该连接只能访问无需鉴权的本地服务。', '清除 API Key'); await api.updateAIConnection(connection.id, { clear_api_key: true }); ElMessage.success('API Key 已清除'); await load() }
  catch (error) { if (error !== 'cancel') ElMessage.error(message(error)) }
}
async function addModel(connectionId: string) {
  const draft = modelDraft(connectionId)
  try { await api.createAIModel(connectionId, { ...draft, enabled: true }); modelDrafts[connectionId] = emptyModel(); ElMessage.success('模型已添加'); await load() }
  catch (error) { ElMessage.error(message(error)) }
}
async function saveModel(model: AIModel) {
  try { await api.updateAIModel(model.id, { model_name: model.model_name, display_name: model.display_name,
    enabled: model.enabled, supports_json_mode: model.supports_json_mode, context_window: model.context_window || null }); ElMessage.success('模型已保存'); await load() }
  catch (error) { ElMessage.error(message(error)) }
}
async function removeModel(model: AIModel) {
  try { await ElMessageBox.confirm(`删除模型“${model.display_name || model.model_name}”？`, '删除模型'); await api.deleteAIModel(model.id); await load() }
  catch (error) { if (error !== 'cancel') ElMessage.error(message(error)) }
}
async function testConnection(connection: AIConnection) {
  try { const result = await api.testAIConnection(connection.id); result.available ? ElMessage.success(`连接成功：${result.response || 'OK'}`) : ElMessage.error(`连接失败：${result.error}`) }
  catch (error) { ElMessage.error(message(error)) }
}
async function saveRoute(route: AITaskRoute) {
  try { await api.updateAITaskRoute(route.task_type, { enabled: route.enabled, model_ids: route.model_ids }); ElMessage.success(`${route.label}路由已保存`); await load() }
  catch (error) { ElMessage.error(message(error)) }
}
onMounted(load)
</script>

<style scoped>
.page-head { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:20px; }.page-head h1 { margin:0; }.sub { color:var(--rp-text-2); }
.settings-block { margin-top:18px; padding:20px; }.settings-block h2 { margin:0 0 14px; font-size:18px; }
.connection-list { display:grid; gap:16px; }.connection-grid { display:grid; grid-template-columns:1fr 2fr 1.5fr 150px; gap:12px; }
.block-head,.models-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }.block-head h2,.models-head h3 { margin:0; }.block-head p,.models-head span,.route-help,.route-row p { color:var(--rp-text-3); font-size:13px; }
.actions,.row-actions { display:flex; flex-wrap:wrap; gap:8px; }.models { margin-top:20px; border-top:1px solid var(--rp-border); padding-top:16px; }
.model-row { display:grid; grid-template-columns:1fr 1.3fr 150px 110px 90px auto; gap:10px; align-items:center; margin-top:10px; }.add-model { padding-top:10px; border-top:1px dashed var(--rp-border); }
.route-row { display:grid; grid-template-columns:minmax(190px,1fr) 60px minmax(280px,2fr) auto; gap:14px; align-items:center; padding:14px 0; border-top:1px solid var(--rp-border); }.route-row p { margin:4px 0 0; }
@media (max-width:900px) { .connection-grid,.model-row,.route-row { grid-template-columns:1fr; }.model-row { padding:12px 0; border-top:1px solid var(--rp-border); }.route-row { align-items:stretch; } }
</style>
