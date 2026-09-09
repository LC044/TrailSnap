<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <img :src="logoUrl" alt="行影集" />
          <span>行影集</span>
          <span class="brand-sub">软件需求管理平台</span>
        </div>
        <nav class="nav" aria-label="主导航">
          <button v-for="item in visibleTabs" :key="item.key" :class="{ active: tab === item.key }" @click="switchTab(item.key)">
            {{ item.label }}
          </button>
        </nav>
        <div class="topbar-side">
          <button class="icon-btn" type="button" aria-label="通知" @click="onNotification">
            <el-icon :size="18"><Bell /></el-icon>
            <span v-if="false" class="dot"></span>
          </button>
          <el-dropdown v-if="user" trigger="click" @command="onUserCommand">
            <button class="user-chip" type="button">
              <span class="avatar" :style="{ width: '30px', height: '30px', fontSize: '13px', ...avatarColor(user.username) }">
                {{ user.username.slice(0, 1) }}
              </span>
              <span style="font-size: 14px">{{ user.username }}</span>
              <el-icon :size="12"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="mine">我的需求</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button v-else type="primary" @click="authDialog = true">登录 / 注册</el-button>
        </div>
      </div>
    </header>

    <main class="main">
      <!-- ============ 需求详情页 ============ -->
      <section v-if="detailRouteNumber">
        <div v-if="detailLoading" class="panel empty">正在加载 REQ-{{ detailRouteNumber }}…</div>
        <RequirementDetail
          v-else-if="detailTarget"
          :requirement="detailTarget"
          :history="detailHistory"
          :manager="isManager"
          :can-follow="canFollow"
          @back="closeDetail"
          @copy-link="copyRequirementLink(detailTarget)"
          @follow="followDetail"
          @edit="openEdit(detailTarget)"
          @review="openReview(detailTarget)"
          @download="downloadAttachment(detailTarget, $event)"
        />
        <div v-else class="panel empty">需求不存在或你没有查看权限。</div>
      </section>

      <!-- ============ 公开需求 ============ -->
      <section v-else-if="tab === 'public'">
        <div class="page-head">
          <div class="page-head-left">
            <div class="page-head-icon"><el-icon :size="26"><Document /></el-icon></div>
            <div>
              <h1>公开需求</h1>
              <p class="sub">一起把行影集变得更好</p>
              <p class="desc">浏览和参与社区提出的需求，共同推动产品进步。</p>
            </div>
          </div>
          <div class="page-head-actions">
            <div class="stat-cards">
              <div class="stat-card"><div class="num">{{ stats.total }}</div><div class="label">公开需求</div></div>
              <div class="stat-card"><div class="num">{{ stats.planned }}</div><div class="label">已规划</div></div>
              <div class="stat-card"><div class="num">{{ stats.developing }}</div><div class="label">开发中</div></div>
              <div class="stat-card"><div class="num">{{ stats.done }}</div><div class="label">已完成</div></div>
            </div>
            <el-button type="primary" size="large" :icon="Plus" @click="switchTab('submit')">提交需求</el-button>
          </div>
        </div>

        <div class="filters">
          <el-input v-model="filters.q" clearable placeholder="搜索 REQ 编号、标题、关键词或描述..." :prefix-icon="Search" class="search" @keyup.enter="loadRequirements" @clear="loadRequirements" />
          <el-select v-model="filters.type" clearable placeholder="全部类型" class="select" @change="loadRequirements">
            <el-option label="新功能" value="feature" /><el-option label="体验优化" value="improvement" /><el-option label="问题修复" value="bug" />
          </el-select>
          <el-select v-model="filters.status" clearable placeholder="全部状态" class="select" @change="loadRequirements">
            <el-option v-for="status in statusOptions" :key="status" :label="statusLabel(status)" :value="status" />
          </el-select>
          <el-select v-model="sortBy" placeholder="最新更新" class="sort" @change="sortRequirements">
            <el-option label="最新更新" value="updated" /><el-option label="最早提交" value="oldest" /><el-option label="关注最多" value="followers" />
          </el-select>
        </div>

        <RequirementTable :items="sortedRequirements" :manager="isManager" :user="user" @open="openDetail" @action="onRowAction" />
      </section>

      <!-- ============ 管理总览 ============ -->
      <section v-else-if="tab === 'dashboard' && isManager">
        <div class="page-head"><div class="page-head-left"><div class="page-head-icon"><el-icon :size="26"><DataAnalysis /></el-icon></div><div><h1>需求总览</h1><p class="desc">掌握需求规模、审核积压和版本推进情况。</p></div></div></div>
        <div v-if="dashboard" class="dashboard-cards">
          <article class="panel dashboard-card"><strong>{{ dashboard.total }}</strong><span>全部需求</span></article>
          <article class="panel dashboard-card"><strong>{{ dashboard.new_last_7_days }}</strong><span>近 7 天新增</span></article>
          <article class="panel dashboard-card"><strong>{{ dashboard.pending_review }}</strong><span>待处理</span></article>
          <article class="panel dashboard-card"><strong>{{ dashboard.in_progress }}</strong><span>开发发布中</span></article>
          <article class="panel dashboard-card"><strong>{{ dashboard.github_linked }}</strong><span>已关联 GitHub</span></article>
          <article class="panel dashboard-card"><strong>{{ dashboard.anonymous }}</strong><span>匿名提交</span></article>
        </div>
        <div v-if="dashboard" class="dashboard-grid">
          <article class="panel"><h2>状态分布</h2><div v-for="(count, status) in dashboard.by_status" :key="status" class="distribution-row"><span>{{ statusLabel(status) }}</span><strong>{{ count }}</strong></div></article>
          <article class="panel"><h2>类型分布</h2><div v-for="(count, kind) in dashboard.by_type" :key="kind" class="distribution-row"><span>{{ typeLabel(kind) }}</span><strong>{{ count }}</strong></div></article>
        </div>
      </section>

      <!-- ============ 提交需求 ============ -->
      <section v-else-if="tab === 'submit'">
        <div class="page-head">
          <div class="page-head-left">
            <div class="page-head-icon"><el-icon :size="26"><EditPen /></el-icon></div>
            <div>
              <h1>提交需求</h1>
              <p class="sub">分享你的想法，让行影集变得更好</p>
              <p class="desc">报告问题、提出改进建议或分享新想法，我们会认真对待每一条反馈。</p>
            </div>
          </div>
        </div>

        <div class="submit-layout">
          <el-form class="panel submit-form" label-position="top" @submit.prevent="submitRequirement" @paste="handlePaste">
            <el-alert v-if="!user" type="info" :closable="false" show-icon title="你正在匿名提交">
              无需登录即可提交。昵称和联系方式均为可选，联系方式仅管理员可见；匿名需求将公开展示。
            </el-alert>
            <div class="section">
              <h2 class="section-head"><el-icon><DocumentAdd /></el-icon>基本信息</h2>
              <el-form-item label="类型" required>
                <el-select v-model="requirementForm.type">
                  <el-option label="新功能" value="feature" /><el-option label="体验优化" value="improvement" /><el-option label="问题修复" value="bug" />
                </el-select>
                <div class="field-hint">选择最符合的类型，便于快速分类处理</div>
              </el-form-item>
              <el-form-item label="影响程度" required>
                <el-select v-model="requirementForm.severity">
                  <el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" />
                </el-select>
                <div class="field-hint">评估该需求对用户和业务的影响范围</div>
              </el-form-item>
              <el-form-item label="标题" required>
                <el-input v-model="requirementForm.title" maxlength="160" show-word-limit placeholder="请输入简洁清晰的标题" />
                <div class="field-hint">必填，4–160 字。用简短的语句概括需求的核心内容。</div>
              </el-form-item>
              <div v-if="!user" class="form-grid">
                <el-form-item label="提交人昵称（可选）">
                  <el-input v-model="requirementForm.submitter_name" maxlength="50" show-word-limit placeholder="如何称呼你" />
                </el-form-item>
                <el-form-item label="联系方式（可选）">
                  <el-input v-model="requirementForm.submitter_contact" maxlength="255" show-word-limit placeholder="邮箱或其他联系方式" />
                  <div class="field-hint">仅管理员可见，不会出现在公开页面。</div>
                </el-form-item>
              </div>
            </div>

            <div class="section">
              <h2 class="section-head"><el-icon><Tickets /></el-icon>需求描述</h2>
              <el-form-item label="需求或问题描述" required>
                <el-input v-model="requirementForm.description" type="textarea" :rows="5" maxlength="8000" show-word-limit placeholder="请详细描述你的需求、遇到的问题或改进建议..." />
                <div class="field-hint">必填，10–8,000 字。提供越详细的信息，越有助于我们理解和处理。</div>
              </el-form-item>
            </div>

            <div v-if="requirementForm.type === 'bug'" class="section">
              <h2 class="section-head"><el-icon><Warning /></el-icon>问题细节</h2>
              <el-form-item label="复现步骤">
                <el-input v-model="requirementForm.steps_to_reproduce" type="textarea" :rows="4" maxlength="4000" show-word-limit placeholder="例如：1. 打开照片页 2. 点击筛选..." />
                <div class="field-hint">最多 4,000 字。请按发生顺序描述操作，便于复现问题。</div>
              </el-form-item>
            </div>

            <div class="section">
              <h2 class="section-head"><el-icon><Switch /></el-icon>行为描述</h2>
              <div class="form-grid">
                <el-form-item label="当前行为">
                  <el-input v-model="requirementForm.current_behavior" type="textarea" :rows="3" maxlength="3000" show-word-limit placeholder="请描述目前的实际情况，例如：现在系统是如何工作的？" />
                  <div class="field-hint">最多 3,000 字。</div>
                </el-form-item>
                <el-form-item label="期望行为">
                  <el-input v-model="requirementForm.expected_behavior" type="textarea" :rows="3" maxlength="3000" show-word-limit placeholder="请描述你期望的结果，例如：希望系统如何改进？" />
                  <div class="field-hint">最多 3,000 字。</div>
                </el-form-item>
              </div>
            </div>

            <div class="section">
              <h2 class="section-head"><el-icon><Document /></el-icon>日志与附件</h2>
              <el-form-item label="日志文字">
                <el-input v-model="requirementForm.log_text" type="textarea" :rows="5" maxlength="20000" show-word-limit placeholder="可粘贴脱敏后的错误日志，请勿提交密码、令牌等敏感信息" />
                <div class="field-hint">最多 20,000 字，仅本人和管理员可见。提交前请移除密码、令牌等敏感信息。</div>
              </el-form-item>
              <el-form-item label="截图或附件">
                <input ref="fileInput" class="native-file" type="file" multiple accept=".png,.jpg,.jpeg,.webp,.txt,.log,.json,.pdf" @change="selectFiles" />
                <div class="field-hint">最多 5 个，单个不超过 5MB；支持 PNG、JPG、WebP、TXT、LOG、JSON、PDF。也可直接 Ctrl/Cmd+V 粘贴截图，仅本人和管理员可见。</div>
                <div v-if="pendingFiles.length" class="file-list">
                  <div v-for="(file, index) in pendingFiles" :key="`${file.name}-${file.size}-${index}`" class="file-row">
                    <span>{{ file.name }}（{{ formatBytes(file.size) }}）</span>
                    <el-button link type="danger" @click="pendingFiles.splice(index, 1)">移除</el-button>
                  </div>
                </div>
              </el-form-item>
            </div>

            <div class="section">
              <h2 class="section-head"><el-icon><InfoFilled /></el-icon>其他信息</h2>
              <div class="form-grid">
                <el-form-item label="TrailSnap 版本">
                  <el-input v-model="requirementForm.product_version" maxlength="50" show-word-limit placeholder="例如 0.14.1" />
                  <div class="field-hint">最多 50 个字符。如果与特定版本相关，请填写版本号。</div>
                </el-form-item>
                <el-form-item v-if="user" label="公开范围">
                  <el-radio-group v-model="requirementForm.visibility">
                    <el-radio value="public">公开</el-radio>
                    <el-radio value="private">仅本人和管理员</el-radio>
                  </el-radio-group>
                  <div class="field-hint">公开需求可被所有用户查看；私有需求仅本人和管理员可见。</div>
                </el-form-item>
                <el-form-item v-else label="公开范围">
                  <el-input model-value="公开" disabled />
                  <div class="field-hint">匿名提交的需求固定公开展示。</div>
                </el-form-item>
              </div>
            </div>

            <div class="submit-quota">所有非管理员用户合计每小时最多提交 20 条需求。</div>
            <div class="actions">
              <el-button type="primary" size="large" :icon="Promotion" :loading="busy" native-type="submit">提交需求</el-button>
              <el-button size="large" @click="saveDraft">保存草稿</el-button>
            </div>
          </el-form>

          <aside>
            <div class="side-card">
              <h3><el-icon><Opportunity /></el-icon>提交小助手</h3>
              <ul class="tip-list">
                <li><el-icon><CircleCheckFilled /></el-icon>用简洁的标题概括核心问题</li>
                <li><el-icon><CircleCheckFilled /></el-icon>详细描述使用场景和背景信息</li>
                <li><el-icon><CircleCheckFilled /></el-icon>如果有截图或示例，请一并提供</li>
                <li><el-icon><CircleCheckFilled /></el-icon>选择合适的需求类型和影响程度</li>
                <li><el-icon><CircleCheckFilled /></el-icon>提交后可以在「我的需求」中查看进度</li>
              </ul>
            </div>
            <div class="side-card">
              <h3><el-icon><Guide /></el-icon>需求处理流程</h3>
              <ol class="step-list">
                <li class="active"><div><div class="step-title">提交需求</div><p class="step-desc">填写并提交需求信息</p></div></li>
                <li><div><div class="step-title">需求评审</div><p class="step-desc">产品和技术团队进行评估</p></div></li>
                <li><div><div class="step-title">规划排期</div><p class="step-desc">纳入版本计划</p></div></li>
                <li><div><div class="step-title">开发实现</div><p class="step-desc">进入开发并跟踪进度</p></div></li>
                <li><div><div class="step-title">完成上线</div><p class="step-desc">需求实现并发布</p></div></li>
              </ol>
            </div>
            <div class="side-card help-card">
              <h3><el-icon><Service /></el-icon>需要帮助？</h3>
              <p>如果你在使用过程中遇到问题，可以联系产品团队或查看帮助文档。</p>
              <a href="https://trailsnap.cn" target="_blank" rel="noopener">
                <el-button plain class="w-full">查看帮助文档</el-button>
              </a>
            </div>
          </aside>
        </div>
      </section>

      <!-- ============ 我的需求 ============ -->
      <section v-else-if="tab === 'mine'">
        <div class="page-head">
          <div class="page-head-left">
            <div class="page-head-icon"><el-icon :size="26"><Collection /></el-icon></div>
            <div>
              <h1>我的需求</h1>
              <p class="sub">查看自己提交的需求和处理进度</p>
              <p class="desc">跟踪每一条需求从提交到上线的全过程。</p>
            </div>
          </div>
        </div>
        <div v-if="!user" class="panel empty">
          <el-icon><User /></el-icon>
          <div>登录后查看自己的需求</div>
          <div class="actions" style="justify-content: center"><el-button type="primary" @click="authDialog = true">登录 / 注册</el-button></div>
        </div>
        <template v-else>
          <RequirementTable :items="myRequirements" :manager="isManager" :user="user" @open="openDetail" @action="onRowAction" />
        </template>
      </section>

      <!-- ============ 版本计划 ============ -->
      <section v-else-if="tab === 'versions'">
        <div class="page-head">
          <div class="page-head-left">
            <div class="page-head-icon"><el-icon :size="26"><Flag /></el-icon></div>
            <div>
              <h1>版本计划</h1>
              <p class="sub">人工选择进入版本开发候选的需求</p>
              <p class="desc">跟踪每个版本的范围、进度和发布状态。</p>
            </div>
          </div>
          <div class="page-head-actions">
            <el-button v-if="isManager" type="primary" :icon="Plus" @click="batchDialog = true">创建版本批次</el-button>
          </div>
        </div>
        <div v-if="!batches.length" class="panel empty">
          <el-icon><Flag /></el-icon>
          <div>暂无版本批次</div>
        </div>
        <div v-else class="batch-grid">
          <article v-for="batch in batches" :key="batch.id" class="panel batch-card">
            <div class="card-head">
              <div>
                <h2 class="card-title">{{ batch.name }}</h2>
                <div class="meta"><span>{{ batch.version_name }}</span><span>{{ batchTypeLabel(batch.batch_type) }}</span><span v-if="batch.target_date">目标 {{ batch.target_date }}</span></div>
              </div>
              <span class="tag" :class="`s-${batch.status}`">{{ statusLabel(batch.status) }}</span>
            </div>
            <p class="description">{{ batch.goal }}</p>
            <a v-if="batch.github_milestone_url" class="github-link" :href="batch.github_milestone_url" target="_blank" rel="noopener">
              GitHub Milestone #{{ batch.github_milestone_number }}
            </a>
            <ul class="batch-items">
              <li v-for="item in batch.items" :key="item.id">
                <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap">
                  <strong style="font-size:14px">{{ item.requirement_snapshot.title }}</strong>
                  <span class="tag no-dot" :class="`d-${item.delivery_status}`">{{ deliveryLabel(item.delivery_status) }}</span>
                </div>
                <div v-if="isManager" class="actions" style="margin-top:8px">
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

      <!-- ============ 需求审核 ============ -->
      <section v-else-if="tab === 'admin' && isManager">
        <div class="page-head">
          <div class="page-head-left">
            <div class="page-head-icon"><el-icon :size="26"><Checked /></el-icon></div>
            <div>
              <h1>需求审核</h1>
              <p class="sub">AI 提供建议，最终结论由所有者或管理员确认</p>
              <p class="desc">处理待审核需求，维护候选池质量。</p>
            </div>
          </div>
          <div class="page-head-actions">
            <el-select v-model="adminStatus" clearable placeholder="全部状态" style="width:150px" @change="loadAdmin">
              <el-option v-for="status in reviewStatuses" :key="status" :label="statusLabel(status)" :value="status" />
            </el-select>
            <el-button :icon="Refresh" @click="loadAdmin">刷新</el-button>
            <el-button type="primary" :loading="syncingGithub" @click="syncGithubIssues">从 GitHub 同步</el-button>
          </div>
        </div>
        <RequirementTable :items="adminRequirements" manager :user="user" @open="openDetail" @action="onRowAction" />
      </section>

      <!-- ============ GitHub 与 Agent 集成 ============ -->
      <section v-else-if="tab === 'integrations' && isManager">
        <div class="page-head">
          <div class="page-head-left">
            <div class="page-head-icon"><el-icon :size="26"><Connection /></el-icon></div>
            <div><h1>GitHub 与 Agent 集成</h1><p class="sub">管理账号绑定和 MCP 访问令牌</p><p class="desc">令牌按作用域授权，可随时撤销；完整令牌只显示一次。</p></div>
          </div>
        </div>
        <div class="integration-grid">
          <article class="panel integration-card">
            <h2>GitHub 账号</h2>
            <div v-if="user?.github" class="account-row">
              <img v-if="user.github.avatar_url" :src="user.github.avatar_url" alt="" class="github-avatar" />
              <div><strong>@{{ user.github.login }}</strong><p class="meta">已绑定，可用于 GitHub 登录</p></div>
              <el-button plain @click="unlinkGithub">解除绑定</el-button>
            </div>
            <div v-else><p class="meta">绑定后可使用 GitHub 登录；平台不会保存 GitHub OAuth 访问令牌。</p><el-button type="primary" :disabled="!githubOauthEnabled" @click="startGithub('link')">绑定 GitHub</el-button></div>
            <p v-if="!githubOauthEnabled" class="form-hint">服务端尚未配置 GitHub OAuth App。</p>
          </article>
          <article class="panel integration-card">
            <h2>MCP 接入地址</h2>
            <code class="code-block">{{ mcpUrl }}</code>
            <p class="meta">Codex 使用 Streamable HTTP 和 Bearer Token 连接此地址。</p>
          </article>
        </div>
        <article class="panel integration-card" style="margin-top:16px">
          <div class="section-title-row"><div><h2>Agent 令牌</h2><p class="meta">仅管理自己创建的令牌。</p></div><el-button type="primary" :icon="Key" @click="tokenDialog = true">创建令牌</el-button></div>
          <el-table :data="agentTokens" style="width:100%">
            <el-table-column prop="name" label="名称" /><el-table-column prop="token_prefix" label="前缀" width="140" />
            <el-table-column label="作用域"><template #default="scope"><span class="meta">{{ scope.row.scopes.join('、') }}</span></template></el-table-column>
            <el-table-column label="最后使用" width="170"><template #default="scope">{{ scope.row.last_used_at ? new Date(scope.row.last_used_at).toLocaleString() : '从未' }}</template></el-table-column>
            <el-table-column label="状态" width="100"><template #default="scope"><span class="tag no-dot plain">{{ scope.row.revoked_at ? '已撤销' : '有效' }}</span></template></el-table-column>
            <el-table-column label="操作" width="150"><template #default="scope"><el-button v-if="!scope.row.revoked_at" text type="primary" :icon="Connection" @click="openMcpConnection(scope.row)">接入</el-button><el-button v-if="!scope.row.revoked_at" text type="danger" @click="revokeToken(scope.row.id)">撤销</el-button></template></el-table-column>
          </el-table>
        </article>
        <article class="panel mcp-guide" style="margin-top:16px">
          <div class="section-title-row">
            <div><h2>MCP 配置教程</h2><p class="meta">适用于 Codex 桌面端、CLI 和 IDE 扩展，三者共享同一份配置。</p></div>
            <a class="github-link" href="https://developers.openai.com/codex/mcp" target="_blank" rel="noopener">查看官方 MCP 文档</a>
          </div>
          <ol class="guide-steps">
            <li>
              <strong>创建最小权限令牌</strong>
              <p>点击上方“创建令牌”。只查询需求时选择 <code>requirements:read</code>；需要提交或审核时再增加对应写入作用域。令牌只显示一次，请立即保存。</p>
            </li>
            <li>
              <strong>添加请求头配置（推荐）</strong>
              <p>编辑用户级 <code>~/.codex/config.toml</code>。Codex 会在连接 MCP 时直接注入请求头，沙盒内的 Agent 无需读取宿主机环境变量。</p>
              <pre class="code-block mcp-code"><code>{{ mcpConfigExample }}</code></pre>
              <el-button size="small" @click="copyText(mcpConfigExample)">复制配置</el-button>
            </li>
            <li>
              <strong>通过 Codex 设置界面接入</strong>
              <p>URL 填 <code>{{ mcpUrl }}</code>；“Bearer 令牌环境变量”留空；在“标头”中填写 <code>Authorization</code> 和 <code>Bearer 完整令牌</code>；“来自环境变量的标头”留空。不要把 <code>bearer_token_env_var</code> 当作标头名。</p>
            </li>
            <li>
              <strong>重启并验证</strong>
              <p>重启 Codex 桌面端或 IDE 扩展，然后运行 <code>codex mcp list</code>，或在 Codex 中输入 <code>/mcp</code>，确认 <code>trailsnap_requirements</code> 已连接。</p>
            </li>
            <li>
              <strong>可选：改用环境变量</strong>
              <p>如果运行环境能够稳定继承宿主机变量，可用下面的配置避免把令牌明文保存在配置文件中。</p>
              <pre class="code-block mcp-code"><code>{{ mcpEnvConfigExample }}</code></pre>
              <el-button size="small" @click="copyText(mcpEnvConfigExample)">复制环境变量配置</el-button>
            </li>
          </ol>
          <el-alert type="warning" :closable="false" show-icon title="令牌与连接安全">
            请求头方案会把令牌保存在用户配置中，请勿提交该文件，并为令牌设置最小权限和有效期；泄露后应立即撤销。MCP 地址必须使用 HTTPS。出现 401 请检查令牌，出现 403 请检查作用域。
          </el-alert>
        </article>
      </section>

      <!-- ============ 角色管理 ============ -->
      <section v-else-if="tab === 'users' && user?.role === 'owner'">
        <div class="page-head">
          <div class="page-head-left">
            <div class="page-head-icon"><el-icon :size="26"><UserFilled /></el-icon></div>
            <div>
              <h1>角色管理</h1>
              <p class="sub">所有者可以任命或移除管理员</p>
            </div>
          </div>
        </div>
        <el-table :data="users" class="panel users-panel">
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="email" label="邮箱" />
          <el-table-column prop="role" label="角色">
            <template #default="scope"><span class="tag no-dot plain">{{ roleLabel(scope.row.role) }}</span></template>
          </el-table-column>
          <el-table-column label="GitHub"><template #default="scope">{{ scope.row.github ? `@${scope.row.github.login}` : '未绑定' }}</template></el-table-column>
          <el-table-column label="操作">
            <template #default="scope">
              <el-button v-if="scope.row.role !== 'owner'" size="small" @click="toggleRole(scope.row)">{{ scope.row.role === 'admin' ? '降为查看者' : '设为管理员' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </main>

    <!-- ============ 页脚 ============ -->
    <footer class="footer">
      <div class="footer-inner">
        <div class="footer-brand"><img :src="logoUrl" alt="" />行影集 <span style="font-weight:400">| 让好想法，变成更好的产品</span></div>
        <div class="footer-links">
          <span>软件需求管理平台</span><span class="sep">•</span><a href="https://trailsnap.cn" target="_blank" rel="noopener">开放</a><span class="sep">•</span><a href="https://trailsnap.cn" target="_blank" rel="noopener">更高效</a><span class="sep">•</span><span>一起创造更好的行影集</span>
        </div>
      </div>
    </footer>

    <el-dialog v-model="editDialog" title="编辑需求" width="min(92vw, 640px)">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="类型" required><el-select v-model="editForm.type"><el-option label="新功能" value="feature" /><el-option label="体验优化" value="improvement" /><el-option label="问题修复" value="bug" /></el-select></el-form-item><el-form-item label="影响程度" required><el-select v-model="editForm.severity"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item></div>
        <el-form-item label="标题" required><el-input v-model="editForm.title" maxlength="160" show-word-limit /><div class="field-hint">4–160 字。</div></el-form-item>
        <el-form-item label="需求描述" required><el-input v-model="editForm.description" type="textarea" :rows="5" maxlength="8000" show-word-limit /><div class="field-hint">10–8,000 字。</div></el-form-item>
        <el-form-item label="复现步骤"><el-input v-model="editForm.steps_to_reproduce" type="textarea" :rows="3" maxlength="4000" show-word-limit /></el-form-item>
        <div class="form-grid"><el-form-item label="当前行为"><el-input v-model="editForm.current_behavior" type="textarea" :rows="3" maxlength="3000" show-word-limit /></el-form-item><el-form-item label="期望行为"><el-input v-model="editForm.expected_behavior" type="textarea" :rows="3" maxlength="3000" show-word-limit /></el-form-item></div>
        <el-form-item label="日志文字（仅提交人和管理员可见）"><el-input v-model="editForm.log_text" type="textarea" :rows="3" maxlength="20000" show-word-limit /></el-form-item>
        <div class="form-grid"><el-form-item label="产品版本"><el-input v-model="editForm.product_version" maxlength="50" /></el-form-item><el-form-item label="公开范围"><el-select v-model="editForm.visibility"><el-option label="公开" value="public" /><el-option label="仅提交人和管理员" value="private" /></el-select></el-form-item></div>
        <el-alert v-if="editTarget?.github_issue_number" type="info" :closable="false">保存后将异步同步 GitHub Issue 的标题、正文、类型和状态标签。</el-alert>
      </el-form>
      <template #footer><el-button @click="editDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="submitEdit">保存</el-button></template>
    </el-dialog>

    <!-- ============ 登录 ============ -->
    <el-dialog v-model="authDialog" title="登录需求平台" width="min(92vw, 440px)">
      <el-tabs v-model="authMode"><el-tab-pane label="登录" name="login" /><el-tab-pane label="注册" name="register" /></el-tabs>
      <el-form label-position="top" @submit.prevent="submitAuth">
        <el-form-item v-if="authMode === 'register'" label="用户名"><el-input v-model="authForm.username" autocomplete="username" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="authForm.email" autocomplete="email" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="authForm.password" type="password" show-password autocomplete="current-password" /><div v-if="authMode === 'register'" class="form-hint">至少 8 位字符</div></el-form-item>
        <el-button type="primary" class="w-full" :loading="busy" native-type="submit">{{ authMode === 'login' ? '登录' : '注册' }}</el-button>
        <el-divider v-if="githubOauthEnabled">或</el-divider>
        <el-button v-if="githubOauthEnabled" class="w-full" @click="startGithub('login')">使用 GitHub 登录</el-button>
      </el-form>
    </el-dialog>

    <el-dialog v-model="tokenDialog" title="创建 Agent MCP 令牌" width="min(92vw, 600px)">
      <el-form label-position="top">
        <el-form-item label="令牌名称"><el-input v-model="tokenForm.name" placeholder="例如 Codex 需求助手" /></el-form-item>
        <el-form-item label="有效期（天）"><el-input-number v-model="tokenForm.expires_in_days" :min="1" :max="365" /></el-form-item>
        <el-form-item label="授权作用域"><el-checkbox-group v-model="tokenForm.scopes"><el-checkbox v-for="scope in scopeOptions" :key="scope" :value="scope">{{ scope }}</el-checkbox></el-checkbox-group></el-form-item>
      </el-form>
      <el-alert v-if="createdToken" type="success" :closable="false" title="请立即复制，关闭后无法再次查看"><code class="code-block">{{ createdToken }}</code><div class="token-created-actions"><el-button @click="copyText(createdToken)">复制令牌</el-button><el-button type="primary" :icon="Connection" @click="openCreatedTokenConnection">接入</el-button></div></el-alert>
      <template #footer><el-button @click="tokenDialog = false; createdToken = ''">关闭</el-button><el-button v-if="!createdToken" type="primary" :loading="busy" @click="createToken">创建</el-button></template>
    </el-dialog>

    <el-dialog v-model="mcpConnectionDialog" title="接入 MCP 客户端" width="min(94vw, 680px)" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="完整令牌" required>
          <el-input v-model="connectionToken" type="password" show-password placeholder="粘贴以 trp_ 开头的完整令牌" autocomplete="off" />
          <div class="field-hint">平台只保存令牌哈希。历史令牌需要重新粘贴；令牌仅保留在当前弹窗内。</div>
        </el-form-item>
      </el-form>
      <div class="connection-section">
        <div class="section-title-row"><div><h3>通用 Streamable HTTP MCP</h3><p class="meta">适用于支持 JSON MCP 配置的客户端。</p></div><el-button :disabled="!connectionToken.trim()" @click="copyText(genericMcpConfig)">复制 JSON</el-button></div>
        <pre class="code-block mcp-code"><code>{{ genericMcpConfig }}</code></pre>
      </div>
      <div class="connection-section">
        <h3>Codex 设置界面</h3>
        <dl class="config-fields">
          <div><dt>URL</dt><dd>{{ mcpUrl }}</dd></div>
          <div><dt>Bearer 令牌环境变量</dt><dd>留空</dd></div>
          <div><dt>标头</dt><dd><code>Authorization</code> → <code>Bearer 完整令牌</code></dd></div>
          <div><dt>来自环境变量的标头</dt><dd>留空</dd></div>
        </dl>
      </div>
      <el-alert type="warning" :closable="false" title="配置包含完整令牌">只复制到可信客户端，不要提交到 Git 或发送给其他人；令牌泄露后请立即撤销。</el-alert>
      <template #footer><el-button @click="closeMcpConnection">关闭</el-button></template>
    </el-dialog>

    <!-- ============ 人工审核 ============ -->
    <el-dialog v-model="reviewDialog" title="人工审核" width="min(92vw, 560px)">
      <p v-if="reviewTarget"><strong>{{ reviewTarget.title }}</strong></p>
      <el-form label-position="top">
        <el-form-item label="审核结论"><el-select v-model="reviewForm.action"><el-option v-for="(label, value) in reviewActionLabels" :key="value" :label="label" :value="value" /></el-select></el-form-item>
        <el-form-item label="原因"><el-input v-model="reviewForm.reason" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="优先级"><el-select v-model="reviewForm.priority"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item>
        <el-form-item label="风险"><el-select v-model="reviewForm.risk_level"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item>
        <el-form-item v-if="reviewForm.action === 'duplicate'" label="主需求 ID"><el-input v-model="reviewForm.duplicate_of_id" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="reviewDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="submitReview">确认</el-button></template>
    </el-dialog>

    <!-- ============ 创建版本批次 ============ -->
    <el-dialog v-model="batchDialog" title="创建版本批次" width="min(92vw, 560px)">
      <el-form label-position="top">
        <el-form-item label="版本名称" required>
          <el-input v-model="batchForm.name" maxlength="120" show-word-limit placeholder="例如：移动端体验优化" />
          <div class="field-hint">必填，2–120 字，用于说明本批次的主题。</div>
        </el-form-item>
        <el-form-item label="版本号" required>
          <el-input v-model="batchForm.version_name" maxlength="50" show-word-limit placeholder="例如 v0.15.0" />
          <div class="field-hint">必填，1–50 个字符；仅支持英文字母、数字、点、下划线和连字符。</div>
        </el-form-item>
        <el-form-item label="版本目标" required>
          <el-input v-model="batchForm.goal" type="textarea" :rows="4" maxlength="4000" show-word-limit placeholder="说明这个版本要解决的问题和预期结果" />
          <div class="field-hint">必填，4–4,000 字。</div>
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="batchForm.batch_type"><el-option label="修复" value="fix" /><el-option label="功能" value="feature" /><el-option label="重大" value="major" /><el-option label="紧急修复" value="hotfix" /></el-select>
          <div class="field-hint">选择最符合本次发布范围的版本类型。</div>
        </el-form-item>
        <el-form-item label="计划日期">
          <el-input v-model="batchForm.target_date" type="date" />
          <div class="field-hint">可选，格式为 YYYY-MM-DD。</div>
        </el-form-item>
        <el-form-item label="允许的最高风险" required>
          <el-select v-model="batchForm.max_risk_level"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select>
          <div class="field-hint">风险高于该级别的需求不能加入此版本。</div>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="batchDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="createBatch">创建</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  ArrowDown, Bell, Checked, CircleCheckFilled, Collection, Connection, DataAnalysis, Document, DocumentAdd, EditPen, Flag, Guide,
  InfoFilled, Key, Opportunity, Plus, Promotion, Refresh, Search, Service, Switch, Tickets, User, UserFilled, Warning,
} from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import logoUrl from './assets/logo.svg'
import { api, type AgentToken, type Batch, type Dashboard, type Requirement, type RequirementHistory, type User as ApiUser } from './api'
import {
  avatarColor, batchTypeLabel, deliveryLabel, reviewActionLabels, roleLabel,
  statusLabel, typeLabel,
} from './labels'
import RequirementTable from './RequirementTable.vue'
import RequirementDetail from './RequirementDetail.vue'

const statusOptions = ['pending_review', 'candidate', 'scheduled', 'developing', 'testing', 'release_ready', 'released', 'deferred', 'rejected']
const reviewStatuses = ['submitted', 'triaging', 'pending_review', 'needs_information', 'candidate', 'deferred', 'rejected', 'duplicate']
const deliveryStatuses = ['not_started', 'developing', 'pr_open', 'testing', 'completed', 'blocked', 'removed']
const batchTransitions: Record<string, string[]> = {
  scope_locked: ['developing', 'blocked', 'paused', 'cancelled'], developing: ['testing', 'blocked', 'paused', 'cancelled'],
  testing: ['developing', 'release_ready', 'blocked', 'paused', 'cancelled'], release_ready: ['testing', 'published', 'blocked', 'paused', 'cancelled'],
  published: ['completed'], blocked: ['developing', 'testing', 'release_ready', 'paused', 'cancelled'],
  paused: ['developing', 'testing', 'release_ready', 'blocked', 'cancelled'], completed: [], cancelled: [],
}
const allowedBatchStatuses = (status: string) => (batchTransitions[status] || []).filter(
  next => user.value?.role === 'owner' || !['completed', 'cancelled'].includes(next),
)

const errorMessage = (error: unknown) => {
  if (!axios.isAxiosError(error)) return String(error)
  const payload = error.response?.data as { msg?: string; detail?: string; data?: { errors?: Array<{ loc?: string[]; type?: string; msg?: string }> } } | undefined
  const fieldError = payload?.data?.errors?.[0]
  if (fieldError) {
    const field = fieldError.loc?.[fieldError.loc.length - 1]
    const labels: Record<string, string> = { username: '用户名', email: '邮箱', password: '密码' }
    if (field === 'password' && fieldError.type === 'string_too_short') return '密码至少需要 8 位字符'
    return `${labels[field || ''] || field || '输入内容'}：${fieldError.msg || '格式不正确'}`
  }
  return String(payload?.msg || payload?.detail || error.message)
}

const emptyRequirementForm = () => ({
  type: 'feature', title: '', description: '', log_text: '', current_behavior: '', expected_behavior: '', steps_to_reproduce: '',
  severity: 'medium', product_version: '', visibility: 'public', submitter_name: '', submitter_contact: '', environment: {} as Record<string, unknown>,
})

type Tab = 'public' | 'dashboard' | 'submit' | 'mine' | 'admin' | 'versions' | 'integrations' | 'users'
const tab = ref<Tab>('public')
const user = ref<ApiUser | null>(null)
const requirements = ref<Requirement[]>([]), myRequirements = ref<Requirement[]>([]), adminRequirements = ref<Requirement[]>([])
const batches = ref<Batch[]>([]), users = ref<ApiUser[]>([]), candidates = ref<Requirement[]>([])
const agentTokens = ref<AgentToken[]>([])
const dashboard = ref<Dashboard | null>(null), detailHistory = ref<RequirementHistory[]>([])
const busy = ref(false), syncingGithub = ref(false), authDialog = ref(false), reviewDialog = ref(false), editDialog = ref(false), batchDialog = ref(false), tokenDialog = ref(false), mcpConnectionDialog = ref(false)
const githubOauthEnabled = ref(false), createdToken = ref(''), createdTokenId = ref(''), connectionToken = ref('')
const authMode = ref<'login' | 'register'>('login'), adminStatus = ref('pending_review')
const sortBy = ref('updated')
const detailRouteNumber = ref<number | null>(routeRequirementNumber())
const detailLoading = ref(false), detailTarget = ref<Requirement | null>(null)
const reviewTarget = ref<Requirement | null>(null)
const editTarget = ref<Requirement | null>(null)
const editForm = reactive({ type: 'feature', severity: 'medium', title: '', description: '', steps_to_reproduce: '', current_behavior: '', expected_behavior: '', log_text: '', product_version: '', visibility: 'public' })
const filters = reactive({ q: '', type: '', status: '' })
const authForm = reactive({ username: '', email: '', password: '' })
const requirementForm = reactive(emptyRequirementForm())
const pendingFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const reviewForm = reactive({ action: 'candidate', reason: '', priority: 'normal', risk_level: 'medium', duplicate_of_id: '' })
const batchForm = reactive({ name: '', version_name: '', goal: '', batch_type: 'feature', target_date: '', max_risk_level: 'high' })
const scopeOptions = ['requirements:read', 'requirements:write', 'requirements:review', 'versions:read', 'versions:write', 'github:write']
const tokenForm = reactive({ name: '', scopes: ['requirements:read'], expires_in_days: 90 })
const mcpUrl = `${window.location.origin}/mcp/`
const mcpConfigExample = computed(() => `[mcp_servers.trailsnap_requirements]\nurl = "${mcpUrl}"\nhttp_headers = { Authorization = "Bearer trp_替换为刚创建的完整令牌" }\ndefault_tools_approval_mode = "writes"`)
const mcpEnvConfigExample = computed(() => `[mcp_servers.trailsnap_requirements]\nurl = "${mcpUrl}"\nbearer_token_env_var = "TRAILSNAP_MCP_TOKEN"\ndefault_tools_approval_mode = "writes"`)
const genericMcpConfig = computed(() => JSON.stringify({
  mcpServers: {
    'trailsnap-feedback': {
      type: 'http',
      url: mcpUrl,
      headers: { Authorization: connectionToken.value.trim() ? `Bearer ${connectionToken.value.trim()}` : 'Bearer <完整令牌>' },
    },
  },
}, null, 2))
const candidateSelection = reactive<Record<string, string>>({})

const isManager = computed(() => user.value?.role === 'admin' || user.value?.role === 'owner')
const visibleTabs = computed(() => [
  { key: 'public' as Tab, label: '公开需求' },
  { key: 'submit' as Tab, label: '提交需求' },
  { key: 'mine' as Tab, label: '我的需求' },
  { key: 'versions' as Tab, label: '版本计划' },
  ...(isManager.value ? [{ key: 'dashboard' as Tab, label: '总览看板' }] : []),
  ...(isManager.value ? [{ key: 'admin' as Tab, label: '需求审核' }] : []),
  ...(isManager.value ? [{ key: 'integrations' as Tab, label: '集成设置' }] : []),
  ...(user.value?.role === 'owner' ? [{ key: 'users' as Tab, label: '角色管理' }] : []),
])

const plannedStatuses = ['scheduled', 'developing', 'testing', 'release_ready']
const doneStatuses = ['released', 'published', 'completed']
const stats = computed(() => ({
  total: requirements.value.length,
  planned: requirements.value.filter(item => plannedStatuses.includes(item.status)).length,
  developing: requirements.value.filter(item => item.status === 'developing').length,
  done: requirements.value.filter(item => doneStatuses.includes(item.status)).length,
}))
const sortedRequirements = computed(() => {
  const list = [...requirements.value]
  if (sortBy.value === 'updated') list.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  else if (sortBy.value === 'oldest') list.sort((a, b) => a.created_at.localeCompare(b.created_at))
  else list.sort((a, b) => (b.follower_count || 0) - (a.follower_count || 0))
  return list
})
const canFollow = computed(() => !!user.value && !!detailTarget.value)

async function loadRequirements() {
  const p = new URLSearchParams()
  if (filters.q) p.set('q', filters.q)
  if (filters.type) p.set('type', filters.type)
  if (filters.status) p.set('status', filters.status)
  requirements.value = await api.requirements(`?${p}`)
}
async function loadMine() { if (user.value) myRequirements.value = await api.requirements('?mine=true') }
async function loadAdmin() { if (isManager.value) adminRequirements.value = await api.requirements(adminStatus.value ? `?status=${adminStatus.value}` : '') }
async function loadDashboard() { if (isManager.value) dashboard.value = await api.dashboard() }
async function loadBatches() { batches.value = await api.batches(); if (isManager.value) candidates.value = await api.requirements('?status=candidate&limit=100') }
async function loadUsers() { if (user.value?.role === 'owner') users.value = await api.users() }
async function loadIntegrations() { if (isManager.value) agentTokens.value = await api.agentTokens() }
async function switchTab(value: Tab) {
  if (detailRouteNumber.value) {
    detailRouteNumber.value = null
    detailTarget.value = null
    detailHistory.value = []
    history.pushState({}, '', '/')
  }
  tab.value = value
  try {
    if (value === 'public') await loadRequirements()
    if (value === 'mine') await loadMine()
    if (value === 'admin') await loadAdmin()
    if (value === 'dashboard') await loadDashboard()
    if (value === 'versions') await loadBatches()
    if (value === 'users') await loadUsers()
    if (value === 'integrations') await loadIntegrations()
  } catch (e) { ElMessage.error(errorMessage(e)) }
}
function sortRequirements() { /* 由 computed 自动排序 */ }

async function restoreSession() {
  if (!localStorage.getItem('rp_token')) return
  try { user.value = await api.me() } catch { localStorage.removeItem('rp_token') }
}

async function submitAuth() {
  if (authMode.value === 'register') {
    if (!/^[A-Za-z0-9_.-]{3,50}$/.test(authForm.username)) { ElMessage.error('用户名需为 3–50 位字母、数字、点、下划线或连字符'); return }
    if (authForm.password.length < 8) { ElMessage.error('密码至少需要 8 位字符'); return }
  }
  busy.value = true
  try {
    const result = authMode.value === 'login'
      ? await api.login({ identifier: authForm.email, password: authForm.password })
      : await api.register(authForm)
    localStorage.setItem('rp_token', result.token)
    user.value = result.user
    authDialog.value = false
    ElMessage.success('登录成功')
    await switchTab('public')
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

async function startGithub(mode: 'login' | 'link') {
  try {
    const result = await api.githubStart(mode)
    window.location.assign(result.authorize_url)
  } catch (e) { ElMessage.error(errorMessage(e)) }
}
async function unlinkGithub() {
  try {
    await ElMessageBox.confirm('解除后仍可使用邮箱密码登录，确认继续？', '解除 GitHub 绑定')
    await api.githubUnlink()
    user.value = await api.me()
    ElMessage.success('GitHub 账号已解除绑定')
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}
async function createToken() {
  if (tokenForm.name.trim().length < 2 || !tokenForm.scopes.length) { ElMessage.error('请填写名称并至少选择一个作用域'); return }
  busy.value = true
  try {
    const result = await api.createAgentToken({ ...tokenForm })
    createdToken.value = result.token
    createdTokenId.value = result.id
    await loadIntegrations()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}
async function revokeToken(id: string) {
  try { await ElMessageBox.confirm('撤销后 Agent 将立即失去访问权限，确认继续？', '撤销令牌'); await api.revokeAgentToken(id); await loadIntegrations(); ElMessage.success('令牌已撤销') } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}
function openMcpConnection(token: AgentToken) {
  connectionToken.value = token.id === createdTokenId.value ? createdToken.value : ''
  mcpConnectionDialog.value = true
}
function openCreatedTokenConnection() {
  connectionToken.value = createdToken.value
  mcpConnectionDialog.value = true
}
function closeMcpConnection() {
  mcpConnectionDialog.value = false
  connectionToken.value = ''
}
async function copyText(value: string) { await navigator.clipboard.writeText(value); ElMessage.success('已复制') }

function onUserCommand(command: string | number | object) {
  if (command === 'logout') logout()
  if (command === 'mine') switchTab('mine')
}
function onNotification() { ElMessage.info('暂无新通知') }

async function submitRequirement() {
  const titleLength = requirementForm.title.trim().length
  const descriptionLength = requirementForm.description.trim().length
  if (titleLength < 4 || titleLength > 160) { ElMessage.error('标题需要 4–160 个字符'); return }
  if (descriptionLength < 10 || descriptionLength > 8000) { ElMessage.error('需求描述需要 10–8,000 个字符'); return }
  busy.value = true
  try {
    const created = await api.createRequirement(requirementForm)
    let uploadError: unknown = null
    for (const file of pendingFiles.value) {
      try { await api.uploadAttachment(created.id, file, created.upload_token) } catch (e) { uploadError = e; break }
    }
    Object.assign(requirementForm, emptyRequirementForm())
    pendingFiles.value = []
    if (fileInput.value) fileInput.value.value = ''
    if (uploadError) ElMessage.warning(`需求已提交，但有附件上传失败：${errorMessage(uploadError)}`)
    else ElMessage.success('需求已提交')
    if (user.value) await switchTab('mine')
    else { await switchTab('public'); await openDetail(created) }
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

const allowedFilePattern = /\.(png|jpe?g|webp|txt|log|json|pdf)$/i
function addFiles(files: File[]) {
  for (const file of files) {
    if (pendingFiles.value.length >= 5) { ElMessage.warning('每条需求最多添加 5 个附件'); break }
    if (file.size > 5 * 1024 * 1024) { ElMessage.warning(`${file.name} 超过 5MB，未添加`); continue }
    if (!allowedFilePattern.test(file.name)) { ElMessage.warning(`${file.name} 的格式不受支持`); continue }
    pendingFiles.value.push(file)
  }
}
function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(Array.from(input.files || []))
  input.value = ''
}
function handlePaste(event: ClipboardEvent) {
  const images = Array.from(event.clipboardData?.items || []).filter(item => item.kind === 'file' && item.type.startsWith('image/'))
  if (!images.length) return
  const files = images.map((item, index) => {
    const blob = item.getAsFile()!
    const extension = blob.type === 'image/jpeg' ? 'jpg' : blob.type === 'image/webp' ? 'webp' : 'png'
    return new File([blob], `clipboard-${Date.now()}-${index + 1}.${extension}`, { type: blob.type })
  })
  addFiles(files)
  ElMessage.success(`已从剪贴板添加 ${files.length} 张截图`)
}
function formatBytes(size: number) { return size < 1024 * 1024 ? `${Math.ceil(size / 1024)}KB` : `${(size / 1024 / 1024).toFixed(1)}MB` }
async function downloadAttachment(requirement: Requirement, attachment: NonNullable<Requirement['attachments']>[number]) {
  try { await api.downloadAttachment(requirement.id, attachment.id, attachment.name) } catch (e) { ElMessage.error(errorMessage(e)) }
}
function saveDraft() {
  const { environment: _env, ...rest } = requirementForm
  localStorage.setItem('rp_draft', JSON.stringify(rest))
  ElMessage.success('草稿已保存，下次进入提交页可继续填写')
}

function routeRequirementNumber() {
  const match = window.location.pathname.match(/^\/requirements\/REQ-(\d+)\/?$/i)
  return match ? Number(match[1]) : null
}
async function loadDetail(number: number) {
  detailLoading.value = true
  try {
    const requirement = await api.requirementByNumber(number)
    detailTarget.value = requirement
    detailHistory.value = await api.requirementHistory(requirement.id)
  } catch (e) {
    detailTarget.value = null
    detailHistory.value = []
    ElMessage.error(errorMessage(e))
  } finally { detailLoading.value = false }
}
async function openDetail(item: Requirement) {
  if (!item.public_number) return
  detailRouteNumber.value = item.public_number
  history.pushState({}, '', `/requirements/REQ-${item.public_number}`)
  window.scrollTo({ top: 0, behavior: 'smooth' })
  await loadDetail(item.public_number)
}
function closeDetail() {
  detailRouteNumber.value = null
  detailTarget.value = null
  detailHistory.value = []
  history.pushState({}, '', '/')
}
function requirementLink(item: Requirement) { return `${window.location.origin}/requirements/REQ-${item.public_number}` }
async function copyRequirementLink(item: Requirement) { await copyText(requirementLink(item)) }
async function followDetail() {
  if (!detailTarget.value) return
  if (!user.value) { authDialog.value = true; return }
  try {
    await api.followRequirement(detailTarget.value.id)
    ElMessage.success('关注状态已更新')
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (e) { ElMessage.error(errorMessage(e)) }
}
function handlePopState() {
  const number = routeRequirementNumber()
  detailRouteNumber.value = number
  if (number) void loadDetail(number)
  else {
    detailTarget.value = null
    detailHistory.value = []
  }
}

function openEdit(item: Requirement) {
  editTarget.value = item
  Object.assign(editForm, {
    type: item.type, severity: item.severity, title: item.title, description: item.description,
    steps_to_reproduce: item.steps_to_reproduce || '', log_text: item.log_text || '',
    current_behavior: item.current_behavior || '', expected_behavior: item.expected_behavior || '',
    product_version: item.product_version || '', visibility: item.visibility,
  })
  editDialog.value = true
}
async function submitEdit() {
  if (!editTarget.value) return
  if (editForm.title.trim().length < 4 || editForm.description.trim().length < 10) { ElMessage.error('请按要求填写标题和需求描述'); return }
  busy.value = true
  try {
    const updated = await api.updateRequirement(editTarget.value.id, { ...editForm, title: editForm.title.trim(), description: editForm.description.trim() })
    editDialog.value = false
    ElMessage.success(updated.github_issue_number ? '需求已保存，GitHub Issue 将自动同步' : '需求已保存')
    await refreshManaged()
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

function onRowAction(payload: { item: Requirement; command: string }) {
  const { item, command } = payload
  if (command === 'follow') follow(item)
  else if (command === 'review') openReview(item)
  else if (command === 'edit') openEdit(item)
  else if (command === 'withdraw') withdraw(item)
  else if (command === 'github-create') createGithubIssue(item)
  else if (command === 'github-link') linkGithubIssue(item)
  else if (command === 'github-close') closeGithubIssue(item)
  else if (command === 'github-unlink') unlinkGithubIssue(item)
  else if (command === 'close') closeManagedRequirement(item)
  else if (command === 'delete') deleteManagedRequirement(item)
}

async function promptReason(title: string) {
  const result = await ElMessageBox.prompt('请输入操作原因（将写入审计记录）', title, { inputPattern: /.{2,}/, inputErrorMessage: '至少输入两个字符' })
  return result.value
}
async function refreshManaged() { await Promise.all([loadAdmin(), loadRequirements()]) }
async function syncGithubIssues() {
  syncingGithub.value = true
  try {
    const result = await api.syncGithubIssues()
    ElMessage.success(`同步完成：新增 ${result.created} 条，更新 ${result.updated} 条，跳过 ${result.skipped} 条`)
    await refreshManaged()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { syncingGithub.value = false }
}
async function createGithubIssue(item: Requirement) { try { await ElMessageBox.confirm('确认在配置的 TrailSnap 仓库中新建 Issue？', '新建 GitHub Issue'); await api.createGithubIssue(item.id); ElMessage.success('GitHub Issue 已创建并关联'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function linkGithubIssue(item: Requirement) { try { const result = await ElMessageBox.prompt('请输入 GitHub Issue 编号', '关联已有 Issue', { inputPattern: /^\d+$/, inputErrorMessage: '请输入正整数' }); await api.linkGithubIssue(item.id, Number(result.value)); ElMessage.success('Issue 已关联'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function closeGithubIssue(item: Requirement) { try { const reason = await promptReason('关闭 GitHub Issue 与需求'); await api.closeGithubIssue(item.id, reason); ElMessage.success('Issue 与需求均已关闭'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function unlinkGithubIssue(item: Requirement) { try { await ElMessageBox.confirm('只解除平台关联，不会修改 GitHub Issue，确认继续？', '取消 Issue 关联'); await api.unlinkGithubIssue(item.id); ElMessage.success('已解除关联'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function closeManagedRequirement(item: Requirement) { try { const reason = await promptReason('关闭需求'); await api.closeRequirement(item.id, reason); ElMessage.success('需求已关闭'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function deleteManagedRequirement(item: Requirement) { try { const reason = await promptReason('删除需求（可恢复）'); await ElMessageBox.confirm(`确认删除“${item.title}”？数据会保留以供审计和恢复。`, '二次确认', { type: 'warning' }); await api.deleteRequirement(item.id, reason); ElMessage.success('需求已删除'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }

async function follow(item: Requirement) {
  if (!user.value) { authDialog.value = true; return }
  try {
    await api.followRequirement(item.id)
    ElMessage.success('关注状态已更新')
    await switchTab(tab.value)
  } catch (e) { ElMessage.error(errorMessage(e)) }
}

async function withdraw(item: Requirement) {
  try {
    await ElMessageBox.confirm('撤回后该需求将不再展示在公开列表，确认撤回？', '撤回需求')
    await api.withdrawRequirement(item.id)
    ElMessage.success('需求已撤回')
    await switchTab(tab.value)
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}

function openReview(item: Requirement) {
  reviewTarget.value = item
  Object.assign(reviewForm, { action: 'candidate', reason: '', priority: item.priority || 'normal', risk_level: item.risk_level || 'medium', duplicate_of_id: '' })
  reviewDialog.value = true
}

async function submitReview() {
  if (!reviewTarget.value) return
  busy.value = true
  try {
    await api.review(reviewTarget.value.id, reviewForm)
    reviewDialog.value = false
    ElMessage.success('审核结果已保存')
    await loadAdmin()
    await loadRequirements()
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

async function createBatch() {
  const name = batchForm.name.trim()
  const versionName = batchForm.version_name.trim()
  const goal = batchForm.goal.trim()
  if (name.length < 2 || name.length > 120) { ElMessage.error('版本名称需要 2–120 个字符'); return }
  if (!/^[A-Za-z0-9._-]{1,50}$/.test(versionName)) { ElMessage.error('版本号只能包含 1–50 个英文字母、数字、点、下划线或连字符'); return }
  if (goal.length < 4 || goal.length > 4000) { ElMessage.error('版本目标需要 4–4,000 个字符'); return }
  busy.value = true
  try {
    await api.createBatch({ ...batchForm, name, version_name: versionName, goal, target_date: batchForm.target_date || null })
    batchDialog.value = false
    Object.assign(batchForm, { name: '', version_name: '', goal: '', batch_type: 'feature', target_date: '', max_risk_level: 'high' })
    ElMessage.success('版本批次已创建')
    await loadBatches()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

async function addCandidate(batchId: string) {
  const id = candidateSelection[batchId]
  if (!id) return
  try { await api.addBatchItem(batchId, id); candidateSelection[batchId] = ''; await loadBatches() } catch (e) { ElMessage.error(errorMessage(e)) }
}

async function removeBatchItem(batchId: string, itemId: string) {
  try {
    await ElMessageBox.confirm('确认将该需求移出版本？', '确认')
    await api.removeBatchItem(batchId, itemId)
    await loadBatches()
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}

async function lockBatch(batchId: string) {
  try {
    await ElMessageBox.confirm('锁定后需求范围将生成快照，确认继续？', '锁定版本范围')
    await api.lockBatch(batchId)
    ElMessage.success('版本范围已锁定')
    await loadBatches()
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}

async function updateBatchState(batchId: string, status: string) {
  try {
    const reason = await ElMessageBox.prompt('请输入状态变更原因', '更新版本状态', { inputPattern: /.{2,}/, inputErrorMessage: '至少输入两个字符' })
    await api.updateBatchStatus(batchId, status, reason.value)
    await loadBatches()
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}

async function updateDelivery(batchId: string, itemId: string, status: string) {
  try { await api.updateDeliveryStatus(batchId, itemId, status); await loadBatches() } catch (e) { ElMessage.error(errorMessage(e)) }
}

async function toggleRole(row: ApiUser) {
  try { await api.updateRole(row.id, row.role === 'admin' ? 'viewer' : 'admin'); await loadUsers() } catch (e) { ElMessage.error(errorMessage(e)) }
}

function logout() {
  localStorage.removeItem('rp_token')
  user.value = null
  tab.value = 'public'
  void loadRequirements()
}

onMounted(async () => {
  window.addEventListener('popstate', handlePopState)
  const params = new URLSearchParams(window.location.search)
  try { githubOauthEnabled.value = (await api.authStatus()).github_oauth_enabled } catch { githubOauthEnabled.value = false }
  const githubError = params.get('github_error')
  if (githubError) {
    const message = githubError === 'oauth_upstream'
      ? 'GitHub 登录暂时失败，请重新发起登录；若持续出现，请管理员检查服务端 OAuth 日志和 Client Secret。'
      : 'GitHub 登录失败，请重试。'
    ElMessage.error({ message, duration: 8000 })
    params.delete('github_error')
    history.replaceState({}, '', `${window.location.pathname}${params.size ? `?${params}` : ''}`)
  }
  const githubGrant = params.get('github_grant')
  if (githubGrant) {
    try {
      const result = await api.githubRedeem(githubGrant)
      localStorage.setItem('rp_token', result.token)
      user.value = result.user
      ElMessage.success('GitHub 登录或绑定成功')
    } catch (e) { ElMessage.error(errorMessage(e)) }
    params.delete('github_grant')
    history.replaceState({}, '', `${window.location.pathname}${params.size ? `?${params}` : ''}`)
  }
  const requestedTab = params.get('view') as Tab | null
  if (requestedTab && ['public', 'dashboard', 'submit', 'mine', 'admin', 'versions', 'integrations', 'users'].includes(requestedTab)) tab.value = requestedTab
  const requestedType = params.get('type')
  if (requestedType && ['bug', 'improvement', 'feature'].includes(requestedType)) requirementForm.type = requestedType
  if (tab.value === 'submit') {
    try {
      const draft = localStorage.getItem('rp_draft')
      if (draft) Object.assign(requirementForm, JSON.parse(draft))
    } catch { localStorage.removeItem('rp_draft') }
  }
  if (!user.value) await restoreSession()
  if ((['admin', 'dashboard', 'integrations'].includes(tab.value) && !isManager.value) || (tab.value === 'users' && user.value?.role !== 'owner')) tab.value = 'public'
  await Promise.all([loadRequirements(), loadBatches()])
  if (tab.value === 'mine') await loadMine()
  if (tab.value === 'admin') await loadAdmin()
  if (tab.value === 'dashboard') await loadDashboard()
  if (tab.value === 'users') await loadUsers()
  if (tab.value === 'integrations') await loadIntegrations()
  if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
})
onBeforeUnmount(() => window.removeEventListener('popstate', handlePopState))
</script>

<style scoped>
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.w-full { width: 100%; }
.github-link { color: var(--rp-primary); font-size: 13.5px; text-decoration: none; }
.github-link:hover { text-decoration: underline; }
.integration-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.integration-card h2 { margin:0 0 12px; font-size:18px; }
.account-row,.section-title-row { display:flex; align-items:center; gap:12px; justify-content:space-between; }
.account-row > div { flex:1; }
.github-avatar { width:44px; height:44px; border-radius:50%; }
.code-block { display:block; padding:12px; border-radius:8px; background:#f3f4f6; color:#111827; overflow-wrap:anywhere; }
.mcp-guide h2 { margin: 0 0 6px; font-size: 18px; }
.guide-steps { margin: 20px 0; padding-left: 24px; display: grid; gap: 18px; }
.guide-steps li { padding-left: 4px; }
.token-created-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.connection-section { margin-bottom: 18px; }
.connection-section h3 { margin: 0 0 6px; font-size: 15px; }
.config-fields { margin: 10px 0 0; border: 1px solid var(--rp-border); border-radius: 10px; overflow: hidden; }
.config-fields > div { display: grid; grid-template-columns: 190px minmax(0, 1fr); border-bottom: 1px solid var(--rp-border); }
.config-fields > div:last-child { border-bottom: 0; }
.config-fields dt, .config-fields dd { margin: 0; padding: 10px 12px; font-size: 13px; }
.config-fields dt { color: var(--rp-text-2); background: #f8fafc; font-weight: 600; }
.config-fields dd { color: var(--rp-text); overflow-wrap: anywhere; }
.guide-steps p { margin: 6px 0 10px; color: var(--rp-text-2); line-height: 1.65; font-size: 13.5px; }
.guide-steps code { font-size: 12.5px; }
.mcp-code { margin: 10px 0; overflow-x: auto; overflow-wrap: normal; white-space: pre; }
@media (prefers-color-scheme: dark) { .code-block { background:#1f2937; color:#f3f4f6; } }
@media (max-width: 720px) {
  .form-grid { grid-template-columns: 1fr; }
  .integration-grid { grid-template-columns:1fr; }
  .account-row,.section-title-row { align-items:flex-start; flex-wrap:wrap; }
  .mcp-guide .section-title-row { display: grid; }
  .guide-steps { padding-left: 20px; }
  .config-fields > div { grid-template-columns: 1fr; }
  .config-fields dt { padding-bottom: 4px; }
  .config-fields dd { padding-top: 4px; }
}
</style>
