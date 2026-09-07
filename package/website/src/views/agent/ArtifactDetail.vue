<template>
  <main class="mx-auto min-h-full max-w-6xl px-4 py-6 sm:px-8">
    <div v-if="loading" class="flex justify-center py-20 text-gray-500 dark:text-gray-400"><LoaderCircle class="h-6 w-6 animate-spin" /></div>
    <template v-else-if="artifact">
      <button type="button" class="mb-5 inline-flex items-center gap-1 rounded-lg text-sm text-gray-600 hover:text-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-gray-300" @click="router.back()"><ArrowLeft class="h-4 w-4" />返回</button>
      <article class="rounded-2xl bg-white p-5 shadow-sm dark:bg-gray-800 sm:p-8">
        <header class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0 flex-1"><p class="text-sm text-primary-600">AI {{ artifactLabel }} · 草稿 v{{ artifact.version }}</p><input v-if="editing" v-model="draftTitle" class="mt-2 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-xl font-semibold text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /><h1 v-else class="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">{{ artifact.title }}</h1></div>
          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <button type="button" class="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700" @click="downloadHtml"><Download class="mr-1 inline h-4 w-4" />导出 HTML</button>
            <button type="button" class="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700" @click="exportLongImage"><ImageDown class="mr-1 inline h-4 w-4" />导出长图</button>
            <button type="button" class="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700" @click="printPdf"><Printer class="mr-1 inline h-4 w-4" />打印 / PDF</button>
            <button type="button" class="rounded-lg border border-primary-500 px-3 py-1.5 text-sm text-primary-600 hover:bg-primary-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="createShare"><Share2 class="mr-1 inline h-4 w-4" />{{ artifact.html_config?.share?.enabled ? '刷新分享链接' : '分享' }}</button>
            <button v-if="artifact.html_config?.share?.enabled" type="button" class="rounded-lg px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-red-400 dark:hover:bg-red-950/30" @click="revokeShare"><Link2Off class="mr-1 inline h-4 w-4" />撤销分享</button>
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
import { ArrowLeft, Download, ImageDown, LayoutTemplate, Link2Off, LoaderCircle, Printer, Share2, Sparkles } from 'lucide-vue-next';
import { ElMessage } from 'element-plus';
import { agentApi, type AIArtifact } from '@/api/agent';
import { toServerUrl } from '@/config/server';
import { useUiStore } from '@/stores/uiStore';
import HtmlArtifactPreview from './components/HtmlArtifactPreview.vue';
import { toPng } from 'html-to-image';

