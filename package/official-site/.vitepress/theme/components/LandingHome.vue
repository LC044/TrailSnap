<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useData } from 'vitepress'
import ContactFooter from './ContactFooter.vue'
import FootprintPuzzle from './FootprintPuzzle.vue'
import DemoEmbed from './DemoEmbed.vue'
import { initHome } from '../landing/home-motion.js'
import { initFixedSamples } from '../landing/fixed-samples.js'
import '../landing/home.css'

const { isDark } = useData()
const root = ref<HTMLElement>()
const menuOpen = ref(false)
const mapView = ref<'3d' | 'city' | 'puzzle'>('3d')
const memoryPage = ref(0)
const mapCaptions = {
  '3d': '拖动地球、缩放视角，直接探索足迹',
  city: '在照片里，点亮去过的城市',
  puzzle: '用照片拼图，重新组织你的旅行记忆',
}
const memories = [
  {
    tab: '人生章节',
    title: '把旅行照片，<br>装订成自己的行影集',
    desc: '一天一页，照片与文字留在一起。翻阅人生章节里的每一页，把散落的生活重新组织成一个日记本。',
    label: '人生章节',
  },
  {
    tab: '月迹 · 阴晴圆缺',
    title: '随手一拍的月亮，<br>也有自己的时间线',
    desc: '按月相回看拍到的月亮。从渐盈到满月，收藏那些曾经抬头的夜晚。',
    label: '月迹',
  },
  {
    tab: '票夹 · 出行凭证',
    title: '一张张票据，<br>替旅程留下凭证',
    desc: '火车票、机票、电影票和演唱会门票，留下路线、日期与行程，把旅程里的凭证和照片放在一起。',
    label: '票夹',
  },
]
const mapViews = [
  { key: '3d' as const, label: '3D 足迹' },
  { key: 'city' as const, label: '城市点亮' },
  { key: 'puzzle' as const, label: '足迹拼图' },
]
const sections = [
  { id: 'capabilities', label: '能力' },
  { id: 'memory', label: '记忆' },
  { id: 'footprints', label: '足迹' },
  { id: 'diary', label: '日记' },
  { id: 'download', label: '下载' },
]
const marquee = ['智能整理', '以文搜图', '足迹地图', '旅行日记', '人生章节', '月迹', '票夹', '断舍离', '5A 景区', '自托管', 'NAS', 'AI相册']
const albumTiles = [
  { name: '家人', note: '按人物', image: '/showcase/assets/lake.jpg' },
  { name: '风景', note: '按场景', image: '/showcase/assets/mountain.jpg' },
  { name: '那一天', note: '按时间', image: '/showcase/assets/sea.jpg' },
]
const stripPhotos = [
  { src: '/showcase/assets/forest.jpg', place: '山野', date: '10 / 03' },
  { src: '/showcase/assets/lake.jpg', place: '湖畔', date: '10 / 04' },
  { src: '/showcase/assets/mountain.jpg', place: '远山', date: '10 / 05' },
]

let api: { destroy: () => void; chooseMemory: (i: number) => void; refresh: () => void } | undefined
let preloadTimers: ReturnType<typeof setTimeout>[] = []
const citySrc = ref('')
const mapPreload3d = ref(false)
const mapPreloadPuzzle = ref(false)

const memoryLabel = computed(() => `0${memoryPage.value + 1} / 03 · ${memories[memoryPage.value].label}`)
const themeLabel = computed(() => (isDark.value ? '切换浅色模式' : '切换深色模式'))

