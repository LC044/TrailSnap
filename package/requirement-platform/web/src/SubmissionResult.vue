<template>
  <section class="panel submission-result" role="status" aria-label="提交结果">
    <strong>已提交 REQ-{{ requirement.public_number }}：{{ requirement.title }}</strong>
    <p>{{ nextAction(requirement.status) }}</p>
    <p class="field-hint">AI 整理完成不代表需求已被采纳。可随时查看进度、追加补充信息。</p>
    <p v-if="hasReceipt" class="field-hint">修改权限已保留在当前页面。请保存修改入口，以免换设备或清除浏览器数据后丢失。</p>
    <div class="actions">
      <el-button type="primary" @click="$emit('open')">查看进度</el-button>
      <el-button v-if="hasReceipt" @click="$emit('save')">保存修改入口</el-button>
      <el-button v-if="requirement.visibility === 'public'" @click="$emit('continueAI')">继续让 AI 处理</el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ElButton } from 'element-plus'
import type { Requirement } from './api'
import { nextAction } from './feedbackExperience'
defineProps<{ requirement: Requirement; hasReceipt: boolean }>()
defineEmits<{ open: []; save: []; continueAI: [] }>()
</script>

<style scoped>
.submission-result { padding: 20px; margin-bottom: 20px; overflow-wrap: anywhere; }
.submission-result p { line-height: 1.65; }
.submission-result .actions { flex-wrap: wrap; gap: 8px; }
.submission-result .el-button { margin-left: 0; }
</style>
