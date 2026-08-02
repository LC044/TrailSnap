<!-- src/views/AboutPage.vue -->
<template>
  <div class="about-page max-w-4xl mx-auto space-y-12">
    <!-- 项目介绍 -->
    <section class="space-y-4">
      <h1 class="text-4xl font-bold text-slate-800 dark:text-slate-100">关于行影集 (TrailSnap)</h1>
      <p class="text-lg text-slate-600 dark:text-slate-300">
        TrailSnap 是一个智能化的 AI 相册应用，致力于帮助用户轻松记录、整理和回顾自己的出行经历。通过强大的 AI 处理能力，让每一张照片和每一段旅程都成为值得珍藏的记忆。
      </p>
    </section>

    <!-- 项目背景与愿景 -->
    <section class="space-y-4">
      <h2 class="text-2xl font-bold text-slate-800 dark:text-slate-100">项目背景</h2>
      <p class="text-slate-600 dark:text-slate-300">
        我相信未来每个人（至少每个家庭）都有一个属于自己的 AI 数据中心，而相册是数据中心的一个重要数据来源，它留存了你生活中的很多瞬间，而 AI 相册则是将这些瞬间转化为有价值的记忆，它可以帮你默默地记录下相册里的车票、景点门票，可以帮你记录旅行中的所见所闻，可以帮你自动整理出可以发朋友圈的照片（甚至帮你准备好文案），可以帮你剪一段15s的短视频······。
      </p>
      <p class="text-slate-600 dark:text-slate-300">
        所以，我给这个项目命名为<strong>《行影集》</strong>，在这里你的数据才 “真正属于你”。
      </p>
    </section>

    <!-- 主要功能 -->
    <section class="space-y-4">
      <h2 class="text-2xl font-bold text-slate-800 dark:text-slate-100">主要功能</h2>
      <ul class="space-y-2 text-slate-600 dark:text-slate-300">
        <li class="flex items-start gap-2">
          <span class="text-primary-500 mt-1">•</span>
          <span>智能相册：自动分类、标签和搜索照片</span>
        </li>
        <li class="flex items-start gap-2">
          <span class="text-primary-500 mt-1">•</span>
          <span>AI能力：一句话生成游记、Vlog智能剪辑（待实现）</span>
        </li>
        <li class="flex items-start gap-2">
          <span class="text-primary-500 mt-1">•</span>
          <span>行程票据：自动识别和分类行程中的票据</span>
        </li>
        <li class="flex items-start gap-2">
          <span class="text-primary-500 mt-1">•</span>
          <span>数据可视化：足迹地图、旅行统计图表、城市打卡点</span>
        </li>
      </ul>
    </section>

    <!-- 版本信息 -->
    <section class="space-y-4">
      <h2 class="text-2xl font-bold text-slate-800 dark:text-slate-100">版本信息</h2>
      <div class="flex items-center gap-4 text-slate-600 dark:text-slate-300">
        <span class="font-semibold">当前版本：</span>
        <span>v{{ currentVersion }}</span>
        <el-button type="primary" size="small" :loading="checking" @click="checkUpdate">
          检查更新
        </el-button>
      </div>
    </section>

    <!-- 服务器 -->
    <section class="space-y-4">
      <h2 class="text-2xl font-bold text-slate-800 dark:text-slate-100">服务器</h2>
      <p class="break-all text-slate-600 dark:text-slate-300">{{ serverUrl || '浏览器同源模式' }}</p>
      <router-link
        to="/server-settings"
        class="inline-flex rounded-lg bg-primary-600 hover:bg-primary-700 px-4 py-2 text-white focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        更改服务器
      </router-link>
    </section>

    <!-- 联系方式 -->
    <section class="space-y-4">
      <h2 class="text-2xl font-bold text-slate-800 dark:text-slate-100">联系方式</h2>
      <div class="flex flex-col gap-3">
        <div class="flex items-center gap-4 text-slate-600 dark:text-slate-300">
          <span class="font-semibold">邮箱：</span>
          <a href="mailto:sixyuan044@gmail.com" class="text-primary-600 hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300 transition-colors">
            sixyuan044@gmail.com
          </a>
        </div>
        <div class="flex items-center gap-4 text-slate-600 dark:text-slate-300">
          <span class="font-semibold">QQ群：</span>
          <span>1078946004</span>
        </div>
      </div>
    </section>

    <!-- 官网 -->
     <section class="space-y-4">
      <h2 class="text-2xl font-bold text-slate-800 dark:text-slate-100">官网</h2>
      <div class="flex items-center gap-4 text-slate-600 dark:text-slate-300">
        <span class="font-semibold">TrailSnap 官网：</span>
        <a href="https://trailsnap.cn/" target="_blank" rel="noopener noreferrer" class="text-primary-600 hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300 transition-colors flex items-center gap-2">
          <span>trailsnap.cn</span>
        </a>
      </div>
    </section>

    <!-- 开源地址 -->
    <section class="space-y-4">
      <h2 class="text-2xl font-bold text-slate-800 dark:text-slate-100">开源地址</h2>
      <div class="flex items-center gap-4 text-slate-600 dark:text-slate-300">
        <span class="font-semibold">GitHub：</span>
        <a href="https://github.com/LC044/TrailSnap" target="_blank" rel="noopener noreferrer" class="text-primary-600 hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300 transition-colors flex items-center gap-2">
          <i class="mgc_github_2_line text-2xl"></i>
          <span>github.com/LC044/TrailSnap</span>
        </a>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { systemApi } from '@/api/system'
import { getServerUrl } from '@/config/server'

const currentVersion = ref('0.0.0') // Default placeholder
const checking = ref(false)
const serverUrl = getServerUrl()

onMounted(async () => {
  try {
    const res = await systemApi.getVersion()
    currentVersion.value = res.version
    checkUpdate()
  } catch (e) {
    console.error('Failed to fetch version', e)
  }
})

const checkUpdate = async () => {
  checking.value = true
  try {
    const data = await systemApi.checkUpdate()
    
    // Update current version in case it changed or was not loaded
    if (data.current_version) {
      currentVersion.value = data.current_version
    }

    if (data.has_update) {
       ElMessageBox.confirm(
        `
        <div class="text-left">
          <p class="font-bold mb-2">发现新版本: ${data.latest_version}</p>
          <div class="mb-2 font-semibold">更新内容：</div>
          <pre class="whitespace-pre-wrap text-sm bg-gray-50 dark:bg-gray-800 p-2 rounded text-slate-600 dark:text-slate-300 font-sans">${data.update_info || '无详细信息'}</pre>
        </div>
        `,
        '检查更新',
        {
          dangerouslyUseHTMLString: true,
          confirmButtonText: '前往下载',
          cancelButtonText: '暂不更新',
          type: 'info',
          center: true
        }
       ).then(() => {
          if (data.download_url) {
            window.open(data.download_url, '_blank')
          } else {
            window.open('https://trailsnap.cn', '_blank')
          }
       }).catch(() => {})
    } else {
      ElMessage.success('当前已是最新版本')
    }
  } catch (error) {
    ElMessage.error('检查更新失败，请稍后重试')
    console.error(error)
  } finally {
    checking.value = false
  }
}
</script>

<style scoped>
.about-page {
  padding-top: 2rem;
  padding-bottom: 4rem;
}
</style>
