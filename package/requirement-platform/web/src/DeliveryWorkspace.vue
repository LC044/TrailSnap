<template>
  <section class="panel workspace">
    <header class="workspace-head">
      <div><h2>规格与执行</h2><p>批准的规格是 Agent 唯一执行依据。</p></div>
      <span v-if="latestSpec" class="spec-state">v{{ latestSpec.revision }} · {{ latestSpec.status }}</span>
    </header>

    <el-alert v-if="approvedSpec" type="success" :closable="false" title="规格已冻结">
      基线 {{ approvedSpec.content.repository }} / {{ approvedSpec.content.target_branch }} @ {{ String(approvedSpec.content.base_sha).slice(0, 12) }}
    </el-alert>
    <div v-if="approvedSpec && !draftSpec && !creatingRevision" class="revision-actions">
      <el-button @click="startRevision">创建新规格修订</el-button>
    </div>

    <el-form v-if="!approvedSpec || draftSpec || creatingRevision" label-position="top" class="spec-form">
      <div class="two-columns">
        <el-form-item label="问题"><el-input v-model="form.problem" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="用户场景"><el-input v-model="form.user_scenario" type="textarea" :rows="3" /></el-form-item>
      </div>
      <el-form-item label="目标"><el-input v-model="form.goal" type="textarea" :rows="2" /></el-form-item>
      <div class="two-columns">
        <el-form-item label="范围（每行一项）"><el-input v-model="form.in_scope" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="非目标（每行一项）"><el-input v-model="form.out_of_scope" type="textarea" :rows="4" /></el-form-item>
      </div>
      <el-form-item label="行为与边界规则（每行一项）"><el-input v-model="form.behavior_rules" type="textarea" :rows="3" /></el-form-item>
      <div class="criteria-head"><strong>验收标准</strong><el-button size="small" @click="addCriterion">增加 AC</el-button></div>
      <article v-for="(criterion, index) in form.acceptance" :key="index" class="criterion">
        <div class="criterion-title"><el-input v-model="criterion.id" placeholder="AC-01" /><el-button link type="danger" @click="form.acceptance.splice(index, 1)">删除</el-button></div>
        <el-input v-model="criterion.given" placeholder="Given：前置条件" />
        <el-input v-model="criterion.when" placeholder="When：用户行为或事件" />
        <el-input v-model="criterion.then" placeholder="Then：可观察结果" />
        <div class="criterion-meta"><el-input v-model="criterion.verification" placeholder="验证方式，如 e2e" /><el-input v-model="criterion.dataset" placeholder="数据集（可选）" /></div>
      </article>
      <div class="two-columns">
        <el-form-item label="约束（每行一项）"><el-input v-model="form.constraints" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="风险（每行一项）"><el-input v-model="form.risks" type="textarea" :rows="3" /></el-form-item>
      </div>
      <el-form-item label="阻塞问题（每行一项；存在时不能批准）"><el-input v-model="form.blocking_questions" type="textarea" :rows="2" /></el-form-item>
      <div class="workspace-actions">
        <el-button :loading="busy" @click="saveSpec">{{ draftSpec ? '保存草稿' : '创建规格草稿' }}</el-button>
        <el-button v-if="draftSpec" type="primary" :loading="busy" @click="approve">批准规格</el-button>
      </div>
    </el-form>

    <div v-if="approvedSpec" class="delivery-section">
      <div class="criteria-head"><strong>交付任务</strong><el-button v-if="!tasks.length" type="primary" :loading="busy" @click="createTask">创建任务</el-button></div>
      <article v-for="task in tasks" :key="task.id" class="task-card">
        <div class="task-title"><strong>{{ task.state }}</strong><code>{{ task.id }}</code></div>
        <p>{{ task.repository }} / {{ task.target_branch }} @ {{ task.base_sha.slice(0, 12) }}</p>
        <p v-if="task.blocked_reason" class="blocked">{{ task.blocked_reason }}</p>
        <div v-for="run in task.runs" :key="run.id" class="run-card">
          <div><strong>{{ run.provider }} · {{ run.status }}</strong><span>{{ run.runner_name }}</span></div>
          <small>attempt {{ run.attempt_id }} · 租约至 {{ formatTime(run.lease_expires_at) }}</small>
          <div v-for="question in run.questions.filter(item => item.status === 'open')" :key="question.id" class="run-question">
            <span>{{ question.question }}</span><el-button size="small" @click="answerQuestion(question.id, run.state_version)">答复</el-button>
          </div>
          <el-button v-if="['running', 'waiting_input'].includes(run.status)" size="small" type="danger" plain @click="cancel(run.id)">取消执行</el-button>
        </div>
        <a v-for="pr in task.pull_requests" :key="pr.id" :href="pr.url" target="_blank" rel="noopener noreferrer">PR #{{ pr.number }} · {{ pr.state }}</a>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type DeliveryTask, type Requirement, type RequirementSpec } from './api'