const route = useRoute(); const router = useRouter(); const uiStore = useUiStore();
const loading = ref(true); const editing = ref(false); const showDesigner = ref(false); const artifact = ref<AIArtifact | null>(null);
const draftTitle = ref(''); const draftContent = ref<Record<string, any>>({}); const activeView = ref<'structured' | 'html' | 'source'>('structured'); const htmlSource = ref('');
const selectedStyle = ref('editorial'); const customStyle = ref(''); const serverApiAccess = ref(false);
const styles = [{ value: 'editorial', label: '旅行杂志' }, { value: 'cinematic', label: '电影叙事' }, { value: 'scrapbook', label: '手账拼贴' }, { value: 'map-story', label: '地图足迹' }, { value: 'minimal', label: '极简画册' }, { value: 'custom', label: '完全自定义' }];
const artifactLabel = computed(() => ({ travel_story: '旅行日志', memory_story: '回忆故事', person_story: '人物故事', nine_grid: '九宫格', album_note: '相册札记' }[artifact.value?.artifact_type || ''] || '相册作品'));
const viewOptions = computed(() => [{ value: 'structured' as const, label: '结构化内容' }, { value: 'html' as const, label: '个性页面' }, ...(artifact.value?.html_content ? [{ value: 'source' as const, label: 'HTML 源码' }] : [])]);
const normalizeSections = (value: unknown) => Array.isArray(value) ? value.filter(item => item && typeof item === 'object').map((item: any, index) => ({
  ...item,
  heading: item.heading || item.title || item.location || `第 ${index + 1} 段`,
  body: item.body || item.narrative || item.story || item.description || '',
  photo_ids: Array.isArray(item.photo_ids) ? item.photo_ids : (item.photo_id ? [item.photo_id] : []),
})) : [];
const sections = computed(() => normalizeSections(editing.value ? draftContent.value.sections : artifact.value?.content_json?.sections));
const startEditing = () => { if (!artifact.value) return; draftTitle.value = artifact.value.title; draftContent.value = JSON.parse(JSON.stringify(artifact.value.content_json)); draftContent.value.sections = normalizeSections(draftContent.value.sections); editing.value = true; activeView.value = 'structured'; };
const saveStructured = async () => { if (!artifact.value || !draftTitle.value.trim()) return; try { const response: any = await agentApi.updateArtifact(artifact.value.id, { title: draftTitle.value.trim(), content_json: draftContent.value }); artifact.value = response.data; editing.value = false; ElMessage.success('草稿已保存'); } catch { ElMessage.error('保存失败'); } };
const saveHtmlSource = async () => { if (!artifact.value || !htmlSource.value.trim()) return; try { const response: any = await agentApi.updateArtifact(artifact.value.id, { html_content: htmlSource.value }); artifact.value = response.data; activeView.value = 'html'; ElMessage.success('HTML 已保存'); } catch { ElMessage.error('HTML 保存失败'); } };
const portableHtmlBlob = async () => {
  if (!artifact.value) throw new Error('作品不存在');
  const response: any = await agentApi.downloadArtifactHtml(artifact.value.id);
  return response.data instanceof Blob ? response.data : new Blob([response.data], { type: 'text/html;charset=utf-8' });
};
const downloadHtml = async () => { try { const blob = await portableHtmlBlob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `${artifact.value?.title || 'trailsnap-story'}.html`; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); ElMessage.success('已导出可离线查看的 HTML'); } catch { ElMessage.error('HTML 导出失败'); } };
const exportLongImage = async () => { let frame: HTMLIFrameElement | null = null; try { const blob = await portableHtmlBlob(); const source = await blob.text(); frame = document.createElement('iframe'); frame.setAttribute('sandbox', 'allow-same-origin'); frame.style.cssText = 'position:fixed;left:-100000px;top:0;width:1080px;height:1000px;border:0;background:#fff'; document.body.appendChild(frame); await new Promise<void>((resolve, reject) => { if (!frame) return reject(new Error('frame')); frame.onload = () => resolve(); frame.onerror = () => reject(new Error('load')); frame.srcdoc = source; }); const doc = frame.contentDocument; if (!doc) throw new Error('无法读取导出页面'); const images = Array.from(doc.images); await Promise.all(images.map(image => image.complete ? Promise.resolve() : new Promise<void>(resolve => { image.onload = image.onerror = () => resolve(); }))); const height = Math.max(doc.documentElement.scrollHeight, doc.body?.scrollHeight || 0); if (height > 30000) throw new Error('页面过长，请拆分作品后导出'); frame.style.height = `${Math.max(height, 600)}px`; const dataUrl = await toPng(doc.documentElement, { backgroundColor: '#ffffff', width: 1080, height: Math.max(height, 600), pixelRatio: 1, cacheBust: true }); const link = document.createElement('a'); link.href = dataUrl; link.download = `${artifact.value?.title || 'trailsnap-story'}.png`; link.click(); ElMessage.success('长图已导出'); } catch (error) { ElMessage.error(error instanceof Error ? error.message : '长图导出失败'); } finally { frame?.remove(); } };
const printPdf = async () => { const target = window.open('', '_blank'); if (!target) { ElMessage.info('请允许浏览器打开新窗口后重试'); return; } try { target.document.write('<p style="font-family:system-ui;padding:24px">正在准备可打印页面…</p>'); const blob = await portableHtmlBlob(); const url = URL.createObjectURL(blob); target.location.href = url; target.addEventListener('load', () => { target.focus(); target.print(); window.setTimeout(() => URL.revokeObjectURL(url), 60_000); }, { once: true }); } catch { target.close(); ElMessage.error('打印页面生成失败'); } };
const createShare = async () => { if (!artifact.value) return; try { const response: any = await agentApi.shareArtifact(artifact.value.id); const url = new URL(toServerUrl(response.data.share_path), window.location.origin).href; await navigator.clipboard.writeText(url); await loadArtifact(); ElMessage.success('新分享链接已复制；旧链接已自动失效'); } catch { ElMessage.error('创建或复制分享链接失败'); } };
const revokeShare = async () => { if (!artifact.value) return; try { await agentApi.revokeArtifactShare(artifact.value.id); await loadArtifact(); ElMessage.success('分享已撤销，原链接立即失效'); } catch { ElMessage.error('撤销分享失败'); } };
const openDesignerAgent = () => { if (!artifact.value) return; const style = customStyle.value.trim() || styles.find(item => item.value === selectedStyle.value)?.label || selectedStyle.value; uiStore.openAgentWithPrompt(`请为已有旅行日志作品 ${artifact.value.id} 生成或重新设计个性化 HTML 页面。先加载 travel-story skill，再读取作品上下文。风格：${style}。Server API 只读权限：${serverApiAccess.value ? '开启' : '关闭'}。请保留现有结构化 JSON，生成完整、响应式、与其他用户不同的 HTML/CSS/JS，并调用 save_artifact_html_page 保存到同一作品。`, true); showDesigner.value = false; };
const loadArtifact = async () => { const response: any = await agentApi.getArtifact(String(route.params.id)); artifact.value = response.data; htmlSource.value = artifact.value?.html_content || ''; selectedStyle.value = artifact.value?.html_config?.style_name || 'editorial'; customStyle.value = artifact.value?.html_config?.custom_style || ''; serverApiAccess.value = Boolean(artifact.value?.html_config?.server_api_access); };
const handleArtifactUpdated = async (event: Event) => { const updated = (event as CustomEvent).detail; if (!artifact.value || updated?.id !== artifact.value.id || !updated?.has_html) return; await loadArtifact(); activeView.value = 'html'; ElMessage.success('个性化页面已生成'); };
onMounted(async () => { window.addEventListener('trailsnap:artifact-updated', handleArtifactUpdated); try { await loadArtifact(); if (route.query.view === 'html') activeView.value = 'html'; } catch { ElMessage.error('旅行日志加载失败'); } finally { loading.value = false; } });
onBeforeUnmount(() => window.removeEventListener('trailsnap:artifact-updated', handleArtifactUpdated));
</script>
