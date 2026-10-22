<script setup lang="ts">
import { computed, ref } from 'vue'
import { useData } from 'vitepress'
const { lang } = useData()
const english = computed(() => lang.value.startsWith('en'))
const active = ref<{ name: string; image: string } | null>(null)
const channels = [
  { name: '微信交流群', image: 'https://blog.siyuan.ink/static/img/46f6ef1506ec8bdc019a796c0aba368b.clipboard-2026-10-18.webp' },
  { name: 'QQ 交流群', image: 'https://blog.siyuan.ink/static/img/51b2cc72642406a33b42b572203a173c.qq_group.webp' },
]
const socialLinks = [
  { key: 'douyin', name: '抖音', icon: '/icons/douyin.svg', image: '/qrcodes/douyin_qr.png' },
  { key: 'wechat', name: '微信公众号 · 忆墨痕', icon: '/icons/wechat.svg', image: '/qrcodes/wechat_official_account_qr.webp' },
  { key: 'xiaohongshu', name: '小红书', icon: '/icons/xiaohongshu.svg', image: '/qrcodes/xiaohongshu_qr.jpg' },
  { key: 'bilibili', name: '哔哩哔哩', icon: '/icons/bilibili.svg', image: '/qrcodes/bilibili_qr.png' },
]
function open(channel: typeof channels[number], event: Event) {
  active.value = channel
  const dialog = (event.currentTarget as HTMLElement).closest('footer')!.querySelector('dialog')!
  dialog.showModal()
}
</script>

<template>
  <footer class="contact-footer">
    <div class="contact-grid">
      <div class="contact-brand"><a href="/" aria-label="行影集首页"><img src="/logo.svg" alt="" width="36" height="36"><strong>行影集 <small>TRAILSNAP</small></strong></a><p>{{ english ? 'A private home for your photos and memories.' : '整理照片，珍藏日常与远方。' }}</p><a href="mailto:sixyuan044@gmail.com">sixyuan044@gmail.com ↗</a></div>
      <div><h2>{{ english ? 'Explore' : '产品与支持' }}</h2><nav><a :href="english ? '/en/download' : '/download'">{{ english ? 'Download' : '下载行影集' }}</a><a :href="english ? '/en/docs/guide/install' : '/docs/guide/install'">{{ english ? 'Documentation' : '使用文档' }}</a><a :href="english ? '/en/docs/guide/changelog' : '/docs/guide/changelog'">{{ english ? 'Changelog' : '更新日志' }}</a><a href="https://feedback.trailsnap.cn/" target="_blank" rel="noopener">{{ english ? 'Feedback' : '建议与反馈' }} ↗</a></nav></div>
      <div><h2>{{ english ? 'Community & source' : '交流与共建' }}</h2><nav class="contact-channels"><button v-for="channel in channels" :key="channel.name" type="button" aria-haspopup="dialog" @click="open(channel, $event)">{{ channel.name }} <span aria-hidden="true">⌑</span></button><a href="https://github.com/LC044/TrailSnap" target="_blank" rel="noopener">GitHub ↗</a><a href="https://atomgit.com/LC044/TrailSnap" target="_blank" rel="noopener">AtomGit ↗</a><a href="https://github.com/LC044/TrailSnap/blob/master/LICENSE" target="_blank" rel="noopener">AGPL-3.0 ↗</a></nav></div>
      <div class="contact-follow"><h2>{{ english ? 'Follow us' : '关注我们' }}</h2><div class="social-links">
        <div v-for="link in socialLinks" :key="link.key" class="social-item" :data-social="link.key">
          <button class="social-trigger" type="button" :aria-label="link.name" :aria-describedby="`social-qr-${link.key}`" aria-haspopup="dialog" @click="open(link, $event)"><img :src="link.icon" alt="" width="42" height="42" loading="lazy"></button>
          <div :id="`social-qr-${link.key}`" class="social-qr" role="tooltip"><img :src="link.image" :alt="`${link.name}二维码`" loading="lazy"><span>{{ link.name }}</span></div>
        </div>
      </div></div>
    </div>
    <div class="contact-bottom"><span>© {{ new Date().getFullYear() }} TrailSnap 行影集</span><span>{{ english ? 'Your photos and memories, always yours.' : '照片与回忆，始终属于你。' }}</span></div>
    <dialog class="contact-dialog" aria-labelledby="contact-dialog-title" @click="($event.target === $event.currentTarget) && ($event.currentTarget as HTMLDialogElement).close()">
      <form method="dialog"><button class="contact-close" aria-label="关闭二维码">×</button></form>
      <template v-if="active"><h2 id="contact-dialog-title">{{ active.name }}</h2><img :src="active.image" :alt="`${active.name}二维码`"><p>使用对应应用扫码关注或加入</p></template>
    </dialog>
  </footer>
