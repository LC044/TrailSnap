<template>
  <div class="detail-page">
    <button class="detail-back" type="button" @click="emit('back')">
      <el-icon><ArrowLeft /></el-icon>返回需求列表
    </button>

    <header class="detail-header">
      <div>
        <div class="detail-eyebrow">需求详情 <span>REQ-{{ requirement.public_number }}</span></div>
        <h1>{{ requirement.title }}</h1>
        <div class="detail-meta">
          <span class="avatar" :style="{ ...avatarColor(requirement.created_by_name || '用户') }">{{ (requirement.created_by_name || '用户').slice(0, 1) }}</span>
          <strong>{{ requirement.created_by_name || '用户' }}</strong>
          <span>{{ formatDateTime(requirement.created_at) }}</span><span>·</span><span>{{ requirement.follower_count || 0 }} 人关注</span>
        </div>
      </div>
      <el-button :icon="Link" @click="emit('copyLink')">复制链接</el-button>
    </header>

    <div class="detail-layout">
      <div class="detail-main">
        <article class="panel issue-content detail-section-card">
          <h2 class="detail-section-title"><span class="detail-section-icon">概</span>需求描述</h2>
          <div class="markdown-body" v-html="renderMarkdown(requirement.description)"></div>

          <section v-if="requirement.steps_to_reproduce" class="issue-section">
            <h2 class="detail-section-title"><span class="detail-section-icon">复</span>复现步骤</h2>
            <div class="markdown-body" v-html="renderMarkdown(requirement.steps_to_reproduce)"></div>
          </section>
          <section v-if="requirement.current_behavior" class="issue-section">
            <h2 class="detail-section-title"><span class="detail-section-icon">现</span>当前行为</h2>
            <div class="markdown-body" v-html="renderMarkdown(requirement.current_behavior)"></div>
          </section>
          <section v-if="requirement.expected_behavior" class="issue-section">
            <h2 class="detail-section-title"><span class="detail-section-icon">期</span>期望行为</h2>
            <div class="markdown-body" v-html="renderMarkdown(requirement.expected_behavior)"></div>
          </section>

          <div v-if="requirement.triage" class="triage-box">
            <div class="triage-head"><el-icon><MagicStick /></el-icon>AI 分析建议</div>
            <div class="markdown-body compact" v-html="renderMarkdown(triageText)"></div>
          </div>
          <div v-if="requirement.review_reason" class="review-note">
            <strong>审核说明</strong>
            <div class="markdown-body compact" v-html="renderMarkdown(requirement.review_reason)"></div>
          </div>
          <div v-if="requirement.log_text" class="log-panel">
            <strong>日志（仅本人和管理员可见）</strong>
            <pre class="log-text">{{ requirement.log_text }}</pre>
          </div>
          <div v-if="requirement.attachments?.length" class="attachments">
            <strong>附件（仅本人和管理员可见）</strong>
            <div v-for="attachment in requirement.attachments" :key="attachment.id" class="file-row">
              <span>{{ attachment.name }}（{{ formatBytes(attachment.size_bytes) }}）</span>
              <el-button link type="primary" @click="emit('download', attachment)">下载</el-button>
            </div>
          </div>
          <div v-if="manager && requirement.submitter_contact" class="contact-box">
            <strong>提交人联系方式（仅管理员可见）：</strong>{{ requirement.submitter_contact }}
          </div>
        </article>
      </div>

      <aside class="detail-sidebar">
        <article class="panel detail-status">
          <div class="detail-tags">
            <span class="tag" :class="`s-${requirement.status}`">{{ statusLabel(requirement.status) }}</span>
            <span class="tag no-dot" :class="`t-${requirement.type}`">{{ typeLabel(requirement.type) }}</span>
            <span class="tag no-dot" :class="`p-${requirement.priority}`">{{ priorityLabel(requirement.priority) }}</span>
            <span class="tag no-dot" :class="`sev-${requirement.severity}`">影响：{{ severityLabel(requirement.severity) }}</span>
          </div>
          <dl>
            <div><dt>产品版本</dt><dd>{{ requirement.product_version || '未填写' }}</dd></div>
            <div><dt>来源</dt><dd>{{ requirement.source === 'github' ? 'GitHub' : '需求平台' }}</dd></div>
            <div><dt>最后更新</dt><dd>{{ formatDateTime(requirement.updated_at) }}</dd></div>
          </dl>
          <a v-if="requirement.github_issue_url" class="github-link" :href="requirement.github_issue_url" target="_blank" rel="noopener noreferrer">
            查看 GitHub Issue #{{ requirement.github_issue_number }}
          </a>
          <div v-if="requirement.github_pull_requests?.length" class="related-prs">
            <h2>关联 Pull Request</h2>
            <a
              v-for="pullRequest in requirement.github_pull_requests"
              :key="pullRequest.number"
              class="pr-link"
              :href="pullRequest.url"
              target="_blank"
              rel="noopener noreferrer"
            >
              <span class="pr-title">#{{ pullRequest.number }} {{ pullRequest.title }}</span>
              <span class="pr-state" :class="`is-${pullRequest.state}`">
                {{ pullRequest.state === 'merged' ? '已合并' : pullRequest.state === 'open' ? (pullRequest.draft ? '草稿' : '进行中') : '已关闭' }}
              </span>
            </a>
          </div>
          <div class="detail-actions">
            <el-button v-if="canFollow" @click="emit('follow')">关注（{{ requirement.follower_count || 0 }}）</el-button>
            <el-button v-if="manager" @click="emit('edit')">编辑</el-button>
            <el-button v-if="manager" @click="emit('status')">修改状态</el-button>
            <el-button v-if="manager" type="primary" @click="emit('review')">审核</el-button>
          </div>
        </article>

        <article class="panel detail-timeline">
          <h2>状态变化</h2>
          <div v-if="!history.length" class="field-hint">暂无状态记录</div>
          <div v-for="event in history" :key="event.id" class="timeline-item">
            <span class="timeline-dot"></span>
            <div>
              <strong>{{ historyLabel(event) }}</strong>
              <p>{{ event.actor_name }} · {{ formatDateTime(event.created_at) }}</p>
              <p v-if="event.reason" class="timeline-reason">{{ event.reason }}</p>
            </div>
          </div>
        </article>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft, Link, MagicStick } from '@element-plus/icons-vue'
