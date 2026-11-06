<template>
<div class="ts-settings-page settings-content">
<SettingsPageHeader v-if="!embedded" :title="info[0]" :description="info[1]" />
<p v-if="['tasks','members','captions'].includes(category)" class="ts-muted text-xs">管理员设置 · 对所有成员生效</p>
<template v-if="category === 'preferences'"><AppearanceSettingsSection /><PhotoViewingSettingsSection /></template>
<template v-if="category === 'gallery'">
  <div v-if="admin" class="flex flex-col gap-4">
    <ScanScheduleSection /><RecycleBinSettingsSection />
  </div>
  <ImageSettingsSection />
</template>
<MapSettingsSection v-if="category === 'map'" />
<AIServiceSettingsSection v-if="category === 'recognition' || category === 'service'" :service-only="category === 'service'" />
<MomentCaptionScheduleSection v-if="category === 'captions' && admin" />
<TaskSettingsSection v-if="category === 'tasks' && admin"><slot name="task-options" /></TaskSettingsSection>
<section v-else-if="category === 'tasks'" class="ts-surface ts-settings-panel">
  <h2 class="ts-section-title">后台处理性能</h2>
  <slot name="task-options" />
</section>
<SecuritySettingsSection v-if="category === 'members' && admin" />
<template v-if="category === 'maintenance'">
<IndexMaintenanceSection v-if="admin" />
<section class="ts-surface p-5 space-y-3"><h2 class="ts-section-title">个人配置迁移</h2><p class="ts-muted text-sm">包含当前账号的图库、地图、识别与图片配置，可能包含密钥，请妥善保管。不包含照片或服务器全局设置。</p>
<div class="flex flex-wrap gap-3"><el-upload :auto-upload="false" :show-file-list="false" accept=".json" @change="handleImportFile"><el-button>导入个人配置</el-button></el-upload><el-button @click="handleExport">导出个人配置</el-button></div></section>
<RouterLink class="ts-surface ts-settings-panel flex items-center gap-4 ts-focus-ring" to="/settings#performance">
  <div class="min-w-0 flex-1"><h2 class="ts-section-title">性能测试</h2><p class="ts-muted mt-1 text-sm">打开性能测试，检查照片浏览与加载表现。</p></div>
  <ChevronRight class="h-5 w-5 shrink-0 ts-muted" />
</RouterLink>
</template>
</div>
</template>
<script setup lang="ts">
import SettingsPageHeader from '@/components/ui/SettingsPageHeader.vue'
import { provideBasicSettings } from '@/composables/settings/useBasicSettings'
import SecuritySettingsSection from './sections/SecuritySettingsSection.vue'
import TaskSettingsSection from './sections/TaskSettingsSection.vue'
import MapSettingsSection from './sections/MapSettingsSection.vue'
import AIServiceSettingsSection from './sections/AIServiceSettingsSection.vue'
import ImageSettingsSection from './sections/ImageSettingsSection.vue'
import PhotoViewingSettingsSection from './sections/PhotoViewingSettingsSection.vue'
import ScanScheduleSection from './sections/ScanScheduleSection.vue'
import MomentCaptionScheduleSection from './sections/MomentCaptionScheduleSection.vue'
import RecycleBinSettingsSection from './sections/RecycleBinSettingsSection.vue'
import IndexMaintenanceSection from './sections/IndexMaintenanceSection.vue'
import AppearanceSettingsSection from './sections/AppearanceSettingsSection.vue'
import { computed } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
const props = withDefaults(defineProps<{ category?: string; embedded?: boolean }>(), { category: 'preferences', embedded: false })
const admin = computed(() => !!useUserStore().userInfo?.is_superuser)
const pages: Record<string, string[]> = {
preferences: ['外观与浏览', '主题颜色、明暗模式与原图加载 · 仅此设备，自动保存'],
gallery: ['图库选项', '自动更新、删除恢复与图片生成质量'],
map: ['地图与地点', '地点解析服务与离线城市数据 · 当前账号'],
recognition: ['人物识别', '调整人物分组效果 · 当前账号'],
service: ['AI 识别服务', '人脸、文字等识别服务连接'],
captions: ['文案生成', '自动补全行影集内的朋友圈文案'],
maintenance: ['高级维护', '索引修复、性能诊断与配置迁移'], tasks: ['', ''], members: ['', ''] }
const info = computed(() => pages[props.category] || pages.preferences)
const { handleExport, handleImportFile, activeNames } = provideBasicSettings()
activeNames.value = ['appearance', 'photo-viewing', 'scan_schedule', 'recycle_bin', 'task', 'security', 'moment_caption_schedule', 'map', 'ai', 'ai-service']
</script>

<style scoped>
.settings-content { container: settings-content / inline-size; }
</style>
