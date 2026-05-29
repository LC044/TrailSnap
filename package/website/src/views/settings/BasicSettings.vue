<template>
  <div>
    <!-- Header with Actions -->
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">系统设置</h1>
      <div class="flex gap-2">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".json"
          @change="handleImportFile"
        >
          <el-button>导入配置</el-button>
        </el-upload>
        <el-button @click="handleExport">导出配置</el-button>
      </div>
    </div>
    <!-- Map Settings -->
    <el-collapse v-model="activeNames" class="mb-8 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700 overflow-hidden">
      <el-collapse-item name="map">
        <template #title>
           <h2 class="text-lg font-semibold dark:text-white px-6">地图设置</h2>
        </template>
        <div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
        <el-form-item label="地图提供商">
          <el-select v-model="mapForm.provider" placeholder="选择地图提供商" class="w-full sm:w-auto">
             <el-option label="天地图 (Tianditu)" value="tianditu" />
             <el-option label="高德地图 (Amap)" value="amap" disabled />
             <el-option label="百度地图 (Baidu)" value="baidu" disabled />
          </el-select>
          <span class="text-sm text-gray-500 ml-2">目前仅支持天地图，其他地图开发中</span>
        </el-form-item>
        
        <el-form-item label="API Keys">
           <el-input v-model="mapApiKeysText" type="textarea" :rows="3" placeholder="请输入 API Key (每行一个)" />
           <p class="text-xs text-gray-500 mt-1">
             <span v-if="mapForm.provider === 'tianditu'"><a href="http://trailsnap.cn/docs/guide/settings/mapsetting.html" target="_blank" class="text-blue-500 hover:underline">获取API Key</a> (支持设置多个Key，每行一个，系统将随机选择使用)</span>
           </p>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="saveMapSettings">保存地图配置</el-button>
        </el-form-item>
      </el-form>

      <div class="mt-6 pt-6 border-t border-gray-100 dark:border-gray-700">
        <h3 class="text-md font-semibold mb-3 dark:text-white">离线地图数据</h3>
        <p class="text-sm text-gray-500 mb-4">下载或上传城市数据以支持离线解析照片拍摄位置。（下载越多解析的时候占用内存越大，请根据实际情况选择下载）<a href="http://trailsnap.cn/docs/guide/settings/mapsetting.html#_4-离线地图数据-offline-map-data" target="_blank" class="text-blue-500 hover:underline">查看详细说明</a></p>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
             <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">下载国家数据</h4>
             <div class="flex gap-2">
               <el-select v-model="selectedCountry" placeholder="选择国家" filterable class="flex-1">
                 <el-option v-for="c in countries" :key="c.code" :label="c.name" :value="c.code">
                    <span class="float-left">{{ c.name }}</span>
                    <span class="float-right text-gray-400 text-xs">{{ c.code }}</span>
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
        
        <div class="mt-6">
           <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">已下载数据</h4>
           <div class="bg-gray-50 dark:bg-gray-900 rounded border dark:border-gray-700 overflow-hidden">
             <div v-if="downloadedCountries.length === 0" class="p-4 text-center text-gray-500 text-sm">暂无数据</div>
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
                   <td class="px-4 py-2 text-gray-600 dark:text-gray-400">{{ item.code }}</td>
                   <td class="px-4 py-2 text-gray-500 font-mono text-xs flex items-center justify-end gap-2">
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
      </el-collapse-item>
    </el-collapse>

    <!-- AI Settings -->
    <el-collapse v-model="activeNames" class="mb-8 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700 overflow-hidden">
      <el-collapse-item name="ai">
        <template #title>
           <h2 class="text-lg font-semibold dark:text-white px-6">AI 相关设置</h2>
        </template>
        <div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
        <el-form-item label="AI API 地址（人脸识别、OCR等AI微服务地址）">
          <el-input v-model="aiForm.ai_api_url" placeholder="http://localhost:8001" />
        </el-form-item>

        <el-collapse v-model="aiActiveNames" class="my-4 border-none">
          <!-- LLM Connections -->
          <el-collapse-item name="connections">
            <template #title>
              <div class="flex items-center w-full">
                <span class="text-sm font-medium text-gray-600 dark:text-gray-300 mr-2">大模型连接配置 (LLM Connections)</span>
                <el-tooltip content="配置大模型 API 连接，用于智能分析、对话等任务" placement="top">
                  <Info class="w-4 h-4 text-gray-400 cursor-help" />
                </el-tooltip>
              </div>
            </template>
            <div class="bg-blue-50 dark:bg-gray-700 p-3 rounded mb-3 text-xs text-blue-600 dark:text-blue-300">
              添加多个大模型提供商连接，配置后可为不同任务分配不同模型。
            </div>
            
            <div v-for="(conn, index) in aiForm.connections" :key="conn.id" class="border border-gray-200 dark:border-gray-600 rounded-md p-4 mb-4 relative bg-gray-50 dark:bg-gray-800 flex justify-between items-center">
              <div class="flex-1 overflow-hidden mr-4">
                <div class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1 truncate" :title="conn.api_base">
                  <span v-if="conn.id === 'builtin'" class="bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 text-xs px-2 py-0.5 rounded mr-2">内置</span>
                  {{ conn.provider !== 'OpenAI' && conn.provider ? conn.provider + ' - ' : '' }}URL: {{ conn.api_base || '未设置' }}
                </div>
                <div class="text-xs text-gray-500 flex items-center">
                  API Key: 
                  <span class="ml-2 font-mono bg-gray-200 dark:bg-gray-700 px-1 py-0.5 rounded cursor-pointer" @click="toggleKeyVisibility(index)">
                    {{ visibleKeys.has(index) ? (conn.api_key || '未设置') : '••••••••••••••••' }}
                  </span>
                </div>
              </div>
              <div class="flex items-center gap-3 shrink-0">
                <el-switch v-model="conn.enable" />
                <el-button type="primary" size="small" plain @click="editConnection(index)">编辑</el-button>
              </div>
            </div>
            
            <el-button type="primary" plain @click="addConnection" class="w-full mt-2">
              + 添加连接
            </el-button>
          </el-collapse-item>

          <!-- Analysis LLM Config -->
          <el-collapse-item name="analysis">
            <template #title>
              <div class="flex items-center w-full">
                <span class="text-sm font-medium text-gray-600 dark:text-gray-300 mr-2">大模型智能分析配置</span>
                <el-tooltip content="选择用于图片内容理解、标签生成、智能总结等核心分析任务的模型" placement="top">
                  <Info class="w-4 h-4 text-gray-400 cursor-help" />
                </el-tooltip>
              </div>
            </template>
            <p class="bg-red-50 dark:bg-gray-700 p-3 rounded mb-3 text-xs text-red-600 dark:text-red-300">
              用于图片内容理解、标签生成、评分等核心任务，请确保选定的模型支持视觉能力。
            </p>
            <el-form-item label="分析连接及模型">
              <div class="flex flex-col sm:flex-row gap-4 w-full">
                <el-select v-model="aiForm.analysis_connection_id" placeholder="选择连接" class="flex-1" @change="onAnalysisConnectionChange">
                  <el-option
                    v-for="conn in aiForm.connections.filter(c => c.enable)"
                    :key="conn.id"
                    :label="conn.api_base || '未命名连接'"
                    :value="conn.id"
                  />
                </el-select>
                <el-select
                  v-model="aiForm.analysis_model_name"
                  placeholder="选择模型"
                  class="flex-1"
                  :disabled="!aiForm.analysis_connection_id"
                  filterable
                  allow-create
                  @focus="fetchModelsFromApi(aiForm.analysis_connection_id)"
                  :loading="fetchingModels[aiForm.analysis_connection_id]"
                >
                  <el-option
                    v-for="m in getAvailableModels(aiForm.analysis_connection_id)"
                    :key="m"
                    :label="m"
                    :value="m"
                  />
                </el-select>
              </div>
              <div v-if="!aiForm.analysis_model_name && aiForm.analysis_connection_id" class="text-red-500 text-xs mt-1">必须指定模型名称</div>
            </el-form-item>
            
            <el-form-item label="图片分析提示词">
                <el-input v-model="aiForm.visual_evaluation_prompt" type="textarea" :rows="4" placeholder="用于生成评分和描述的提示词" />
            </el-form-item>
          </el-collapse-item>

          <!-- Chat LLM Config -->
          <el-collapse-item name="chat">
            <template #title>
              <div class="flex items-center w-full">
                <span class="text-sm font-medium text-gray-600 dark:text-gray-300 mr-2">AI 对话默认配置</span>
                <el-tooltip content="设置智能助手对话时默认使用的连接和模型" placement="top">
                  <Info class="w-4 h-4 text-gray-400 cursor-help" />
                </el-tooltip>
              </div>
            </template>
            <p class="bg-blue-50 dark:bg-gray-700 p-3 rounded mb-3 text-xs text-blue-600 dark:text-blue-300">
              用于设置智能助手对话时默认加载的模型。您依然可以在对话界面中临时切换。
            </p>
            <el-form-item label="默认对话连接及模型">
              <div class="flex flex-col sm:flex-row gap-4 w-full">
                <el-select v-model="aiForm.chat_connection_id" placeholder="选择连接" class="flex-1" @change="onChatConnectionChange">
                  <el-option
                    v-for="conn in aiForm.connections.filter(c => c.enable)"
                    :key="conn.id"
                    :label="conn.api_base || '未命名连接'"
                    :value="conn.id"
                  />
                </el-select>
                <el-select
                  v-model="aiForm.chat_model_name"
                  placeholder="选择模型"
                  class="flex-1"
                  :disabled="!aiForm.chat_connection_id"
                  filterable
                  allow-create
                  @focus="fetchModelsFromApi(aiForm.chat_connection_id)"
                  :loading="fetchingModels[aiForm.chat_connection_id]"
                >
                  <el-option
                    v-for="m in getAvailableModels(aiForm.chat_connection_id)"
                    :key="m"
                    :label="m"
                    :value="m"
                  />
                </el-select>
              </div>
              <div v-if="!aiForm.chat_model_name && aiForm.chat_connection_id" class="text-red-500 text-xs mt-1">建议指定模型名称</div>
            </el-form-item>
          </el-collapse-item>

          <!-- Face Recognition -->
          <el-collapse-item name="face">
            <template #title>
              <span class="text-sm font-medium text-gray-600 dark:text-gray-300">人脸识别配置</span>
            </template>
            <el-form-item label="识别阈值">
              <div class="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 w-full">
                <el-slider v-model="aiForm.face_recognition_threshold" :min="0" :max="1" :step="0.05" class="w-full sm:w-64" show-input />
                <span class="text-sm text-gray-500">判定为人脸的最低置信度 (默认 0.7)</span>
              </div>
            </el-form-item>
            <el-form-item label="聚类阈值">
              <div class="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 w-full">
                <el-slider v-model="aiForm.face_cluster_threshold" :min="0" :max="1" :step="0.05" class="w-full sm:w-64" show-input />
                <span class="text-sm text-gray-500">判定为同一人的距离阈值 (默认 0.4，越小越严格)</span>
              </div>
            </el-form-item>
            <el-form-item label="最少照片数">
              <el-input-number v-model="aiForm.face_recognition_min_photos" :min="1" />
              <span class="text-sm text-gray-500 ml-2">形成人物聚类所需的最少照片数量 (默认 5)</span>
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
        
        <el-form-item>
          <el-button type="primary" @click="saveAISettings">保存 AI 配置</el-button>
        </el-form-item>
          </el-form>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- Image Settings -->
    <el-collapse v-model="activeNames" class="mb-8 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700 overflow-hidden">
      <el-collapse-item name="image">
        <template #title>
           <h2 class="text-lg font-semibold dark:text-white px-6">图片设置</h2>
        </template>
        <div class="px-6 pb-6">
          <div class="text-sm text-gray-500 mt-1 w-full">修改图片配置后将在下次新增照片时生效，如果要修改已有图片质量请在任务管理中执行缩略图生成任务</div>
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="缩略图大小">
              <el-select v-model="imageForm.thumbnail_size" placeholder="选择缩略图大小" class="w-full sm:w-auto min-w-[120px]">
                <el-option label="250px" :value="250" />
                <el-option label="480px" :value="480" />
                <el-option label="720px" :value="720" />
                <el-option label="1080px" :value="1080" />
              </el-select>
              <span class="text-sm text-gray-500 ml-0 sm:ml-2 block sm:inline mt-1 sm:mt-0">默认 250px</span>
            </el-form-item>

            <el-form-item label="缩略图质量">
              <el-slider v-model="imageForm.thumbnail_quality" :min="1" :max="100" show-input class="w-full sm:w-64" />
            </el-form-item>

            <el-form-item label="预览图大小">
              <el-select v-model="imageForm.preview_size" placeholder="选择预览图大小" class="w-full sm:w-auto min-w-[120px]">
                <el-option label="720px" :value="720" />
                <el-option label="1080px" :value="1080" />
                <el-option label="1440px" :value="1440" />
                <el-option label="2160px" :value="2160" />
              </el-select>
              <span class="text-sm text-gray-500 ml-0 sm:ml-2 block sm:inline mt-1 sm:mt-0">默认 1440px</span>
            </el-form-item>

            <el-form-item label="预览图质量">
              <el-slider v-model="imageForm.preview_quality" :min="1" :max="100" show-input class="w-full sm:w-64" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveImageSettings">保存图片配置</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- Scheduled Scan Settings -->
    <el-collapse v-model="activeNames" class="mb-8 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700 overflow-hidden">
      <el-collapse-item name="scan_schedule">
        <template #title>
           <h2 class="text-lg font-semibold dark:text-white px-6">定时扫描设置</h2>
        </template>
        <div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="扫描模式">
              <el-radio-group v-model="scanScheduleForm.mode">
                <el-radio value="off">关闭</el-radio>
                <el-radio value="interval">间隔循环</el-radio>
                <el-radio value="weekly">每周定时</el-radio>
              </el-radio-group>
            </el-form-item>
            
            <el-form-item v-if="scanScheduleForm.mode === 'interval'" label="间隔时间 (分钟)">
              <el-select v-model="scanScheduleForm.interval" placeholder="选择间隔时间" class="w-full sm:w-auto" style="min-width: 120px;">
                <el-option label="5分钟" :value="5" />
                <el-option label="10分钟" :value="10" />
                <el-option label="15分钟" :value="15" />
                <el-option label="30分钟" :value="30" />
                <el-option label="60分钟" :value="60" />
              </el-select>
              <div class="text-sm text-gray-500 mt-1 w-full">适合频繁上传，机械硬盘唤醒较频繁</div>
            </el-form-item>

            <template v-if="scanScheduleForm.mode === 'weekly'">
              <el-form-item label="执行日期">
                <el-checkbox-group v-model="scanScheduleForm.weekdays">
                  <el-checkbox :value="0">周一</el-checkbox>
                  <el-checkbox :value="1">周二</el-checkbox>
                  <el-checkbox :value="2">周三</el-checkbox>
                  <el-checkbox :value="3">周四</el-checkbox>
                  <el-checkbox :value="4">周五</el-checkbox>
                  <el-checkbox :value="5">周六</el-checkbox>
                  <el-checkbox :value="6">周日</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
              <el-form-item label="执行时间">
                <el-time-select
                  v-model="scanScheduleForm.time"
                  start="00:00"
                  step="00:30"
                  end="23:30"
                  placeholder="选择时间"
                />
                <div class="text-sm text-gray-500 mt-1 w-full">NAS推荐凌晨02:00~04:00执行，全选等价每天执行</div>
              </el-form-item>
            </template>

            <el-form-item>
              <el-button type="primary" @click="saveScanScheduleSettings">保存扫描设置</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- Recycle Bin Settings -->
    <el-collapse v-model="activeNames" class="mb-8 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700 overflow-hidden">
      <el-collapse-item name="recycle_bin">
        <template #title>
           <h2 class="text-lg font-semibold dark:text-white px-6">回收站设置</h2>
        </template>
        <div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="保留天数">
              <el-input-number v-model="recycleBinForm.retention_days" :min="1" :max="365" class="w-full sm:w-auto" />
              <div class="text-sm text-gray-500 mt-1 w-full">照片在回收站中保留的天数，超过该天数将被永久删除。</div>
            </el-form-item>
            <el-form-item label="自动清理时间">
              <el-time-select
                v-model="recycleBinForm.cleanup_time"
                start="00:00"
                step="00:30"
                end="23:30"
                placeholder="选择时间"
              />
              <div class="text-sm text-gray-500 mt-1 w-full">每天执行自动清理过期照片的时间。</div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveRecycleBinSettings">保存回收站设置</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- Index Maintenance -->
    <el-collapse v-model="activeNames" class="mb-8 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700 overflow-hidden">
      <el-collapse-item name="index">
        <template #title>
           <h2 class="text-lg font-semibold dark:text-white px-6">索引维护</h2>
        </template>
        <div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
        <el-form-item label="重建索引">
          <el-button type="danger" @click="rebuildIndex" :disabled="indexStatus.running">立即重建索引</el-button>
          <div class="mt-4 w-full" v-if="indexStatus.running || indexStatus.progress > 0">
            <div class="flex justify-between text-sm mb-1">
              <span>进度: {{ Math.round(indexStatus.progress*100) }}%</span>
              <span v-if="indexStatus.running" class="text-blue-600 animate-pulse">正在扫描... {{ indexStatus.message }}</span>
            </div>
            <div v-if="indexStatus.current_task" class="text-xs text-gray-500 mb-1">当前任务: {{ indexStatus.current_task }}</div>
            <el-progress :percentage="Math.round(indexStatus.progress*100)" :status="indexStatus.running ? undefined : 'success'" :stroke-width="15" />
            <div class="grid grid-cols-3 gap-4 mt-2 text-sm text-center bg-gray-50 p-2 rounded">
              <div class="text-green-600">新增: {{ indexStatus.added }}</div>
              <div class="text-red-600">删除: {{ indexStatus.deleted }}</div>
              <div class="text-orange-600">错误: {{ indexStatus.errors }}</div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="索引日志">
           <div class="w-full bg-gray-900 text-gray-100 p-4 rounded h-64 overflow-y-auto font-mono text-xs">
              <div v-for="(log, i) in logs" :key="i" class="mb-1">
                 <span class="text-gray-500">[{{ new Date(log.created_at).toLocaleTimeString() }}]</span>
                 <span :class="{'text-green-400': log.action==='added', 'text-red-400': log.action==='deleted'}"> {{ log.action.toUpperCase() }} </span>
                 <span class="text-gray-300">{{ log.file_path }}</span>
              </div>
              <div v-if="logs.length===0" class="text-gray-600 italic">暂无日志</div>
           </div>
        </el-form-item>
          </el-form>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- Appearance Settings -->
    <el-collapse v-model="activeNames" class="mb-8 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700 overflow-hidden">
      <el-collapse-item name="appearance">
        <template #title>
           <h2 class="text-lg font-semibold dark:text-white px-6">外观设置</h2>
        </template>
        <div class="px-6 pb-6">
          <div class="space-y-6 max-w-3xl">

        <div>
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">显示模式</h3>
          <div class="flex bg-gray-100 dark:bg-gray-700 p-1 rounded-lg w-full sm:w-96">
            <button
              @click="setMode('light')"
              :class="['flex-1 flex items-center justify-center py-2 rounded-md text-sm font-medium transition-all', currentMode === 'light' ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 dark:text-gray-400 dark:bg-gray-800 dark:text-white']"
            >
              <Sun class="w-4 h-4 mr-2" /> 浅色
            </button>
            <button
              @click="setMode('auto')"
              :class="['flex-1 flex items-center justify-center py-2 rounded-md text-sm font-medium transition-all', currentMode === 'auto' ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 dark:text-gray-400 dark:bg-gray-800 dark:text-white']"
            >
              <Palette class="w-4 h-4 mr-2" /> 自动
            </button>
            <button
              @click="setMode('dark')"
              :class="['flex-1 flex items-center justify-center py-2 rounded-md text-sm font-medium transition-all', currentMode === 'dark' ? 'bg-gray-600 shadow-sm text-white' : 'text-gray-500 dark:text-gray-400 dark:bg-gray-800 dark:text-white']"
            >
              <Moon class="w-4 h-4 mr-2" /> 深色
            </button>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">主题颜色</h3>
          <div class="flex flex-wrap gap-4">
            <button
              v-for="color in themeColors"
              :key="color.name"
              @click="setTheme(color)"
              class="w-10 h-10 rounded-full border-2 transition-transform hover:scale-110 flex items-center justify-center relative"
              :style="{ backgroundColor: color.primary, borderColor: currentTheme.name === color.name ? 'var(--text-color)' : 'transparent' }"
              :title="color.label"
            >
              <Check v-if="currentTheme.name === color.name" class="w-5 h-5 text-white drop-shadow-md" />
            </button>
          </div>
        </div>

          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- Edit Connection Dialog -->
    <el-dialog v-model="editDialogVisible" title="编辑大模型连接" width="500px">
      <el-form label-position="top" v-if="editingConnection">
        <el-form-item label="API 提供商">
          <el-select v-model="editingConnection.provider" placeholder="选择提供商" class="w-full" :disabled="editingConnection.id === 'builtin'">
             <el-option label="内置AI (Built-in AI)" value="Built-in AI" v-if="editingConnection.id === 'builtin'" />
             <el-option label="OpenAI" value="OpenAI" />
             <el-option label="Ollama" value="Ollama" disabled />
             <el-option label="Google" value="Google" disabled />
             <el-option label="Amazon" value="Amazon" disabled />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="editingConnection.api_base" placeholder="https://api.openai.com/v1" :disabled="editingConnection.id === 'builtin'" />
          <div v-if="editingConnection.id === 'builtin'" class="text-xs text-gray-500 mt-1">内置连接的地址会自动与上方的“AI API 地址”保持同步</div>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="editingConnection.api_key" type="password" show-password placeholder="sk-..." :disabled="editingConnection.id === 'builtin'" />
        </el-form-item>
        <el-form-item label="可用模型 (可选)">
          <el-select
            v-model="editingConnection.model_names"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入模型名称后按回车，不填则可以使用该连接的所有模型"
            class="w-full"
          >
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="flex justify-between items-center w-full">
          <div class="flex gap-2">
            <el-button type="danger" plain @click="deleteEditingConnection" :disabled="editingConnection.id === 'builtin'">删除</el-button>
            <el-button type="success" plain @click="verifyEditingConnection" :loading="verifying">验证</el-button>
          </div>
          <div>
            <el-button @click="editDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="saveEditingConnection">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
