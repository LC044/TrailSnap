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
        <SettingsFormRow v-if="!serviceOnly" label="识别档位" description="宽松更容易归为同一人，严格更倾向分开。保存后自动整理已有的未命名人物。">
          <el-select :model-value="recognitionPreset" aria-label="人脸识别档位" class="w-full max-w-sm" @change="applyRecognitionPreset">
            <el-option v-for="(preset, key) in faceRecognitionPresets" :key="key" :value="key" :label="preset.label" />
            <el-option value="custom" label="自定义" />
          </el-select>
        </SettingsFormRow>
        <el-collapse v-if="!serviceOnly" v-model="aiActiveNames" class="my-4 border-none">


<!-- Face Recognition -->
          <el-collapse-item name="face">
            <template #title>
              <span class="text-sm font-medium text-gray-600 dark:text-gray-300">高级识别参数 · 通常无需修改</span>
            </template>
            <SettingsFormRow label="识别阈值" description="判定为人脸的最低置信度 (默认 0.7)"><el-slider v-model="aiForm.face_recognition_threshold" :min="0" :max="1" :step="0.05" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="聚类阈值" description="单张脸加入外观簇的距离上限，越小越严格。普通档为 0.5。"><el-slider v-model="aiForm.face_cluster_threshold" :min="0" :max="1" :step="0.05" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="物理合簇距离" description="外观簇合成一个簇的严格距离上限，普通档为 0.25。"><el-input-number v-model="aiForm.face_cluster_merge_threshold" :min="0" :max="1" :step="0.01" :precision="4" /></SettingsFormRow>
            <SettingsFormRow label="人物归属距离" description="新外观簇归入已有的人物时，中心和代表人脸的距离上限。普通档为 0.425。"><el-input-number v-model="aiForm.face_identity_match_threshold" :min="0" :max="1" :step="0.01" :precision="4" /></SettingsFormRow>
            <SettingsFormRow label="未命名人物合并距离" description="两个未命名人物的簇中心距离上限，还需代表人脸双向核验。普通档为 0.2。"><el-input-number v-model="aiForm.face_identity_merge_threshold" :min="0" :max="1" :step="0.01" :precision="4" /></SettingsFormRow>
            <SettingsFormRow label="重扫高置信度阈值" description="低于该距离时默认勾选新增（默认 0.35）"><el-slider v-model="aiForm.face_rescan_auto_match_threshold" :min="0.2" :max="aiForm.face_rescan_candidate_threshold" :step="0.01" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="重扫候选阈值" description="低于该距离时展示为潜在新增（默认 0.45）"><el-slider v-model="aiForm.face_rescan_candidate_threshold" :min="aiForm.face_rescan_auto_match_threshold" :max="aiForm.face_rescan_removal_threshold" :step="0.01" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="重扫移出阈值" description="高于该距离时展示为潜在移出（默认 0.52）"><el-slider v-model="aiForm.face_rescan_removal_threshold" :min="aiForm.face_rescan_candidate_threshold" :max="0.8" :step="0.01" class="!w-full max-w-sm" show-input /></SettingsFormRow>
            <SettingsFormRow label="最少照片数" description="形成人物聚类所需的最少照片数量 (默认 5)"><el-input-number v-model="aiForm.face_recognition_min_photos" :min="1" /></SettingsFormRow>
          </el-collapse-item>
        </el-collapse>

        <SettingsFormRow v-if="!serviceOnly" label="重新整理人物" description="按已保存的识别参数重新聚类，清除人物名称、封面和合并结果。照片和人脸特征将用于重新整理">
          <div class="flex flex-col items-start gap-2">
            <el-button type="danger" plain :loading="clustering.submitting" :disabled="clustering.status?.phase === 'resetting'" @click="resetPeople">
              {{ clustering.status?.phase === 'failed' ? '重试人物整理' : '重置人物聚类' }}
            </el-button>
            <span v-if="clustering.status?.phase === 'resetting'" role="status" class="ts-muted text-sm">正在重新整理</span>
            <span v-if="clustering.status?.phase === 'failed'" role="alert" class="ts-muted text-sm">整理中断，请重试。</span>
          </div>
        </SettingsFormRow>
        <div v-if="!serviceOnly || !managedAI" class="mt-2 flex flex-wrap items-center justify-end gap-3 border-t ts-divider pt-3">
          <el-button type="primary" @click="serviceOnly ? saveAIServiceSettings() : saveAISettings()">{{ serviceOnly ? '保存服务地址' : '保存识别参数' }}</el-button>
        </div>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useFaceClusteringStore } from '@/stores/faceClustering'
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
import { detectFaceRecognitionPreset, faceRecognitionPresets, type FaceRecognitionPreset } from '@/composables/settings/faceRecognitionPresets'
import { CheckCircle2, Loader2, XCircle } from 'lucide-vue-next'
const props = withDefaults(defineProps<{ serviceOnly?: boolean }>(), { serviceOnly: false })
const { managedAI, activeNames, aiActiveNames, aiForm, aiServiceTest, resetAIServiceTest, saveAISettings, saveAIServiceSettings, testAIServiceConnection } = useBasicSettingsContext()
const clustering = useFaceClusteringStore()
const editingCustom = ref(false)
const recognitionPreset = computed(() => editingCustom.value ? 'custom' : detectFaceRecognitionPreset(aiForm.value))
function applyRecognitionPreset(value: FaceRecognitionPreset | 'custom') {
  if (value === 'custom') {
    editingCustom.value = true
    aiActiveNames.value = ['face']
    return
  }
  editingCustom.value = false
  Object.assign(aiForm.value, faceRecognitionPresets[value].parameters)
}
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
async function refreshClustering() {
  try {
    await clustering.refresh()
  } catch {
    return
  }
  if (!disposed && clustering.status?.phase === 'resetting') timer = setTimeout(refreshClustering, 3000)
}
async function resetPeople() {
  if (clustering.status?.phase === 'failed') {
    await clustering.retry()
    await refreshClustering()
    return
  }
  try {
    await ElMessageBox.confirm('将清除人物名称、封面、合并和照片归属，并使用已有特征重新聚类。使用旧人物的相册条件需重新选择。此操作无法撤销。请先保存需要使用的识别参数。', '重置人物聚类', {
      confirmButtonText: '清空并重新聚类', cancelButtonText: '取消', type: 'warning'
    })
  } catch {
    return
  }
  await clustering.reset()
  ElMessage.success('已开始重新整理人物')
  if (timer) clearTimeout(timer)
  await refreshClustering()
}
onMounted(() => { if (!props.serviceOnly) void refreshClustering() })
onBeforeUnmount(() => { disposed = true; if (timer) clearTimeout(timer) })
</script>
