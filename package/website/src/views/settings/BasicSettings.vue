<template>
  <div>
    <!-- Header with Actions -->
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">系统设置</h1>
      <div class="flex gap-2">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".json"
          @change="handleImportFile"
        >
          <el-button>导入配置</el-button>
        </el-upload>
        <el-button @click="handleExport">导出配置</el-button>
      </div>
    </div>
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
import { provideBasicSettings } from '@/composables/settings/useBasicSettings'
import SecuritySettingsSection from './sections/SecuritySettingsSection.vue'
import TaskSettingsSection from './sections/TaskSettingsSection.vue'
import MapSettingsSection from './sections/MapSettingsSection.vue'
import AIServiceSettingsSection from './sections/AIServiceSettingsSection.vue'
import ImageSettingsSection from './sections/ImageSettingsSection.vue'
import ScanScheduleSection from './sections/ScanScheduleSection.vue'
import MomentCaptionScheduleSection from './sections/MomentCaptionScheduleSection.vue'
import RecycleBinSettingsSection from './sections/RecycleBinSettingsSection.vue'
import IndexMaintenanceSection from './sections/IndexMaintenanceSection.vue'
import AppearanceSettingsSection from './sections/AppearanceSettingsSection.vue'
const { handleExport, handleImportFile } = provideBasicSettings()
</script>