import { ElButton, ElIcon } from 'element-plus'
import MarkdownIt from 'markdown-it'
import type { Requirement, RequirementHistory } from './api'
import { avatarColor, formatDateTime, priorityLabel, severityLabel, statusLabel, typeLabel } from './labels'

type Attachment = NonNullable<Requirement['attachments']>[number]

const props = defineProps<{
  requirement: Requirement
  history: RequirementHistory[]
  manager: boolean
  canFollow: boolean
}>()
const emit = defineEmits<{
  back: []
  copyLink: []
  follow: []
  edit: []
  status: []
  review: []
  download: [attachment: Attachment]
}>()

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
markdown.renderer.rules.link_open = (tokens, index, options, _env, self) => {
  const token = tokens[index]
  if (!token) return ''
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer')
  return self.renderToken(tokens, index, options)
}

const triageText = computed(() => String(
  props.requirement.triage?.summary || props.requirement.triage?.recommendation || '分析已完成',
))
const renderMarkdown = (value?: string) => markdown.render(value || '')
const formatBytes = (size: number) => size < 1024 * 1024 ? `${Math.ceil(size / 1024)}KB` : `${(size / 1024 / 1024).toFixed(1)}MB`
const historyLabel = (event: RequirementHistory) => {
  if (event.before && event.after && event.before !== event.after) return `状态由“${statusLabel(event.before)}”变为“${statusLabel(event.after)}”`
  if (event.action === 'requirement.created') return '需求已提交'
  if (event.action === 'requirement.updated') return '需求内容已更新'
  if (event.action === 'triage.completed') return 'AI 分析完成，进入待审核'
  if (event.after) return `状态更新为“${statusLabel(event.after)}”`
  return '需求有新动态'
}
</script>

