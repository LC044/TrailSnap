<template>
  <div class="app-shell" :class="{ 'nav-collapsed': navCollapsed }">
    <AppHeader ref="header" :items="visibleTabs" :active="tab" :collapsed="navCollapsed" :user="user"
      @navigate="switchTab" @notification="onNotification" @login="authDialog = true" @toggle="toggleNavigation" @user-command="onUserCommand" />

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
          :can-edit-summary="canEditSummary"
          :user-role="user?.role || 'viewer'"
          @back="closeDetail"
          @copy-link="copyRequirementLink(detailTarget)"
          @follow="followDetail"
          @edit="openEdit(detailTarget)"
          @status="openStatusChange(detailTarget)"
          @review="openReview(detailTarget)"
          @download="downloadAttachment(detailTarget, $event)"
          @refresh="refreshDetail"
        />
        <div v-else class="panel empty">需求不存在或你没有查看权限。</div>
      </section>

      <PublicRequirementsPage v-else-if="tab === 'public'" :stats="stats" :filters="filters" :status-options="statusOptions"
        v-model:sort-by="sortBy" :items="sortedRequirements" :manager="isManager" :user="user"
        @reload="loadRequirements" @submit="switchTab('submit')" @open="openDetail" @action="onRowAction" />

      <!-- ============ 管理总览 ============ -->
      <DashboardPage v-else-if="tab === 'dashboard' && isManager && dashboard" :data="dashboard" />

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
              <el-button type="primary" size="large" :icon="Promotion" :loading="busy" native-type="submit">{{ !user && !preflightChecked ? 'AI 分析并继续' : '提交需求' }}</el-button>
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
      <MyRequirementsPage v-else-if="tab === 'mine'" :items="myRequirements" :manager="isManager" :user="user"
        @login="authDialog = true" @open="openDetail" @action="onRowAction" />

      <!-- ============ 版本计划 ============ -->
      <VersionPlanPage v-else-if="tab === 'versions'" :batches="batches" :candidates="candidates" :manager="isManager"
        :candidate-selection="candidateSelection" :delivery-statuses="deliveryStatuses" :allowed-statuses="allowedBatchStatuses"
        @create="openCreateBatch" @edit="openEditBatch" @add="addCandidate" @remove="removeBatchItem" @lock="lockBatch"
        @update-state="updateBatchState" @update-delivery="updateDelivery" />

      <!-- ============ Token 用量 ============ -->
      <section v-else-if="tab === 'usage'">
        <TokenUsage :manager="isManager" />
      </section>

      <!-- ============ 需求审核 ============ -->
      <RequirementReviewPage v-else-if="tab === 'admin' && isManager" :items="adminRequirements" :user="user"
        v-model:status="adminStatus" :statuses="reviewStatuses" :syncing="syncingGithub"
        @reload="loadAdmin" @sync="syncGithubIssues" @open="openDetail" @action="onRowAction" />

      <!-- ============ GitHub 与 Agent 集成 ============ -->
      <IntegrationSettingsPage v-else-if="tab === 'integrations' && isManager && user" :user="user" :tokens="agentTokens"
        :github-oauth-enabled="githubOauthEnabled" :mcp-url="mcpUrl" :mcp-config="mcpConfigExample" :mcp-env-config="mcpEnvConfigExample"
        @unlink-github="unlinkGithub" @link-github="startGithub('link')" @create-token="tokenDialog = true"
        @connect-token="openMcpConnection" @revoke-token="revokeToken" @copy="copyText" />

      <!-- ============ AI 模型设置 ============ -->
      <AISettingsPage v-else-if="tab === 'ai-settings' && isManager" />

      <!-- ============ 角色管理 ============ -->
      <UserManagementPage v-else-if="tab === 'users' && user?.role === 'owner'" :users="users" @toggle-role="toggleRole" />
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

    <el-dialog v-model="analysisDialog" title="AI 需求分析" width="min(94vw, 680px)" :close-on-click-modal="analysisProgress.done" :show-close="analysisProgress.done">
      <div class="analysis-progress-dialog">
        <el-progress :percentage="analysisProgress.percent" :status="analysisProgress.failed ? 'exception' : analysisProgress.done ? 'success' : undefined" />
        <div class="analysis-current"><el-icon :class="{ spinning: !analysisProgress.done }"><MagicStick /></el-icon><div><strong>{{ analysisProgress.title }}</strong><p>{{ analysisProgress.detail }}</p></div></div>
        <ol class="analysis-stages">
          <li v-for="stage in analysisProgress.stages" :key="stage.label" :class="stage.status"><span></span>{{ stage.label }}</li>
        </ol>
        <div v-if="analysisProgress.reasoningOutput || analysisProgress.output || analysisProgress.attempt" class="analysis-stream">
          <div class="analysis-stream-head"><strong>AI 分析过程</strong><span v-if="analysisProgress.attempt">第 {{ analysisProgress.attempt }}/{{ analysisProgress.maxAttempts }} 次</span></div>
          <pre v-if="analysisProgress.reasoningOutput" class="analysis-reasoning">{{ analysisProgress.reasoningOutput }}</pre>
          <div v-if="analysisProgress.output" class="analysis-output-label">结构化输出</div>
          <pre v-if="analysisProgress.output" ref="analysisOutputEl">{{ analysisProgress.output }}</pre>
          <pre v-else-if="!analysisProgress.reasoningOutput" ref="analysisOutputEl">等待 AI 返回内容…</pre>
          <ul v-if="analysisProgress.retryMessages.length" class="analysis-retries"><li v-for="(message, index) in analysisProgress.retryMessages" :key="index">第 {{ index + 1 }} 次校验未通过：{{ message }}</li></ul>
        </div>
        <div v-if="analysisProgress.summary" class="analysis-result">
          <strong>分析结果</strong><p>{{ analysisProgress.summary }}</p>
        </div>
        <div v-if="analysisProgress.done && preflightQuestions.length" class="analysis-questions">
          <div class="analysis-questions-head"><strong>AI 需要补充确认</strong><span>回答后将自动完善并提交表单</span></div>
          <div v-for="question in preflightQuestions" :key="question.question_id" class="analysis-question">
            <label>{{ question.question }}</label>
            <el-select v-if="question.suggested_options.length" v-model="preflightAnswers[question.question_id]" allow-create filterable placeholder="选择或输入答案">
              <el-option v-for="option in question.suggested_options" :key="option" :label="option" :value="option" />
            </el-select>
            <el-input v-else v-model="preflightAnswers[question.question_id]" type="textarea" :rows="2" placeholder="请输入答案；不确定时可填写“不确定”" />
            <small>{{ question.rationale }}</small>
          </div>
        </div>
        <el-alert v-if="analysisProgress.appliedUpdates.length" type="success" :closable="false" :title="`AI 已根据回答更新：${analysisProgress.appliedUpdates.join('、')}`" />
        <el-alert v-if="analysisProgress.done" :type="analysisProgress.failed ? 'warning' : 'success'" :closable="false" :title="analysisProgress.failed ? (submittedRequirement ? '需求已保存，AI 分析仍可在后台继续' : 'AI 分析未通过，可查看详细原因后重试') : (submittedRequirement ? 'AI 已完成分析，结果已写入需求详情' : (preflightQuestions.length ? '请直接在下方回答，AI 将自动完善并提交需求' : 'AI 已完成提交前分析'))" />
      </div>
      <template #footer>
        <el-button v-if="analysisProgress.done" @click="analysisDialog = false">关闭</el-button>
        <el-button v-if="analysisProgress.done && preflightQuestions.length" type="primary" :loading="busy" @click="answerPreflightAndSubmit">应用回答并提交需求</el-button>
        <el-button v-if="analysisProgress.done && submittedRequirement" type="primary" @click="openAnalyzedRequirement">查看需求与分析结果</el-button>
      </template>
    </el-dialog>

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
        <el-form-item label="Agent 角色"><el-select v-model="tokenForm.agent_role" clearable placeholder="通用管理客户端"><el-option label="编码" value="coding" /><el-option label="测试" value="testing" /><el-option label="审查" value="review" /></el-select></el-form-item>
        <el-form-item label="限制到交付任务（可选）"><el-input v-model="tokenForm.task_id" placeholder="DeliveryTask UUID；留空表示不限具体任务" /></el-form-item>
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

    <!-- ============ 修改状态 ============ -->
    <el-dialog v-model="statusDialog" title="修改需求状态" width="min(92vw, 480px)">
      <p v-if="statusTarget" class="status-dialog-title">
        <strong>{{ statusTarget.title }}</strong>
        <span class="tag" :class="`s-${statusTarget.status}`">{{ statusLabel(statusTarget.status) }}</span>
      </p>
      <el-form label-position="top" @submit.prevent="submitStatusChange">
        <el-form-item label="目标状态" required>
          <el-select v-model="statusForm.status" filterable placeholder="选择目标状态">
            <el-option v-for="status in statusChangeOptions" :key="status" :label="statusLabel(status)" :value="status" />
          </el-select>
          <div class="field-hint">流转将在状态时间线中记录操作人与原因。</div>
        </el-form-item>
        <el-form-item label="变更原因" required>
          <el-input v-model="statusForm.reason" type="textarea" :rows="4" maxlength="2000" show-word-limit placeholder="请说明状态变更的原因" />
        </el-form-item>
        <el-alert v-if="statusTarget?.github_issue_number" type="info" :closable="false" show-icon title="已关联 GitHub Issue">
          状态保存后会异步同步 GitHub Issue 的状态标签与开闭状态。
        </el-alert>
      </el-form>
      <template #footer><el-button @click="statusDialog = false">取消</el-button><el-button type="primary" :loading="busy" native-type="submit" @click="submitStatusChange">保存</el-button></template>
    </el-dialog>

    <!-- ============ 创建/编辑版本批次 ============ -->
    <el-dialog v-model="batchDialog" :title="batchEditTarget ? '编辑版本批次' : '创建版本批次'" width="min(92vw, 560px)">
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
      <template #footer><el-button @click="batchDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="submitBatch">{{ batchEditTarget ? '保存' : '创建' }}</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import {
  Checked, Collection, Connection, DataAnalysis, Document, DocumentAdd, EditPen, Flag, Guide,
  InfoFilled, MagicStick, Opportunity, Promotion, Service, Setting, Switch, Tickets, TrendCharts, Warning,
} from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElMessage, ElMessageBox } from 'element-plus'
import { storeToRefs } from 'pinia'
import axios from 'axios'
import logoUrl from './assets/logo.svg'
import { api, type AgentToken, type Batch, type Dashboard, type Requirement, type RequirementHistory, type User as ApiUser } from './api'
import {
  requirementStatuses, reviewActionLabels,
  statusLabel,
} from './labels'
import RequirementDetail from './RequirementDetail.vue'
import TokenUsage from './TokenUsage.vue'
import AISettingsPage from './AISettingsPage.vue'
import { useSessionStore } from './stores/session'
import { usePreflightTriage } from './composables/usePreflightTriage'
import PublicRequirementsPage from './views/requirements/PublicRequirementsPage.vue'
import DashboardPage from './views/dashboard/DashboardPage.vue'
import VersionPlanPage from './views/versions/VersionPlanPage.vue'
import RequirementReviewPage from './views/requirements/RequirementReviewPage.vue'
import UserManagementPage from './views/settings/UserManagementPage.vue'
import MyRequirementsPage from './views/requirements/MyRequirementsPage.vue'
import AppHeader from './layouts/AppHeader.vue'
import IntegrationSettingsPage from './views/settings/IntegrationSettingsPage.vue'
import { useRoute, useRouter } from 'vue-router'
import type { AppTab as Tab } from './router'

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