const props = defineProps<{ requirement: Requirement; userRole: string }>()
const emit = defineEmits<{ refresh: [] }>()
const busy = ref(false)
const creatingRevision = ref(false)
const specs = computed(() => props.requirement.specs || [])
const tasks = computed<DeliveryTask[]>(() => props.requirement.delivery_tasks || [])
const latestSpec = computed(() => specs.value[0])
const draftSpec = computed(() => specs.value.find(item => item.status === 'draft'))
const approvedSpec = computed(() => specs.value.find(item => item.status === 'approved'))
const lines = (values?: unknown[]) => (values || []).join('\n')
const values = (text: string) => text.split('\n').map(item => item.trim()).filter(Boolean)
const emptyCriterion = (index: number) => ({ id: `AC-${String(index + 1).padStart(2, '0')}`, given: '', when: '', then: '', required: true, verification: 'e2e', dataset: '' })
const form = reactive({ problem: '', user_scenario: '', goal: '', in_scope: '', out_of_scope: '', behavior_rules: '',
  constraints: '', risks: '', blocking_questions: '', acceptance: [emptyCriterion(0)] })

function loadForm(spec?: RequirementSpec) {
  const content = spec?.content || {}
  form.problem = String(content.problem || props.requirement.confirmed_summary || props.requirement.description)
  form.user_scenario = String(content.user_scenario || props.requirement.description)
  form.goal = String(content.goal || props.requirement.expected_behavior || '')
  form.in_scope = lines(content.in_scope)
  form.out_of_scope = lines(content.out_of_scope)
  form.behavior_rules = lines(content.behavior_rules)
  form.constraints = lines(content.constraints)
  form.risks = lines(content.risks)
  form.blocking_questions = lines(content.blocking_questions)
  form.acceptance = Array.isArray(content.acceptance) && content.acceptance.length
    ? content.acceptance.map((item: any) => ({ ...item, dataset: item.dataset || '' })) : [emptyCriterion(0)]
}
watch(() => props.requirement.id, () => { creatingRevision.value = false; loadForm(draftSpec.value) }, { immediate: true })
watch(draftSpec, value => { if (value) creatingRevision.value = false; loadForm(value) })
const addCriterion = () => form.acceptance.push(emptyCriterion(form.acceptance.length))
function startRevision() { if (approvedSpec.value) { loadForm(approvedSpec.value); creatingRevision.value = true } }

function content() {
  return { problem: form.problem, user_scenario: form.user_scenario, goal: form.goal,
    confirmed_facts: [], references: [`REQ-${props.requirement.public_number}`], in_scope: values(form.in_scope),
    out_of_scope: values(form.out_of_scope), behavior_rules: values(form.behavior_rules),
    acceptance: form.acceptance.map(item => ({ ...item, dataset: item.dataset || null })),
    test_data_requirements: [], environment_requirements: [], constraints: values(form.constraints), risks: values(form.risks),
    dependencies: [], release_requirements: [], rollback_requirements: [], blocking_questions: values(form.blocking_questions),
    assumptions: [], repository: 'LC044/TrailSnap', target_branch: 'master' }
}

async function saveSpec() {
  busy.value = true
  try {
    if (draftSpec.value && draftSpec.value.requirement_revision === props.requirement.content_revision) await api.updateSpec(draftSpec.value.id, { content: content(), expected_state_version: draftSpec.value.state_version })
    else await api.createSpec(props.requirement.id, { content: content(), expected_requirement_state_version: props.requirement.state_version })
    creatingRevision.value = false
    ElMessage.success('规格草稿已保存'); emit('refresh')
  } catch (error: any) { ElMessage.error(error?.response?.data?.msg || '保存失败') } finally { busy.value = false }
}