<style scoped>
.detail-back { display: inline-flex; align-items: center; gap: 6px; margin: 0 0 18px; padding: 7px 0; border: 0; background: transparent; color: var(--rp-text-2); cursor: pointer; }
.detail-back:hover { color: var(--rp-primary); }
.detail-back:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 3px; border-radius: 4px; }
.detail-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
.detail-eyebrow { margin-bottom: 8px; color: var(--rp-primary); font-size: 12px; font-weight: 700; letter-spacing: .08em; }
.detail-eyebrow span { margin-left: 8px; color: var(--rp-text-3); font-weight: 600; letter-spacing: .02em; }
.detail-header h1 { margin: 0 0 12px; max-width: 920px; font-size: 28px; line-height: 1.3; letter-spacing: -.025em; overflow-wrap: anywhere; }
.detail-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; color: var(--rp-text-3); font-size: 13px; }
.detail-meta .avatar { width: 26px; height: 26px; font-size: 11px; }
.detail-meta strong { color: var(--rp-text-2); font-weight: 600; }
.detail-layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 20px; align-items: start; }
.detail-main, .detail-sidebar { min-width: 0; }
.issue-content { padding: 20px; overflow: hidden; }
.detail-section-card { background: rgba(255,255,255,.96); }
.detail-section-title { display: flex; align-items: center; gap: 10px; margin: 0 0 14px; color: var(--rp-text); font-size: 16px; }
.detail-section-icon { width: 29px; height: 29px; display: inline-flex; align-items: center; justify-content: center; border-radius: 9px; background: var(--rp-primary-soft); color: var(--rp-primary); font-size: 12px; font-weight: 800; }
.issue-author { display: flex; align-items: center; gap: 8px; padding: 12px 18px; border-bottom: 1px solid var(--rp-border); background: #f8fafc; color: var(--rp-text-3); font-size: 13px; }
.issue-author .avatar { width: 28px; height: 28px; font-size: 12px; }
.issue-author strong { color: var(--rp-text); }
.issue-content > .markdown-body { padding: 0 0 4px 39px; }
.issue-section { margin: 18px 0 0; padding: 18px 0 0; border-top: 1px solid var(--rp-border); }
.issue-section > .markdown-body { padding-left: 39px; }
.triage-box, .review-note, .log-panel, .attachments, .contact-box { margin: 18px 0 0; }
.review-note { padding: 12px 14px; border-radius: 10px; background: #f8fafc; border: 1px solid var(--rp-border); }
.review-note > strong { font-size: 13px; }
.log-panel, .attachments { padding-top: 16px; border-top: 1px solid var(--rp-border); }
.detail-sidebar { position: sticky; top: 84px; }
.detail-status, .detail-timeline { padding: 16px; }
.detail-tags { display: flex; flex-wrap: wrap; gap: 8px; padding-bottom: 14px; border-bottom: 1px solid var(--rp-border); }
.detail-status dl { margin: 0; }
.detail-status dl > div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--rp-border); font-size: 13px; }
.detail-status dt { color: var(--rp-text-3); }
.detail-status dd { margin: 0; color: var(--rp-text-2); text-align: right; }
.github-link { display: inline-flex; margin-top: 12px; color: var(--rp-primary); font-size: 13px; text-decoration: none; }
.github-link:hover { text-decoration: underline; }
.related-prs { margin-top: 16px; }
.related-prs h2 { margin: 0 0 8px; color: var(--rp-text); font-size: 13px; }
.pr-link { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; padding: 8px 0; border-top: 1px solid var(--rp-border); color: var(--rp-text-2); font-size: 13px; text-decoration: none; }
.pr-link:hover .pr-title { color: var(--rp-primary); text-decoration: underline; }
.pr-link:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; border-radius: 4px; }
.pr-title { min-width: 0; overflow-wrap: anywhere; }
.pr-state { flex: none; padding: 1px 6px; border-radius: 999px; background: #e2e8f0; color: #475569; font-size: 11px; }
.pr-state.is-open { background: #dcfce7; color: #166534; }
.pr-state.is-merged { background: #f3e8ff; color: #7e22ce; }
.detail-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }
.detail-actions .el-button { margin-left: 0; }
.detail-actions .el-button:first-child:last-child, .detail-actions .el-button:nth-last-child(3):first-child { grid-column: 1 / -1; }
.detail-timeline h2 { margin: 0 0 16px; font-size: 16px; }
.timeline-item { position: relative; display: flex; gap: 10px; padding: 0 0 16px; }
.timeline-item:not(:last-child)::before { content: ''; position: absolute; left: 4px; top: 13px; bottom: 0; width: 1px; background: var(--rp-border); }
.timeline-dot { position: relative; z-index: 1; width: 9px; height: 9px; margin-top: 5px; border-radius: 50%; background: var(--rp-primary); flex: none; }
.timeline-item strong { font-size: 13px; line-height: 1.45; }
.timeline-item p { margin: 3px 0 0; color: var(--rp-text-3); font-size: 12px; line-height: 1.45; }
.timeline-item .timeline-reason { color: var(--rp-text-2); }
.markdown-body { min-width: 0; color: var(--rp-text-2); font-size: 14px; line-height: 1.75; overflow-wrap: anywhere; }
.markdown-body.compact { font-size: 13px; }
.markdown-body :deep(:first-child) { margin-top: 0; }
.markdown-body :deep(:last-child) { margin-bottom: 0; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { color: var(--rp-text); line-height: 1.4; }
.markdown-body :deep(h1) { font-size: 22px; padding-bottom: 8px; border-bottom: 1px solid var(--rp-border); }
.markdown-body :deep(h2) { font-size: 18px; padding-bottom: 6px; border-bottom: 1px solid var(--rp-border); }
.markdown-body :deep(h3) { font-size: 16px; }
.markdown-body :deep(a) { color: var(--rp-primary); }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 1px 14px; border-left: 4px solid var(--rp-border); color: var(--rp-text-3); }
.markdown-body :deep(code) { padding: 2px 5px; border-radius: 5px; background: #f1f5f9; color: #be123c; font-size: 12.5px; }
.markdown-body :deep(pre) { max-width: 100%; padding: 14px; border-radius: 9px; background: #0f172a; color: #e2e8f0; overflow-x: auto; }
.markdown-body :deep(pre code) { padding: 0; background: transparent; color: inherit; }
.markdown-body :deep(img) { max-width: 100%; height: auto; border-radius: 8px; }
.markdown-body :deep(table) { display: block; max-width: 100%; border-collapse: collapse; overflow-x: auto; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: 7px 10px; border: 1px solid var(--rp-border); }

@media (max-width: 860px) {
  .detail-layout { grid-template-columns: 1fr; }
  .detail-sidebar { position: static; }
}
@media (max-width: 520px) {
  .detail-header { display: grid; }
  .detail-header h1 { font-size: 22px; }
  .detail-header .el-button { width: 100%; }
  .detail-meta { align-items: flex-start; }
  .issue-content > .markdown-body, .issue-section > .markdown-body { padding-left: 0; }
}
</style>