import { settingsApi } from '@/api/settings'
import { ElMessage, ElMessageBox } from 'element-plus'
import { injectTheme } from '@/composables/useTheme.js'
import { Sun, Moon, Palette, Check, Info, Download, Loader2, Trash2 } from 'lucide-vue-next'

const {
  currentMode,
  currentTheme,
  themeColors,
  setMode,
  setTheme
} = injectTheme();

const activeNames = ref([])
const aiActiveNames = ref([])

const storageForm = ref({ 
  photo_storage_path: '',
  external_directories: [] as string[]
})

const mapForm = ref({
  provider: 'tianditu',
  api_keys: [] as string[]
})

const mapApiKeysText = computed({
  get: () => mapForm.value.api_keys.join('\n'),
  set: (val) => {
    mapForm.value.api_keys = val.split('\n').map(k => k.trim()).filter(k => k)
  }
})

const aiForm = ref({
  ai_api_url: 'http://localhost:8001',
  face_recognition_threshold: 0.6,
  face_cluster_threshold: 0.4,
  face_recognition_min_photos: 5,
  visual_evaluation_prompt: '',
  visual_narrative_prompt: '',
  connections: [] as Array<{
    id: string;
    provider: string;
    api_base: string;
    api_key: string;
    model_names: string[];
    enable: boolean;
  }>,
  analysis_connection_id: '',
  analysis_model_name: '',
  chat_connection_id: '',
  chat_model_name: ''
})

