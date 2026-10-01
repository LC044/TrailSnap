<template>
<SettingsSection v-model="activeNames" name="security" title="安全设置">
<div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="允许新用户注册">
              <div class="flex items-center gap-3">
                <el-switch v-model="securityForm.allow_registration" />
                <span class="text-sm text-gray-500 dark:text-gray-400">{{ securityForm.allow_registration ? '任何人可以自行注册账号' : '关闭后仅管理员可在「用户管理」中添加账号' }}</span>
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveSecuritySettings">保存安全配置</el-button>
            </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, saveSecuritySettings, securityForm } = useBasicSettingsContext()
</script>
