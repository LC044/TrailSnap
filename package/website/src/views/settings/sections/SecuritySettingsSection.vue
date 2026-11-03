<template>
  <SettingsSection v-model="activeNames" name="security" title="开放注册">
    <div class="px-4 pb-4 md:px-6">
      <SettingsFormRow inline label="允许新用户注册" control-id="allow-registration" :description="securityForm.allow_registration ? '任何人可以自行注册账号。' : '关闭后仅管理员可在「成员与注册」中添加账号。'">
        <el-switch id="allow-registration" v-model="securityForm.allow_registration" aria-label="允许新用户注册" />
      </SettingsFormRow>
      <div class="flex justify-end border-t ts-divider mt-2 pt-3"><el-button type="primary" @click="saveSecuritySettings">保存注册设置</el-button></div>
    </div>
  </SettingsSection>
</template>
<script setup lang="ts">
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, saveSecuritySettings, securityForm } = useBasicSettingsContext()
</script>