const addConnection = () => {
  const newConn = {
    id: `conn_${Date.now()}`,
    provider: 'OpenAI',
    api_base: '',
    api_key: '',
    model_names: [],
    enable: true
  }
  aiForm.value.connections.push(newConn)
  editConnection(aiForm.value.connections.length - 1)
}

const removeConnection = (index: number) => {
  aiForm.value.connections.splice(index, 1)
  if (aiForm.value.analysis_connection_id && !aiForm.value.connections.find(c => c.id === aiForm.value.analysis_connection_id)) {
    aiForm.value.analysis_connection_id = ''
    aiForm.value.analysis_model_name = ''
  }
}

const visibleKeys = ref(new Set<number>())
const toggleKeyVisibility = (index: number) => {
  const newSet = new Set(visibleKeys.value)
  if (newSet.has(index)) {
    newSet.delete(index)
  } else {
    newSet.add(index)
  }
  visibleKeys.value = newSet
}

const editDialogVisible = ref(false)
const editingConnectionIndex = ref(-1)
const editingConnection = ref<any>(null)
const verifying = ref(false)

const editConnection = (index: number) => {
  editingConnectionIndex.value = index
  editingConnection.value = JSON.parse(JSON.stringify(aiForm.value.connections[index]))
  editDialogVisible.value = true
}

