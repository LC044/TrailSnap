<template>
  <div class="space-y-8">
    <div>
      <h2 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white mb-2">问题反馈</h2>
      <p class="text-gray-500 dark:text-gray-400">遇到问题或有功能建议？可以直接提交，并持续查看审核和版本进展。</p>
    </div>

    <!-- Requirement platform -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-100 dark:border-gray-700 p-6">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 rounded-lg bg-gray-900 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
          <ListChecks class="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 class="font-semibold text-gray-800 dark:text-white">行影集需求平台</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400">提交需求、查看审核结论和版本计划</p>
        </div>
      </div>

      <div class="space-y-3 mb-5">
        <a
          :href="`${requirementPlatformUrl}/?view=submit&type=bug`"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600 hover:border-primary-500 dark:hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-gray-700 transition-colors group focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <div class="w-8 h-8 rounded-md bg-red-100 dark:bg-red-900/30 flex items-center justify-center flex-shrink-0">
            <Bug class="w-4 h-4 text-red-600 dark:text-red-400" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400">报告 Bug</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 truncate">发现异常行为？提交 Bug 报告帮助我们改进</div>
          </div>
          <ExternalLink class="w-4 h-4 text-gray-400 group-hover:text-primary-500 flex-shrink-0" />
        </a>

        <a
          :href="`${requirementPlatformUrl}/?view=submit&type=feature`"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600 hover:border-primary-500 dark:hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-gray-700 transition-colors group focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <div class="w-8 h-8 rounded-md bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
            <Lightbulb class="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400">功能建议</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 truncate">有想要的新功能？告诉我们你的想法</div>
          </div>
          <ExternalLink class="w-4 h-4 text-gray-400 group-hover:text-primary-500 flex-shrink-0" />
        </a>

        <a
          :href="`${requirementPlatformUrl}/?view=public`"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600 hover:border-primary-500 dark:hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-gray-700 transition-colors group focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <div class="w-8 h-8 rounded-md bg-green-100 dark:bg-green-900/30 flex items-center justify-center flex-shrink-0">
            <ListChecks class="w-4 h-4 text-green-600 dark:text-green-400" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400">查看需求与版本进度</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 truncate">浏览公开需求、审核状态和版本批次</div>
          </div>
          <ExternalLink class="w-4 h-4 text-gray-400 group-hover:text-primary-500 flex-shrink-0" />
        </a>
      </div>

      <div class="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
        <AlertCircle class="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
        <p class="text-xs text-amber-700 dark:text-amber-300">提交前请先搜索已有需求，避免重复。报告问题时请尽量附上复现步骤、版本和环境信息。</p>
      </div>
    </div>

    <section class="ts-surface p-5 md:p-6 space-y-4" aria-labelledby="ai-feedback-title">
      <div class="flex items-start gap-3">
        <div class="w-10 h-10 rounded-xl bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center flex-shrink-0">
          <Sparkles class="w-5 h-5 text-primary-600 dark:text-primary-400" />
        </div>
        <div class="min-w-0">
          <h3 id="ai-feedback-title" class="font-semibold">让你的 AI 帮忙</h3>
          <p class="ts-muted text-sm mt-1">先说说你的想法，再交给你自己的 AI 帮忙整理、设计或尝试实现。</p>
        </div>
      </div>
      <div>
        <label for="ai-feedback-idea" class="block text-sm font-medium mb-2">你的想法 <span class="ts-muted font-normal">（可选，也可以稍后告诉 AI）</span></label>
        <textarea id="ai-feedback-idea" v-model="idea" rows="3" maxlength="4000"
          class="ts-input w-full resize-y" placeholder="描述遇到的问题，或你希望增加的功能……"></textarea>
      </div>
      <div class="flex flex-wrap gap-2" aria-label="选择 AI 帮助方式">
        <button v-for="option in aiModes" :key="option.value" type="button"
          class="ts-button" :class="aiMode === option.value ? 'ts-button-primary' : 'ts-button-secondary'"
          :aria-pressed="aiMode === option.value" @click="aiMode = option.value; copyStatus = ''">{{ option.label }}</button>
      </div>
      <p v-if="aiMode === 'code'" class="ts-muted text-sm">需要能读写本地文件、运行命令的 AI 工具。可以仅在本地使用，也可以贡献 PR；PR 还需维护者审核，合并后等待版本发布。</p>
      <p v-else-if="aiMode === 'design'" class="ts-muted text-sm">AI 会帮你整理使用场景、交互和验收标准，形成设计提案后提交给维护者评估。</p>
      <div class="flex flex-wrap items-center gap-3">
        <button type="button" class="ts-button ts-button-primary" @click="copyPrompt"><Copy class="w-4 h-4" />复制给 AI</button>
        <span class="ts-muted text-sm" role="status">{{ copyStatus || '复制后粘贴到你自己的 AI 对话中' }}</span>
      </div>
      <ol v-if="copyStatus" class="ts-muted text-sm list-decimal pl-5 space-y-1" aria-label="下一步">
        <li>打开你的 Trae、Codex 等 AI 工具，粘贴并发送。</li>
        <li>告诉 AI 想解决什么问题，它会整理信息并返回真实的提交结果。</li>
        <li>提交后打开公开需求链接查看进度，私下保存修改入口，方便下次继续。</li>
      </ol>
      <p class="ts-muted text-xs">无需登录需求平台，无需配置 MCP。代码贡献需 AI 具备本地开发及 GitHub 操作能力。</p>
      <details :open="showPrompt">
        <summary class="text-sm cursor-pointer ts-muted">查看完整提示词</summary>
        <textarea ref="promptText" :value="prompt" readonly rows="12" aria-label="可复制的完整提示词"
          class="ts-input w-full mt-3 text-sm" @focus="($event.target as HTMLTextAreaElement).select()"></textarea>
      </details>
    </section>

    <!-- Community -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-100 dark:border-gray-700 p-6">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 rounded-lg bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center flex-shrink-0">
          <MessageCircle class="w-5 h-5 text-primary-600 dark:text-primary-400" />
        </div>
        <div>
          <h3 class="font-semibold text-gray-800 dark:text-white">交流社群</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400">加入社群与其他用户交流</p>
        </div>
      </div>

      <div class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600">
        <div class="w-8 h-8 rounded-md bg-sky-100 dark:bg-sky-900/30 flex items-center justify-center flex-shrink-0">
          <i class="mgc_qq_line text-sky-600 dark:text-sky-400 text-sm"></i>
        </div>
        <div>
          <div class="text-sm font-medium text-gray-800 dark:text-white">QQ 群</div>
          <div class="text-xs text-gray-500 dark:text-gray-400">1078946004</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Bug, Lightbulb, ExternalLink, ListChecks, AlertCircle, MessageCircle, Sparkles, Copy } from 'lucide-vue-next'