</template>

<style scoped>
.contact-footer{--contact-ink:var(--ink,var(--vp-c-text-1));--contact-muted:var(--muted,var(--vp-c-text-2));--contact-line:var(--line,var(--vp-c-divider));padding:64px max(24px,calc((100% - 1200px)/2)) 26px;border-top:1px solid var(--contact-line);background:var(--bg,var(--vp-c-bg));color:var(--contact-ink);font-family:var(--vp-font-family-base);font-size:13px;line-height:1.8}
.contact-grid{display:grid;grid-template-columns:1.25fr .9fr 1fr 1.15fr;gap:40px}.contact-footer a,.contact-footer button{color:inherit;text-decoration:none}.contact-brand>a:first-child{display:flex;align-items:center;gap:12px}.contact-brand strong{font-size:22px}.contact-brand small{display:block;font-size:9px;letter-spacing:2px;line-height:1}.contact-brand p{margin:18px 0 8px;color:var(--contact-muted)}.contact-footer h2{font:600 14px var(--vp-font-family-base);margin:0 0 20px;border:0;padding:0;letter-spacing:.04em}.contact-footer nav{display:grid;gap:10px;color:var(--contact-muted)}.contact-channels{grid-template-columns:1fr;column-gap:18px}.contact-footer button{font:inherit;text-align:left;padding:0;border:0;background:none;cursor:pointer}.contact-footer nav a:hover,.contact-footer nav button:hover{color:var(--contact-ink)}.contact-footer button:focus-visible,.contact-footer a:focus-visible{outline:2px solid currentColor;outline-offset:5px}.contact-channels span{opacity:.5}.contact-bottom{display:flex;justify-content:space-between;border-top:1px solid var(--contact-line);margin-top:48px;padding-top:20px;color:var(--contact-muted);font-size:11px}.contact-dialog{position:fixed;inset:0;margin:auto;padding:32px;border:1px solid var(--contact-line);border-radius:16px;background:var(--bg,var(--vp-c-bg));color:var(--contact-ink);width:min(360px,calc(100vw - 32px));max-height:90svh;overflow:auto;text-align:center}.contact-dialog::backdrop{background:#15251db3;backdrop-filter:blur(5px)}.contact-dialog h2{margin:8px 0 22px}.contact-dialog img{width:100%;height:auto;border-radius:8px;object-fit:contain}.contact-dialog p{font-size:12px;color:var(--contact-muted);margin:16px 0 0}.contact-dialog .contact-close{position:absolute;right:14px;top:8px;font-size:28px;padding:0 8px}.contact-dialog form{margin:0}
@media(max-width:900px){.contact-grid{grid-template-columns:1fr 1fr;gap:32px}.contact-channels{max-width:300px}}@media(max-width:520px){.contact-footer{padding-top:40px}.contact-grid{grid-template-columns:1fr 1fr;gap:28px 20px}.contact-brand{grid-column:1/-1}.contact-channels{grid-template-columns:1fr}.contact-bottom{gap:16px;flex-direction:column;margin-top:32px}}

.social-links{display:flex;align-items:center;gap:14px}
.social-item{position:relative;flex-shrink:0}
.contact-footer .social-trigger{display:flex;align-items:center;justify-content:center;width:42px;height:42px;border-radius:9px;transition:transform .18s ease}
.social-trigger img{width:42px;height:42px;object-fit:contain;padding:3px;opacity:.85}
.social-item:hover .social-trigger img,.social-item:focus-within .social-trigger img{opacity:1}
.social-qr{position:absolute;bottom:calc(100% + 12px);left:50%;width:220px;padding:10px;border:1px solid var(--contact-line);border-radius:10px;background:var(--bg,var(--vp-c-bg));box-shadow:0 12px 32px #0002;z-index:30;text-align:center;opacity:0;visibility:hidden;pointer-events:none;transform:translate(-50%,6px);transition:opacity .18s ease,transform .18s ease,visibility .18s}
.social-qr:after{content:'';position:absolute;top:100%;left:0;right:0;height:14px}
.social-qr img{width:100%;height:auto;object-fit:contain;border-radius:5px}
.social-qr span{display:block;margin-top:8px;font-size:12px;color:var(--contact-ink)}
.social-item:hover .social-qr,.social-item:focus-within .social-qr{opacity:1;visibility:visible;pointer-events:auto;transform:translate(-50%,0)}
@media(max-width:520px){.contact-follow{grid-column:1/-1}.social-links{gap:18px}}
@media(hover:none){.social-item:hover .social-qr,.social-item:focus-within .social-qr{display:none}}
@media(prefers-reduced-motion:reduce){.social-qr,.contact-footer .social-trigger{transition:none}}
</style>
