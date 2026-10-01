<template>
<SettingsSection v-model="activeNames" name="ai" title="AI 服务与人脸设置">
<div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
        <el-form-item label="AI API 地址（人脸识别、OCR等AI微服务地址）">
          <div class="w-full">
            <div class="flex flex-col gap-2 sm:flex-row">
              <el-input
                v-model="aiForm.ai_api_url"
                class="min-w-0 flex-1"
                placeholder="http://localhost:8001"
                aria-label="AI API 地址"
                @input="resetAIServiceTest"
              />
              <el-button :loading="aiServiceTest.status === 'testing'" @click="testAIServiceConnection">测试连通性</el-button>
            </div>
            <div v-if="aiServiceTest.status !== 'idle'" class="mt-2 flex items-center gap-1.5 text-xs">
              <Loader2 v-if="aiServiceTest.status === 'testing'" class="h-3.5 w-3.5 animate-spin text-primary-500" />
              <CheckCircle2 v-else-if="aiServiceTest.status === 'valid'" class="h-3.5 w-3.5 text-green-500" />
              <XCircle v-else class="h-3.5 w-3.5 text-red-500" />
              <span :class="aiServiceTest.status === 'valid' ? 'text-green-600 dark:text-green-400' : aiServiceTest.status === 'invalid' ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'">
                {{ aiServiceTest.message }}
              </span>
            </div>
            <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">检查由 TrailSnap Server 发起，可正确验证 Docker 或内网中的 AI 服务地址。</p>
          </div>
        </el-form-item>

        <el-collapse v-model="aiActiveNames" class="my-4 border-none">


<!-- Face Recognition -->
          <el-collapse-item name="face">
            <template #title>
              <span class="text-sm font-medium text-gray-600 dark:text-gray-300">人脸识别配置</span>
            </template>
            <el-form-item label="识别阈值">
              <div class="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 w-full">
                <el-slider v-model="aiForm.face_recognition_threshold" :min="0" :max="1" :step="0.05" class="w-full sm:w-64" show-input />
                <span class="text-sm text-gray-500 dark:text-gray-400">判定为人脸的最低置信度 (默认 0.7)</span>
              </div>
            </el-form-item>
            <el-form-item label="聚类阈值">
              <div class="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 w-full">
                <el-slider v-model="aiForm.face_cluster_threshold" :min="0" :max="1" :step="0.05" class="w-full sm:w-64" show-input />
                <span class="text-sm text-gray-500 dark:text-gray-400">判定为同一人的距离阈值 (默认 0.4，越小越严格)</span>
              </div>
            </el-form-item>
            <el-form-item label="重扫高置信度阈值">
              <div class="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 w-full">
                <el-slider v-model="aiForm.face_rescan_auto_match_threshold" :min="0.2" :max="aiForm.face_rescan_candidate_threshold" :step="0.01" class="w-full sm:w-64" show-input />
                <span class="text-sm text-gray-500 dark:text-gray-400">低于该距离时默认勾选新增（默认 0.35）</span>
              </div>
            </el-form-item>
            <el-form-item label="重扫候选阈值">
              <div class="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 w-full">
                <el-slider v-model="aiForm.face_rescan_candidate_threshold" :min="aiForm.face_rescan_auto_match_threshold" :max="aiForm.face_rescan_removal_threshold" :step="0.01" class="w-full sm:w-64" show-input />
                <span class="text-sm text-gray-500 dark:text-gray-400">低于该距离时展示为潜在新增（默认 0.45）</span>
              </div>
            </el-form-item>
            <el-form-item label="重扫移出阈值">
              <div class="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 w-full">
                <el-slider v-model="aiForm.face_rescan_removal_threshold" :min="aiForm.face_rescan_candidate_threshold" :max="0.8" :step="0.01" class="w-full sm:w-64" show-input />
                <span class="text-sm text-gray-500 dark:text-gray-400">高于该距离时展示为潜在移出（默认 0.52）</span>
              </div>
            </el-form-item>
            <el-form-item label="最少照片数">
              <el-input-number v-model="aiForm.face_recognition_min_photos" :min="1" />
              <span class="text-sm text-gray-500 dark:text-gray-400 ml-2">形成人物聚类所需的最少照片数量 (默认 5)</span>
            </el-form-item>
          </el-collapse-item>
        </el-collapse>

        <el-form-item>
          <el-button type="primary" @click="saveAISettings">保存 AI 配置</el-button>
        </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
import { CheckCircle2, Loader2, XCircle } from 'lucide-vue-next'
const { activeNames, aiActiveNames, aiForm, aiServiceTest, resetAIServiceTest, saveAISettings, testAIServiceConnection } = useBasicSettingsContext()
</script>