import { copyTextToClipboard } from '@/utils/clipboard'

const requirementPlatformUrl = (import.meta.env.VITE_REQUIREMENT_PLATFORM_URL || 'https://feedback.trailsnap.cn').replace(/\/$/, '')
const aiModes = [
  { value: 'feedback', label: '帮我整理并提交' },
  { value: 'design', label: '帮我形成设计方案' },
  { value: 'code', label: '帮我尝试实现' },
] as const
const aiMode = ref<'feedback' | 'design' | 'code'>('feedback')
const idea = ref('')
const copyStatus = ref('')
const showPrompt = ref(false)
const promptText = ref<HTMLTextAreaElement | null>(null)
const prompt = computed(() => `请帮助我参与 TrailSnap（行影集）的${aiMode.value === 'code' ? '代码贡献' : '需求反馈'}。
我的想法：${idea.value.trim() || '请先询问我遇到的问题或想实现的功能。'}

请先读取官方 HTTP 指南：${requirementPlatformUrl}/api/agent-guide
项目仓库：https://github.com/LC044/TrailSnap
需求平台：${requirementPlatformUrl}
日志地址：行影集数据目录下logs文件夹的.log文件

这是普通用户流程，不需要需求平台账号、MCP 或管理员令牌。${aiMode.value === 'code' ? '先确认仅本地使用还是贡献 PR，再决定是否公开提交需求。需要贡献 PR 时，' : ''}请直接用公开 HTTP 接口搜索已有需求，整理问题、使用场景、目标、范围和验收标准；需要时编写设计方案。只询问影响方案的重要歧义。${aiMode.value === 'code' ? '仅在需要公开贡献且已获授权时提交；' : '我的想法明确时直接整理并提交；'}有敏感信息或关键歧义时先让我确认。如果找到相似需求，先说明差异；没有修改权限不能改别人的需求。
请按指南自动生成并安全保存单条需求的编辑回执，以后继续补充时用它修改自己的需求。不要让我配置令牌，不把凭证放入代码、PR、公开文档或日志。返回公开需求链接，并单独提供私有管理链接，我打开一次即可在浏览器中继续管理。不要上传照片、密钥或未脱敏日志。
${aiMode.value === 'code' ? `
请先确认我是仅在本地使用，还是希望贡献 PR。仅本地使用时不强制提交公共需求。请检查本地仓库，没有仓库时确认克隆位置，阅读 AGENTS.md、相关规范和测试说明，按官方指南的普通贡献流程执行，不调用受信任 Agent 的 MCP 审核或任务领取接口。计划清晰且已获授权时直接实现和测试。贡献 PR 时通过我的 GitHub 授权提交、推送并创建 PR，没有主仓库权限走 Fork。PR 关联平台需求；尚未关联 Issue 时创建草稿 PR 等待维护者关联，不直接创建 GitHub Issue。说明创建 PR、合并与版本发布是不同阶段，不自动合并或发布，CLA 声明须基于我的明确同意。` : aiMode.value === 'design' ? '\n本次请形成设计提案，包含问题、使用场景、目标、范围、交互方案、风险和验收标准，按指南提交到需求平台。提案不代表已经批准，不修改代码。' : '\n本次只整理并提交需求，不修改代码。'}
最后用简洁结果卡说明：需求编号与标题、公开链接、当前状态、接下来谁需要做什么、验证结果及未完成事项。私有修改入口单独提供，说明换设备或清除浏览器数据前需要保存。没有所需工具时说明限制，不假装提交成功。`)

async function copyPrompt() {
  if (await copyTextToClipboard(prompt.value)) {
    copyStatus.value = '已复制，粘贴给 AI 就可以开始'
  } else {
    showPrompt.value = true
    await nextTick()
    promptText.value?.focus()
    promptText.value?.select()
    copyStatus.value = '浏览器未允许自动复制。完整提示词已选中，请按 Ctrl/Cmd+C，或长按文字复制'
  }
}
</script>
