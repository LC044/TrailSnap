<template>
  <iframe ref="frameRef" class="h-[72vh] min-h-[520px] w-full rounded-xl border border-gray-200 bg-white dark:border-gray-700" :srcdoc="runtimeHtml" sandbox="allow-scripts" referrerpolicy="no-referrer" :title="`${artifact.title} 个性化页面`" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import request from '@/utils/request';
import { getServerUrl } from '@/config/server';
import type { AIArtifact } from '@/api/agent';

const props = defineProps<{ artifact: AIArtifact }>();
const frameRef = ref<HTMLIFrameElement | null>(null);
const deniedApiPrefixes = ['/api/auth', '/api/login', '/api/register', '/api/settings', '/api/users', '/api/tokens', '/api/system', '/api/agent/chat'];
const bridgeScript = `<script>(()=>{let n=0;const p=new Map();window.TrailSnap=Object.freeze({request(path){return new Promise((resolve,reject)=>{const id='ts-'+(++n)+'-'+Date.now();p.set(id,{resolve,reject});parent.postMessage({type:'trailsnap:request',id,path},'*')})}});addEventListener('message',event=>{const d=event.data||{};if(d.type!=='trailsnap:response'||!p.has(d.id))return;const task=p.get(d.id);p.delete(d.id);d.ok?task.resolve(d.data):task.reject(new Error(d.error||'请求失败'))})})();<\/script>`;

const runtimeHtml = computed(() => {
  const html = props.artifact.html_content || '<!doctype html><html><body></body></html>';
  const origin = getServerUrl() || window.location.origin;
  const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${origin} data: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:; media-src ${origin} data: blob:; connect-src 'none';">`;
  const injection = `${policy}<base href="${origin.replace(/\/$/, '')}/">${bridgeScript}`;
  if (/<head(?:\s[^>]*)?>/i.test(html)) return html.replace(/<head(?:\s[^>]*)?>/i, match => `${match}${injection}`);
  if (/<html(?:\s[^>]*)?>/i.test(html)) return html.replace(/<html(?:\s[^>]*)?>/i, match => `${match}<head>${injection}</head>`);
  return `<!doctype html><html><head>${injection}</head><body>${html}</body></html>`;
});

const isAllowedPath = (path: unknown): path is string => {
  if (!props.artifact.html_config?.server_api_access || typeof path !== 'string') return false;
  if (path.length > 2000 || !path.startsWith('/api/') || path.includes('..') || path.includes('://')) return false;
  return !deniedApiPrefixes.some(prefix => path === prefix || path.startsWith(`${prefix}/`) || path.startsWith(`${prefix}?`));
};

const handleMessage = async (event: MessageEvent) => {
  if (event.source !== frameRef.value?.contentWindow || event.data?.type !== 'trailsnap:request') return;
  const { id, path } = event.data;
  if (!isAllowedPath(path)) {
    frameRef.value?.contentWindow?.postMessage({ type: 'trailsnap:response', id, ok: false, error: '该作品未授权访问此 Server API' }, '*');
    return;
  }
  try {
    const response: any = await request.get(path);
    frameRef.value?.contentWindow?.postMessage({ type: 'trailsnap:response', id, ok: true, data: response?.data ?? response }, '*');
  } catch (error) {
    frameRef.value?.contentWindow?.postMessage({ type: 'trailsnap:response', id, ok: false, error: error instanceof Error ? error.message : '请求失败' }, '*');
  }
};

onMounted(() => window.addEventListener('message', handleMessage));
onBeforeUnmount(() => window.removeEventListener('message', handleMessage));
</script>
