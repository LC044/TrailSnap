<template>
<SettingsSection v-model="activeNames" name="index" title="索引维护">
<div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
        <el-form-item label="重建索引">
          <el-button type="danger" @click="rebuildIndex" :disabled="indexStatus.running">立即重建索引</el-button>
          <div class="mt-4 w-full" v-if="indexStatus.running || indexStatus.progress > 0">
            <div class="flex justify-between text-sm mb-1">
              <span>进度: {{ Math.round(indexStatus.progress*100) }}%</span>
              <span v-if="indexStatus.running" class="text-blue-600 animate-pulse">正在扫描... {{ indexStatus.message }}</span>
            </div>
            <div v-if="indexStatus.current_task" class="text-xs text-gray-500 dark:text-gray-400 mb-1">当前任务: {{ indexStatus.current_task }}</div>
            <el-progress :percentage="Math.round(indexStatus.progress*100)" :status="indexStatus.running ? undefined : 'success'" :stroke-width="15" />
            <div class="grid grid-cols-3 gap-4 mt-2 text-sm text-center bg-gray-50 p-2 rounded">
              <div class="text-green-600">新增: {{ indexStatus.added }}</div>
              <div class="text-red-600">删除: {{ indexStatus.deleted }}</div>
              <div class="text-orange-600">错误: {{ indexStatus.errors }}</div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="索引日志">
           <div class="w-full bg-gray-900 text-gray-100 dark:text-gray-300 p-4 rounded h-64 overflow-y-auto font-mono text-xs">
              <div v-for="(log, i) in logs" :key="i" class="mb-1">
                 <span class="text-gray-500 dark:text-gray-400">[{{ new Date(log.created_at).toLocaleTimeString() }}]</span>
                 <span :class="{'text-green-400': log.action==='added', 'text-red-400': log.action==='deleted'}"> {{ log.action.toUpperCase() }} </span>
                 <span class="text-gray-300 dark:text-gray-600">{{ log.file_path }}</span>
              </div>
              <div v-if="logs.length===0" class="text-gray-600 dark:text-gray-300 italic">暂无日志</div>
           </div>
        </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, indexStatus, logs, rebuildIndex } = useBasicSettingsContext()
</script>