const deleteEditingConnection = () => {
  if (editingConnectionIndex.value >= 0) {
    removeConnection(editingConnectionIndex.value)
    editDialogVisible.value = false
  }
}

const saveEditingConnection = () => {
  if (editingConnectionIndex.value >= 0) {
    aiForm.value.connections[editingConnectionIndex.value] = editingConnection.value
    editDialogVisible.value = false
    // Clear the cached models so it re-fetches if they changed settings
    delete fetchedModels.value[editingConnection.value.id]
    if (editingConnection.value.model_names && editingConnection.value.model_names.length > 0) {
      fetchedModels.value[editingConnection.value.id] = editingConnection.value.model_names
    } else {
      if (aiForm.value.analysis_connection_id === editingConnection.value.id) {
        fetchModelsFromApi()
      }
    }
  }
  saveAISettings();
}

const verifyEditingConnection = async () => {
  if (!editingConnection.value.api_base) {
    ElMessage.warning('请先填写 Base URL')
    return
  }
  verifying.value = true
  try {
    const res = await settingsApi.verifyConnection(editingConnection.value.api_base, editingConnection.value.api_key || '')
    if (res && res.success) {
      ElMessage.success(`连接成功！发现 ${res.models.length} 个可用模型`)
    } else {
      ElMessage.error(`验证失败: ${res?.message || '未知错误'}`)
    }
  } catch (e: any) {
    ElMessage.error(`验证失败: ${e.message || '网络错误'}`)
  } finally {
    verifying.value = false
  }
}

