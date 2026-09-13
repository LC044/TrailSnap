<template>
  <section>
    <div class="page-head"><div class="page-head-left"><div class="page-head-icon"><el-icon :size="26"><Connection /></el-icon></div><div><h1>GitHub 与 Agent 集成</h1><p class="sub">管理账号绑定和 MCP 访问令牌</p><p class="desc">令牌按作用域授权，可随时撤销；完整令牌只显示一次。</p></div></div></div>
    <div class="integration-grid">
      <article class="panel integration-card"><h2>GitHub 账号</h2><div v-if="user.github" class="account-row"><img v-if="user.github.avatar_url" :src="user.github.avatar_url" alt="" class="github-avatar" /><div><strong>@{{ user.github.login }}</strong><p class="meta">已绑定，可用于 GitHub 登录</p></div><el-button plain @click="$emit('unlink-github')">解除绑定</el-button></div><div v-else><p class="meta">绑定后可使用 GitHub 登录；平台不会保存 GitHub OAuth 访问令牌。</p><el-button type="primary" :disabled="!githubOauthEnabled" @click="$emit('link-github')">绑定 GitHub</el-button></div><p v-if="!githubOauthEnabled" class="form-hint">服务端尚未配置 GitHub OAuth App。</p></article>
      <article class="panel integration-card"><h2>MCP 接入地址</h2><code class="code-block">{{ mcpUrl }}</code><p class="meta">Codex 使用 Streamable HTTP 和 Bearer Token 连接此地址。</p></article>
    </div>
    <article class="panel integration-card" style="margin-top:16px">
      <div class="section-title-row"><div><h2>Agent 令牌</h2><p class="meta">仅管理自己创建的令牌。</p></div><el-button type="primary" :icon="Key" @click="$emit('create-token')">创建令牌</el-button></div>
      <el-table :data="tokens" style="width:100%"><el-table-column prop="name" label="名称" /><el-table-column prop="token_prefix" label="前缀" width="140" /><el-table-column label="作用域"><template #default="scope"><span class="meta">{{ scope.row.scopes.join('、') }}</span></template></el-table-column><el-table-column label="最后使用" width="170"><template #default="scope">{{ scope.row.last_used_at ? formatDateTime(scope.row.last_used_at) : '从未' }}</template></el-table-column><el-table-column label="状态" width="100"><template #default="scope"><span class="tag no-dot plain">{{ scope.row.revoked_at ? '已撤销' : '有效' }}</span></template></el-table-column><el-table-column label="操作" width="150"><template #default="scope"><el-button v-if="!scope.row.revoked_at" text type="primary" :icon="Connection" @click="$emit('connect-token', scope.row)">接入</el-button><el-button v-if="!scope.row.revoked_at" text type="danger" @click="$emit('revoke-token', scope.row.id)">撤销</el-button></template></el-table-column></el-table>
    </article>
    <article class="panel mcp-guide" style="margin-top:16px">
      <div class="section-title-row"><div><h2>MCP 配置教程</h2><p class="meta">适用于 Codex 桌面端、CLI 和 IDE 扩展，三者共享同一份配置。</p></div><a class="github-link" href="https://developers.openai.com/codex/mcp" target="_blank" rel="noopener">查看官方 MCP 文档</a></div>
      <ol class="guide-steps">
        <li><strong>创建最小权限令牌</strong><p>点击上方“创建令牌”。只查询需求时选择 <code>requirements:read</code>；需要提交或审核时再增加对应写入作用域。令牌只显示一次，请立即保存。</p></li>
        <li><strong>添加请求头配置（推荐）</strong><p>编辑用户级 <code>~/.codex/config.toml</code>。Codex 会在连接 MCP 时直接注入请求头，沙盒内的 Agent 无需读取宿主机环境变量。</p><pre class="code-block mcp-code"><code>{{ mcpConfig }}</code></pre><el-button size="small" @click="$emit('copy', mcpConfig)">复制配置</el-button></li>
        <li><strong>通过 Codex 设置界面接入</strong><p>URL 填 <code>{{ mcpUrl }}</code>；“Bearer 令牌环境变量”留空；在“标头”中填写 <code>Authorization</code> 和 <code>Bearer 完整令牌</code>；“来自环境变量的标头”留空。不要把 <code>bearer_token_env_var</code> 当作标头名。</p></li>
        <li><strong>重启并验证</strong><p>重启 Codex 桌面端或 IDE 扩展，然后运行 <code>codex mcp list</code>，或在 Codex 中输入 <code>/mcp</code>，确认 <code>trailsnap_requirements</code> 已连接。</p></li>
        <li><strong>可选：改用环境变量</strong><p>如果运行环境能够稳定继承宿主机变量，可用下面的配置避免把令牌明文保存在配置文件中。</p><pre class="code-block mcp-code"><code>{{ mcpEnvConfig }}</code></pre><el-button size="small" @click="$emit('copy', mcpEnvConfig)">复制环境变量配置</el-button></li>
      </ol>
      <el-alert type="warning" :closable="false" show-icon title="令牌与连接安全">请求头方案会把令牌保存在用户配置中，请勿提交该文件，并为令牌设置最小权限和有效期；泄露后应立即撤销。MCP 地址必须使用 HTTPS。出现 401 请检查令牌，出现 403 请检查作用域。</el-alert>
    </article>
  </section>
</template>

<script setup lang="ts">
import { Connection, Key } from '@element-plus/icons-vue'
import { formatDateTime } from '../../labels'
import type { AgentToken, User } from '../../api'
defineProps<{ user: User; tokens: AgentToken[]; githubOauthEnabled: boolean; mcpUrl: string; mcpConfig: string; mcpEnvConfig: string }>()
defineEmits<{ 'unlink-github': []; 'link-github': []; 'create-token': []; 'connect-token': [token: AgentToken]; 'revoke-token': [id: string]; copy: [value: string] }>()
</script>
