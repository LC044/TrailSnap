<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand">行影集 · 需求平台</div>
        <nav class="nav" aria-label="主导航">
          <button v-for="item in visibleTabs" :key="item.key" :class="{ active: tab === item.key }" @click="switchTab(item.key)">
            {{ item.label }}
          </button>
        </nav>
        <el-button v-if="user" text @click="logout">{{ user.username }} · 退出</el-button>
        <el-button v-else type="primary" plain @click="authDialog = true">登录</el-button>
      </div>
    </header>

    <main class="main">
      <section v-if="tab === 'public'">
        <div class="hero">
          <div><h1>一起把行影集变得更好</h1><p>查看公开需求、候选功能和版本进展。</p></div>
          <el-button type="primary" size="large" @click="switchTab('submit')">提交需求</el-button>
        </div>
        <div class="panel filters">
          <el-input v-model="filters.q" clearable placeholder="搜索标题或描述" @keyup.enter="loadRequirements" />
          <el-select v-model="filters.type" clearable placeholder="全部类型" @change="loadRequirements">
            <el-option label="Bug" value="bug" /><el-option label="改进" value="improvement" /><el-option label="新功能" value="feature" />
          </el-select>
          <el-select v-model="filters.status" clearable placeholder="全部状态" @change="loadRequirements">
            <el-option v-for="status in statusOptions" :key="status" :label="statusLabel(status)" :value="status" />
          </el-select>
        </div>
        <RequirementCards :items="requirements" :manager="isManager" @follow="follow" @review="openReview" />
      </section>

      <section v-else-if="tab === 'submit'">
        <div class="hero"><div><h1>提交需求</h1><p>报告问题、提出改进或分享新想法。</p></div></div>
        <div v-if="!user" class="panel empty">请先登录或注册，再提交需求。<div class="actions" style="justify-content:center"><el-button type="primary" @click="authDialog = true">登录 / 注册</el-button></div></div>
        <el-form v-else class="panel form-grid" label-position="top" @submit.prevent="submitRequirement">
          <el-form-item label="类型"><el-select v-model="requirementForm.type"><el-option label="Bug" value="bug" /><el-option label="改进" value="improvement" /><el-option label="新功能" value="feature" /></el-select></el-form-item>
          <el-form-item label="影响程度"><el-select v-model="requirementForm.severity"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item>
          <el-form-item class="span-2" label="标题"><el-input v-model="requirementForm.title" maxlength="160" show-word-limit /></el-form-item>
          <el-form-item class="span-2" label="需求或问题描述"><el-input v-model="requirementForm.description" type="textarea" :rows="5" maxlength="8000" show-word-limit /></el-form-item>
          <el-form-item label="当前行为"><el-input v-model="requirementForm.current_behavior" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="期望行为"><el-input v-model="requirementForm.expected_behavior" type="textarea" :rows="3" /></el-form-item>
          <el-form-item v-if="requirementForm.type === 'bug'" class="span-2" label="复现步骤"><el-input v-model="requirementForm.steps_to_reproduce" type="textarea" :rows="4" /></el-form-item>
          <el-form-item label="TrailSnap 版本"><el-input v-model="requirementForm.product_version" placeholder="例如 0.14.1" /></el-form-item>
          <el-form-item label="公开范围"><el-radio-group v-model="requirementForm.visibility"><el-radio value="public">公开</el-radio><el-radio value="private">仅本人和管理员</el-radio></el-radio-group></el-form-item>
          <div class="span-2 actions"><el-button type="primary" :loading="busy" native-type="submit">确认提交</el-button></div>
        </el-form>
      </section>

      <section v-else-if="tab === 'mine'">
        <div class="hero"><div><h1>我的需求</h1><p>查看自己提交的需求和处理进度。</p></div></div>
        <div v-if="!user" class="panel empty">登录后查看自己的需求。</div>
        <RequirementCards v-else :items="myRequirements" :manager="isManager" @follow="follow" @review="openReview" />
      </section>

      <section v-else-if="tab === 'admin' && isManager">
        <div class="hero"><div><h1>需求审核</h1><p>AI 提供建议，最终结论由所有者或管理员确认。</p></div></div>
        <div class="panel filters">
          <el-select v-model="adminStatus" clearable placeholder="全部状态" @change="loadAdmin"><el-option v-for="status in reviewStatuses" :key="status" :label="statusLabel(status)" :value="status" /></el-select>
          <el-button type="primary" @click="loadAdmin">刷新</el-button>
        </div>
        <RequirementCards :items="adminRequirements" manager @follow="follow" @review="openReview" />
      </section>

      <section v-else-if="tab === 'versions'">
        <div class="hero">
          <div><h1>版本批次</h1><p>人工选择进入版本开发候选的需求。</p></div>
          <el-button v-if="isManager" type="primary" @click="batchDialog = true">创建版本批次</el-button>
        </div>
        <div v-if="!batches.length" class="panel empty">暂无版本批次</div>
        <div v-else class="batch-grid">
          <article v-for="batch in batches" :key="batch.id" class="panel batch-card">
            <div class="card-head"><div><h2 class="card-title">{{ batch.name }}</h2><div class="meta"><span>{{ batch.version_name }}</span><span>{{ batch.batch_type }}</span></div></div><span :class="['tag', batch.status]">{{ statusLabel(batch.status) }}</span></div>
            <p class="description">{{ batch.goal }}</p>
            <a v-if="batch.github_milestone_url" :href="batch.github_milestone_url" target="_blank" rel="noopener">GitHub Milestone #{{ batch.github_milestone_number }}</a>
            <ul class="batch-items">
              <li v-for="item in batch.items" :key="item.id">
                <strong>{{ item.requirement_snapshot.title }}</strong>
                <div class="meta"><span>{{ deliveryLabel(item.delivery_status) }}</span></div>
                <div v-if="isManager" class="actions">
                  <el-select v-if="!['planning','candidate_selection','published','completed','cancelled'].includes(batch.status)" :model-value="item.delivery_status" size="small" style="width:150px" @change="updateDelivery(batch.id, item.id, String($event))">
                    <el-option v-for="status in deliveryStatuses" :key="status" :label="deliveryLabel(status)" :value="status" />
                  </el-select>
                  <el-button v-if="['planning','candidate_selection'].includes(batch.status)" size="small" type="danger" plain @click="removeBatchItem(batch.id, item.id)">移出</el-button>
                </div>
              </li>
            </ul>
            <div v-if="isManager" class="actions">
              <el-select v-if="['planning','candidate_selection'].includes(batch.status)" v-model="candidateSelection[batch.id]" filterable placeholder="选择候选需求" style="width:240px">
                <el-option v-for="req in candidates" :key="req.id" :label="req.title" :value="req.id" />
              </el-select>
              <el-button v-if="['planning','candidate_selection'].includes(batch.status)" @click="addCandidate(batch.id)">加入</el-button>
              <el-button v-if="batch.items.length && ['planning','candidate_selection'].includes(batch.status)" type="primary" @click="lockBatch(batch.id)">锁定范围</el-button>
              <el-dropdown v-if="allowedBatchStatuses(batch.status).length" @command="updateBatchState(batch.id, String($event))">
                <el-button>更新状态</el-button>
                <template #dropdown><el-dropdown-menu><el-dropdown-item v-for="status in allowedBatchStatuses(batch.status)" :key="status" :command="status">{{ statusLabel(status) }}</el-dropdown-item></el-dropdown-menu></template>
              </el-dropdown>
            </div>
          </article>
        </div>
      </section>

      <section v-else-if="tab === 'users' && user?.role === 'owner'">
        <div class="hero"><div><h1>角色管理</h1><p>所有者可以任命或移除管理员。</p></div></div>
        <el-table :data="users" class="panel">
          <el-table-column prop="username" label="用户名" /><el-table-column prop="email" label="邮箱" />
          <el-table-column prop="role" label="角色"><template #default="scope"><span class="tag">{{ roleLabel(scope.row.role) }}</span></template></el-table-column>
          <el-table-column label="操作"><template #default="scope"><el-button v-if="scope.row.role !== 'owner'" size="small" @click="toggleRole(scope.row)">{{ scope.row.role === 'admin' ? '降为查看者' : '设为管理员' }}</el-button></template></el-table-column>
        </el-table>
      </section>
    </main>

    <el-dialog v-model="authDialog" title="登录需求平台" width="min(92vw, 460px)">
      <el-tabs v-model="authMode"><el-tab-pane label="登录" name="login" /><el-tab-pane label="注册" name="register" /></el-tabs>
      <el-form label-position="top" @submit.prevent="submitAuth">
        <el-form-item v-if="authMode === 'register'" label="用户名"><el-input v-model="authForm.username" autocomplete="username" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="authForm.email" autocomplete="email" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="authForm.password" type="password" show-password autocomplete="current-password" /></el-form-item>
        <el-button type="primary" :loading="busy" native-type="submit">{{ authMode === 'login' ? '登录' : '注册' }}</el-button>
      </el-form>
    </el-dialog>

    <el-dialog v-model="reviewDialog" title="人工审核" width="min(92vw, 560px)">
      <p v-if="reviewTarget"><strong>{{ reviewTarget.title }}</strong></p>
      <el-form label-position="top">
        <el-form-item label="审核结论"><el-select v-model="reviewForm.action"><el-option label="进入候选池" value="candidate" /><el-option label="需要补充" value="needs_information" /><el-option label="暂缓" value="deferred" /><el-option label="拒绝" value="rejected" /><el-option label="重复需求" value="duplicate" /><el-option label="关闭" value="close" /></el-select></el-form-item>
        <el-form-item label="原因"><el-input v-model="reviewForm.reason" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="优先级"><el-select v-model="reviewForm.priority"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item>
        <el-form-item label="风险"><el-select v-model="reviewForm.risk_level"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item>
        <el-form-item v-if="reviewForm.action === 'duplicate'" label="主需求 ID"><el-input v-model="reviewForm.duplicate_of_id" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="reviewDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="submitReview">确认</el-button></template>
    </el-dialog>

    <el-dialog v-model="batchDialog" title="创建版本批次" width="min(92vw, 560px)">
      <el-form label-position="top">
        <el-form-item label="版本名称"><el-input v-model="batchForm.name" /></el-form-item>
        <el-form-item label="版本号"><el-input v-model="batchForm.version_name" placeholder="例如 v0.15.0" /></el-form-item>
        <el-form-item label="版本目标"><el-input v-model="batchForm.goal" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="batchForm.batch_type"><el-option label="修复" value="fix" /><el-option label="功能" value="feature" /><el-option label="重大" value="major" /><el-option label="紧急修复" value="hotfix" /></el-select></el-form-item>
        <el-form-item label="计划日期"><el-input v-model="batchForm.target_date" type="date" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="batchDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="createBatch">创建</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { ElButton, ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { api, type Batch, type Requirement, type User } from './api'

