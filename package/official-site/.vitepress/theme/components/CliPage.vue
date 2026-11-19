<template>
  <div class="trailsnap-home trailsnap-subpage cli-page" :class="{ 'is-en': isEn }">
    <SiteChrome current="cli" />

    <main class="subpage-main cli-main">
      <section class="sub-wrap cli-hero">
        <div class="cli-hero-copy">
          <p class="kicker"><span>01</span>{{ isEn ? 'CLI / COMMAND LINE' : 'CLI / 命令行工具' }}</p>
          <h1 class="subpage-title">
            {{ isEn ? 'Your library,' : '把照片库，' }}<br>
            <span class="title-accent">{{ isEn ? ' in your terminal' : '搬进终端' }}</span>
          </h1>
          <p class="subpage-lead">{{ t.desc }}</p>
          <div class="cli-package">
            <span>Package</span><strong>trailsnap-cli</strong>
            <i aria-hidden="true"></i>
            <span>Binary</span><code>trailsnap</code>
          </div>
        </div>

        <div class="cli-install-card">
          <div class="cli-install-tabs" role="tablist" :aria-label="t.package">
            <button v-for="tab in t.installTabs" :id="`cli-tab-${tab}`" :key="tab" type="button" role="tab"
              :aria-selected="activeTab === tab" :aria-controls="'cli-command-panel'" :tabindex="activeTab === tab ? 0 : -1"
              @click="activeTab = tab">{{ tab }}</button>
          </div>
          <div id="cli-command-panel" class="cli-command" role="tabpanel" :aria-labelledby="`cli-tab-${activeTab}`">
            <span class="dollar" aria-hidden="true">$</span>
            <code>{{ t.installCmds[activeTab] }}</code>
            <button class="copy-btn" type="button" :title="t.copy" :aria-label="t.copy" @click="copyToClipboard(t.installCmds[activeTab])">
              <svg v-if="copiedText === t.installCmds[activeTab]" xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9bd4b2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            </button>
          </div>
        </div>
      </section>

      <section class="sub-wrap cli-power">
        <header class="section-head">
          <div>
            <p class="kicker"><span>02</span>{{ isEn ? 'COMMANDS / CAPABILITIES' : 'COMMANDS / 能做什么' }}</p>
            <h2>{{ t.powerTitle }}</h2>
          </div>
          <p class="section-note">{{ t.powerDesc }}</p>
        </header>

        <div class="cli-grid">
          <article v-for="(section, index) in t.sections" :key="section.id" class="cli-card">
            <span class="cli-index">0{{ index + 1 }}</span>
            <h3>{{ section.title }}</h3>
            <p>{{ section.desc }}</p>
            <div class="terminal">
              <div class="terminal-bar" aria-hidden="true"><i></i><i></i><i></i><span>terminal</span></div>
              <div class="terminal-body" v-html="section.terminal"></div>
            </div>
          </article>
        </div>
      </section>

      <section class="cli-agent">
        <div class="sub-wrap agent-inner">
          <p class="kicker"><span>03</span>AGENT READY</p>
          <h2>{{ t.readyTitle }}</h2>
          <p>{{ t.readyDesc }}</p>
          <button type="button" class="btn btn-primary" @click="copyInstruction">
            <svg v-if="copiedText === instructionText" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9bd4b2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            {{ t.copyInstruction }}
          </button>
        </div>
      </section>

      <section class="sub-wrap cli-cta">
        <div class="cli-cta-inner">
          <div class="cli-cta-mark" aria-hidden="true">$</div>
          <h2>{{ t.getStartedTitle }}</h2>
          <p>{{ t.getStartedDesc }}</p>
          <div class="cli-cta-actions">
            <div class="inline-command">
              <span class="dollar" aria-hidden="true">$</span>
              <code>npm i -g trailsnap-cli</code>
              <button class="copy-btn" type="button" :title="t.copy" :aria-label="t.copy" @click="copyToClipboard('npm i -g trailsnap-cli')">
                <svg v-if="copiedText === 'npm i -g trailsnap-cli'" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9bd4b2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              </button>
            </div>
            <a class="btn btn-ghost" href="https://www.npmjs.com/package/trailsnap-cli" target="_blank" rel="noopener">{{ t.cliReference }} <span class="btn-arrow" aria-hidden="true">↗</span></a>
          </div>
        </div>
      </section>
    </main>

    <ContactFooter />
  </div>
