<script setup>
import { computed, ref } from 'vue'
import { useData } from 'vitepress'

const { lang } = useData()
const isEn = computed(() => lang.value === 'en-US')

const t = computed(() => {
  if (isEn.value) {
    return {
      package: 'Package trailsnap-cli',
      title: 'TrailSnap CLI',
      desc: 'Install trailsnap-cli, run trailsnap, and use TrailSnap from any terminal.',
      installTabs: ['pip', 'npm'],
      installCmds: {
        'pip': 'pip install trailsnap-cli',
        'npm': 'npm install -g trailsnap-cli'
      },
      powerTitle: 'Power of TrailSnap, in your terminal',
      powerDesc: 'Manage photos, albums, tags, locations, and people from the terminal — install trailsnap-cli, then use the trailsnap command.',
      sections: [
        {
          id: 'photos',
          title: 'Photos',
          desc: 'Manage photos from the shell: list, info, delete — the rich command set for day-to-day workflows.',
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
          desc: 'Statistics based on photo GPS information, query location distribution, and footprint timeline.',
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
          desc: 'One-click queries for system album lists and classification tag lists. Supports pagination and custom output formats.',
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
          desc: 'Query intelligently recognized people and faces, or directly retrieve the original media files and access URLs.',
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
      readyDesc: 'Expose TrailSnap as a tool other agents can call. Standard input and output, predictable exit codes, no UI required — just plug it into the orchestration of your choice.',
      copyInstruction: 'Copy Instruction for Agent',
      getStartedTitle: 'Get started with TrailSnap CLI',
      getStartedDesc: 'Install globally, run trailsnap --help, then explore photos, locations, albums, and media command groups.',
      cliReference: 'CLI reference on npm',
      copy: 'Copy',
      copied: 'Copied!'
    }
  }
  
  return {
    package: '包 trailsnap-cli',
    title: 'TrailSnap CLI',
    desc: '安装 trailsnap-cli，运行 trailsnap，在任意终端使用 TrailSnap。',
    installTabs: ['pip', 'npm'],
    installCmds: {
      'pip': 'pip install trailsnap-cli',
      'npm': 'npm install -g trailsnap-cli'
    },
    powerTitle: '终端里的强大能力',
    powerDesc: '从终端管理照片、相册、标签、位置和人物等数据——安装 trailsnap-cli，然后使用 trailsnap 命令。',
    sections: [
      {
        id: 'photos',
        title: '照片管理',
        desc: '从 shell 管理照片：查询列表、获取详情、删除——面向日常工作流的丰富命令集。',
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
        desc: '基于照片的 GPS 信息统计，查询照片位置分布、足迹时间轴。',
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
        desc: '一键查询系统中的相册列表和分类标签列表，支持分页和自定义输出格式。',
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
        desc: '查询智能识别出的人物与面孔，或是直接通过命令行获取照片的原始媒体文件和访问链接。',
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
    readyDesc: '将 TrailSnap 暴露为可供其他 Agent 调用的工具。标准输入与输出、可预测的退出码、无需 UI —— 直接接入你选择的编排体系。',
    copyInstruction: '复制 Agent 指令',
    getStartedTitle: '开始使用 TrailSnap CLI',
    getStartedDesc: '全局安装，运行 trailsnap --help，然后探索照片、位置、相册和媒体等命令组。',
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

const copyInstruction = () => {
  const text = isEn.value 
    ? 'Please install trailsnap-cli and skill : https://trailsnap.cn/install.md'
    : '帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md'
  copyToClipboard(text)
}
</script>

<template>
  <div class="cli-page bg-[#fafafa] dark:bg-black min-h-screen text-gray-900 dark:text-gray-100 font-sans pb-24">
    
    <!-- Hero Section -->
    <section class="relative max-w-6xl mx-auto px-4 pt-32 pb-24 sm:px-6 lg:px-8 flex flex-col items-center text-center overflow-hidden">
      <!-- Background Glow (LobeHub style) -->
      <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-primary/20 dark:bg-primary/10 blur-[120px] rounded-full pointer-events-none -z-10"></div>
      
      <h1 class="text-6xl md:text-7xl font-extrabold tracking-tight mb-6 max-w-4xl leading-tight">
        <span class="italic font-serif pr-2">TrailSnap</span> CLI
      </h1>
      
      <p class="text-lg md:text-xl text-gray-600 dark:text-gray-400 mb-10 max-w-2xl leading-relaxed">
        {{ t.desc }}
      </p>

      <div class="inline-flex items-center justify-center px-4 py-2 mb-10 text-sm rounded-full bg-white dark:bg-[#111] text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-[#333] shadow-sm">
        <span class="text-gray-400 dark:text-gray-500 mr-2">Package</span> <span class="font-medium">trailsnap-cli</span>
        <span class="mx-3 text-gray-300 dark:text-gray-600">·</span>
        <span class="text-gray-400 dark:text-gray-500 mr-2">CLI binary</span> <code class="font-mono text-primary dark:text-primary-light">trailsnap</code>
      </div>

      <!-- Install Widget (LobeHub style) -->
      <div class="w-full max-w-lg bg-white dark:bg-[#111] rounded-2xl border border-gray-200 dark:border-[#333] overflow-hidden shadow-xl shadow-black/5 dark:shadow-black/40">
        <div class="flex p-2 gap-2 border-b border-gray-100 dark:border-[#222]">
          <button 
            v-for="tab in t.installTabs" 
            :key="tab"
            @click="activeTab = tab"
            class="flex-1 py-2 text-sm font-medium rounded-lg transition-all"
            :class="activeTab === tab ? 'bg-gray-100 dark:bg-[#222] text-gray-900 dark:text-white' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'"
          >
            {{ tab }}
          </button>
        </div>
        <div class="p-4 flex items-center justify-between">
          <div class="flex items-center gap-3 overflow-hidden">
            <span class="text-primary font-bold select-none">$</span>
            <code class="text-sm font-mono text-gray-800 dark:text-gray-200 truncate">
              {{ t.installCmds[activeTab] }}
            </code>
          </div>
          <button 
            @click="copyToClipboard(t.installCmds[activeTab])" 
            class="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors rounded-md hover:bg-gray-100 dark:hover:bg-[#222] flex-shrink-0 ml-2"
            :title="t.copy"
          >
            <svg v-if="copiedText === t.installCmds[activeTab]" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
          </button>
        </div>
      </div>
    </section>

    <!-- Title Section before Grid -->
    <section class="max-w-6xl mx-auto px-4 py-12 sm:px-6 lg:px-8">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 pb-10">
        <h2 class="text-2xl md:text-3xl font-bold tracking-tight max-w-lg leading-tight">
          {{ t.powerTitle }}
        </h2>
        <p class="text-gray-500 dark:text-gray-400 max-w-md text-md">
          {{ t.powerDesc }}
        </p>
      </div>
    </section>

    <!-- Features Grid Layout (2x2) -->
    <section class="max-w-6xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div 
          v-for="section in t.sections" 
          :key="section.id"
          class="flex flex-col bg-white dark:bg-[#111] border border-gray-200 dark:border-[#222] rounded-2xl overflow-hidden hover:border-gray-300 dark:hover:border-[#444] transition-colors"
        >
          <!-- Text Content -->
          <div class="p-8 pb-6">
            <h3 class="text-2xl font-bold tracking-tight mb-3">
              {{ section.title }}
            </h3>
            <p class="text-gray-500 dark:text-gray-400 leading-relaxed min-h-[3rem]">
              {{ section.desc }}
            </p>
          </div>
          
          <!-- Terminal Window inside card -->
          <div class="px-6 pb-6 mt-auto">
            <div class="rounded-xl overflow-hidden bg-[#fafafa] dark:bg-black border border-gray-200 dark:border-[#222]">
              <!-- Mac Window Header -->
              <div class="flex items-center px-4 py-3 bg-white dark:bg-[#0a0a0a] border-b border-gray-200 dark:border-[#222]">
                <div class="flex gap-2">
                  <div class="w-3 h-3 rounded-full bg-[#ff5f56]"></div>
                  <div class="w-3 h-3 rounded-full bg-[#ffbd2e]"></div>
                  <div class="w-3 h-3 rounded-full bg-[#27c93f]"></div>
                </div>
                <div class="mx-auto text-xs font-medium text-gray-400">terminal</div>
              </div>
              <!-- Terminal Content -->
              <div class="p-5 font-mono text-[13px] leading-loose overflow-x-auto whitespace-pre" v-html="section.terminal">
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Agent Ready Section -->
    <section class="max-w-4xl mx-auto px-4 py-24 sm:px-6 lg:px-8 text-center flex flex-col items-center">
      <h2 class="text-4xl font-bold tracking-tight mb-6">
        {{ t.readyTitle }}
      </h2>
      <p class="text-lg text-gray-500 dark:text-gray-400 max-w-2xl mx-auto leading-relaxed mb-10">
        {{ t.readyDesc }}
      </p>
      <button 
        @click="copyInstruction"
        class="inline-flex items-center gap-2 px-6 py-3 bg-gray-100 dark:bg-[#1a1a1a] hover:bg-gray-200 dark:hover:bg-[#2a2a2a] text-gray-900 dark:text-white rounded-full font-medium transition-colors border border-gray-200 dark:border-[#333]"
      >
      <!--     ? 'Please install trailsnap-cli and skill : https://trailsnap.cn/install.md'
    : '帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md' -->
        <svg v-if="copiedText === '帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md' || copiedText === 'Please install trailsnap-cli and skill : https://trailsnap.cn/install.md'" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        <!-- <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg> -->
        {{ t.copyInstruction }}
      </button>

      <!-- Decorative Glitch Text -->
      <div class="mt-20 relative w-full h-32 flex items-center justify-center opacity-80 select-none pointer-events-none">
        <div class="absolute inset-0 bg-gradient-to-b from-transparent to-[#fafafa] dark:to-black z-10"></div>
        <h2 class="text-6xl md:text-8xl font-black tracking-widest text-transparent bg-clip-text bg-gradient-to-b from-gray-300 to-gray-100 dark:from-gray-700 dark:to-gray-900" style="filter: blur(2px);">
          TRAILSNAP CLI
        </h2>
        <h2 class="absolute text-6xl md:text-8xl font-black tracking-widest text-gray-200 dark:text-gray-800 mix-blend-overlay">
          TRAILSNAP CLI
        </h2>
      </div>
    </section>

    <!-- Bottom CTA -->
    <section class="max-w-4xl mx-auto px-4 py-16 sm:px-6 lg:px-8 text-center flex flex-col items-center">
      <div class="w-16 h-16 bg-primary text-white rounded-2xl flex items-center justify-center mb-8 shadow-lg shadow-primary/20">
        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
      </div>
      <h2 class="text-3xl md:text-4xl font-bold tracking-tight mb-4">
        {{ t.getStartedTitle }}
      </h2>
      <p class="text-gray-500 dark:text-gray-400 mb-10 max-w-lg">
        {{ t.getStartedDesc }}
      </p>

      <div class="flex flex-col sm:flex-row items-center gap-4">
        <div class="flex items-center bg-white dark:bg-[#111] rounded-lg border border-gray-200 dark:border-[#333] shadow-sm">
          <div class="px-4 py-2.5 text-sm font-mono text-gray-800 dark:text-gray-200">
            <span class="text-primary mr-2">$</span> npm i -g trailsnap-cli
          </div>
          <button 
            @click="copyToClipboard('npm i -g trailsnap-cli')" 
            class="p-2.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 border-l border-gray-200 dark:border-[#333] transition-colors"
            :title="t.copy"
          >
            <svg v-if="copiedText === 'npm i -g trailsnap-cli'" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
          </button>
        </div>
        
        <a href="https://www.npmjs.com/package/trailsnap-cli" target="_blank" class="inline-flex items-center gap-2 px-5 py-2.5 bg-white dark:bg-[#111] hover:bg-gray-50 dark:hover:bg-[#1a1a1a] text-gray-900 dark:text-white rounded-lg text-sm font-medium transition-colors border border-gray-200 dark:border-[#333] shadow-sm">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
          {{ t.cliReference }}
        </a>
      </div>
    </section>
    
  </div>
</template>

<style scoped>
.cli-page {
  /* Prevent horizontal scroll from terminal overflow */
  overflow-x: hidden;
}
</style>