const statusLabels: Record<string, string> = { submitted:'待分析',triaging:'分析中',pending_review:'待审核',needs_information:'待补充',candidate:'开发候选',rejected:'已拒绝',deferred:'已暂缓',duplicate:'已合并',scheduled:'已排期',developing:'开发中',testing:'测试中',release_ready:'待发布',released:'已发布',withdrawn:'已撤回',closed:'已关闭',planning:'规划中',candidate_selection:'候选确认中',scope_locked:'范围已锁定',published:'已发布',completed:'已完成',blocked:'已阻塞',paused:'已暂停',cancelled:'已取消' }
const deliveryLabels: Record<string,string> = { not_started:'未开始',developing:'开发中',pr_open:'PR 已创建',testing:'测试中',completed:'已完成',blocked:'已阻塞',removed:'已移出' }
const statusLabel = (value: string) => statusLabels[value] || value
const deliveryLabel = (value: string) => deliveryLabels[value] || value
const roleLabel = (value: string) => ({viewer:'查看者',admin:'管理员',owner:'所有者'}[value] || value)
const errorMessage = (error: unknown) => axios.isAxiosError(error) ? String(error.response?.data?.msg || error.response?.data?.detail || error.message) : String(error)

const RequirementCards = defineComponent({
  props: { items: { type: Array as () => Requirement[], required: true }, manager: Boolean },
  emits: ['follow','review'],
  setup(props, { emit }) {
    return () => props.items.length ? h('div', { class:'cards' }, props.items.map(item => h('article', { key:item.id, class:'requirement-card' }, [
      h('div', { class:'card-head' }, [h('div', [h('h2', { class:'card-title' }, item.title), h('div', { class:'meta' }, [item.type, `影响：${item.severity}`, new Date(item.created_at).toLocaleString()])]), h('span', { class:['tag',item.status] }, statusLabel(item.status))]),
      h('p', { class:'description' }, item.description),
      item.triage ? h('div', { class:'panel', style:'margin:12px 0 0;padding:12px;background:#f8fafc' }, [h('strong','AI 分析'), h('p',{class:'description'},String(item.triage.summary || item.triage.recommendation || '分析已完成'))]) : null,
      item.review_reason ? h('p', { class:'meta' }, `审核说明：${item.review_reason}`) : null,
      h('div', { class:'actions' }, [h(ElButton,{size:'small',onClick:()=>emit('follow',item)},()=>`关注 ${item.follower_count || 0}`), item.github_issue_url ? h(ElButton,{size:'small',tag:'a',href:item.github_issue_url,target:'_blank'},()=>`GitHub #${item.github_issue_number}`) : null, props.manager ? h(ElButton,{size:'small',type:'primary',plain:true,onClick:()=>emit('review',item)},()=> '审核') : null])
    ]))) : h('div',{class:'panel empty'},'暂无需求')
  }
})