function chooseMemory(index: number) {
  memoryPage.value = index
  api?.chooseMemory(index)
}
function onMemoryKey(event: KeyboardEvent, index: number) {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return
  event.preventDefault()
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3
  chooseMemory(next)
  const tab = root.value?.querySelector<HTMLButtonElement>(`#memory-tab-${next}`)
  tab?.focus()
}
function selectMap(view: '3d' | 'city' | 'puzzle') {
  mapView.value = view
  nextTick(() => api?.refresh())
}
function onMapKey(event: KeyboardEvent, index: number) {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return
  event.preventDefault()
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3
  selectMap(mapViews[next].key)
  const tab = root.value?.querySelector<HTMLButtonElement>(`#map-view-${mapViews[next].key}`)
  tab?.focus()
}
function jumpToMap(view: '3d' | 'city' | 'puzzle', event: Event) {
  event.preventDefault()
  selectMap(view)
  root.value?.querySelector('#footprints')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function toggleTheme(event: MouseEvent) {
  const next = !isDark.value
  const doc = document as Document & { startViewTransition?: (cb: () => Promise<void> | void) => void }
  if (!doc.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    isDark.value = next
    return
  }
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  document.documentElement.style.setProperty('--theme-x', `${rect.left + rect.width / 2}px`)
  document.documentElement.style.setProperty('--theme-y', `${rect.top + rect.height / 2}px`)
  doc.startViewTransition(async () => {
    isDark.value = next
    await nextTick()
  })
}
function closeMenu() {
  if (typeof document !== 'undefined') document.body.style.overflow = ''
  menuOpen.value = false
}
watch(menuOpen, (open) => {
  if (typeof document === 'undefined') return
  document.body.style.overflow = open ? 'hidden' : ''
})

onMounted(() => {
  if (root.value) {
    initFixedSamples(root.value)
    api = initHome(root.value, {
      setMapView: (view: '3d' | 'city' | 'puzzle') => { mapView.value = view },
      setMemoryPage: (index: number) => { memoryPage.value = index },
      closeMenu: () => { menuOpen.value = false },
    })
  }
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection
  if (connection?.saveData) return
  const scheduleMapPreload = () => {
    preloadTimers.push(setTimeout(() => { mapPreloadPuzzle.value = true }, 600))
    preloadTimers.push(setTimeout(() => { citySrc.value = '/showcase/city-fragment.html' }, 1500))
    preloadTimers.push(setTimeout(() => { mapPreload3d.value = true }, 2800))
  }
  if (document.readyState === 'complete') scheduleMapPreload()
  else window.addEventListener('load', scheduleMapPreload, { once: true })
})
onBeforeUnmount(() => {
  api?.destroy()
  preloadTimers.forEach(clearTimeout)
  preloadTimers = []
  document.body.style.overflow = ''
})
</script>

<template>
  <div ref="root" class="trailsnap-home" :class="{ 'menu-open': menuOpen }">
    <div class="grain" aria-hidden="true"></div>
    <div class="scroll-progress" aria-hidden="true"><span id="scroll-progress-bar"></span></div>

    <header class="site-header">
      <div class="wrap header-inner">
        <a class="brand" href="/" aria-label="行影集首页">
          <img src="/logo.svg" alt="" width="34" height="34">
          <span class="brand-text"><strong>行影集</strong><small>TRAILSNAP</small></span>
        </a>
        <nav class="nav-links" aria-label="主导航">
          <a href="#capabilities"><span>01</span>功能</a>
          <a href="#memory"><span>02</span>记忆</a>
          <a href="#footprints"><span>03</span>足迹</a>
          <a href="#diary"><span>04</span>日记</a>
          <a href="#start"><span>05</span>开始</a>
        </nav>
        <div class="nav-actions">
          <a class="nav-doc" href="/docs/guide/install">文档 <span aria-hidden="true">↗</span></a>
          <button class="theme-toggle" type="button" :aria-pressed="isDark" :aria-label="themeLabel" @click="toggleTheme">
            <svg class="icon-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.2A8.2 8.2 0 0 1 9.8 4 8.5 8.5 0 1 0 20 14.2Z" /></svg>
            <svg class="icon-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.4M12 19.6V22M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M2 12h2.4M19.6 12H22M4.9 19.1l1.7-1.7M17.4 6.6l1.7-1.7" /></svg>
          </button>
          <a class="btn btn-primary btn-sm nav-cta" href="/download">下载安装 <span class="btn-arrow" aria-hidden="true">↓</span></a>
          <button class="menu-toggle" type="button" :aria-expanded="menuOpen" aria-controls="mobile-menu" :aria-label="menuOpen ? '关闭菜单' : '打开菜单'" @click="menuOpen = !menuOpen">
            <span></span><span></span>
          </button>
        </div>
      </div>
    </header>

    <div id="mobile-menu" class="mobile-menu" :class="{ 'is-open': menuOpen }" :aria-hidden="!menuOpen">
      <div class="mobile-menu-inner">
        <p class="mobile-menu-kicker">行影集 · TRAILSNAP</p>
        <nav aria-label="移动端主导航">
          <a href="#capabilities" @click="closeMenu"><span>01</span>能做什么</a>
          <a href="#memory" @click="closeMenu"><span>02</span>记忆的三种形状</a>
          <a href="#footprints" @click="closeMenu"><span>03</span>足迹地图</a>
          <a href="#diary" @click="closeMenu"><span>04</span>旅行日记</a>
          <a href="#start" @click="closeMenu"><span>05</span>如何开始</a>
          <a href="/docs/guide/install" @click="closeMenu"><span>06</span>使用文档 <i aria-hidden="true">↗</i></a>
        </nav>
        <div class="mobile-menu-foot">
          <a class="btn btn-primary" href="/download" @click="closeMenu">下载行影集 <span class="btn-arrow" aria-hidden="true">↓</span></a>
          <a class="mobile-demo" href="https://demo.trailsnap.cn" target="_blank" rel="noopener">或先在线体验 <span aria-hidden="true">↗</span></a>
        </div>
      </div>
    </div>

    <main>
      <section id="top" class="hero">
        <div class="hero-atmosphere" aria-hidden="true">
          <span class="hero-sun"></span>
          <span class="hero-arch"></span>
          <span class="hero-rule rule-a"></span>
          <span class="hero-rule rule-b"></span>
        </div>
        <div class="wrap hero-inner">
          <div class="hero-copy">
            <p class="eyebrow"><span class="pulse"></span>开源自托管 · 私人 AI 相册</p>
            <h1 class="hero-title">
              <span class="title-line"><span>把散落的回忆，</span></span>
              <span class="title-line"><span>收进一本</span><span class="title-accent">行影集</span></span>
            </h1>
            <p class="hero-lead">接入自己的照片库，AI 会按人物、场景与时间归类；用一句话找回某个瞬间，在地图上重走一段旅程，再把它们写进属于你的日记。</p>
            <div class="hero-actions">
              <a class="btn btn-primary" href="https://demo.trailsnap.cn" target="_blank" rel="noopener">在线体验相册 <span class="btn-arrow" aria-hidden="true">↗</span></a>
              <a class="btn btn-ghost" href="/download">下载安装 <span class="btn-arrow" aria-hidden="true">↓</span></a>
            </div>
            <ul class="hero-meta">
              <li><i aria-hidden="true"></i>自托管</li>
              <li><i aria-hidden="true"></i>开源免费</li>
              <li><i aria-hidden="true"></i>NAS / 电脑 / 移动设备</li>
            </ul>
          </div>

          <div class="hero-stage">
            <span class="stage-glow" aria-hidden="true"></span>
            <figure class="hero-window">
              <div class="window-chrome">
                <span class="window-dots" aria-hidden="true"><i></i><i></i><i></i></span>
                <span class="window-url"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>demo.trailsnap.cn</span>
                <span class="window-live"><i></i>LIVE</span>
                <a class="window-open" href="https://demo.trailsnap.cn" target="_blank" rel="noopener">打开体验 <span aria-hidden="true">↗</span></a>
              </div>
              <div class="desktop-viewport">
                <DemoEmbed id="live-home" path="/" title="行影集在线演示" eager />
              </div>
            </figure>

            <div class="photo-strip" aria-hidden="true">
              <figure v-for="(photo, index) in stripPhotos" :key="photo.src" class="strip-card" :class="`strip-${index}`">
                <img :src="photo.src" alt="" loading="lazy">
                <figcaption><span>{{ photo.place }}</span><small>{{ photo.date }}</small></figcaption>
              </figure>
            </div>

            <div class="seal" aria-hidden="true">
              <svg viewBox="0 0 120 120">
                <defs><path id="seal-path" d="M60,60 m-44,0 a44,44 0 1,1 88,0 a44,44 0 1,1 -88,0" /></defs>
                <text><textPath href="#seal-path">TRAILSNAP · PRIVATE AI ALBUM · OPEN SOURCE ·</textPath></text>
              </svg>
              <span class="seal-core">行</span>
            </div>

            <div class="stage-quote">
              <span class="quote-mark" aria-hidden="true">“</span>
              <p>照片不只是文件，<br>它们是你走过的旅程。</p>
              <small>THE ARCHIVE OF LIGHT</small>
            </div>
          </div>
        </div>
        <div class="wrap hero-foot">
          <span class="scroll-hint"><i aria-hidden="true"></i>向下滚动，看看它能做什么</span>
          <span class="hero-foot-meta">智能相册 / 足迹地图 / 旅行日记</span>
        </div>
      </section>

      <div class="ticker" aria-hidden="true">
        <div class="ticker-track">
          <span v-for="(word, index) in marquee.concat(marquee)" :key="`${word}-${index}`">{{ word }}<i>✦</i></span>
        </div>
      </div>

      <section id="capabilities" class="section capabilities">
        <div class="wrap">
          <header class="section-head">
            <div class="section-head-main">
              <p class="kicker"><span>01</span>能做什么 / CAPABILITIES</p>
              <h2 class="section-title">AI智能相册<br>行影集让照片不只是文件</h2>
            </div>
            <p class="section-note">智能分类、以文搜图、地图、旅行日记——<br>照片也是知识库</p>
          </header>

          <div class="cap-layout">
            <article class="cap-card cap-organize" data-spotlight data-reveal>
              <div class="cap-top">
                <span class="cap-index">01</span>
                <span class="cap-tag">整理 / ORGANIZE</span>
              </div>
              <h3>智能分类</h3>
              <p>人物、风景、时间自动归档。打开相册，就像翻开一本已经整理好的书。</p>
              <div class="album-wall">
                <figure v-for="(tile, index) in albumTiles" :key="tile.name" class="album-tile" :class="`tile-${index}`">
                  <img :src="tile.image" alt="" loading="lazy">
                  <figcaption><strong>{{ tile.name }}</strong><small>{{ tile.note }}</small></figcaption>
                </figure>
              </div>
              <a class="cap-link" href="https://demo.trailsnap.cn" target="_blank" rel="noopener">体验智能相册 <span aria-hidden="true">↗</span></a>
            </article>

            <div class="cap-stack">
              <article class="cap-card cap-search" data-spotlight data-reveal style="--reveal-delay: 80ms">
                <div class="cap-top">
                  <span class="cap-index">02</span>
                  <span class="cap-tag">查找 / RECALL</span>
                </div>
                <h3>以文搜图</h3>
                <p>记得画面，却忘了文件名。用一句话描述，就能把那张照片找回来。</p>
                <div class="search-demo">
                  <div class="search-field" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.4" /><path d="m16 16 4.4 4.4" /></svg>
                    <span id="search-typed">海边看日落的照片</span><i class="caret"></i>
                  </div>
                  <div class="search-chips" aria-hidden="true"><span>海边</span><span>日落</span><span>傍晚</span><span>2025</span></div>
                </div>
                <a class="cap-link" href="https://demo.trailsnap.cn/search?q=海边日落" target="_blank" rel="noopener">试试照片搜索 <span aria-hidden="true">↗</span></a>
              </article>

              <article class="cap-card cap-route" data-spotlight data-reveal style="--reveal-delay: 160ms">
                <div class="cap-top">
                  <span class="cap-index">03</span>
                  <span class="cap-tag">回顾 / RETRACE</span>
                </div>
                <h3>足迹相册</h3>
                <p>照片落回地图，城市被一一点亮，沿途的路线连成一段旅程。</p>
                <div class="route-demo" aria-hidden="true">
                  <svg viewBox="0 0 320 92" preserveAspectRatio="none">
                    <path class="route-line" d="M18 70 C70 70 82 26 150 26 S238 70 302 70" />
                    <circle cx="18" cy="70" r="4" /><circle cx="150" cy="26" r="4" /><circle cx="302" cy="70" r="4" />
                  </svg>
                  <span class="route-pin pin-a">山间</span>
                  <span class="route-pin pin-b">海岸</span>
                  <span class="route-pin pin-c">日落</span>
                  <span class="route-badge">5A 景区识别</span>
                </div>
                <a class="cap-link" href="#footprints" @click="jumpToMap('3d', $event)">查看足迹地图 <span aria-hidden="true">↓</span></a>
              </article>
            </div>
          </div>
        </div>
      </section>

      <section id="memory" class="memory-scene">
        <div class="memory-stage">
          <div class="wrap memory-grid">
            <div class="memory-copy">
              <p class="kicker"><span>02</span>记忆的三种形状 / KEEPING</p>
              <div class="memory-texts">
                <article v-for="(item, index) in memories" :key="item.tab" class="memory-text" :class="{ 'is-active': memoryPage === index }" :aria-hidden="memoryPage !== index">
                  <h2 class="section-title" v-html="item.title"></h2>
                  <p>{{ item.desc }}</p>
                </article>
              </div>
              <div class="memory-tabs" role="tablist" aria-label="切换记忆展示">
                <button v-for="(item, index) in memories" :id="`memory-tab-${index}`" :key="item.tab" type="button" role="tab" :aria-selected="memoryPage === index" :aria-controls="`memory-panel-${index}`" :tabindex="memoryPage === index ? 0 : -1" @click="chooseMemory(index)" @keydown="onMemoryKey($event, index)">
                  <span>0{{ index + 1 }}</span>{{ item.tab }}<i aria-hidden="true"></i>
                </button>
              </div>
              <p class="memory-counter" aria-live="polite">{{ memoryLabel }}</p>
            </div>
            <div class="memory-visual">
              <div id="memory-panel-0" class="memory-panel" :class="{ 'is-active': memoryPage === 0 }" role="tabpanel" aria-labelledby="memory-tab-0" :inert="memoryPage !== 0">
                <div id="fixed-book" class="fixed-book"></div>
              </div>
              <div id="memory-panel-1" class="memory-panel" :class="{ 'is-active': memoryPage === 1 }" role="tabpanel" aria-labelledby="memory-tab-1" :inert="memoryPage !== 1">
                <div id="fixed-moon" class="fixed-moon"></div>
              </div>
              <div id="memory-panel-2" class="memory-panel" :class="{ 'is-active': memoryPage === 2 }" role="tabpanel" aria-labelledby="memory-tab-2" :inert="memoryPage !== 2">
                <div id="fixed-tickets" class="fixed-tickets"></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="footprints" class="section footprints">
        <div class="wrap">
          <header class="section-head">
            <div class="section-head-main">
              <p class="kicker"><span>03</span>足迹 / FOOTPRINTS</p>
              <h2 class="section-title">用拍过的照片，<br>点亮你的足迹地图。</h2>
            </div>
            <p class="section-note">在地球上回望旅程，<br>在地图上点亮城市。</p>
          </header>

          <div id="live-map-shell" class="panel map-panel">
            <div class="panel-bar">
              <span class="panel-dots" aria-hidden="true"><i></i><i></i><i></i></span>
              <div class="map-view-tabs" role="tablist" aria-label="选择足迹展示方式">
                <button v-for="(view, index) in mapViews" :id="`map-view-${view.key}`" :key="view.key" type="button" role="tab" :aria-selected="mapView === view.key" :aria-controls="view.key === '3d' ? 'live-map' : view.key === 'city' ? 'city-showcase-frame' : 'puzzle-showcase-frame'" :tabindex="mapView === view.key ? 0 : -1" @click="selectMap(view.key)" @keydown="onMapKey($event, index)">{{ view.label }}</button>
              </div>
              <button class="panel-expand" type="button" data-expand="live-map-shell" aria-expanded="false">全屏查看</button>
            </div>
            <div class="desktop-viewport map-viewport">
              <DemoEmbed id="live-map" path="/footprint" title="行影集 · 3D 足迹地图" :active="mapView === '3d'" :preload="mapPreload3d" />
              <iframe v-show="mapView === 'city'" id="city-showcase-frame" :src="citySrc" :loading="citySrc ? 'eager' : 'lazy'" title="城市点亮地图节选"></iframe>
              <div id="puzzle-showcase-frame" v-show="mapView === 'puzzle'" class="native-map-content">
                <FootprintPuzzle :preload="mapPreloadPuzzle" />
              </div>
            </div>
            <div class="panel-foot">
              <p id="map-view-caption">{{ mapCaptions[mapView] }}</p>
              <span class="panel-foot-meta">实时演示 · 可交互</span>
            </div>
          </div>
        </div>
      </section>

      <section id="diary" class="section diary">
        <div class="wrap diary-grid">
          <div class="diary-copy">
            <p class="kicker"><span>04</span>旅行日记 / TRAVEL DIARY</p>
            <h2 class="section-title">让旅程成为<br>可以重读的故事</h2>
            <p class="diary-lead">把沿途的照片与足迹写成一篇旅行日记，收藏风景，也留下出发时的心情。</p>
            <blockquote class="diary-quote">
              <p>「假期太短，脚步太长。后来才发现，这一天最喜欢的，是随手按下的快门。」</p>
              <cite>国庆七日 · 2025 / 山海之间</cite>
            </blockquote>
            <a class="btn btn-ghost" href="/examples/travel-diary-2025-golden-week.html" target="_blank" rel="noopener">打开完整游记 <span class="btn-arrow" aria-hidden="true">↗</span></a>
          </div>
          <div id="diary-panel" class="panel diary-panel">
            <div class="panel-bar">
              <span class="diary-label"><i aria-hidden="true"></i>国庆七日 · 2025 / 完整游记</span>
              <div class="panel-actions">
                <button type="button" data-reload="live-story">刷新</button>
                <button type="button" data-expand="diary-panel">全屏查看</button>
                <a href="/examples/travel-diary-2025-golden-week.html" target="_blank" rel="noopener">新窗口 <span aria-hidden="true">↗</span></a>
              </div>
            </div>
            <div id="diary-shell" class="desktop-viewport diary-viewport">
              <iframe id="live-story" src="/examples/travel-diary-2025-golden-week.html" title="国庆七日 · 2025 / 完整游记" loading="lazy" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox" allow="fullscreen" referrerpolicy="strict-origin-when-cross-origin"></iframe>
            </div>
          </div>
        </div>
      </section>

      <section id="tools" class="section tools">
        <div class="wrap">
          <header class="section-head">
            <div class="section-head-main">
              <p class="kicker"><span>05</span>记录与整理 / EVERYDAY TOOLS</p>
              <h2 class="section-title">给相册减减负，<br>留下真正喜欢的</h2>
            </div>
            <p class="section-note">向右保留，向左丢弃。<br>给回忆做一次断舍离</p>
          </header>
          <div class="panel tool-panel" data-reveal>
            <div class="tool-copy">
              <span class="tool-chip">断舍离 / SWIPE</span>
              <h3>留下喜欢的，<br>放下多余的</h3>
              <p>向右保留，向左丢弃。给相册做一次轻松的断舍离，只留下真正想记住的画面。</p>
              <a class="cap-link" href="https://demo.trailsnap.cn/swipe-filter" target="_blank" rel="noopener">在演示站打开断舍离 <span aria-hidden="true">↗</span></a>
            </div>
            <div class="tool-demo">
              <iframe src="/showcase/swipe-fragment.html" title="断舍离本地交互示例，操作不会删除照片" loading="lazy"></iframe>
            </div>
          </div>
        </div>
      </section>

      <section id="start" class="section start">
        <div class="wrap">
          <header class="section-head">
            <div class="section-head-main">
              <p class="kicker"><span>06</span>开始使用 / GET STARTED</p>
              <h2 class="section-title">三步，整理你的相册</h2>
            </div>
            <a class="btn btn-ghost" href="/docs/guide/install">查看完整安装指南 <span class="btn-arrow" aria-hidden="true">↗</span></a>
          </header>
          <ol class="start-steps">
            <li data-reveal>
              <span class="step-number">01</span>
              <h3>选择安装方式</h3>
              <p>个人电脑使用，可下载桌面版；希望长期运行，可参考文档在自己的NAS上部署。</p>
              <a href="/download">查看下载选项 <span aria-hidden="true">→</span></a>
            </li>
            <li data-reveal style="--reveal-delay: 90ms">
              <span class="step-number">02</span>
              <h3>接入照片文件夹</h3>
              <p>添加照片所在目录，等待扫描与索引。</p>
              <a href="https://demo.trailsnap.cn" target="_blank" rel="noopener">先看看演示 <span aria-hidden="true">→</span></a>
            </li>
            <li data-reveal style="--reveal-delay: 180ms">
              <span class="step-number">03</span>
              <h3>浏览与配置 AI</h3>
              <p>浏览时间轴与相册，再按需要配置模型，启用相应的识别、检索和日记生成能力。</p>
              <a href="/docs/guide/install">阅读配置文档 <span aria-hidden="true">→</span></a>
            </li>
          </ol>
        </div>
      </section>

      <section id="trust" class="section trust">
        <div class="wrap trust-grid">
          <div class="trust-intro">
            <p class="kicker"><span>07</span>数据与存储 / YOUR HOME</p>
            <h2 class="section-title">珍贵的回忆，<br>自己保管。</h2>
            <p>从照片存储，到 AI 整理，每一步都由你掌握。</p>
          </div>
          <div class="trust-items">
            <article data-reveal>
              <span class="trust-num">01 / STORAGE</span>
              <h3>有一个自己的家</h3>
              <p>将相册部署在自己的电脑或服务器上，按自己的方式保存照片，并为珍贵原片做好独立备份。</p>
            </article>
            <article data-reveal style="--reveal-delay: 90ms">
              <span class="trust-num">02 / INTELLIGENCE</span>
              <h3>选择合适的 AI</h3>
              <p>AI 能力取决于配置的模型与服务。使用外部服务时，相关照片或文本可能被发送给所选服务商。</p>
            </article>
            <article data-reveal style="--reveal-delay: 180ms">
              <span class="trust-num">03 / OPEN SOURCE</span>
              <h3>让长期收藏更踏实</h3>
              <p>开放的源代码、持续更新的文档与社区，让你能了解相册如何工作，也能参与它的成长。</p>
            </article>
          </div>
        </div>
      </section>

      <section id="download" class="finale">
        <span class="finale-glow" aria-hidden="true"></span>
        <div class="wrap finale-inner">
          <p class="kicker"><span>08</span>THE NEXT CHAPTER IS YOURS</p>
          <h2>准备好照片，<br>开始你的<span class="title-accent">行影集</span></h2>
          <p class="finale-lead">下载行影集，开始整理你的日常照片与旅行记忆。</p>
          <div class="finale-actions">
            <a class="btn btn-primary" href="/download">下载行影集 <span class="btn-arrow" aria-hidden="true">↓</span></a>
            <a class="btn btn-ghost" href="/docs/guide/install">查看部署指南 <span class="btn-arrow" aria-hidden="true">→</span></a>
          </div>
          <div class="finale-meta">
            <span>开源 · 自托管</span><i></i><span>照片与回忆，始终属于你</span><i></i><span>AGPL-3.0</span>
          </div>
        </div>
      </section>
    </main>

    <ContactFooter />

    <div class="mobile-dock" aria-label="快捷操作">
      <a href="https://demo.trailsnap.cn" target="_blank" rel="noopener">在线体验 <span aria-hidden="true">↗</span></a>
      <a class="is-primary" href="/download">下载安装 <span aria-hidden="true">↓</span></a>
    </div>

    <nav class="section-rail" aria-label="页面章节">
      <a v-for="item in sections" :key="item.id" :href="`#${item.id}`" :data-rail="item.id"><span>{{ item.label }}</span><i></i></a>
    </nav>
  </div>
</template>