<template>
<SettingsSection v-model="activeNames" name="map" title="地图设置">
<div class="px-4 sm:px-6 pb-6">
          <div class="max-w-3xl rounded-xl border border-gray-200 bg-gray-50 p-4 sm:p-5 dark:border-gray-700 dark:bg-gray-900">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div class="flex min-w-0 items-start gap-3">
                <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-500/10 text-primary-600 dark:text-primary-500">
                  <KeyRound class="h-5 w-5" />
                </div>
                <div>
                  <h3 class="font-medium text-gray-900 dark:text-white">天地图服务端 API</h3>
                  <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">配置一个或多个服务端 Key，网页、桌面端和手机 App 均通过 TrailSnap Server 使用，真实 Key 不会进入地图资源 URL。保存前会自动验证每个 Key。</p>
                </div>
              </div>
              <el-select v-model="mapForm.provider" aria-label="地图提供商" class="w-full sm:w-48" @change="resetMapKeyTests">
                <el-option label="天地图 (Tianditu)" value="tianditu" />
                <el-option label="高德地图 (开发中)" value="amap" disabled />
                <el-option label="百度地图 (开发中)" value="baidu" disabled />
              </el-select>
            </div>

            <div class="mt-4 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
              <AlertCircle class="mt-0.5 h-5 w-5 shrink-0" />
              <div class="text-sm leading-6">
                <p class="font-medium">旧版本升级用户需要更换 Key</p>
                <p class="mt-1">旧版本使用的是浏览器端 Key，升级后不会自动转换。请前往天地图控制台创建“服务端”Key，在此替换原 Key；如启用 IP 白名单，请填写 TrailSnap Server 的公网出口 IP。</p>
              </div>
            </div>

            <div class="mt-5 space-y-3">
              <div
                v-for="(_, index) in mapForm.api_keys"
                :key="index"
                class="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-800"
              >
                <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <el-input
                    v-model="mapForm.api_keys[index]"
                    class="min-w-0 flex-1"
                    type="password"
                    show-password
                    clearable
                    :placeholder="`API Key ${index + 1}`"
                    :aria-label="`地图 API Key ${index + 1}`"
                    @input="resetMapKeyTest(index)"
                  />
                  <div class="flex gap-2">
                    <el-button class="flex-1 sm:flex-none" :loading="mapKeyTests[index]?.status === 'testing'" @click="testMapKey(index)">测试</el-button>
                    <el-button
                      circle
                      plain
                      aria-label="删除 API Key"
                      :disabled="mapForm.api_keys.length === 1"
                      @click="removeMapKey(index)"
                    >
                      <Trash2 class="h-4 w-4" />
                    </el-button>
                  </div>
                </div>
                <div v-if="mapKeyTests[index]?.status !== 'idle'" class="mt-2 flex items-center gap-1.5 text-xs">
                  <Loader2 v-if="mapKeyTests[index]?.status === 'testing'" class="h-3.5 w-3.5 animate-spin text-primary-500" />
                  <CheckCircle2 v-else-if="mapKeyTests[index]?.status === 'valid'" class="h-3.5 w-3.5 text-green-500" />
                  <XCircle v-else class="h-3.5 w-3.5 text-red-500" />
                  <span :class="mapKeyTests[index]?.status === 'valid' ? 'text-green-600 dark:text-green-400' : mapKeyTests[index]?.status === 'invalid' ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'">
                    {{ mapKeyTests[index]?.message }}
                  </span>
                </div>
              </div>
            </div>

            <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                class="inline-flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700 dark:text-primary-500 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                @click="addMapKey"
              >
                <Plus class="h-4 w-4" /> 添加 Key
              </button>
              <a
                v-if="mapForm.provider === 'tianditu'"
                href="http://trailsnap.cn/docs/guide/settings/mapsetting.html"
                target="_blank"
                rel="noopener noreferrer"
                class="text-sm text-primary-600 hover:text-primary-700 hover:underline dark:text-primary-500 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              >获取与配置 API Key</a>
            </div>

            <div class="mt-5 flex flex-col-reverse gap-2 border-t border-gray-200 pt-4 dark:border-gray-700 sm:flex-row sm:justify-end">
              <el-button :loading="testingAllMapKeys" @click="testAllMapKeys">测试全部</el-button>
              <el-button type="primary" :loading="savingMapSettings" @click="saveMapSettings">验证并保存</el-button>
            </div>
          </div>

      <div class="mt-6 pt-6 border-t border-gray-100 dark:border-gray-700">
        <h3 class="text-md font-semibold mb-3 dark:text-white">离线地图数据</h3>
        <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">下载或上传城市数据以支持离线解析照片拍摄位置。（下载越多解析的时候占用内存越大，请根据实际情况选择下载）<a href="http://trailsnap.cn/docs/guide/settings/mapsetting.html#_4-离线地图数据-offline-map-data" target="_blank" class="text-blue-500 hover:underline">查看详细说明</a></p>
        <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">修改后需要到任务管理里重新执行元数据提取任务</p>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
             <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">下载国家数据</h4>
             <div class="flex gap-2">
               <el-select v-model="selectedCountry" placeholder="选择国家" filterable class="flex-1">
                 <el-option v-for="c in countries" :key="c.code" :label="c.name" :value="c.code">
                    <span class="float-left">{{ c.name }}</span>
                    <span class="float-right text-gray-400 dark:text-gray-500 text-xs">{{ c.code }}</span>
                 </el-option>
               </el-select>
               <el-button type="primary" @click="downloadCountry" :loading="downloading">下载</el-button>
             </div>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">上传自定义数据</h4>
             <el-upload
                :auto-upload="true"
                :show-file-list="false"
                accept=".csv"
                :http-request="handleUploadMapData"
              >
                <el-button>点击上传 CSV 文件</el-button>
                <template #tip>
                  <div class="el-upload__tip">
                    格式要求: longitude,latitude,country,admin_1,admin_2,admin_3,admin_4
                  </div>
                </template>
              </el-upload>
          </div>
        </div>

        <!-- 下载进度提示：模拟进度推进，完成时以真实列表命中收尾 -->
        <div v-if="downloadPhase !== 'idle'" class="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-100 dark:border-gray-700">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-700 dark:text-gray-300 flex items-center gap-2">
              <Loader2 v-if="downloadPhase === 'downloading'" class="w-4 h-4 animate-spin text-primary-500" />
              <CheckCircle2 v-else-if="downloadPhase === 'done'" class="w-4 h-4 text-green-500" />
              <AlertCircle v-else class="w-4 h-4" :class="downloadPhase === 'timeout' ? 'text-amber-500' : 'text-red-500'" />
              {{ downloadStatusText }}
            </span>
            <span class="text-xs text-gray-500 dark:text-gray-400 font-mono">{{ Math.round(downloadProgress) }}%</span>
          </div>
          <el-progress
            :percentage="Math.round(downloadProgress)"
            :status="downloadProgressStatus"
            :stroke-width="12"
            :show-text="false"
            striped
            :striped-flow="downloadPhase === 'downloading'"
          />
          <div class="text-xs text-gray-500 dark:text-gray-400 mt-2">{{ downloadHint }}</div>
        </div>

        <div class="mt-6">
           <div class="flex items-center justify-between mb-2">
             <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300">已下载数据</h4>
             <el-button size="small" @click="handleRefreshMapData" :loading="refreshingMapData" plain>
               <RefreshCw class="w-4 h-4 mr-1" /> 刷新
             </el-button>
           </div>
           <div class="bg-gray-50 dark:bg-gray-900 rounded border dark:border-gray-700 overflow-hidden">
             <div v-if="downloadedCountries.length === 0" class="p-4 text-center text-gray-500 dark:text-gray-400 text-sm">暂无数据</div>
             <table v-else class="min-w-full text-sm">
               <thead class="bg-gray-100 dark:bg-gray-800">
                 <tr>
                   <th class="px-4 py-2 text-left font-medium text-gray-600 dark:text-gray-300">国家/地区</th>
                   <th class="px-4 py-2 text-left font-medium text-gray-600 dark:text-gray-300">代码</th>
                   <th class="px-4 py-2 text-left font-medium text-gray-600 dark:text-gray-300">文件名</th>
                 </tr>
               </thead>
               <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
                 <tr v-for="item in downloadedCountries" :key="item.filename">
                   <td class="px-4 py-2 text-gray-800 dark:text-gray-200">{{ item.name }}</td>
                   <td class="px-4 py-2 text-gray-600 dark:text-gray-300 dark:text-gray-400">{{ item.code }}</td>
                   <td class="px-4 py-2 text-gray-500 dark:text-gray-400 font-mono text-xs flex items-center justify-end gap-2">
                      <span class="mr-auto">{{ item.filename }}</span>
                      <button
                        @click="downloadFile(item.filename)"
                        class="text-blue-500 hover:text-blue-700 p-1 disabled:opacity-50 disabled:cursor-not-allowed"
                        :title="downloadingFiles.has(item.filename) ? '下载中...' : '下载到本地'"
                        :disabled="downloadingFiles.has(item.filename)"
                      >
                        <Loader2 v-if="downloadingFiles.has(item.filename)" class="w-4 h-4 animate-spin" />
                        <Download v-else class="w-4 h-4" />
                      </button>
                      <button
                        @click="deleteFile(item.filename)"
                        class="text-red-500 hover:text-red-700 p-1 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="删除文件"
                        :disabled="downloadingFiles.has(item.filename)"
                      >
                        <Trash2 class="w-4 h-4" />
                      </button>
                   </td>
                 </tr>
               </tbody>
             </table>
           </div>
        </div>
      </div>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
import { CheckCircle2, AlertCircle, Download, Loader2, Trash2, RefreshCw, KeyRound, Plus, XCircle } from 'lucide-vue-next'
const { activeNames, addMapKey, countries, deleteFile, downloadCountry, downloadFile, downloadHint, downloadPhase, downloadProgress, downloadProgressStatus, downloadStatusText, downloadedCountries, downloading, downloadingFiles, handleRefreshMapData, handleUploadMapData, mapForm, mapKeyTests, refreshingMapData, removeMapKey, resetMapKeyTest, resetMapKeyTests, saveMapSettings, savingMapSettings, selectedCountry, testAllMapKeys, testMapKey, testingAllMapKeys } = useBasicSettingsContext()
</script>