type Tab = 'public'|'submit'|'mine'|'admin'|'versions'|'users'
const tab = ref<Tab>('public')
const user = ref<User|null>(null)
const requirements = ref<Requirement[]>([]), myRequirements = ref<Requirement[]>([]), adminRequirements = ref<Requirement[]>([])
const batches = ref<Batch[]>([]), users = ref<User[]>([]), candidates = ref<Requirement[]>([])
const busy = ref(false), authDialog = ref(false), reviewDialog = ref(false), batchDialog = ref(false)
const authMode = ref<'login'|'register'>('login'), adminStatus = ref('pending_review')
const reviewTarget = ref<Requirement|null>(null)
const filters = reactive({ q:'', type:'', status:'' })
const authForm = reactive({ username:'', email:'', password:'' })
const requirementForm = reactive({ type:'feature', title:'', description:'', current_behavior:'', expected_behavior:'', steps_to_reproduce:'', severity:'medium', product_version:'', visibility:'public', environment:{} })
const reviewForm = reactive({ action:'candidate', reason:'', priority:'normal', risk_level:'medium', duplicate_of_id:'' })
const batchForm = reactive({ name:'', version_name:'', goal:'', batch_type:'feature', target_date:'', max_risk_level:'high' })
const candidateSelection = reactive<Record<string,string>>({})
const statusOptions = ['pending_review','candidate','scheduled','developing','testing','release_ready','released','deferred','rejected']
const reviewStatuses = ['submitted','triaging','pending_review','needs_information','candidate','deferred','rejected','duplicate']
const deliveryStatuses = ['not_started','developing','pr_open','testing','completed','blocked','removed']
const batchTransitions: Record<string,string[]> = {
  scope_locked:['developing','blocked','paused','cancelled'], developing:['testing','blocked','paused','cancelled'],
  testing:['developing','release_ready','blocked','paused','cancelled'], release_ready:['testing','published','blocked','paused','cancelled'],
  published:['completed'], blocked:['developing','testing','release_ready','paused','cancelled'],
  paused:['developing','testing','release_ready','blocked','cancelled'], completed:[], cancelled:[]
}
const allowedBatchStatuses = (status:string) => (batchTransitions[status] || []).filter(
  next => user.value?.role === 'owner' || !['completed','cancelled'].includes(next)
)
const isManager = computed(() => user.value?.role === 'admin' || user.value?.role === 'owner')
const visibleTabs = computed(() => [{key:'public',label:'公开需求'},{key:'submit',label:'提交需求'},{key:'mine',label:'我的需求'},{key:'versions',label:'版本计划'},...(isManager.value?[{key:'admin',label:'需求审核'}]:[]),...(user.value?.role==='owner'?[{key:'users',label:'角色管理'}]:[]) ] as {key:Tab;label:string}[])

