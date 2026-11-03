<template>
<SettingsSection v-model="activeNames" :name="serviceOnly ? 'ai-service' : 'ai'" :title="serviceOnly ? 'AI 识别服务连接' : '人物识别参数'">
<div class="px-4 pb-4 md:px-6 md:pb-6">
          <el-form label-position="top" class="max-w-3xl">
        <el-form-item v-if="serviceOnly && !managedAI" label="AI API 地址（人脸识别、OCR等AI微服务地址）">
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

        <p v-if="serviceOnly && managedAI" class="ts-muted text-sm">识别服务由桌面应用管理，无需填写地址。</p>
        <el-collapse v-if="!serviceOnly" v-model="aiActiveNames" class="my-4 border-none">


<!-- Face Recognition -->
          <el-collapse-item name="face">
            <template #title>
              <span class="text-sm font-medium text-gray-600 dark:text-gray-300">高级识别参数 · 通常无需修改</span>
            </template>
            <SettingsFormRow label="识别阈值" description="判定为人脸的最低置信度 (默认 0.7)"><el-slider v-model="aiForm.face_recognition_threshold" :min="0" :max="1" :step="0.05" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="聚类阈值" description="越小越严格，较少混入其他人，但同一个人可能分成多组。默认 0.4。"><el-slider v-model="aiForm.face_cluster_threshold" :min="0" :max="1" :step="0.05" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="重扫高置信度阈值" description="低于该距离时默认勾选新增（默认 0.35）"><el-slider v-model="aiForm.face_rescan_auto_match_threshold" :min="0.2" :max="aiForm.face_rescan_candidate_threshold" :step="0.01" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="重扫候选阈值" description="低于该距离时展示为潜在新增（默认 0.45）"><el-slider v-model="aiForm.face_rescan_candidate_threshold" :min="aiForm.face_rescan_auto_match_threshold" :max="aiForm.face_rescan_removal_threshold" :step="0.01" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="重扫移出阈值" description="高于该距离时展示为潜在移出（默认 0.52）"><el-slider v-model="aiForm.face_rescan_removal_threshold" :min="aiForm.face_rescan_candidate_threshold" :max="0.8" :step="0.01" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="最少照片数" description="形成人物聚类所需的最少照片数量 (默认 5)"><el-input-number v-model="aiForm.face_recognition_min_photos" :min="1" /></SettingsFormRow>
          </el-collapse-item>
        </el-collapse>

        <el-form-item v-if="!serviceOnly || !managedAI">
          <el-button type="primary" @click="serviceOnly ? saveAIServiceSettings() : saveAISettings()">{{ serviceOnly ? '保存服务地址' : '保存识别参数' }}</el-button>
        </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
import { CheckCircle2, Loader2, XCircle } from 'lucide-vue-next'
withDefaults(defineProps<{ serviceOnly?: boolean }>(), { serviceOnly: false })
const { managedAI, activeNames, aiActiveNames, aiForm, aiServiceTest, resetAIServiceTest, saveAISettings, saveAIServiceSettings, testAIServiceConnection } = useBasicSettingsContext()
</script>
