<!-- src/App.vue -->
<template>
  <el-config-provider :locale="zhCn">
    <!-- 动态渲染当前路由对应的布局 -->
    <component :is="currentLayout" />
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
// 导入所有布局组件
import MainLayout from '@/layouts/MainLayout.vue';
import BlankLayout from '@/layouts/BlankLayout.vue';
import { provideTheme } from '@/composables/useTheme';
import { provideNavItems } from '@/composables/useNavItems';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
// 🚨 关键：确保调用了 provideTheme()
const {
  isDarkMode,
  currentTheme,
  themeStyle,
  themeColors,
  setMode,
  setTheme
} = provideTheme();
provideNavItems();

const route = useRoute();

// 布局映射：路由 meta.layout 对应实际布局组件
const layoutMap = {
  main: MainLayout,   // 主布局（默认）
  blank: BlankLayout  // 空白布局
};

// 计算当前要渲染的布局（默认使用主布局）
const currentLayout = computed(() => {
  // 从路由 meta 中获取布局类型，未指定则默认主布局
  const layoutType = route.meta.layout as 'main' | 'blank' || undefined;
  return layoutMap[layoutType] || MainLayout;
});

</script>

<!-- 全局样式可移到 src/styles/main.scss，这里清空 -->
<style></style>