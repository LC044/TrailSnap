<template>
<section v-if="direct" class="ts-surface settings-native-group overflow-hidden">
  <header class="px-4 py-4 md:px-6"><h2 class="ts-section-title">{{ title }}</h2><p v-if="hint" class="ts-muted mt-1 text-sm">{{ hint }}</p></header><div class="settings-native-fields"><slot /></div>
</section>
<el-collapse v-else v-model="activeNames" class="ts-surface ts-settings-section overflow-hidden">
  <el-collapse-item :name="name"><template #title><div class="px-4 py-3 md:px-6"><h2 class="ts-section-title">{{ title }}</h2><p v-if="hint" class="ts-muted mt-1 text-xs font-normal">{{ hint }}</p></div></template><slot /></el-collapse-item>
</el-collapse>
</template>
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ name: string; title: string }>()
const activeNames = defineModel<string[]>({ required: true })
const direct = computed(() => ['appearance', 'photo-viewing', 'scan_schedule', 'recycle_bin', 'task', 'security', 'moment_caption_schedule'].includes(props.name))
const hints: Record<string, string> = {
 appearance: '仅此设备 · 自动保存', 'photo-viewing': '仅此设备 · 自动保存',
 scan_schedule: '定期检查照片文件夹，频繁扫描可能唤醒硬盘。按服务器时区执行。',
 recycle_bin: '超过保留期限后自动永久删除，请预留足够的恢复时间。',
 image: '当前账号 · 控制生成文件的清晰度与体积，不改变原始照片',
 index: '高级维护 · 图库内容异常时使用', ai: '当前账号 · 人物分组与高级识别参数', 'ai-service': '当前账号 · 人脸、文字等识别服务连接',
 map: '当前账号 · 地点解析服务与离线数据',
}
const hint = computed(() => hints[props.name] || '')
</script>