const onAnalysisConnectionChange = async () => {
  aiForm.value.analysis_model_name = ''
  const connId = aiForm.value.analysis_connection_id
  if (!connId) return
  delete fetchedModels.value[connId]
  fetchModelsFromApi(connId)
}

const onChatConnectionChange = async () => {
  aiForm.value.chat_model_name = ''
  const connId = aiForm.value.chat_connection_id
  if (!connId) return
  delete fetchedModels.value[connId]
  fetchModelsFromApi(connId)
}

const fetchedModels = ref<Record<string, string[]>>({})
const fetchingModels = ref<Record<string, boolean>>({})

const fetchModelsFromApi = async (connId?: string) => {
  if (!connId) return
  
  const conn = aiForm.value.connections.find(c => c.id === connId)
  if (conn && conn.model_names && conn.model_names.length > 0) {
    fetchedModels.value[connId] = conn.model_names
    return
  }
  
  if (fetchedModels.value[connId]) return // already fetched

  if (conn && conn.api_base) {
    fetchingModels.value[connId] = true
    try {
      const res = await settingsApi.verifyConnection(conn.api_base, conn.api_key || '')
      if (res && res.success && res.models) {
        fetchedModels.value[connId] = res.models
      }
    } catch (e) {
      console.error('Failed to fetch models for initial connection', e)
    } finally {
      fetchingModels.value[connId] = false
    }
  }
}