const route = useRoute()
const router = useRouter()
const tab = ref<Tab>((route.meta.tab as Tab | undefined) || 'public')
const navCollapsed = ref(localStorage.getItem('rp_nav_collapsed') === '1')
const header = ref<InstanceType<typeof AppHeader> | null>(null)
const session = useSessionStore()
const { user, isManager } = storeToRefs(session)
const requirements = ref<Requirement[]>([]), myRequirements = ref<Requirement[]>([]), adminRequirements = ref<Requirement[]>([])
const batches = ref<Batch[]>([]), users = ref<ApiUser[]>([]), candidates = ref<Requirement[]>([])
const agentTokens = ref<AgentToken[]>([])
const dashboard = ref<Dashboard | null>(null), detailHistory = ref<RequirementHistory[]>([])
const busy = ref(false), syncingGithub = ref(false), authDialog = ref(false), reviewDialog = ref(false), editDialog = ref(false), statusDialog = ref(false), batchDialog = ref(false), tokenDialog = ref(false), mcpConnectionDialog = ref(false)
const analysisDialog = ref(false)
const analysisOutputEl = ref<HTMLElement | null>(null)
const submittedRequirement = ref<Requirement | null>(null)
const githubOauthEnabled = ref(false), createdToken = ref(''), createdTokenId = ref(''), connectionToken = ref('')
const authMode = ref<'login' | 'register'>('login'), adminStatus = ref('pending_review')
const sortBy = ref('updated')
const detailRouteNumber = ref<number | null>(route.name === 'requirement-detail' ? Number(route.params.number) : null)
const detailLoading = ref(false), detailTarget = ref<Requirement | null>(null)
const reviewTarget = ref<Requirement | null>(null)
const statusTarget = ref<Requirement | null>(null)
const editTarget = ref<Requirement | null>(null)
const editForm = reactive({ type: 'feature', severity: 'medium', title: '', description: '', steps_to_reproduce: '', current_behavior: '', expected_behavior: '', log_text: '', product_version: '', visibility: 'public' })
const filters = reactive({ q: '', type: '', status: '' })
const authForm = reactive({ username: '', email: '', password: '' })
const requirementForm = reactive(emptyRequirementForm())
const pendingFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const reviewForm = reactive({ action: 'candidate', reason: '', priority: 'normal', risk_level: 'medium', duplicate_of_id: '' })
const statusForm = reactive({ status: '', reason: '' })
const batchForm = reactive({ name: '', version_name: '', goal: '', batch_type: 'feature', target_date: '', max_risk_level: 'high' })
const batchEditTarget = ref<Batch | null>(null)
const scopeOptions = ['requirements:read', 'requirements:write', 'requirements:review', 'versions:read', 'versions:write', 'github:write', 'specs:read', 'tasks:write', 'tasks:claim', 'runs:write', 'artifacts:write']
const tokenForm = reactive({ name: '', scopes: ['requirements:read'], expires_in_days: 90, project_key: 'trailsnap', agent_role: '', task_id: '' })
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
const preflightChecked = ref(false)
const preflightQuestions = ref<Array<{ question_id: string; target_field?: string; question: string; rationale: string; suggested_options: string[] }>>([])
const preflightAnswers = reactive<Record<string, string>>({})
const {
  progress: analysisProgress,
  reset: resetAnalysisProgress,
  run: runPreflightAnalysis,
  setStage: setAnalysisStage,
} = usePreflightTriage(requirementForm, preflightAnswers, analysisOutputEl)

