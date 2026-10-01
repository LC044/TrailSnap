<template>
<SettingsSection v-model="activeNames" name="appearance" title="外观设置">
<div class="px-6 pb-6">
          <div class="space-y-6 max-w-3xl">

        <div>
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">显示模式</h3>
          <div class="flex bg-gray-100 dark:bg-gray-700 p-1 rounded-lg w-full sm:w-96">
            <button
              @click="setMode('light')"
              :class="['flex-1 flex items-center justify-center py-2 rounded-md text-sm font-medium transition-all', currentMode === 'light' ? 'bg-white dark:bg-gray-800 shadow-sm text-gray-800 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 dark:bg-gray-800 dark:text-white']"
            >
              <Sun class="w-4 h-4 mr-2" /> 浅色
            </button>
            <button
              @click="setMode('auto')"
              :class="['flex-1 flex items-center justify-center py-2 rounded-md text-sm font-medium transition-all', currentMode === 'auto' ? 'bg-white dark:bg-gray-800 shadow-sm text-gray-800 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 dark:bg-gray-800 dark:text-white']"
            >
              <Palette class="w-4 h-4 mr-2" /> 自动
            </button>
            <button
              @click="setMode('dark')"
              :class="['flex-1 flex items-center justify-center py-2 rounded-md text-sm font-medium transition-all', currentMode === 'dark' ? 'bg-gray-600 shadow-sm text-white' : 'text-gray-500 dark:text-gray-400 dark:bg-gray-800 dark:text-white']"
            >
              <Moon class="w-4 h-4 mr-2" /> 深色
            </button>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">主题颜色</h3>
          <div class="flex flex-wrap gap-4">
            <button
              v-for="color in themeColors"
              :key="color.name"
              @click="setTheme(color)"
              class="w-10 h-10 rounded-full border-2 transition-transform hover:scale-110 flex items-center justify-center relative"
              :style="{ backgroundColor: color.primary, borderColor: currentTheme.name === color.name ? 'var(--text-color)' : 'transparent' }"
              :title="color.label"
            >
              <Check v-if="currentTheme.name === color.name" class="w-5 h-5 text-white drop-shadow-md" />
            </button>
          </div>
        </div>

          </div>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
import { Sun, Moon, Palette, Check } from 'lucide-vue-next'
const { activeNames, currentMode, currentTheme, setMode, setTheme, themeColors } = useBasicSettingsContext()
</script>
