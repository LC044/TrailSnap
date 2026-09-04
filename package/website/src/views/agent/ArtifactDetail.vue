<template>
  <main class="mx-auto min-h-full max-w-6xl px-4 py-6 sm:px-8">
    <div v-if="loading" class="flex justify-center py-20 text-gray-500 dark:text-gray-400"><LoaderCircle class="h-6 w-6 animate-spin" /></div>
    <template v-else-if="artifact">
      <button type="button" class="mb-5 inline-flex items-center gap-1 rounded-lg text-sm text-gray-600 hover:text-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-gray-300" @click="router.back()"><ArrowLeft class="h-4 w-4" />返回</button>
      <article class="rounded-2xl bg-white p-5 shadow-sm dark:bg-gray-800 sm:p-8">
        <header class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0 flex-1"><p class="text-sm text-primary-600">AI 旅行日志 · 草稿 v{{ artifact.version }}</p><input v-if="editing" v-model="draftTitle" class="mt-2 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-xl font-semibold text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /><h1 v-else class="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">{{ artifact.title }}</h1></div>
          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <button type="button" class="rounded-lg border border-primary-500 px-3 py-1.5 text-sm text-primary-600 hover:bg-primary-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="showDesigner = !showDesigner"><Sparkles class="mr-1 inline h-4 w-4" />{{ artifact.html_content ? '重新设计' : '生成个性页面' }}</button>
            <button type="button" class="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700" @click="editing ? saveStructured() : startEditing()">{{ editing ? '保存' : '编辑内容' }}</button>
            <button v-if="editing" type="button" class="rounded-lg px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-gray-400 dark:hover:bg-gray-700" @click="editing = false">取消</button>
          </div>
        </header>

        <section v-if="showDesigner" class="mb-6 rounded-xl border border-primary-500/30 bg-gray-50 p-4 dark:bg-gray-900">
          <h2 class="font-medium text-gray-900 dark:text-white">让 Agent 设计这篇旅行日志</h2>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <label class="text-sm text-gray-600 dark:text-gray-300">风格<select v-model="selectedStyle" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"><option v-for="style in styles" :key="style.value" :value="style.value">{{ style.label }}</option></select></label>
            <label class="text-sm text-gray-600 dark:text-gray-300">自定义风格<input v-model="customStyle" placeholder="例如：夏日公路电影，大留白、胶片颗粒" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white" /></label>
          </div>
          <label class="mt-3 flex items-start gap-3 rounded-lg bg-white p-3 text-sm text-gray-600 dark:bg-gray-800 dark:text-gray-300"><input v-model="serverApiAccess" type="checkbox" class="mt-0.5 h-4 w-4 accent-[var(--theme-primary)] focus-visible:ring-2 focus-visible:ring-primary-500" /><span><strong class="block text-gray-900 dark:text-white">允许页面只读访问 Server API</strong>可动态展示搜索、统计、相册等数据。页面无法获得登录令牌，敏感和写入接口仍被禁止。</span></label>
          <button type="button" class="mt-4 rounded-lg bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="openDesignerAgent">在 Agent 中生成</button>
        </section>

        <nav class="mb-6 flex gap-1 overflow-x-auto rounded-xl bg-gray-100 p-1 dark:bg-gray-900" aria-label="作品视图"><button v-for="item in viewOptions" :key="item.value" type="button" class="whitespace-nowrap rounded-lg px-4 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :class="activeView === item.value ? 'bg-white text-primary-600 shadow-sm dark:bg-gray-700' : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'" @click="activeView = item.value">{{ item.label }}</button></nav>

        <HtmlArtifactPreview v-if="activeView === 'html' && artifact.html_content" :artifact="artifact" />
        <div v-else-if="activeView === 'html'" class="rounded-xl border border-dashed border-gray-300 py-20 text-center dark:border-gray-600"><LayoutTemplate class="mx-auto h-9 w-9 text-gray-400" /><p class="mt-3 text-gray-600 dark:text-gray-300">还没有个性化 HTML 页面</p></div>
        <section v-else-if="activeView === 'source'">
          <textarea v-model="htmlSource" rows="28" spellcheck="false" class="w-full rounded-xl border border-gray-300 bg-gray-950 p-4 font-mono text-sm leading-6 text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600" />
          <div class="mt-3 flex items-center justify-between gap-3"><p class="text-xs text-gray-500 dark:text-gray-400">HTML 会在沙箱中运行，保存后可切换到个性页面预览。</p><button type="button" class="shrink-0 rounded-lg bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="saveHtmlSource">保存 HTML</button></div>
        </section>
        <section v-else>
          <textarea v-if="editing" v-model="draftContent.summary" rows="4" class="mb-8 w-full rounded-lg border border-gray-300 bg-white p-3 leading-7 text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200" /><p v-else-if="artifact.content_json.summary" class="mb-8 text-base leading-7 text-gray-600 dark:text-gray-300">{{ artifact.content_json.summary }}</p>
          <section v-for="(section, index) in sections" :key="index" class="mb-9"><input v-if="editing" v-model="section.heading" class="mb-3 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-lg font-medium text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /><h2 v-else class="mb-3 text-xl font-medium text-gray-900 dark:text-white">{{ section.heading || `第 ${index + 1} 段` }}</h2><textarea v-if="editing" v-model="section.body" rows="6" class="w-full rounded-lg border border-gray-300 bg-white p-3 leading-7 text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200" /><p v-else class="whitespace-pre-wrap leading-7 text-gray-700 dark:text-gray-200">{{ section.body }}</p><div v-if="section.photo_ids?.length" class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3"><img v-for="photoId in section.photo_ids" :key="photoId" :src="toServerUrl(`/api/medias/${photoId}/thumbnail?size=medium`)" class="aspect-square w-full rounded-lg object-cover" loading="lazy" alt="旅行照片" /></div></section>
        </section>
      </article>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, LayoutTemplate, LoaderCircle, Sparkles } from 'lucide-vue-next';