const visibleTabs = computed(() => [
  { key: 'public' as Tab, label: '公开需求', icon: Document },
  { key: 'submit' as Tab, label: '提交需求', icon: EditPen },
  { key: 'mine' as Tab, label: '我的需求', icon: Collection },
  { key: 'versions' as Tab, label: '版本计划', icon: Flag },
  { key: 'usage' as Tab, label: 'Token 用量', icon: TrendCharts },
  ...(isManager.value ? [{ key: 'dashboard' as Tab, label: '总览看板', icon: DataAnalysis }] : []),
  ...(isManager.value ? [{ key: 'admin' as Tab, label: '需求审核', icon: Checked }] : []),
  ...(isManager.value ? [{ key: 'ai-settings' as Tab, label: 'AI 设置', icon: MagicStick }] : []),
  ...(isManager.value ? [{ key: 'integrations' as Tab, label: '集成设置', icon: Connection }] : []),
  ...(user.value?.role === 'owner' ? [{ key: 'users' as Tab, label: '角色管理', icon: Setting }] : []),
])

function toggleNavigation() {
  navCollapsed.value = !navCollapsed.value
  localStorage.setItem('rp_nav_collapsed', navCollapsed.value ? '1' : '0')
}

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
const canEditSummary = computed(() => !!user.value && !!detailTarget.value && (isManager.value || detailTarget.value.created_by === user.value.id))