</template>
<script setup>
import { computed, ref } from 'vue'
import { useData } from 'vitepress'
import ContactFooter from './ContactFooter.vue'
import SiteChrome from './SiteChrome.vue'
import '../landing/home.css'
import '../landing/subpage.css'

const { lang } = useData()
const isEn = computed(() => lang.value === 'en-US')

const t = computed(() => {
  if (isEn.value) {
    return {
      package: 'Package trailsnap-cli',
      title: 'TrailSnap CLI',
      desc: 'Install trailsnap-cli, run trailsnap, and use TrailSnap from any terminal',
      installTabs: ['pip', 'npm'],
      installCmds: {
        'pip': 'pip install trailsnap-cli',
        'npm': 'npm install -g trailsnap-cli'
      },
      powerTitle: 'Power of TrailSnap, in your terminal',
      powerDesc: 'Manage photos, albums, tags, locations, and people from the terminal — install trailsnap-cli, then use the trailsnap command',
      sections: [
        {
          id: 'photos',
          title: 'Photos',
          desc: 'Manage photos from the shell: list, info, delete — the rich command set for day-to-day workflows',
          terminal: `<span class="text-blue-500 dark:text-blue-400">$ trailsnap photos --help</span>

<span class="text-gray-600 dark:text-gray-300">Usage: trailsnap photos [options] [command]</span>

<span class="text-gray-600 dark:text-gray-300">Manage photos</span>

<span class="text-gray-500 dark:text-gray-400">Options:</span>
  <span class="text-green-600 dark:text-green-400">-h, --help</span>  <span class="text-gray-500 dark:text-gray-400">display help for command</span>

<span class="text-gray-500 dark:text-gray-400">Commands:</span>
  <span class="text-yellow-600 dark:text-yellow-400">list</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>          <span class="text-gray-600 dark:text-gray-300">List photos with filters</span>
  <span class="text-yellow-600 dark:text-yellow-400">info</span> <span class="text-gray-400 dark:text-gray-500">--photo-id &lt;id&gt;</span>  <span class="text-gray-600 dark:text-gray-300">View photo metadata and description</span>
  <span class="text-yellow-600 dark:text-yellow-400">delete</span> <span class="text-gray-400 dark:text-gray-500">--photo-id &lt;id&gt;</span><span class="text-gray-600 dark:text-gray-300">Delete a photo permanently</span>
  <span class="text-yellow-600 dark:text-yellow-400">help</span> <span class="text-gray-400 dark:text-gray-500">[command]</span>        <span class="text-gray-600 dark:text-gray-300">display help for command</span>`
        },
        {
          id: 'locations',
          title: 'Locations',
          desc: 'Statistics based on photo GPS information, query location distribution, and footprint timeline',
          terminal: `<span class="text-blue-500 dark:text-blue-400">$ trailsnap locations --help</span>

<span class="text-gray-600 dark:text-gray-300">Usage: trailsnap locations [options] [command]</span>

<span class="text-gray-600 dark:text-gray-300">Query locations and footprint timeline</span>

<span class="text-gray-500 dark:text-gray-400">Options:</span>
  <span class="text-green-600 dark:text-green-400">-h, --help</span>  <span class="text-gray-500 dark:text-gray-400">display help for command</span>

<span class="text-gray-500 dark:text-gray-400">Commands:</span>
  <span class="text-yellow-600 dark:text-yellow-400">list</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>      <span class="text-gray-600 dark:text-gray-300">Query location distribution</span>
  <span class="text-yellow-600 dark:text-yellow-400">timeline</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>  <span class="text-gray-600 dark:text-gray-300">Query footprint timeline</span>
  <span class="text-yellow-600 dark:text-yellow-400">help</span> <span class="text-gray-400 dark:text-gray-500">[command]</span>      <span class="text-gray-600 dark:text-gray-300">display help for command</span>`
        },
        {
          id: 'albums',
          title: 'Albums & Tags',
          desc: 'One-click queries for system album lists and classification tag lists. Supports pagination and custom output formats',
          terminal: `<span class="text-blue-500 dark:text-blue-400">$ trailsnap albums --help</span>

<span class="text-gray-600 dark:text-gray-300">Usage: trailsnap albums|tags [options] [command]</span>

<span class="text-gray-600 dark:text-gray-300">Manage albums and tags</span>

<span class="text-gray-500 dark:text-gray-400">Options:</span>
  <span class="text-green-600 dark:text-green-400">-h, --help</span>  <span class="text-gray-500 dark:text-gray-400">display help for command</span>

<span class="text-gray-500 dark:text-gray-400">Commands:</span>
  <span class="text-yellow-600 dark:text-yellow-400">list</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>      <span class="text-gray-600 dark:text-gray-300">List albums or tags with pagination</span>
  <span class="text-yellow-600 dark:text-yellow-400">help</span> <span class="text-gray-400 dark:text-gray-500">[command]</span>      <span class="text-gray-600 dark:text-gray-300">display help for command</span>`
        },
        {
          id: 'media',
          title: 'Media & People',
          desc: 'Query intelligently recognized people and faces, or directly retrieve the original media files and access URLs',
          terminal: `<span class="text-blue-500 dark:text-blue-400">$ trailsnap medias --help</span>

<span class="text-gray-600 dark:text-gray-300">Usage: trailsnap medias [options] [command]</span>

<span class="text-gray-600 dark:text-gray-300">Get media files or URLs</span>

<span class="text-gray-500 dark:text-gray-400">Options:</span>
  <span class="text-green-600 dark:text-green-400">-h, --help</span>  <span class="text-gray-500 dark:text-gray-400">display help for command</span>

<span class="text-gray-500 dark:text-gray-400">Commands:</span>
  <span class="text-yellow-600 dark:text-yellow-400">get</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>       <span class="text-gray-600 dark:text-gray-300">Get photo media file or URL</span>
  <span class="text-yellow-600 dark:text-yellow-400">help</span> <span class="text-gray-400 dark:text-gray-500">[command]</span>      <span class="text-gray-600 dark:text-gray-300">display help for command</span>`
        }
      ],
      readyTitle: 'Ready for agent use',
      readyDesc: 'Expose TrailSnap as a tool other agents can call. Standard input and output, predictable exit codes, no UI required — just plug it into the orchestration of your choice',
      copyInstruction: 'Copy Instruction for Agent',
      getStartedTitle: 'Get started with TrailSnap CLI',
      getStartedDesc: 'Install globally, run trailsnap --help, then explore photos, locations, albums, and media command groups',
      cliReference: 'CLI reference on npm',
      copy: 'Copy',
      copied: 'Copied!'
    }
  }
  
  return {
    package: '包 trailsnap-cli',
    title: 'TrailSnap CLI',
    desc: '安装 trailsnap-cli，运行 trailsnap，在任意终端使用 TrailSnap',
    installTabs: ['pip', 'npm'],
    installCmds: {
      'pip': 'pip install trailsnap-cli',
      'npm': 'npm install -g trailsnap-cli'
    },
    powerTitle: '终端里的强大能力',
    powerDesc: '从终端管理照片、相册、标签、位置和人物等数据——安装 trailsnap-cli，然后使用 trailsnap 命令',
    sections: [
      {
        id: 'photos',
        title: '照片管理',
        desc: '从 shell 管理照片：查询列表、获取详情、删除——面向日常工作流的丰富命令集',
        terminal: `<span class="text-blue-500 dark:text-blue-400">$ trailsnap photos --help</span>

<span class="text-gray-600 dark:text-gray-300">Usage: trailsnap photos [options] [command]</span>

<span class="text-gray-600 dark:text-gray-300">Manage photos</span>

<span class="text-gray-500 dark:text-gray-400">Options:</span>
  <span class="text-green-600 dark:text-green-400">-h, --help</span>  <span class="text-gray-500 dark:text-gray-400">display help for command</span>

<span class="text-gray-500 dark:text-gray-400">Commands:</span>
  <span class="text-yellow-600 dark:text-yellow-400">list</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>          <span class="text-gray-600 dark:text-gray-300">查询带有过滤条件的照片列表</span>
  <span class="text-yellow-600 dark:text-yellow-400">info</span> <span class="text-gray-400 dark:text-gray-500">--photo-id &lt;id&gt;</span>  <span class="text-gray-600 dark:text-gray-300">查看照片元数据与描述信息</span>
  <span class="text-yellow-600 dark:text-yellow-400">delete</span> <span class="text-gray-400 dark:text-gray-500">--photo-id &lt;id&gt;</span><span class="text-gray-600 dark:text-gray-300">永久删除一张照片</span>
  <span class="text-yellow-600 dark:text-yellow-400">help</span> <span class="text-gray-400 dark:text-gray-500">[command]</span>        <span class="text-gray-600 dark:text-gray-300">display help for command</span>`
      },
      {
        id: 'locations',
        title: '位置与时间轴',
        desc: '基于照片的 GPS 信息统计，查询照片位置分布、足迹时间轴',
        terminal: `<span class="text-blue-500 dark:text-blue-400">$ trailsnap locations --help</span>

<span class="text-gray-600 dark:text-gray-300">Usage: trailsnap locations [options] [command]</span>

<span class="text-gray-600 dark:text-gray-300">Query locations and footprint timeline</span>

<span class="text-gray-500 dark:text-gray-400">Options:</span>
  <span class="text-green-600 dark:text-green-400">-h, --help</span>  <span class="text-gray-500 dark:text-gray-400">display help for command</span>

<span class="text-gray-500 dark:text-gray-400">Commands:</span>
  <span class="text-yellow-600 dark:text-yellow-400">list</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>      <span class="text-gray-600 dark:text-gray-300">查询位置分布</span>
  <span class="text-yellow-600 dark:text-yellow-400">timeline</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>  <span class="text-gray-600 dark:text-gray-300">查询足迹时间轴</span>
  <span class="text-yellow-600 dark:text-yellow-400">help</span> <span class="text-gray-400 dark:text-gray-500">[command]</span>      <span class="text-gray-600 dark:text-gray-300">display help for command</span>`
      },
      {
        id: 'albums',
        title: '相册与分类标签',
        desc: '一键查询系统中的相册列表和分类标签列表，支持分页和自定义输出格式',
        terminal: `<span class="text-blue-500 dark:text-blue-400">$ trailsnap albums --help</span>

<span class="text-gray-600 dark:text-gray-300">Usage: trailsnap albums|tags [options] [command]</span>

<span class="text-gray-600 dark:text-gray-300">Manage albums and tags</span>

<span class="text-gray-500 dark:text-gray-400">Options:</span>
  <span class="text-green-600 dark:text-green-400">-h, --help</span>  <span class="text-gray-500 dark:text-gray-400">display help for command</span>

<span class="text-gray-500 dark:text-gray-400">Commands:</span>
  <span class="text-yellow-600 dark:text-yellow-400">list</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>      <span class="text-gray-600 dark:text-gray-300">分页查询相册或标签列表</span>
  <span class="text-yellow-600 dark:text-yellow-400">help</span> <span class="text-gray-400 dark:text-gray-500">[command]</span>      <span class="text-gray-600 dark:text-gray-300">display help for command</span>`
      },
      {
        id: 'media',
        title: '人物识别与媒体文件',
        desc: '查询智能识别出的人物与面孔，或是直接通过命令行获取照片的原始媒体文件和访问链接',
        terminal: `<span class="text-blue-500 dark:text-blue-400">$ trailsnap medias --help</span>

<span class="text-gray-600 dark:text-gray-300">Usage: trailsnap medias [options] [command]</span>

<span class="text-gray-600 dark:text-gray-300">Get media files or URLs</span>

<span class="text-gray-500 dark:text-gray-400">Options:</span>
  <span class="text-green-600 dark:text-green-400">-h, --help</span>  <span class="text-gray-500 dark:text-gray-400">display help for command</span>

<span class="text-gray-500 dark:text-gray-400">Commands:</span>
  <span class="text-yellow-600 dark:text-yellow-400">get</span> <span class="text-gray-400 dark:text-gray-500">[options]</span>       <span class="text-gray-600 dark:text-gray-300">获取照片媒体文件或URL</span>
  <span class="text-yellow-600 dark:text-yellow-400">help</span> <span class="text-gray-400 dark:text-gray-500">[command]</span>      <span class="text-gray-600 dark:text-gray-300">display help for command</span>`
      }
    ],
    readyTitle: '可供 Agent 使用',
    readyDesc: '将 TrailSnap 暴露为可供其他 Agent 调用的工具。标准输入与输出、可预测的退出码、无需 UI —— 直接接入你选择的编排体系',
    copyInstruction: '复制 Agent 指令',
    getStartedTitle: '开始使用 TrailSnap CLI',
    getStartedDesc: '全局安装，运行 trailsnap --help，然后探索照片、位置、相册和媒体等命令组',
    cliReference: 'npm 上的 CLI 参考',
    copy: '复制',
    copied: '已复制!'
  }
})

const activeTab = ref('npm')
const copiedText = ref('')

const copyToClipboard = (text) => {
  navigator.clipboard.writeText(text).then(() => {
    copiedText.value = text
    setTimeout(() => {
      copiedText.value = ''
    }, 2000)
  })
}

const instructionText = computed(() => isEn.value
  ? 'Please install trailsnap-cli and skill : https://trailsnap.cn/install.md'
  : '帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md')

const copyInstruction = () => {
  copyToClipboard(instructionText.value)
}
</script>