async function loadRequirements() { const p=new URLSearchParams(); if(filters.q)p.set('q',filters.q);if(filters.type)p.set('type',filters.type);if(filters.status)p.set('status',filters.status); requirements.value=await api.requirements(`?${p}`) }
async function loadMine() { if(user.value) myRequirements.value=await api.requirements('?mine=true') }
async function loadAdmin() { if(isManager.value) adminRequirements.value=await api.requirements(adminStatus.value?`?status=${adminStatus.value}`:'') }
async function loadBatches() { batches.value=await api.batches(); if(isManager.value)candidates.value=await api.requirements('?status=candidate&limit=100') }
async function loadUsers() { if(user.value?.role==='owner') users.value=await api.users() }
async function switchTab(value: Tab) { tab.value=value; try { if(value==='public')await loadRequirements();if(value==='mine')await loadMine();if(value==='admin')await loadAdmin();if(value==='versions')await loadBatches();if(value==='users')await loadUsers() } catch(e){ElMessage.error(errorMessage(e))} }
async function restoreSession() { if(!localStorage.getItem('rp_token'))return; try{user.value=await api.me()}catch{localStorage.removeItem('rp_token')} }
async function submitAuth(){busy.value=true;try{const result=authMode.value==='login'?await api.login({identifier:authForm.email,password:authForm.password}):await api.register(authForm);localStorage.setItem('rp_token',result.token);user.value=result.user;authDialog.value=false;ElMessage.success('登录成功');await switchTab('public')}catch(e){ElMessage.error(errorMessage(e))}finally{busy.value=false}}
function logout(){localStorage.removeItem('rp_token');user.value=null;tab.value='public';void loadRequirements()}
async function submitRequirement(){busy.value=true;try{await api.createRequirement(requirementForm);Object.assign(requirementForm,{type:'feature',title:'',description:'',current_behavior:'',expected_behavior:'',steps_to_reproduce:'',severity:'medium',product_version:'',visibility:'public',environment:{}});ElMessage.success('需求已提交');await switchTab('mine')}catch(e){ElMessage.error(errorMessage(e))}finally{busy.value=false}}
async function follow(item:Requirement){if(!user.value){authDialog.value=true;return}try{await api.followRequirement(item.id);ElMessage.success('关注状态已更新');await switchTab(tab.value)}catch(e){ElMessage.error(errorMessage(e))}}
function openReview(item:Requirement){reviewTarget.value=item;Object.assign(reviewForm,{action:'candidate',reason:'',priority:item.priority||'normal',risk_level:item.risk_level||'medium',duplicate_of_id:''});reviewDialog.value=true}
async function submitReview(){if(!reviewTarget.value)return;busy.value=true;try{await api.review(reviewTarget.value.id,reviewForm);reviewDialog.value=false;ElMessage.success('审核结果已保存');await loadAdmin();await loadRequirements()}catch(e){ElMessage.error(errorMessage(e))}finally{busy.value=false}}
async function createBatch(){busy.value=true;try{await api.createBatch({...batchForm,target_date:batchForm.target_date||null});batchDialog.value=false;Object.assign(batchForm,{name:'',version_name:'',goal:'',batch_type:'feature',target_date:'',max_risk_level:'high'});ElMessage.success('版本批次已创建');await loadBatches()}catch(e){ElMessage.error(errorMessage(e))}finally{busy.value=false}}
async function addCandidate(batchId:string){const id=candidateSelection[batchId];if(!id)return;try{await api.addBatchItem(batchId,id);candidateSelection[batchId]='';await loadBatches()}catch(e){ElMessage.error(errorMessage(e))}}
async function removeBatchItem(batchId:string,itemId:string){try{await ElMessageBox.confirm('确认将该需求移出版本？','确认');await api.removeBatchItem(batchId,itemId);await loadBatches()}catch(e){if(e!=='cancel')ElMessage.error(errorMessage(e))}}
async function lockBatch(batchId:string){try{await ElMessageBox.confirm('锁定后需求范围将生成快照，确认继续？','锁定版本范围');await api.lockBatch(batchId);ElMessage.success('版本范围已锁定');await loadBatches()}catch(e){if(e!=='cancel')ElMessage.error(errorMessage(e))}}
async function updateBatchState(batchId:string,status:string){try{const reason=await ElMessageBox.prompt('请输入状态变更原因','更新版本状态',{inputPattern:/.{2,}/,inputErrorMessage:'至少输入两个字符'});await api.updateBatchStatus(batchId,status,reason.value);await loadBatches()}catch(e){if(e!=='cancel')ElMessage.error(errorMessage(e))}}
async function updateDelivery(batchId:string,itemId:string,status:string){try{await api.updateDeliveryStatus(batchId,itemId,status);await loadBatches()}catch(e){ElMessage.error(errorMessage(e))}}
async function toggleRole(row:User){try{await api.updateRole(row.id,row.role==='admin'?'viewer':'admin');await loadUsers()}catch(e){ElMessage.error(errorMessage(e))}}

onMounted(async()=>{
  const params = new URLSearchParams(window.location.search)
  const requestedTab = params.get('view') as Tab | null
  if (requestedTab && ['public','submit','mine','admin','versions','users'].includes(requestedTab)) tab.value=requestedTab
  const requestedType = params.get('type')
  if (requestedType && ['bug','improvement','feature'].includes(requestedType)) requirementForm.type=requestedType
  await restoreSession()
  if ((tab.value==='admin' && !isManager.value) || (tab.value==='users' && user.value?.role!=='owner')) tab.value='public'
  await Promise.all([loadRequirements(),loadBatches()])
  if (tab.value==='mine') await loadMine()
  if (tab.value==='admin') await loadAdmin()
  if (tab.value==='users') await loadUsers()
})
</script>