async function refreshDetail() {
  if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
}

async function loadRequirements() {
  const p = new URLSearchParams()
  if (filters.q) p.set('q', filters.q)
  if (filters.type) p.set('type', filters.type)
  if (filters.status) p.set('status', filters.status)
  else p.set('include_closed', 'false')
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
    await router.push({ name: value })
  }
  tab.value = value
  if (route.name !== value) await router.push({ name: value })
  await scrollActiveTab()
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
async function scrollActiveTab() {
  await nextTick()
  header.value?.element?.querySelector<HTMLElement>('button.active')?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
}
async function restoreSession() {
  await session.restore()
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
    session.acceptSession(result.token, result.user)
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
    const result = await api.createAgentToken({ ...tokenForm, agent_role: tokenForm.agent_role || null, task_id: tokenForm.task_id.trim() || null })
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

const editableFormLabels: Record<string, string> = {
  type: '需求类型', title: '标题', description: '需求描述', current_behavior: '当前行为', expected_behavior: '期望行为',
  steps_to_reproduce: '复现步骤', severity: '影响程度', product_version: '产品版本',
}

function applyAIFormUpdates(updates: unknown) {
  const values = updates && typeof updates === 'object' ? updates as Record<string, unknown> : {}
  const changed: string[] = []
  for (const [field, rawValue] of Object.entries(values)) {
    if (!(field in editableFormLabels) || typeof rawValue !== 'string' || !rawValue.trim()) continue
    const value = rawValue.trim()
    if (field === 'type' && !['bug', 'improvement', 'feature'].includes(value)) continue
    if (field === 'severity' && !['low', 'medium', 'high', 'critical'].includes(value)) continue
    if (field === 'title' && (value.length < 4 || value.length > 160)) continue
    if (field === 'description' && (value.length < 10 || value.length > 8000)) continue
    if (field in requirementForm && requirementForm[field as keyof typeof requirementForm] !== value) {
      ;(requirementForm as Record<string, unknown>)[field] = value
      changed.push(editableFormLabels[field]!)
    }
  }
  analysisProgress.appliedUpdates = changed
}

async function submitRequirement() {
  const titleLength = requirementForm.title.trim().length
  const descriptionLength = requirementForm.description.trim().length
  if (titleLength < 4 || titleLength > 160) { ElMessage.error('标题需要 4–160 个字符'); return }
  if (descriptionLength < 10 || descriptionLength > 8000) { ElMessage.error('需求描述需要 10–8,000 个字符'); return }
  busy.value = true
  resetAnalysisProgress(preflightChecked.value && analysisProgress.appliedUpdates.length > 0)
  analysisDialog.value = true
  try {
    if (!preflightChecked.value) {
      const preflight = await runPreflightAnalysis()
      preflightChecked.value = true
      preflightQuestions.value = preflight.available ? (preflight.questions || []) : []
      if (preflightQuestions.value.length) {
        analysisProgress.percent = 100; analysisProgress.done = true; analysisProgress.title = '分析完成，需要补充信息'; analysisProgress.detail = `AI 提出了 ${preflightQuestions.value.length} 个问题，请直接在当前窗口回答`
        analysisProgress.summary = String(preflight.analysis?.problem_summary || '')
        setAnalysisStage(1, 'done')
        ElMessage.info('请在当前窗口回答问题，AI 会自动完善并提交表单')
        return
      }
      if (!preflight.available) {
        analysisProgress.retryMessages.push(preflight.reason || '模型未返回可用结果')
        ElMessage.info('AI 分析未通过校验，将直接提交需求；详细原因可在窗口中查看')
      }
    }
    analysisProgress.percent = 48; analysisProgress.title = '正在保存需求'; analysisProgress.detail = '创建需求记录并加入后台分析队列'
    setAnalysisStage(0, 'done'); setAnalysisStage(1, 'done'); setAnalysisStage(2, 'active')
    const aiAnswers = Object.fromEntries(preflightQuestions.value.map(item => [item.question_id, (preflightAnswers[item.question_id] || '不确定').trim()]))
    const created = await api.createRequirement({ ...requirementForm, ai_clarification_answers: aiAnswers })
    submittedRequirement.value = created
    let uploadError: unknown = null
    for (const file of pendingFiles.value) {
      try { await api.uploadAttachment(created.id, file, created.upload_token) } catch (e) { uploadError = e; break }
    }
    Object.assign(requirementForm, emptyRequirementForm())
    preflightChecked.value = false
    preflightQuestions.value = []
    Object.keys(preflightAnswers).forEach(key => delete preflightAnswers[key])
    pendingFiles.value = []
    if (fileInput.value) fileInput.value.value = ''
    analysisProgress.percent = 68; analysisProgress.title = '需求已保存，AI 正在后台分析'; analysisProgress.detail = '分析器会提取问题摘要、完整度、重复候选和验收草案'
    setAnalysisStage(2, 'done'); setAnalysisStage(3, 'active')
    let analyzed: Requirement | null = null
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const latest = await api.requirementByNumber(created.public_number!)
      if (latest.triage) { analyzed = latest; break }
      analysisProgress.percent = Math.min(94, 68 + attempt)
      await new Promise(resolve => window.setTimeout(resolve, 1500))
    }
    if (analyzed) {
      submittedRequirement.value = analyzed
      analysisProgress.percent = 100; analysisProgress.done = true; analysisProgress.title = 'AI 分析已完成'; analysisProgress.detail = '结构化结果已保存，可在需求详情中持续查看'
      analysisProgress.summary = String(analyzed.confirmed_summary || analyzed.triage?.problem_summary || analyzed.triage?.summary || '')
      setAnalysisStage(3, 'done')
    } else {
      analysisProgress.percent = 100; analysisProgress.done = true; analysisProgress.failed = true; analysisProgress.title = '后台分析仍在进行'; analysisProgress.detail = '等待时间较长，但需求已经保存，不会丢失；稍后进入详情页刷新即可查看结果'
    }
    if (uploadError) ElMessage.warning(`需求已提交，但有附件上传失败：${errorMessage(uploadError)}`)
    else ElMessage.success('需求已提交')
  } catch (e) {
    analysisProgress.percent = 100; analysisProgress.done = true; analysisProgress.failed = true; analysisProgress.title = '提交或分析失败'; analysisProgress.detail = errorMessage(e)
    ElMessage.error(errorMessage(e))
  } finally { busy.value = false }
}

