<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useData } from 'vitepress'
import { UsersRound, Mountain, Sun } from 'lucide-vue-next'
import ContactFooter from './ContactFooter.vue'
import FootprintPuzzle from './FootprintPuzzle.vue'
import DemoEmbed from './DemoEmbed.vue'
import { initHome } from '../landing/home-motion.js'
import { initFixedSamples } from '../landing/fixed-samples.js'
import '../landing/home.css'
import '../landing/capabilities.css'
import '../landing/memory-showcase.css'
const { isDark } = useData()
const root = ref<HTMLElement>()
const mapView = ref<'3d' | 'city' | 'puzzle'>('3d')
const mapCaptions = { '3d': '拖动地球、缩放视角，直接探索演示相册的足迹。', city: '在照片里，点亮去过的城市。', puzzle: '用沿途的照片，拼起走过的世界。' }
let cleanup: (() => void) | undefined
onMounted(() => { if (root.value) { initFixedSamples(root.value); cleanup = initHome(root.value, { setMapView: (view: '3d' | 'city' | 'puzzle') => { mapView.value = view } }) } })
onBeforeUnmount(() => cleanup?.())
</script>
<template><div ref="root" class="trailsnap-home">

<header>
    <nav class="wrap nav" aria-label="主导航"><a class="brand" href="#"><img src="/logo.svg" alt=""><div><div class="brand-name">行影集</div><div class="brand-en">TRAILSNAP</div></div></a><div class="nav-links"><a href="#capabilities">能做什么</a><a href="#journeys">旅行特色</a><a href="#chapter-showcase">记忆与月迹</a><a href="#product">如何开始</a><a href="/docs/guide/install">使用文档 ↗</a></div><div class="nav-right"><button class="theme" id="theme" @click="isDark = !isDark" :aria-pressed="isDark" :aria-label="isDark ? '切换浅色模式' : '切换深色模式'">◐</button><a class="btn small" href="/download">下载行影集 <span>↗</span></a></div></nav></header>