async function approve() {
  if (!draftSpec.value) return
  busy.value = true
  try {
    await api.approveSpec(draftSpec.value.id, { expected_state_version: draftSpec.value.state_version })
    ElMessage.success('规格已批准并冻结基线'); emit('refresh')
  } catch (error: any) {
    const message = error?.response?.data?.msg || '批准失败'
    if (props.userRole === 'owner' && message.includes('GitHub')) {
      try {
        const prompt = await ElMessageBox.prompt('GitHub 基线解析失败，可输入完整 40 位 SHA 作为受审计的 Owner 兜底。', '手工基线', { inputPattern: /^[0-9a-fA-F]{40}$/, inputErrorMessage: '请输入完整 40 位 SHA' })
        await api.approveSpec(draftSpec.value.id, { expected_state_version: draftSpec.value.state_version, manual_base_sha: prompt.value })
        ElMessage.success('规格已使用手工基线批准'); emit('refresh')
      } catch (fallbackError: any) { if (fallbackError !== 'cancel') ElMessage.error(fallbackError?.response?.data?.msg || '批准失败') }
    } else ElMessage.error(message)
  } finally { busy.value = false }
}

async function createTask() {
  if (!approvedSpec.value) return
  busy.value = true
  try { await api.createDeliveryTask({ spec_id: approvedSpec.value.id, risk_level: props.requirement.risk_level }); ElMessage.success('交付任务已创建'); emit('refresh') }
  catch (error: any) { ElMessage.error(error?.response?.data?.msg || '创建失败') } finally { busy.value = false }
}
async function cancel(runId: string) { await api.cancelRun(runId); ElMessage.success('执行已取消'); emit('refresh') }
async function answerQuestion(questionId: string, runVersion: number) {
  try {
    const prompt = await ElMessageBox.prompt('请输入对 Agent 的明确答复。若涉及范围变化，请取消后创建新规格修订。', '答复澄清')
    await api.answerRunQuestion(questionId, { answer: prompt.value, expected_run_state_version: runVersion, requires_spec_revision: false })
    ElMessage.success('答复已提交'); emit('refresh')
  } catch (error: any) { if (error !== 'cancel') ElMessage.error(error?.response?.data?.msg || '答复失败') }
}
const formatTime = (value: string) => new Date(value).toLocaleString('zh-CN')
</script>

<style scoped>
.workspace { margin-top: 20px; padding: 18px; }
.workspace-head, .criteria-head, .task-title, .run-card > div:first-child { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.workspace-head h2 { margin: 0; font-size: 18px; }.workspace-head p { margin: 4px 0 0; color: var(--rp-text-3); font-size: 13px; }
.spec-state { color: var(--rp-primary); font-size: 13px; }.spec-form, .delivery-section { margin-top: 18px; }
.revision-actions { display: flex; justify-content: flex-end; margin-top: 10px; }
.two-columns, .criterion-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.criterion { display: grid; gap: 8px; margin: 10px 0; padding: 12px; border: 1px solid var(--rp-border); border-radius: 10px; }
.criterion-title { display: grid; grid-template-columns: 140px auto; justify-content: space-between; gap: 8px; }
.workspace-actions { display: flex; justify-content: flex-end; gap: 8px; }.task-card { margin-top: 12px; padding: 14px; border: 1px solid var(--rp-border); border-radius: 10px; }
.task-card p, .run-card small { color: var(--rp-text-3); font-size: 12px; }.task-card code { overflow-wrap: anywhere; }.blocked { color: #b45309 !important; }
.run-card { display: grid; gap: 8px; margin: 10px 0; padding: 10px; background: var(--rp-bg); border-radius: 8px; }.run-card span { color: var(--rp-text-3); font-size: 12px; }
.run-question { display: flex; justify-content: space-between; gap: 8px; }.task-card a { color: var(--rp-primary); font-size: 13px; }.task-card a:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; border-radius: 4px; }
@media (max-width: 680px) { .two-columns, .criterion-meta { grid-template-columns: 1fr; }.workspace-head { align-items: flex-start; }.criterion-title { grid-template-columns: 1fr auto; } }
</style>