async function answerPreflightAndSubmit() {
  if (busy.value) return
  const answered = Object.fromEntries(preflightQuestions.value.map(question => [question.question_id, (preflightAnswers[question.question_id] || '不确定').trim()]))
  busy.value = true
  resetAnalysisProgress()
  analysisDialog.value = true
  analysisProgress.title = '正在根据回答完善需求'
  analysisProgress.detail = 'AI 正在结合你的回答更新需求表单'
  try {
    const result = await runPreflightAnalysis()
    const directUpdates = Object.fromEntries(preflightQuestions.value.flatMap(question => {
      const answer = answered[question.question_id]
      return question.target_field && question.target_field in editableFormLabels && answer && answer !== '不确定' ? [[question.target_field, answer]] : []
    }))
    applyAIFormUpdates({ ...directUpdates, ...(result.analysis?.form_updates || {}) })
    preflightQuestions.value = []
    preflightChecked.value = true
  } catch (e) {
    analysisProgress.percent = 100; analysisProgress.done = true; analysisProgress.failed = true
    analysisProgress.title = '未能根据回答完善需求'; analysisProgress.detail = errorMessage(e)
    ElMessage.error(errorMessage(e))
    return
  } finally {
    busy.value = false
  }
  await submitRequirement()
}

async function openAnalyzedRequirement() {
  const target = submittedRequirement.value
  analysisDialog.value = false
  if (target) await openDetail(target)
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
  await router.push({ name: 'requirement-detail', params: { number: item.public_number } })
  window.scrollTo({ top: 0, behavior: 'smooth' })
  await loadDetail(item.public_number)
}
function closeDetail() {
  detailRouteNumber.value = null
  detailTarget.value = null
  detailHistory.value = []
  void router.push({ name: tab.value })
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
watch(() => route.fullPath, () => {
  const number = route.name === 'requirement-detail' ? Number(route.params.number) : null
  detailRouteNumber.value = number
  if (number) void loadDetail(number)
  else {
    detailTarget.value = null
    detailHistory.value = []
    tab.value = (route.meta.tab as Tab | undefined) || 'public'
  }
})

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
  else if (command === 'status') openStatusChange(item)
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

// 常用流转：按当前状态给出推荐的下一步，供弹窗默认展示；其余状态仍可通过筛选选择。
const suggestedStatusTransitions: Record<string, string[]> = {
  submitted: ['pending_review', 'needs_information', 'rejected', 'closed'],
  triaging: ['pending_review', 'needs_information', 'rejected', 'closed'],
  pending_review: ['candidate', 'needs_information', 'deferred', 'rejected', 'closed'],
  needs_information: ['submitted', 'pending_review', 'rejected', 'closed'],
  candidate: ['scheduled', 'developing', 'deferred', 'rejected', 'closed'],
  scheduled: ['developing', 'testing', 'candidate', 'closed'],
  developing: ['testing', 'release_ready', 'closed'],
  testing: ['developing', 'release_ready', 'closed'],
  release_ready: ['released', 'testing', 'closed'],
  released: ['closed'],
  deferred: ['pending_review', 'candidate', 'closed'],
  rejected: ['pending_review', 'closed'],
  duplicate: ['pending_review', 'closed'],
  withdrawn: ['pending_review', 'closed'],
  closed: ['pending_review'],
}
const statusChangeOptions = computed(() => {
  if (!statusTarget.value) return requirementStatuses
  const current = statusTarget.value.status
  const suggested = (suggestedStatusTransitions[current] || []).filter(status => status !== current)
  const rest = requirementStatuses.filter(status => status !== current && !suggested.includes(status))
  return [...suggested, ...rest]
})

function openStatusChange(item: Requirement) {
  statusTarget.value = item
  Object.assign(statusForm, {
    status: (suggestedStatusTransitions[item.status] || requirementStatuses.filter(s => s !== item.status))[0] || '',
    reason: '',
  })
  statusDialog.value = true
}

async function submitStatusChange() {
  if (!statusTarget.value) return
  if (!statusForm.status) { ElMessage.error('请选择目标状态'); return }
  if (statusForm.reason.trim().length < 2) { ElMessage.error('请填写至少 2 个字符的变更原因'); return }
  busy.value = true
  try {
    const updated = await api.updateRequirementStatus(statusTarget.value.id, statusForm.status, statusForm.reason.trim())
    statusDialog.value = false
    ElMessage.success(updated.github_issue_number ? '状态已更新，GitHub Issue 将自动同步' : '状态已更新')
    await refreshManaged()
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

const emptyBatchForm = () => ({ name: '', version_name: '', goal: '', batch_type: 'feature', target_date: '', max_risk_level: 'high' })

function openCreateBatch() {
  batchEditTarget.value = null
  Object.assign(batchForm, emptyBatchForm())
  batchDialog.value = true
}

function openEditBatch(batch: Batch) {
  batchEditTarget.value = batch
  Object.assign(batchForm, {
    name: batch.name, version_name: batch.version_name, goal: batch.goal,
    batch_type: batch.batch_type, target_date: batch.target_date || '', max_risk_level: batch.max_risk_level,
  })
  batchDialog.value = true
}

async function submitBatch() {
  const name = batchForm.name.trim()
  const versionName = batchForm.version_name.trim()
  const goal = batchForm.goal.trim()
  if (name.length < 2 || name.length > 120) { ElMessage.error('版本名称需要 2–120 个字符'); return }
  if (!/^[A-Za-z0-9._-]{1,50}$/.test(versionName)) { ElMessage.error('版本号只能包含 1–50 个英文字母、数字、点、下划线或连字符'); return }
  if (goal.length < 4 || goal.length > 4000) { ElMessage.error('版本目标需要 4–4,000 个字符'); return }
  const payload = { name, version_name: versionName, goal, batch_type: batchForm.batch_type, target_date: batchForm.target_date || null, max_risk_level: batchForm.max_risk_level }
  busy.value = true
  try {
    if (batchEditTarget.value) {
      await api.updateBatch(batchEditTarget.value.id, payload)
      batchDialog.value = false
      ElMessage.success('版本批次已更新')
    } else {
      await api.createBatch(payload)
      batchDialog.value = false
      Object.assign(batchForm, emptyBatchForm())
      ElMessage.success('版本批次已创建')
    }
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
  session.clear()
  tab.value = 'public'
  void loadRequirements()
}

onMounted(async () => {
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
      session.acceptSession(result.token, result.user)
      ElMessage.success('GitHub 登录或绑定成功')
    } catch (e) { ElMessage.error(errorMessage(e)) }
    params.delete('github_grant')
    history.replaceState({}, '', `${window.location.pathname}${params.size ? `?${params}` : ''}`)
  }
  const requestedTab = params.get('view') as Tab | null
  if (requestedTab && ['public', 'dashboard', 'submit', 'mine', 'admin', 'versions', 'usage', 'integrations', 'ai-settings', 'users'].includes(requestedTab)) tab.value = requestedTab
  const requestedType = params.get('type')
  if (requestedType && ['bug', 'improvement', 'feature'].includes(requestedType)) requirementForm.type = requestedType
  if (tab.value === 'submit') {
    try {
      const draft = localStorage.getItem('rp_draft')
      if (draft) Object.assign(requirementForm, JSON.parse(draft))
    } catch { localStorage.removeItem('rp_draft') }
  }
  if (!user.value) await restoreSession()
  if ((['admin', 'dashboard', 'integrations', 'ai-settings'].includes(tab.value) && !isManager.value) || (tab.value === 'users' && user.value?.role !== 'owner')) tab.value = 'public'
  await Promise.all([loadRequirements(), loadBatches()])
  if (tab.value === 'mine') await loadMine()
  if (tab.value === 'admin') await loadAdmin()
  if (tab.value === 'dashboard') await loadDashboard()
  if (tab.value === 'users') await loadUsers()
  if (tab.value === 'integrations') await loadIntegrations()
  if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  await scrollActiveTab()
})
</script>

<style>
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.w-full { width: 100%; }
.status-dialog-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 0 0 14px; }
.status-dialog-title strong { overflow-wrap: anywhere; }
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