<main>
    <div class="scroll-scene">
        <section class="wrap hero">
            <div class="hero-copy">
                <div class="eyebrow">行影集 TRAILSNAP · 开源 AI 相册</div>
                <h1>一个会整理照片的<br><span>私人 AI 相册。</span></h1>
                <p class="hero-desc">把电脑里的照片接入行影集，按人物、场景和时间整理；用一句话查找照片，在地图上回顾足迹，还能让 AI 帮你写旅行日记。</p>
                <p class="hosting-note">安装在自己的电脑或服务器上，照片由自己保存。</p>
                <div class="actions">
                    <a class="btn" href="https://demo.siyuan.ink" target="_blank" rel="noopener">在线体验相册 <span>↗</span></a>
                    <a class="btn secondary" href="/download">下载安装 <span>↓</span></a>
                </div>
                <div class="fine"><a href="#product">了解安装与使用 →</a></div>
            </div>
            <div class="hero-live">
                <div class="live-shell hero-window" id="live-home-shell">
                    <div class="desktop-viewport"><DemoEmbed id="live-home" path="/" title="行影集在线演示" eager /></div>
                </div>
            </div>
            <div class="scene-controls"><span class="scroll-cue">向下滚动，探索行影集 <i>↓</i></span></div>
            <div class="scene-progress" aria-hidden="true"><span></span></div>
        </section>
    </div>
    <div class="wrap hero-bottom"><span>整理日常照片，也珍藏每一段旅行。</span><div><span>智能相册 / 足迹地图 / 旅行日记</span><a href="#capabilities">了解它能做什么 ↓</a></div></div>
    <section class="wrap capabilities" id="capabilities">
        <div class="cap-heading">
            <div>
                <div class="eyebrow">从照片文件夹，到自己的智能相册</div>
                <h2 class="section-title">整理、查找、回顾，让照片不止于存放。</h2>
            </div>
        </div>
        <div class="cap-grid">
            <article>
                <span class="cap-icon" aria-hidden="true">▦</span><span class="cap-label">01 / 整理</span>
                <h3>智能分类</h3>
                <p>按人物、场景和时间归类，浏览照片，不必反复翻文件夹。</p>
                <div class="cap-preview cap-organize">
                    <span class="cap-preview-label">分类效果示例</span>
                    <div class="cap-albums">
                        <div class="cap-album"><UsersRound class="cap-album-icon" aria-hidden="true" /><span>家人<small>按人物浏览</small></span></div>
                        <div class="cap-album"><Mountain class="cap-album-icon" aria-hidden="true" /><span>风景<small>按场景浏览</small></span></div>
                    </div>
                    <div class="cap-preview-foot">也可以按时间，回看某一天。</div>
                </div>
                <a class="cap-link" href="https://demo.siyuan.ink" target="_blank" rel="noopener">体验智能相册 <span aria-hidden="true">↗</span></a>
            </article>
            <article>
                <span class="cap-icon" aria-hidden="true">⌕</span><span class="cap-label">02 / 查找</span>
                <h3>以文搜图</h3>
                <p>试着说“海边看日落的照片”，用记得的画面找回回忆。</p>
                <div class="cap-preview cap-search">
                    <span class="cap-preview-label">搜索效果示例</span>
                    <div class="cap-search-query"><span aria-hidden="true">⌕</span>海边看日落的照片</div>
                    <div class="cap-search-results">
                        <span>海边</span><span>日落</span><span>傍晚</span>
                    </div>
                    <div class="cap-search-hint"><Sun aria-hidden="true" /><span>从画面线索开始<small>还可结合人物、时间与地点查找</small></span></div>
                </div>
                <a class="cap-link" href="https://demo.siyuan.ink/search" target="_blank" rel="noopener">试试照片搜索 <span aria-hidden="true">↗</span></a>
            </article>
            <article>
                <span class="cap-icon" aria-hidden="true">⌁</span><span class="cap-label">03 / 回顾</span>
                <h3>足迹相册</h3>
                <p>在地图上回看拍摄地点，让沿途照片串成可以重读的旅行日记，专门的5A景区识别，记录去过的景区。</p>
                <div class="cap-preview cap-recall">
                    <span class="cap-preview-label">旅程效果示例</span>
                    <div class="cap-route" aria-label="示例旅程：山间、海岸、日落">
                        <svg viewBox="0 0 300 66" preserveAspectRatio="none" aria-hidden="true"><path d="M20 42 C65 42 80 12 150 12 S230 42 280 42" /><circle cx="20" cy="42" r="4" /><circle cx="150" cy="12" r="4" /><circle cx="280" cy="42" r="4" /></svg>
                        <div class="cap-route-labels"><span>山间</span><span>海岸</span><span>日落</span></div>
                    </div>
                    <div class="cap-trip-diary"><span>旅行日记 · 示例片段</span><strong>沿着海岸，等一场日落。</strong><small>把沿途照片与足迹，留在同一个故事里。</small></div>
                </div>
                <a class="cap-link" href="#journeys" data-jump-map="3d">查看足迹地图 <span aria-hidden="true">↓</span></a>
            </article>
        </div>
    </section>
    <nav class="wrap feature-jumps" aria-label="更多功能展示">
        <span>继续探索</span>
        <a href="#chapter-showcase">记忆 · 人生章节 ↗</a>
        <a href="#chapter-showcase" data-jump-memory="1">月迹 ↗</a>
        <a href="#journeys" data-jump-map="city">城市点亮 ↗</a>
        <a href="#everyday-tools">断舍离 ↗</a>
    </nav>
    <section class="memory-scene" id="chapter-showcase">
        <div class="wrap memory-stage">
            <div class="memory-copy">
                <div class="eyebrow">生活里的线索 / 三种方式，重新遇见</div>
                <div class="memory-copy-body">
                    <div class="memory-copy-item is-active" data-memory-copy="0">
                        <h2>把一段时光，<br>装订成自己的日记。</h2>
                        <p>一天一页，照片与文字留在一起。翻阅人生章节里的每日日记，把散落的生活重新读一遍。</p>
                    </div>
                    <div class="memory-copy-item" data-memory-copy="1" hidden>
                        <h2>你拍过的月亮，<br>也有自己的时间线。</h2>
                        <p>按月相回看拍到的月亮。从渐盈到满月，收藏那些曾经抬头的夜晚。</p>
                    </div>
                    <div class="memory-copy-item" data-memory-copy="2" hidden>
                        <h2>每一张票，<br>都是出发的证据。</h2>
                        <p>火车票和机票，留下路线、日期与车次。把旅程里的凭证放在一起，也找回当时为什么出发。</p>
                    </div>
                </div>
                <div class="memory-tabs" role="tablist" aria-label="切换生活记录展示">
                    <button type="button" id="memory-tab-0" data-memory-tab="0" role="tab" aria-selected="true" aria-controls="memory-panel-0">
                        <span>01</span>记忆 · 人生章节<i></i></button>
                        <button type="button" id="memory-tab-1" data-memory-tab="1" role="tab" aria-selected="false" aria-controls="memory-panel-1" tabindex="-1">
                            <span>02</span>月迹 · 阴晴圆缺<i></i>
                        </button>
                        <button type="button" id="memory-tab-2" data-memory-tab="2" role="tab" aria-selected="false" aria-controls="memory-panel-2" tabindex="-1">
                            <span>03</span>票夹 · 出行凭证<i></i>
                        </button>
                    </div>
                </div>
                <div class="memory-visual"><div class="memory-panel is-active" id="memory-panel-0" role="tabpanel" aria-labelledby="memory-tab-0">
                    <div class="fixed-book" id="fixed-book"></div>
                </div>
                <div class="memory-panel" id="memory-panel-1" role="tabpanel" aria-labelledby="memory-tab-1" aria-hidden="true" inert>
                    <div class="fixed-moon" id="fixed-moon"></div>
                </div>
                <div class="memory-panel" id="memory-panel-2" role="tabpanel" aria-labelledby="memory-tab-2" aria-hidden="true" inert>
                    <div class="fixed-tickets" id="fixed-tickets"></div>
                </div>
            </div>
            <div class="memory-footer">
                <span>生活的不同侧面，都值得留下。</span>
                <span id="memory-page-label" aria-live="polite">01 / 03 · 人生章节</span>
            </div>
            <div class="memory-progress" aria-hidden="true"><span></span></div>
        </div>
    </section>
    <div class="feature-scene">
        <section class="wrap real-feature motion-feature" id="journeys">
            <div class="live-section-heading">
                <div>
                    <div class="eyebrow">足迹 / 走过的地方</div>
                    <h2 class="section-title">走过的世界，<br>换个视角再看一遍。</h2>
                    <p class="section-desc">在地球上回望旅程，在地图上点亮城市，再用沿途照片，拼起走过的世界。</p>
                </div>
            </div>
            <div class="live-shell map-window" id="live-map-shell">
                <div class="map-switcher">
                    <div class="map-view-tabs" role="tablist" aria-label="选择足迹展示方式">
                        <button type="button" data-map-view="3d" id="map-view-3d" role="tab" :aria-selected="mapView === '3d'" :tabindex="mapView === '3d' ? 0 : -1" @click="mapView = '3d'" aria-controls="live-map">3D 足迹</button><button type="button" data-map-view="city" id="map-view-city" role="tab" :aria-selected="mapView === 'city'" :tabindex="mapView === 'city' ? 0 : -1" @click="mapView = 'city'" aria-controls="city-showcase-frame">城市点亮</button><button type="button" data-map-view="puzzle" id="map-view-puzzle" role="tab" :aria-selected="mapView === 'puzzle'" :tabindex="mapView === 'puzzle' ? 0 : -1" @click="mapView = 'puzzle'" aria-controls="puzzle-showcase-frame">足迹拼图</button></div><button type="button" class="map-expand" data-expand="live-map-shell" aria-expanded="false">全屏查看</button></div><div class="desktop-viewport"><DemoEmbed id="live-map" path="/footprint" title="行影集 · 3D 足迹地图" :active="mapView === '3d'" /><iframe :hidden="mapView !== 'city'" id="city-showcase-frame" src="/showcase/city-fragment.html" title="城市点亮地图节选" loading="lazy"></iframe><div id="puzzle-showcase-frame" class="native-map-content" :hidden="mapView !== 'puzzle'"><FootprintPuzzle /></div></div></div><p class="feature-caption" id="map-view-caption">{{ mapCaptions[mapView] }}</p><div class="feature-progress" aria-hidden="true"><span></span></div></section></div>
    <section class="wrap real-feature reading-feature" id="stories">
        <div class="live-section-heading">
            <div>
                <div class="eyebrow">旅行日记 / 让照片连成故事</div>
                <h2 class="section-title">让一段旅程，<br>成为可以重读的故事。</h2>
                <p class="section-desc">把沿途的照片与足迹串成旅行日记，收藏风景，也留下出发时的心情。</p>
            </div>
        </div>
        <div class="live-shell story-window" id="live-story-shell">
            <div class="live-toolbar"><span><i></i> 国庆七日 · 2025 / 完整游记</span>
                <div>
                    <button type="button" data-reload="live-story">刷新</button>
                    <button type="button" data-expand="live-story-shell">全屏查看</button>
                    <a href="/examples/travel-diary-2025-golden-week.html" id="live-story-link" target="_blank" rel="noopener">新窗口打开 ↗</a>
                </div>
            </div>
            <div class="desktop-viewport">
                <iframe id="live-story" src="/examples/travel-diary-2025-golden-week.html" title="国庆七日 · 2025 / 完整游记" loading="lazy" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox" allow="fullscreen" referrerpolicy="strict-origin-when-cross-origin"></iframe>
            </div>
        </div>
    </section>
    <section class="wrap everyday-tools" id="everyday-tools">
        <div class="tools-heading">
            <div class="eyebrow">记录与整理 / 不止于浏览照片</div>
            <h2>给相册减减负，留住真正喜欢的。</h2>
        </div>
        <div class="tools-grid">
            <article class="tool-showcase">
                <div class="tool-copy"><span class="eyebrow">断舍离 / 轻一点的相册</span>
                    <h3>留下喜欢的，放下多余的。</h3>
                    <p>向右保留，向左丢弃，给相册做个断舍离。</p>
                    <a href="https://demo.siyuan.ink/swipe-filter" target="_blank" rel="noopener">在演示站打开断舍离 ↗</a>
                </div>
                <iframe src="/showcase/swipe-fragment.html" title="断舍离本地交互示例，操作不会删除照片" loading="lazy"></iframe>
            </article>
        </div>
    </section>
    <section class="product" id="product">
        <div class="wrap">
            <div class="product-head">
                <div>
                    <div class="eyebrow">开始使用 / YOUR OWN PHOTO LIBRARY</div>
                    <h2 class="section-title">装好相册，接入照片，就能开始浏览。</h2>
                </div>
                <a class="btn secondary" href="/docs/guide/install">查看完整安装指南 ↗</a>
            </div>
            <div class="start-grid">
                <article><span>01</span>
                    <h3>选择安装方式</h3>
                    <p>个人电脑使用可下载桌面端；希望长期运行，可参考文档在自己的服务器上部署。</p>
                    <a href="/download">查看下载选项 →</a>
                </article>
                <article>
                    <span>02</span>
                    <h3>接入照片文件夹</h3>
                    <p>添加照片所在目录，等待扫描与索引。建议先用少量照片体验，再接入完整图库。</p>
                </article>
                <article>
                    <span>03</span>
                    <h3>浏览与配置 AI</h3>
                    <p>浏览时间轴与相册，再按需要配置模型，启用相应的识别、检索和日记生成能力。</p>
                </article>
            </div>
        </div>
    </section>
    <section class="wrap trust">
        <div class="trust-heading">
            <div>
                <div class="eyebrow">数据与存储 / YOUR MEMORIES, YOUR HOME</div>
                <h2 class="section-title">珍贵的回忆，自己保管。</h2>
            </div>
            <p class="section-desc">从照片存储，到 AI 整理，<br>每一步都由你掌握。</p>
        </div>
        <div class="trust-grid">
            <article><span class="number">01 / STORAGE</span><h3>有一个自己的家</h3><p>将相册部署在自己的电脑或服务器上，按自己的方式保存照片，并为珍贵原片做好独立备份。</p></article>
            <article><span class="number">02 / INTELLIGENCE</span><h3>选择合适的 AI</h3><p>AI 能力取决于配置的模型与服务。使用外部服务时，相关照片或文本可能被发送给所选服务商。</p></article>
            <article><span class="number">03 / OPEN SOURCE</span><h3>让长期收藏更踏实</h3><p>开放的源代码、持续更新的文档与社区，让你能了解相册如何工作，也能参与它的成长。</p></article>
        </div>
    </section>
    <section class="wrap end">
        <div class="eyebrow">THE NEXT CHAPTER IS YOURS</div>
        <h2>给照片一个家，让回忆更好找。</h2>
        <p>下载行影集，开始整理你的日常照片与旅行记忆。</p>
        <div class="actions">
            <a class="btn" href="/download">下载行影集 <span>↗</span></a>
            <a class="btn secondary" href="/docs/guide/install">查看部署指南 <span>→</span></a>
        </div>
    </section>
</main>
<ContactFooter />

</div></template>