const getAvailableModels = (connId: string) => {
  const conn = aiForm.value.connections.find(c => c.id === connId)
  if (conn && conn.model_names && conn.model_names.length > 0) {
    return conn.model_names
  }
  return fetchedModels.value[connId] || []
}

const imageForm = ref({
  thumbnail_quality: 80,
  preview_quality: 85,
  preview_size: 1440,
  thumbnail_size: 250
})

const scanScheduleForm = ref({
  mode: 'off',
  interval: 15,
  weekdays: [0, 1, 2, 3, 4, 5, 6],
  time: '02:00'
})

const recycleBinForm = ref({
  retention_days: 7,
  cleanup_time: '00:00'
})

const saveScanScheduleSettings = async () => {
  if (scanScheduleForm.value.mode === 'weekly' && scanScheduleForm.value.weekdays.length === 0) {
    ElMessage.warning('请至少选择一天执行日期')
    return
  }
  try {
    await settingsApi.updateSystemConfig({ scan_schedule: scanScheduleForm.value })
    ElMessage.success('定时扫描设置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

const saveRecycleBinSettings = async () => {
  if (!recycleBinForm.value.cleanup_time) {
    ElMessage.warning('请选择自动清理时间')
    return
  }
  try {
    await settingsApi.updateSystemConfig({ recycle_bin: recycleBinForm.value })
    ElMessage.success('回收站设置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

const pathValid = ref<boolean | null>(null)
const indexStatus = ref({ running: false, progress: 0, added: 0, deleted: 0, errors: 0, message: '', current_task: '' })
const logs = ref<any[]>([])
let pollTimer: number | null = null

// Map Data Logic
const countries = ref<any[]>([])
const downloadedCountries = ref<any[]>([])
const selectedCountry = ref('')
const downloading = ref(false)
const downloadingFiles = ref(new Set<string>())

const loadMapDataInfo = async () => {
  try {
    const [cData, dData] = await Promise.all([
      settingsApi.getMapCountries(),
      settingsApi.getDownloadedMapData()
    ])
    countries.value = cData
    downloadedCountries.value = dData
  } catch (e) {
    console.error('Failed to load map data info', e)
  }
}

const downloadCountry = async () => {
  if (!selectedCountry.value) return
  downloading.value = true
  try {
    await settingsApi.downloadMapData(selectedCountry.value)
    ElMessage.success('已开始后台下载，请稍候刷新查看')
    // We might want to poll or just reload after a delay?
    // Since it's background, immediate reload might not show it.
    // Just tell user it started.
    selectedCountry.value = ''
    setTimeout(loadMapDataInfo, 2000)
  } catch (e) {
    ElMessage.error('下载请求失败')
  } finally {
    downloading.value = false
  }
}

const handleUploadMapData = async (options: any) => {
  const { file } = options
  try {
    await settingsApi.uploadMapData(file)
    ElMessage.success('上传成功')
    await loadMapDataInfo()
  } catch (e: any) {
    const msg = e.response?.data?.detail || '上传失败'
    ElMessage.error(msg)
  }
}

const downloadFile = async (filename: string) => {
  if (downloadingFiles.value.has(filename)) return
  downloadingFiles.value.add(filename)
  ElMessage.info(`开始下载文件: ${filename}`)

  try {
    const blob = await settingsApi.downloadMapFile(filename)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success(`文件 ${filename} 下载完成`)
  } catch (e) {
    ElMessage.error(`文件 ${filename} 下载失败`)
  } finally {
    downloadingFiles.value.delete(filename)
  }
}

const deleteFile = async (filename: string) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除已下载的数据文件 "${filename}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    
    await settingsApi.deleteMapData(filename)
    ElMessage.success('删除成功')
    await loadMapDataInfo()
  } catch (e) {
    if (e !== 'cancel') {
       ElMessage.error('删除失败')
    }
  }
}

const pathStatusText = computed(() => {
  if (pathValid.value === null) return ''
  return pathValid.value ? '路径有效' : '路径无效或不可写'
})

const pathStatusClass = computed(() => {
  if (pathValid.value === null) return ''
  return pathValid.value ? 'text-green-600' : 'text-red-600'
})

const loadData = async () => {
  try {
    const settings = await settingsApi.getSettings()
    if (settings) {
      // Map nested settings to forms
      if (settings.storage) {
          storageForm.value = { ...settings.storage }
      }
      if (settings.map) {
          const mapData = settings.map
          if (mapData.api_keys) {
             mapForm.value = { ...mapData }
          } else if (mapData.api_key) {
             mapForm.value = { 
                 provider: mapData.provider, 
                 api_keys: [mapData.api_key] 
             }
          } else {
             mapForm.value = { ...mapData, api_keys: [] }
          }
      }
      if (settings.ai) {
          aiForm.value = { 
            ...aiForm.value,
            ...settings.ai,
            connections: settings.ai.connections || [],
            analysis_connection_id: settings.ai.analysis_connection_id || '',
            analysis_model_name: settings.ai.analysis_model_name || '',
            chat_connection_id: settings.ai.chat_connection_id || '',
            chat_model_name: settings.ai.chat_model_name || '',
            visual_evaluation_prompt: settings.ai.visual_evaluation_prompt || '',
            visual_narrative_prompt: settings.ai.visual_narrative_prompt || ''
          }
      }
      if (settings.image) {
          imageForm.value = { ...settings.image }
      }

      try {
        const sysConfig = await settingsApi.getSystemConfig()
        if (sysConfig.scan_schedule) {
            scanScheduleForm.value = { ...sysConfig.scan_schedule }
        }
        if (sysConfig.recycle_bin) {
            recycleBinForm.value = { ...sysConfig.recycle_bin }
        }
      } catch (err) {
        console.error('Failed to load system config', err)
      }

      if (storageForm.value.photo_storage_path) {
          // Verify path silently on load? Or just assume valid if saved.
          // Let's verify to show status
          validatePath(true)
      }
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('加载配置失败')
  }
}

const saveAISettings = async () => {
  try {
    await settingsApi.updateSettings({ ai: aiForm.value })
    ElMessage.success('AI 配置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

const saveMapSettings = async () => {
  try {
    await settingsApi.updateSettings({ map: mapForm.value })
    ElMessage.success('地图配置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

const saveImageSettings = async () => {
  try {
    await settingsApi.updateSettings({ image: imageForm.value })
    ElMessage.success('图片配置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

const validatePath = async (silent = false) => {
  if (!storageForm.value.photo_storage_path) return
  try {
    // Only update storage path if we are validating explicitly
    if (!silent) {
        await settingsApi.updateSettings({ 
            storage: { 
                ...storageForm.value,
                photo_storage_path: storageForm.value.photo_storage_path 
            } 
        })
    }
    // We assume backend validates on save, but we can also use updateStorageRoot logic if we want specific validation endpoint
    // But since we unified config, let's trust updateSettings for now or call specific validation if needed.
    // However, the original code called updateStorageRoot which did validation.
    // Let's assume updateSettings saves it.
    
    // To strictly validate, we might want to check if the path exists on server.
    // For now, let's assume success if no error.
    pathValid.value = true
    if (!silent) ElMessage.success('存储配置已保存')
  } catch {
    pathValid.value = false
    if (!silent) ElMessage.error('路径无效或保存失败')
  }
}

const handleExport = async () => {
  try {
    const data = await settingsApi.exportSettings()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `trailsnap-config-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('配置导出成功')
  } catch (e) {
    ElMessage.error('导出失败')
    console.error(e)
  }
}

const handleImportFile = async (file: any) => {
  const reader = new FileReader()
  reader.onload = async (e) => {
    try {
      const config = JSON.parse(e.target?.result as string)
      await settingsApi.importSettings(config)
      ElMessage.success('配置导入成功')
      await loadData() // Reload current page data
    } catch (err) {
      ElMessage.error('配置导入失败：格式错误或网络异常')
      console.error(err)
    }
  }
  reader.readAsText(file.raw)
}

const rebuildIndex = async () => {
  try {
    await settingsApi.rebuildIndex()
    ElMessage.success('索引重建任务已启动')
    pollStatus()
  } catch {
    ElMessage.error('启动失败')
  }
}

const fetchStatus = async () => {
  try {
      indexStatus.value = await settingsApi.getIndexStatus()
  } catch (e) {}
}

const pollStatus = async () => {
  await fetchStatus()
  await fetchLogs()
  if (indexStatus.value.running) {
    pollTimer = window.setTimeout(pollStatus, 2000)
  }
}

const fetchLogs = async () => {
  try {
      logs.value = await settingsApi.getIndexLogs(50)
  } catch (e) {}
}

onMounted(() => {
  loadData()
  loadMapDataInfo()
  pollStatus()
})

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>
