<template>
  <section>
    <div class="page-head">
      <div class="page-head-left"><div class="page-head-icon"><el-icon :size="26"><Collection /></el-icon></div><div><h1>{{ user ? '我的需求与本机记录' : '本机提交记录' }}</h1><p class="sub">查看提交结果、处理进度，继续补充信息</p></div></div>
    </div>
    <el-alert type="info" :closable="false" title="本机记录保存在此浏览器">
      清除浏览器数据或换设备后，本机记录和修改权限可能丢失。请进入需求详情保存修改入口；持有该链接的人可以修改对应需求，请勿公开分享。AI 提交后，打开它给你的私有管理链接即可添加记录。
    </el-alert>
    <div v-if="!user && !items.length" class="panel empty"><div>还没有本机提交的需求</div><div class="actions" style="justify-content:center"><el-button type="primary" @click="$emit('submit')">提交一个想法</el-button></div></div>
    <RequirementTable v-else :items="items" :manager="manager" :user="user" @open="$emit('open', $event)" @action="$emit('action', $event)" />
  </section>
</template>

<script setup lang="ts">
import { Collection } from '@element-plus/icons-vue'
import RequirementTable from '../../RequirementTable.vue'
import type { Requirement, User as ApiUser } from '../../api'
defineProps<{ items: Requirement[]; manager: boolean; user: ApiUser | null }>()
defineEmits<{ login: []; submit: []; open: [item: Requirement]; action: [payload: { item: Requirement; command: string }] }>()
</script>
