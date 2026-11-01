<template>
  <div class="ts-settings-page">
    <!-- Header with Actions -->
    <SettingsPageHeader title="系统设置" description="管理安全、地图、照片浏览与后台处理选项">
      <template #actions>
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".json"
          @change="handleImportFile"
        >
          <el-button>导入配置</el-button>
        </el-upload>
        <el-button @click="handleExport">导出配置</el-button>
      </template>
    </SettingsPageHeader>
    <!-- Map Settings -->
    <SecuritySettingsSection />

    <!-- Task Settings -->
    <TaskSettingsSection />

    <!-- Map Settings (original) -->
    <MapSettingsSection />

    <!-- AI Settings -->
    <AIServiceSettingsSection />

    <!-- Image Settings -->
    <ImageSettingsSection />

    <PhotoViewingSettingsSection />

    <!-- Scheduled Scan Settings -->
    <ScanScheduleSection />

    <!-- Moment Caption Schedule -->
    <MomentCaptionScheduleSection />

    <!-- Recycle Bin Settings -->
    <RecycleBinSettingsSection />

    <!-- Index Maintenance -->
    <IndexMaintenanceSection />

    <!-- Appearance Settings -->
    <AppearanceSettingsSection />
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
const { handleExport, handleImportFile } = provideBasicSettings()
</script>
