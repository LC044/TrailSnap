<template>
  <div class="max-w-3xl space-y-8">
    <div>
      <h2 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white mb-2">问题反馈</h2>
      <p class="text-gray-500 dark:text-gray-400">遇到问题或有功能建议？欢迎通过以下方式反馈</p>
    </div>

    <!-- GitHub Issues -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-100 dark:border-gray-700 p-6">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 rounded-lg bg-gray-900 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
          <i class="mgc_github_2_line text-xl text-white"></i>
        </div>
        <div>
          <h3 class="font-semibold text-gray-800 dark:text-white">GitHub Issues</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400">提交 Bug 报告或功能建议</p>
        </div>
      </div>

      <div class="space-y-3 mb-5">
        <a
          href="https://github.com/LC044/TrailSnap/issues/new?template=bug_report.yml"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600 hover:border-primary-500 dark:hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-gray-700 transition-colors group"
        >
          <div class="w-8 h-8 rounded-md bg-red-100 dark:bg-red-900/30 flex items-center justify-center flex-shrink-0">
            <Bug class="w-4 h-4 text-red-600 dark:text-red-400" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400">报告 Bug</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 truncate">发现异常行为？提交 Bug 报告帮助我们改进</div>
          </div>
          <ExternalLink class="w-4 h-4 text-gray-400 group-hover:text-primary-500 flex-shrink-0" />
        </a>

        <a
          href="https://github.com/LC044/TrailSnap/issues/new?template=feature_request.yml"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600 hover:border-primary-500 dark:hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-gray-700 transition-colors group"
        >
          <div class="w-8 h-8 rounded-md bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
            <Lightbulb class="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400">功能建议</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 truncate">有想要的新功能？告诉我们你的想法</div>
          </div>
          <ExternalLink class="w-4 h-4 text-gray-400 group-hover:text-primary-500 flex-shrink-0" />
        </a>

        <a
          href="https://github.com/LC044/TrailSnap/issues"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600 hover:border-primary-500 dark:hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-gray-700 transition-colors group"
        >
          <div class="w-8 h-8 rounded-md bg-green-100 dark:bg-green-900/30 flex items-center justify-center flex-shrink-0">
            <ListChecks class="w-4 h-4 text-green-600 dark:text-green-400" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400">查看已有 Issues</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 truncate">浏览已知问题和正在开发的功能</div>
          </div>
          <ExternalLink class="w-4 h-4 text-gray-400 group-hover:text-primary-500 flex-shrink-0" />
        </a>
      </div>

      <div class="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
        <AlertCircle class="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
        <p class="text-xs text-amber-700 dark:text-amber-300">提交 Issue 前请先搜索已有 Issues，避免重复提交。描述问题时请尽量详细，包括复现步骤和环境信息。</p>
      </div>
    </div>

    <!-- Community -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-100 dark:border-gray-700 p-6">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 rounded-lg bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center flex-shrink-0">
          <MessageCircle class="w-5 h-5 text-primary-600 dark:text-primary-400" />
        </div>
        <div>
          <h3 class="font-semibold text-gray-800 dark:text-white">交流社群</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400">加入社群与其他用户交流</p>
        </div>
      </div>

      <div class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600">
        <div class="w-8 h-8 rounded-md bg-sky-100 dark:bg-sky-900/30 flex items-center justify-center flex-shrink-0">
          <i class="mgc_qq_line text-sky-600 dark:text-sky-400 text-sm"></i>
        </div>
        <div>
          <div class="text-sm font-medium text-gray-800 dark:text-white">QQ 群</div>
          <div class="text-xs text-gray-500 dark:text-gray-400">1078946004</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bug, Lightbulb, ExternalLink, ListChecks, AlertCircle, MessageCircle } from 'lucide-vue-next'
</script>