import { ElMessage } from 'element-plus';
import { agentApi, type AIArtifact } from '@/api/agent';
import { toServerUrl } from '@/config/server';
import { useUiStore } from '@/stores/uiStore';
import HtmlArtifactPreview from './components/HtmlArtifactPreview.vue';

const route = useRoute(); const router = useRouter(); const uiStore = useUiStore();
const loading = ref(true); const editing = ref(false); const showDesigner = ref(false); const artifact = ref<AIArtifact | null>(null);
const draftTitle = ref(''); const draftContent = ref<Record<string, any>>({}); const activeView = ref<'structured' | 'html' | 'source'>('structured'); const htmlSource = ref('');
const selectedStyle = ref('editorial'); const customStyle = ref(''); const serverApiAccess = ref(false);
const styles = [{ value: 'editorial', label: '旅行杂志' }, { value: 'cinematic', label: '电影叙事' }, { value: 'scrapbook', label: '手账拼贴' }, { value: 'map-story', label: '地图足迹' }, { value: 'minimal', label: '极简画册' }, { value: 'custom', label: '完全自定义' }];
const viewOptions = computed(() => [{ value: 'structured' as const, label: '结构化内容' }, { value: 'html' as const, label: '个性页面' }, ...(artifact.value?.html_content ? [{ value: 'source' as const, label: 'HTML 源码' }] : [])]);
const sections = computed(() => editing.value ? (draftContent.value.sections || []) : (Array.isArray(artifact.value?.content_json?.sections) ? artifact.value!.content_json.sections : []));
const startEditing = () => { if (!artifact.value) return; draftTitle.value = artifact.value.title; draftContent.value = JSON.parse(JSON.stringify(artifact.value.content_json)); editing.value = true; activeView.value = 'structured'; };
const saveStructured = async () => { if (!artifact.value || !draftTitle.value.trim()) return; try { const response: any = await agentApi.updateArtifact(artifact.value.id, { title: draftTitle.value.trim(), content_json: draftContent.value }); artifact.value = response.data; editing.value = false; ElMessage.success('草稿已保存'); } catch { ElMessage.error('保存失败'); } };
const saveHtmlSource = async () => { if (!artifact.value || !htmlSource.value.trim()) return; try { const response: any = await agentApi.updateArtifact(artifact.value.id, { html_content: htmlSource.value }); artifact.value = response.data; activeView.value = 'html'; ElMessage.success('HTML 已保存'); } catch { ElMessage.error('HTML 保存失败'); } };
const openDesignerAgent = () => { if (!artifact.value) return; const style = customStyle.value.trim() || styles.find(item => item.value === selectedStyle.value)?.label || selectedStyle.value; uiStore.openAgentWithPrompt(`请为已有旅行日志作品 ${artifact.value.id} 生成或重新设计个性化 HTML 页面。先加载 travel-story skill，再读取作品上下文。风格：${style}。Server API 只读权限：${serverApiAccess.value ? '开启' : '关闭'}。请保留现有结构化 JSON，生成完整、响应式、与其他用户不同的 HTML/CSS/JS，并调用 save_artifact_html_page 保存到同一作品。`, true); showDesigner.value = false; };
const loadArtifact = async () => { const response: any = await agentApi.getArtifact(String(route.params.id)); artifact.value = response.data; htmlSource.value = artifact.value?.html_content || ''; selectedStyle.value = artifact.value?.html_config?.style_name || 'editorial'; customStyle.value = artifact.value?.html_config?.custom_style || ''; serverApiAccess.value = Boolean(artifact.value?.html_config?.server_api_access); };
const handleArtifactUpdated = async (event: Event) => { const updated = (event as CustomEvent).detail; if (!artifact.value || updated?.id !== artifact.value.id || !updated?.has_html) return; await loadArtifact(); activeView.value = 'html'; ElMessage.success('个性化页面已生成'); };
onMounted(async () => { window.addEventListener('trailsnap:artifact-updated', handleArtifactUpdated); try { await loadArtifact(); if (route.query.view === 'html') activeView.value = 'html'; } catch { ElMessage.error('旅行日志加载失败'); } finally { loading.value = false; } });
onBeforeUnmount(() => window.removeEventListener('trailsnap:artifact-updated', handleArtifactUpdated));
</script>
