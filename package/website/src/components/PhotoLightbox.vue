<template>
  <Transition name="fade">
    <div v-if="visible" class="fixed inset-0 z-[100] flex bg-black/95 backdrop-blur-sm" @click="close" tabindex="0">

      <!-- Top Toolbar (Mobile Adapted) — hidden in edit mode -->
      <Transition name="viewer-controls">
      <div v-if="!isEditing && controlsVisible" data-testid="photo-lightbox-toolbar" class="fixed top-0 left-0 right-0 z-[102] p-2 flex items-center justify-between bg-gradient-to-b from-black/80 to-transparent pointer-events-none">
         <button
            @click.stop="close"
            class="pointer-events-auto w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0"
            title="关闭 (Esc)"
        >
            <X class="w-6 h-6" />
        </button>

        <div class="flex items-center gap-1 pointer-events-auto p-0">
            <!-- Zoom Controls -->
            <button @click.stop="zoomOut" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" title="缩小 (-)">
                <ZoomOut class="w-6 h-6" />
            </button>
            <button @click.stop="zoomIn" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" title="放大 (+)">
                <ZoomIn class="w-6 h-6" />
            </button>

            <!-- Actions -->
            <button @click.stop="downloadImage" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" title="下载图片 (D)">
                <Download class="w-6 h-6" />
            </button>
             <button v-if="allowEdit && image && image.file_type === 'image'" @click.stop="enterEditMode" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" title="编辑图片 (E)">
                <Pencil class="w-6 h-6" />
            </button>
             <button v-if="allowDelete" @click.stop="handleDelete" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors text-red-400 hover:text-red-300 bg-transparent p-0" title="删除图片 (Del)">
                <Trash2 class="w-6 h-6" />
            </button>
            <button @click.stop="toggleOriginal" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" :class="{ 'text-primary-400': showOriginal }" title="查看原图 (Shift+O)">
                <Focus class="w-6 h-6" />
            </button>
            <button @click.stop="toggleSidebar" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" :class="{ 'bg-white/20 text-white': showSidebar }" title="查看元数据 (I)">
                <Info class="w-6 h-6" />
            </button>

            <div @click.stop @mousedown.stop class="flex items-center">
                <el-dropdown trigger="click" @command="handleCommand">
                    <button
                        class="w-12 h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                        :class="{ 'bg-white/20 text-white': showOCR }"
                        aria-label="更多"
                        title="更多"
                    >
                        <MoreHorizontal class="w-6 h-6" />
                    </button>
                    <template #dropdown>
                        <el-dropdown-menu class="w-36">
                            <el-dropdown-item command="ocr">
                                <div class="flex items-center gap-2">
                                    <ScanText class="w-4 h-4" />
                                    <span>{{ showOCR ? '关闭识别' : '文字识别 (O)' }}</span>
                                </div>
                            </el-dropdown-item>
                            <div class="px-1" @click.stop>
                                <el-popover
                                    v-model:visible="processingMenuVisible"
                                    placement="left-start"
                                    trigger="click"
                                    :width="220"
                                    :disabled="!canProcessCurrentPhoto"
                                >
                                    <template #reference>
                                        <button
                                            type="button"
                                            data-testid="photo-processing-menu"
                                            class="w-full min-h-8 px-3 py-1.5 flex items-center gap-2 rounded text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                                            :disabled="!canProcessCurrentPhoto"
                                            title="为当前照片单独执行任务"
                                        >
                                            <WandSparkles class="w-4 h-4" />
                                            <span class="flex-1 text-left">重新识别</span>
                                            <ChevronLeft class="w-4 h-4" />
                                        </button>
                                    </template>

                                    <div class="space-y-1" data-testid="photo-processing-operations">
                                        <div class="px-2 pb-1 text-xs text-gray-500 dark:text-gray-400">选择要重新执行的任务</div>
                                        <button
                                            v-for="item in photoProcessingOperations"
                                            :key="item.operation"
                                            type="button"
                                            class="w-full min-h-9 px-2 py-1.5 flex items-center gap-2 rounded text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:cursor-wait disabled:opacity-60 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                                            :disabled="isPhotoProcessingActive(item.operation)"
                                            @click.stop="startPhotoProcessing(item.operation)"
                                        >
                                            <component :is="item.icon" class="w-4 h-4 shrink-0" />
                                            <span class="flex-1 text-left">{{ item.label }}</span>
                                            <LoaderCircle
                                                v-if="isPhotoProcessingActive(item.operation)"
                                                class="w-4 h-4 animate-spin text-primary-500"
                                            />
                                            <span
                                                v-else-if="photoProcessingStatusLabel(item.operation)"
                                                class="text-xs"
                                                :class="photoProcessingStatusClass(item.operation)"
                                            >
                                                {{ photoProcessingStatusLabel(item.operation) }}
                                            </span>
                                        </button>
                                    </div>
                                </el-popover>
                            </div>
                            <el-dropdown-item v-if="allowAddToAlbum" command="addToAlbum">
                                <div class="flex items-center gap-2">
                                    <ImagePlus class="w-4 h-4" />
                                    <span>添加到相册 (A)</span>
                                </div>
                            </el-dropdown-item>
                            <el-dropdown-item v-if="allowAddToPerson" command="addToPerson">
                                <div class="flex items-center gap-2">
                                    <UserPlus class="w-4 h-4" />
                                    <span>添加到人物 (P)</span>
                                </div>
                            </el-dropdown-item>
                            <el-dropdown-item v-if="allowMoveToFolder" command="moveToFolder">
                                <div class="flex items-center gap-2">
                                    <FolderOutput class="w-4 h-4" />
                                    <span>移动到目录 (F)</span>
                                </div>
                            </el-dropdown-item>
                            <el-dropdown-item v-if="allowEdit" command="adjustLocation">
                                <div class="flex items-center gap-2">
                                    <MapPin class="w-4 h-4" />
                                    <span>调整位置 (L)</span>
                                </div>
                            </el-dropdown-item>
                            <el-dropdown-item command="viewDescription">
                                <div class="flex items-center gap-2">
                                    <FileText class="w-4 h-4" />
                                    <span>查看AI分析结果</span>
                                </div>
                            </el-dropdown-item>
                        </el-dropdown-menu>
                    </template>
                </el-dropdown>
            </div>
        </div>
      </div>
      </Transition>

      <!-- Feature pages can add compact contextual information without forking the lightbox. -->
      <slot name="context-overlay"></slot>

      <!-- Photo Editor (replaces viewer when editing) -->
      <PhotoEditor
        v-if="isEditing && image"
        :image-url="image.url"
        :image-width="image.width"
        :image-height="image.height"
        @save="handleEditorSave"
        @cancel="exitEditMode"
      />

      <!-- Main Image Area (hidden when editing) -->
      <div v-else class="flex-1 relative flex items-center justify-center h-full overflow-hidden group">

        <!-- Navigation -->
        <button
            v-if="hasPrev && controlsVisible"
            @click.stop="prev"
            class="absolute left-4 z-[101] hidden md:flex w-12 h-12 items-center justify-center rounded-full hover:bg-black/40 text-white/90 transition-all p-0 bg-transparent"
        >
            <ChevronLeft class="w-8 h-8" />
        </button>
        <button
            v-if="hasNext && controlsVisible"
            @click.stop="next"
            class="absolute right-4 z-[101] hidden md:flex w-12 h-12 items-center justify-center rounded-full hover:bg-black/40 text-white/90 transition-all p-0 bg-transparent"
        >
            <ChevronRight class="w-8 h-8" />
        </button>


        <div
          ref="mediaViewport"
          data-testid="photo-lightbox-media"
          class="relative w-full h-full flex items-center justify-center overflow-hidden touch-none"
          @click.stop="handleMediaTap"
          @wheel.prevent="handleWheel"
          @touchstart="startTouch"
        >
          <div
            data-testid="photo-lightbox-track"
            class="flex h-full shrink-0 will-change-transform"
            style="width: 300%"
            :style="swipeTrackStyle"
          >
            <div class="h-full flex items-center justify-center" style="width: 33.333333%">
              <img
                v-if="previousImage"
                :src="adjacentPreviewSrc(previousImage)"
                class="block w-full h-full object-contain pointer-events-none select-none"
                draggable="false"
                alt=""
              />
            </div>

            <div class="relative h-full flex items-center justify-center overflow-hidden" style="width: 33.333333%">
              <div
                v-if="image && (!image.file_type || image.file_type === 'image' || image.file_type === 'live_photo')"
                class="relative w-full h-full transition-transform duration-200 ease-out origin-center select-none flex items-center justify-center"
                :style="{ transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)` }"
                @mousedown="startDrag"
              >
                <!-- Image Wrapper for Correct Overlay Positioning -->
                <div class="relative flex justify-center items-center h-full">
                    <img
                        ref="imageRef"
                        data-testid="photo-lightbox-current-image"
                        :src="displayImageSrc"
                        class="block w-full h-full object-contain pointer-events-none"
                        draggable="false"
                    />
                    
                    <!-- Face Highlight Overlay -->
                    <div 
                        v-if="highlightedFace && faceBoxStyle"
                        class="absolute border-2 border-yellow-400 z-20 shadow-[0_0_10px_rgba(255,215,0,0.5)] pointer-events-none"
                        :style="faceBoxStyle"
                    >
                         <div class="absolute -top-8 left-0 bg-black/70 backdrop-blur-sm text-white text-xs px-2 py-1 rounded whitespace-nowrap flex items-center gap-1">
                            <span class="font-bold">{{ highlightedFaceName }}</span>
                            <span v-if="highlightedFaceConfidence" class="text-yellow-400">
                                {{ highlightedFaceConfidence }}% {{ highlightedFaceRecognitionConfidence }}%
                            </span>
                        </div>
                    </div>

                    <!-- OCR Overlay -->
                    <div v-if="showOCR && ocrRecords.length > 0" class="absolute inset-0 z-10">
                        <svg viewBox="0 0 1 1" class="w-full h-full pointer-events-none" preserveAspectRatio="none">
                            <polygon
                                v-for="rec in ocrRecords"
                                :key="rec.id"
                                :points="getPolygonPoints(rec.polygon)"
                                class="fill-transparent stroke-primary-500 stroke-[0.002] cursor-pointer pointer-events-auto hover:fill-primary-500/20 hover:stroke-[0.004] transition-all"
                                :class="{ 'fill-primary-500/30 stroke-[0.004]': highlightedOCR?.id === rec.id }"
                                @click.stop="onPolygonClick(rec)"
                            />
                        </svg>
                    </div>

                    <!-- Live Photo Video Overlay -->
                    <video
                        v-if="isPlayingLive"
                        ref="liveVideoRef"
                        :key="image.id"
                        class="absolute inset-0 w-full h-full object-contain z-10 pointer-events-none"
                        :style="videoStyle"
                        autoplay
                        playsinline
                        x5-playsinline
                        webkit-playsinline
                        :loop="false"
                        @ended="onLiveEnded"
                        @loadedmetadata="onVideoLoaded"
                    >
                        <source :src="image.live_photo_video_url" type="video/mp4" />
                    </video>
                </div>
              </div>

              <div
                v-else-if="image && image.file_type === 'video'"
                class="relative w-full h-full flex items-center justify-center bg-black"
              >
                <div ref="videoPlayer" class="w-full h-full"></div>
              </div>
            </div>

            <div class="h-full flex items-center justify-center" style="width: 33.333333%">
              <img
                v-if="nextImage"
                :src="adjacentPreviewSrc(nextImage)"
                class="block w-full h-full object-contain pointer-events-none select-none"
                draggable="false"
                alt=""
              />
            </div>
          </div>

          <div
            v-if="image && image.file_type === 'live_photo' && controlsVisible"
            class="absolute top-16 left-4 md:top-24 md:left-8 z-[101] cursor-pointer"
            @click.stop="toggleLivePlayback"
          >
            <div class="flex items-center gap-1 bg-gray-900/60 backdrop-blur-md rounded-full px-2 py-1 text-white/90 hover:bg-gray-800/80 transition-colors">
              <span class="icon-[tabler--live-photo] w-4 h-4 text-white drop-shadow-md opacity-90" :class="{ 'animate-spin': isPlayingLive }"></span>
              <span class="text-xs font-medium">LIVE</span>
                </div>
            </div>
        </div>
      </div>

      <Transition name="viewer-thumbnails">
        <div
          v-if="!isEditing && controlsVisible && thumbnailWindow.length > 0"
          data-testid="photo-lightbox-thumbnails"
          class="fixed inset-x-0 bottom-0 z-[102] flex justify-center px-3 pt-8 pb-[calc(0.75rem+env(safe-area-inset-bottom))] bg-gradient-to-t from-black/85 via-black/55 to-transparent pointer-events-none"
          @click.stop
        >
          <div ref="thumbnailStrip" class="flex max-w-full items-center gap-2 overflow-x-auto px-1 py-1 pointer-events-auto scrollbar-hide">
            <button
              v-for="entry in thumbnailWindow"
              :key="entry.item.id"
              type="button"
              :data-photo-index="entry.index"
              class="h-12 w-12 sm:h-14 sm:w-14 shrink-0 overflow-hidden rounded-md border-2 bg-black/30 transition-all focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              :class="entry.index === resolvedCurrentIndex ? 'border-primary-500 scale-105 shadow-lg shadow-primary-500/30' : 'border-white/30 opacity-70 hover:opacity-100'"
              :aria-label="`查看第 ${entry.index + 1} 张照片`"
              @click.stop="navigateToIndex(entry.index)"
            >
              <img :src="entry.item.thumbnail || entry.item.preview || entry.item.url" class="h-full w-full object-cover" alt="" />
            </button>
          </div>
        </div>
      </Transition>

      <!-- Sidebar (Metadata) — hidden in edit mode -->
      <PhotoMetadataSidebar
        v-if="!isEditing"
        :visible="showSidebar"
        :image="image"
        :metadata="metadata"
        :loading="loading"
        :allow-edit="allowEdit"
        :allow-delete="allowDelete"
        :force-open-location-edit="forceOpenLocationEdit"
        @close="showSidebar = false"
        @update="handleSidebarUpdate"
        @delete="handleDelete"
        @highlight-face="handleHighlightFace"
      />

      <!-- OCR Panel (Separate) — hidden in edit mode -->
      <PhotoOCRPanel
        v-if="!isEditing"
        :visible="showOCR"
        :loading="ocrLoading"
        :records="ocrRecords"
        :highlighted-record="highlightedOCR"
        @close="showOCR = false"
        @click-record="onOCRRecordClick"
      />

      <!-- First-launch shortcut hint toast -->
      <!-- <Transition name="fade">
        <div
          v-if="!isEditing && showShortcutHint"
          class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[103] bg-gray-900/80 dark:bg-gray-100/90 text-white dark:text-gray-900 rounded-lg px-4 py-2 text-sm backdrop-blur-sm pointer-events-none select-none"
        >
          <span class="text-primary-500 font-medium">←/→</span> 切换 ·
          <span class="text-primary-500 font-medium">+/-</span> 缩放 ·
          <span class="text-primary-500 font-medium">I</span> 信息 ·
          <span class="text-primary-500 font-medium">D</span> 下载 ·
          <span class="text-primary-500 font-medium">Del</span> 删除 ·
          <span class="text-primary-500 font-medium">?</span> 查看全部
        </div>
      </Transition> -->

      <!-- Shortcut help panel -->
      <el-dialog
        v-model="showShortcutHelp"
        :show-close="false"
        align-center
        class="shortcut-help-dialog"
        append-to-body
        width="auto"
        @opened="shortcutHelpOpened = true"
        @closed="shortcutHelpOpened = false"
      >
        <template #header>
          <div class="text-lg font-semibold text-gray-900 dark:text-gray-100">键盘快捷键</div>
        </template>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-x-8 gap-y-4 text-sm">
          <!-- Navigation -->
          <div>
            <h4 class="text-gray-500 dark:text-gray-400 font-medium mb-2 text-xs uppercase tracking-wider">导航</h4>
            <div class="space-y-1.5">
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">上一张 / 下一张</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">←</kbd><span class="text-gray-400 dark:text-gray-500">/</span><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">→</kbd></div></div>
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">下一张</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">Space</kbd></div></div>
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">关闭灯箱</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">Esc</kbd></div></div>
            </div>
          </div>
          <!-- Zoom -->
          <div>
            <h4 class="text-gray-500 dark:text-gray-400 font-medium mb-2 text-xs uppercase tracking-wider">缩放</h4>
            <div class="space-y-1.5">
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">放大</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">+</kbd><span class="text-gray-400 dark:text-gray-500">/</span><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">=</kbd></div></div>
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">缩小</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">-</kbd><span class="text-gray-400 dark:text-gray-500">/</span><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">_</kbd></div></div>
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">重置缩放</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">0</kbd></div></div>
            </div>
          </div>
          <!-- Edit -->
          <div v-if="allowEdit || allowDelete">
            <h4 class="text-gray-500 dark:text-gray-400 font-medium mb-2 text-xs uppercase tracking-wider">编辑</h4>
            <div class="space-y-1.5">
              <div v-if="allowEdit" class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">进入编辑</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">E</kbd></div></div>
              <div v-if="allowDelete" class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">删除图片</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">Del</kbd></div></div>
            </div>
          </div>
          <!-- Media -->
          <div>
            <h4 class="text-gray-500 dark:text-gray-400 font-medium mb-2 text-xs uppercase tracking-wider">媒体</h4>
            <div class="space-y-1.5">
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">下载图片</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">D</kbd></div></div>
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">查看原图</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">Shift+O</kbd></div></div>
            </div>
          </div>
          <!-- Info -->
          <div>
            <h4 class="text-gray-500 dark:text-gray-400 font-medium mb-2 text-xs uppercase tracking-wider">信息</h4>
            <div class="space-y-1.5">
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">元数据侧栏</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">I</kbd><span class="text-gray-400 dark:text-gray-500">/</span><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">M</kbd></div></div>
              <div class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">文字识别</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">O</kbd></div></div>
            </div>
          </div>
          <!-- Organize -->
          <div v-if="allowAddToAlbum || allowAddToPerson || allowMoveToFolder">
            <h4 class="text-gray-500 dark:text-gray-400 font-medium mb-2 text-xs uppercase tracking-wider">整理</h4>
            <div class="space-y-1.5">
              <div v-if="allowAddToAlbum" class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">添加到相册</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">A</kbd></div></div>
              <div v-if="allowAddToPerson" class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">添加到人物</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">P</kbd></div></div>
              <div v-if="allowMoveToFolder" class="flex items-center justify-between gap-3"><span class="text-gray-600 dark:text-gray-300">移动到目录</span><div class="flex gap-1"><kbd class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-mono border border-gray-200 dark:border-gray-700">F</kbd></div></div>
            </div>
          </div>
        </div>
      </el-dialog>

      <PersonSelector
        v-if="!isEditing"
        v-model:visible="showPersonSelector"
        :submitting="isAddingPerson"
        @select="handlePersonSelected"
      />

      <el-dialog
        v-model="showDescription"
        title="AI智能分析"
        align-center
        class="rounded-xl w-[90%] md:w-[500px]"
        append-to-body
      >
        <div v-loading="descriptionLoading">
            <div v-if="imageDescription">
                <p v-if="imageDescription.narrative" class="mb-4 text-lg font-medium">{{ imageDescription.narrative }}</p>
                <p v-if="imageDescription.description" class="mb-2 text-gray-600 dark:text-gray-300">{{ imageDescription.description }}</p>
                
                <div class="flex gap-2 mt-4">
                    <el-tag v-if="imageDescription.memory_score !== null">回忆值: {{ imageDescription.memory_score }}</el-tag>
                    <el-tag v-if="imageDescription.quality_score !== null" type="success">质量分: {{ imageDescription.quality_score }}</el-tag>
                </div>
                 <div class="flex flex-wrap gap-2 mt-2" v-if="imageDescription.tags && imageDescription.tags.length">
                    <el-tag v-for="tag in imageDescription.tags" :key="tag" type="info" size="small">{{ tag }}</el-tag>
                </div>
                <p v-if="imageDescription.reason" class="mt-2 text-sm text-gray-500">评分理由: {{ imageDescription.reason }}</p>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
                暂无描述信息
            </div>
        </div>
      </el-dialog>

    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch, computed, onUnmounted, nextTick, onMounted, defineAsyncComponent } from 'vue'
import {
    X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download, FolderPlus, Info,
    ImagePlus,
    ScanText,
    MoreHorizontal,
    Image as ImageIcon,
    Trash2,
    Aperture,
    Maximize2,
    Focus,
    UserPlus,
    FileText,
    FolderOutput,
    Pencil,
    MapPin,
    WandSparkles,
    ScanFace,
    Tags,
    Sparkles,
    Binary,
    LoaderCircle,
} from 'lucide-vue-next'
// xgplayer 体积大（~数百 KB），且只在查看视频时需要，故改为按需动态导入；
// 这里仅保留类型，运行时在 initPlayer 内 await import('xgplayer')。
import type Player from 'xgplayer'
import { albumService } from '@/api/album'
import { ocrApi, type OCRRecord } from '@/api/ocr'
import { faceApi } from '@/api/face'
import { tasksApi, type PhotoProcessingOperation } from '@/api/tasks'
import type { PhotoMetadata, AlbumImage, CoverPhotoInfo } from '@/types/album'
import { ElMessageBox, ElMessage } from 'element-plus'
import PhotoMetadataSidebar from './PhotoMetadataSidebar.vue'
import PhotoOCRPanel from './PhotoOCRPanel.vue'
import PersonSelector from './PersonSelector.vue'
// PhotoEditor 依赖 fabric（~数百 KB），只在用户点击编辑时才需要，异步化以延迟加载。
const PhotoEditor = defineAsyncComponent(() => import('./PhotoEditor.vue'))
import { useHotkeys, type HotkeyDef } from '@/composables/useHotkeys'
import { useOverlayStack } from '@/composables/useOverlayStack'


interface Props {
    visible: boolean
    image: AlbumImage | null
    images?: AlbumImage[]
    currentIndex?: number
    hasPrev?: boolean
    hasNext?: boolean
    allowEdit?: boolean
    allowDelete?: boolean
    allowAddToAlbum?: boolean
    allowAddToPerson?: boolean
    allowMoveToFolder?: boolean
    confirmDelete?: boolean
    deleteTitle?: string
    deleteMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
    images: () => [],
    currentIndex: -1,
    allowEdit: false,
    allowDelete: false,
    allowAddToAlbum: false,
    allowAddToPerson: false,
    allowMoveToFolder: false,
    confirmDelete: true,
    deleteTitle: '删除确认',
    deleteMessage: '确定要删除这张照片吗？删除后将移入回收站，可稍后恢复。'
})

const showOriginal = ref(false)
const isEditing = ref(false)
const controlsVisible = ref(true)
const mediaViewport = ref<HTMLElement | null>(null)
const thumbnailStrip = ref<HTMLElement | null>(null)
const swipeOffset = ref(0)
const isSwipeAnimating = ref(false)
let swipeAnimationTimer: ReturnType<typeof setTimeout> | null = null
const isPlayingLive = ref(false)
const liveVideoRef = ref<HTMLVideoElement | null>(null)
const videoStyle = ref<Record<string, string>>({})

// Shortcut hint & help state
const SHORTCUT_HINT_KEY = 'trailsnap_seen_shortcut_hint'
const showShortcutHint = ref(false)
let shortcutHintTimer: ReturnType<typeof setTimeout> | null = null
const showShortcutHelp = ref(false)
const shortcutHelpOpened = ref(false)

const toggleShortcutHelp = () => {
  showShortcutHelp.value = !showShortcutHelp.value
  // Permanently dismiss the first-launch hint when user opens the help panel
  if (showShortcutHelp.value && showShortcutHint.value) {
    showShortcutHint.value = false
    localStorage.setItem(SHORTCUT_HINT_KEY, '1')
    if (shortcutHintTimer) {
      clearTimeout(shortcutHintTimer)
      shortcutHintTimer = null
    }
  }
}

const handleEscKey = () => {
  if (shortcutHelpOpened.value) {
    showShortcutHelp.value = false
  } else {
    close()
  }
}

// Register lightbox hotkeys (priority 100, only when visible and not editing)
useHotkeys([
  { key: 'Escape', handler: handleEscKey },
  { key: 'ArrowLeft', handler: () => prev(), when: () => !!props.hasPrev },
  { key: 'ArrowRight', handler: () => next(), when: () => !!props.hasNext },
  { key: ' ', handler: () => next(), when: () => !!props.hasNext },
  { key: '+', handler: () => zoomIn() },
  { key: '=', handler: () => zoomIn() },
  { key: '-', handler: () => zoomOut() },
  { key: '_', handler: () => zoomOut() },
  { key: '0', handler: () => resetZoom() },
  { key: 'i', handler: () => toggleSidebar() },
  { key: 'I', handler: () => toggleSidebar() },
  { key: 'm', handler: () => toggleSidebar() },
  { key: 'M', handler: () => toggleSidebar() },
  { key: 'o', handler: () => toggleOCR() },
  { key: 'O', handler: () => toggleOriginal(), shift: true },
  { key: 'd', handler: () => downloadImage() },
  { key: 'D', handler: () => downloadImage() },
  { key: 'e', handler: () => enterEditMode(), when: () => props.allowEdit && !!props.image && props.image.file_type === 'image' },
  { key: 'E', handler: () => enterEditMode(), when: () => props.allowEdit && !!props.image && props.image.file_type === 'image' },
  { key: 'Delete', handler: () => handleDelete(), when: () => props.allowDelete },
  { key: 'Backspace', handler: () => handleDelete(), when: () => props.allowDelete },
  { key: 'a', handler: () => emit('add-to-album', props.image), when: () => props.allowAddToAlbum },
  { key: 'A', handler: () => emit('add-to-album', props.image), when: () => props.allowAddToAlbum },
  { key: 'p', handler: () => { showPersonSelector.value = true }, when: () => props.allowAddToPerson },
  { key: 'P', handler: () => { showPersonSelector.value = true }, when: () => props.allowAddToPerson },
  { key: 'f', handler: () => emit('transfer', 'move'), when: () => props.allowMoveToFolder },
  { key: 'F', handler: () => emit('transfer', 'move'), when: () => props.allowMoveToFolder },
  { key: 'l', handler: () => { showSidebar.value = true; forceOpenLocationEdit.value = true; nextTick(() => { forceOpenLocationEdit.value = false }) }, when: () => props.allowEdit },
  { key: 'L', handler: () => { showSidebar.value = true; forceOpenLocationEdit.value = true; nextTick(() => { forceOpenLocationEdit.value = false }) }, when: () => props.allowEdit },
  { key: '?', handler: () => toggleShortcutHelp() },
  { key: 'h', handler: () => toggleShortcutHelp() },
  { key: 'H', handler: () => toggleShortcutHelp() },
], { priority: 100, enabled: () => props.visible && !isEditing.value })

const displayImageSrc = computed(() => {
    if (!props.image) return ''
    if (showOriginal.value) return props.image.url
    return props.image.preview || props.image.url
})

const resolvedCurrentIndex = computed(() => {
    if (props.currentIndex >= 0) return props.currentIndex
    if (!props.image) return -1
    return props.images.findIndex(item => item.id === props.image?.id)
})

const previousImage = computed(() => {
    const index = resolvedCurrentIndex.value
    return index > 0 ? props.images[index - 1] : null
})

const nextImage = computed(() => {
    const index = resolvedCurrentIndex.value
    return index >= 0 && index < props.images.length - 1 ? props.images[index + 1] : null
})

const adjacentPreviewSrc = (item: AlbumImage | null) => item?.preview || item?.thumbnail || item?.url || ''

const thumbnailWindow = computed(() => {
    const index = resolvedCurrentIndex.value
    if (index < 0 || props.images.length < 2) return []
    const start = Math.max(0, index - 3)
    const end = Math.min(props.images.length, index + 4)
    return props.images.slice(start, end).map((item, offset) => ({ item, index: start + offset }))
})

const swipeTrackStyle = computed(() => ({
    transform: `translate3d(calc(-33.333333% + ${swipeOffset.value}px), 0, 0)`,
    transition: isSwipeAnimating.value ? 'transform 240ms cubic-bezier(0.22, 1, 0.36, 1)' : 'none',
}))

watch(resolvedCurrentIndex, async (index) => {
    await nextTick()
    thumbnailStrip.value
        ?.querySelector<HTMLElement>(`[data-photo-index="${index}"]`)
        ?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'nearest', inline: 'center' })
})

const onVideoLoaded = (e: Event) => {
    const video = e.target as HTMLVideoElement
    // Explicitly try to play (handling potential autoplay rejections)
    video.play().catch(err => {
        console.warn("Autoplay failed, trying muted play", err)
        video.muted = true
        video.play().catch(e => console.error("Muted autoplay also failed", e))
    })
}

const toggleLivePlayback = () => {
    if (isPlayingLive.value) {
        // Stop
        isPlayingLive.value = false
    } else {
        // Play
        isPlayingLive.value = true
    }
}

const onLiveEnded = () => {
    isPlayingLive.value = false
}

const toggleOriginal = () => {
    showOriginal.value = !showOriginal.value
}

const emit = defineEmits(['close', 'delete', 'update', 'prev', 'next', 'select', 'add-to-album', 'transfer'])

// Keep the lightbox in the browser history so the mobile browser/gesture back
// action closes it before Vue Router navigates away from the current page.
const LIGHTBOX_HISTORY_KEY = '__trailsnapPhotoLightbox'
const lightboxHistoryId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
let historyEntryActive = false
let historyBackPending = false
let historyListenerMounted = false

const isCurrentLightboxHistoryEntry = () =>
    window.history.state?.[LIGHTBOX_HISTORY_KEY] === lightboxHistoryId

const pushLightboxHistoryEntry = () => {
    if (!historyListenerMounted || historyEntryActive) return
    window.history.pushState(
        { ...(window.history.state ?? {}), [LIGHTBOX_HISTORY_KEY]: lightboxHistoryId },
        '',
        window.location.href,
    )
    historyEntryActive = true
}

const removeLightboxHistoryEntry = () => {
    if (!historyEntryActive || historyBackPending) return
    historyEntryActive = false
    if (isCurrentLightboxHistoryEntry()) window.history.back()
}

const handleHistoryPopState = () => {
    historyBackPending = false
    if (!historyEntryActive) return

    historyEntryActive = false
    if (props.visible) emit('close')
}

// State
const showSidebar = ref(false)
const forceOpenLocationEdit = ref(false)
const loading = ref(false)
const metadata = ref<PhotoMetadata | null>(null)

// OCR State
const showOCR = ref(false)
const ocrLoading = ref(false)
const ocrRecords = ref<OCRRecord[]>([])
const highlightedOCR = ref<OCRRecord | null>(null)
const imageRef = ref<HTMLImageElement | null>(null)

interface PhotoProcessingTracker {
    taskId: string
    photoId: string
    operation: PhotoProcessingOperation
    status: string
}

const processingMenuVisible = ref(false)
const photoProcessingTrackers = ref<Record<string, PhotoProcessingTracker>>({})
let photoProcessingPollTimer: ReturnType<typeof setInterval> | null = null

const photoProcessingOperations = [
    { operation: 'VISUAL_DESCRIPTION' as const, label: 'AI 智能分析', icon: Sparkles },
    { operation: 'RECOGNIZE_FACE' as const, label: '人脸识别', icon: ScanFace },
    { operation: 'OCR' as const, label: '文字识别 OCR', icon: ScanText },
    { operation: 'CLASSIFY_IMAGE' as const, label: '场景分类', icon: Tags },
    { operation: 'IMAGE_EMBEDDING' as const, label: '生成搜索特征', icon: Binary },
]

const canProcessCurrentPhoto = computed(() =>
    !!props.image && props.image.file_type !== 'video'
)

const processingTrackerKey = (photoId: string, operation: PhotoProcessingOperation) =>
    `${photoId}:${operation}`

const currentPhotoProcessingTracker = (operation: PhotoProcessingOperation) => {
    if (!props.image) return undefined
    return photoProcessingTrackers.value[processingTrackerKey(props.image.id, operation)]
}

const isPhotoProcessingActive = (operation: PhotoProcessingOperation) => {
    const status = currentPhotoProcessingTracker(operation)?.status
    return status === 'submitting' || status === 'pending' || status === 'processing'
}

const photoProcessingStatusLabel = (operation: PhotoProcessingOperation) => {
    const status = currentPhotoProcessingTracker(operation)?.status
    if (status === 'completed') return '已完成'
    if (status === 'failed') return '失败'
    return ''
}

const photoProcessingStatusClass = (operation: PhotoProcessingOperation) =>
    currentPhotoProcessingTracker(operation)?.status === 'failed'
        ? 'text-red-500 dark:text-red-400'
        : 'text-green-600 dark:text-green-400'

// Zoom & Pan State
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)

const startX = ref(0)
const startY = ref(0)
const initialDistance = ref(0)
const touchStartX = ref(0)
const touchStartY = ref(0)
const touchStartTime = ref(0)
const touchDeltaX = ref(0)
const touchDeltaY = ref(0)
const suppressNextTap = ref(false)
let suppressTapTimer: ReturnType<typeof setTimeout> | null = null

// Video Player State
const videoPlayer = ref<HTMLElement | null>(null)
const player = ref<Player | null>(null)

const initPlayer = async () => {
    if (videoPlayer.value && props.image) {
        if (player.value) {
            player.value.destroy()
            player.value = null
        }
        // 按需加载 xgplayer 及其样式（首次加载后由浏览器/构建缓存命中）
        const [{ default: XgPlayer }] = await Promise.all([
            import('xgplayer'),
            import('xgplayer/dist/index.min.css'),
        ])
        // 动态导入期间组件可能已卸载或切换了图片，再次校验避免在失效节点上创建播放器
        if (!videoPlayer.value || !props.image) return
        player.value = new XgPlayer({
            el: videoPlayer.value,
            url: props.image.url,
            poster: props.image.thumbnail,
            playsinline: true,
            autoplay: true,
            download: true,
            height: '100%',
            width: '100%',
            fitVideoSize: 'fixHeight',
            videoInit: true, // 初始化显示首帧
            lang: 'zh-cn',
            playbackRate: [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 5], // 倍速
            fluid: false, // 禁止流式布局，让width/height生效
            // 针对移动端的特殊配置
            commonStyle: {
                progressColor: '#1989fa',
                playedColor: '#1989fa',
            },
            // x5 内核适配
            x5: {
                type: 'h5',
                videoType: 'h5', 
                // orientation: 'landscape' 
            },
            fullscreen: {
                index: 1, // 全屏按钮位置
                rotateFullscreen: false // 旋转全屏
            },
            cssFullscreen: false, // 使用原生全屏
            controls: {
                mode: 'flex'
            },
            screenShot: {
                saveImg: true,
                quality: 0.92,
                type: 'image/png',
                format: '.png'
            },
            keyShortcut: true,
            keyShortcutStep: { //设置调整步长
                currentTime: 15, //播放进度调整步长，默认10秒
                volume: 0.2 //音量调整步长，默认0.1
            }
        })
    }
}

const disposePlayer = () => {
    if (player.value) {
        player.value.destroy()
        player.value = null
    }
}

onMounted(() => {
    historyListenerMounted = true
    window.addEventListener('popstate', handleHistoryPopState)
    if (props.visible) pushLightboxHistoryEntry()
})

onUnmounted(() => {
    historyListenerMounted = false
    window.removeEventListener('popstate', handleHistoryPopState)
    removeLightboxHistoryEntry()
    disposePlayer()
    document.body.style.overflow = ''
    stopDrag()
    stopTouch()
    if (shortcutHintTimer) {
        clearTimeout(shortcutHintTimer)
        shortcutHintTimer = null
    }
    if (suppressTapTimer) clearTimeout(suppressTapTimer)
    if (swipeAnimationTimer) clearTimeout(swipeAnimationTimer)
    if (photoProcessingPollTimer) {
        clearInterval(photoProcessingPollTimer)
        photoProcessingPollTimer = null
    }
})

const isDragging = ref(false)
watch(() => props.image, async (newImg, oldImg) => {
    // 1. Reset State
    showOriginal.value = false
    isEditing.value = false
    scale.value = 1
    translateX.value = 0
    translateY.value = 0
    ocrRecords.value = []
    highlightedOCR.value = null
    highlightedFace.value = null
    videoStyle.value = {}
    isDragging.value = false // Ensure dragging is reset
    processingMenuVisible.value = false

    // 2. Handle Resource Cleanup & Initialization
    if (oldImg?.file_type === 'video') {
        disposePlayer()
    }

    if (newImg && props.visible) {
        // Auto play if live photo
        if (newImg.file_type === 'live_photo') {
            isPlayingLive.value = true
        } else {
            isPlayingLive.value = false
        }

        // Init new player if switching to video
        if (newImg.file_type === 'video') {
            await nextTick()
            await initPlayer()
        }

        // Fetch Data
        // Don't await these to prevent blocking UI updates if they are slow
        fetchMetadata(newImg.id)
        
        if (showOCR.value) {
            fetchOCR(newImg.id)
        }
    } else {
        // If image is null (closed or cleared), dispose
        disposePlayer()
        isPlayingLive.value = false
    }
})

watch(() => props.visible, async (newVal) => {
    if (newVal && props.image) {
        pushLightboxHistoryEntry()
        document.body.style.overflow = 'hidden'
        resetZoom()
        controlsVisible.value = true

        if (props.image.file_type === 'live_photo') {
             isPlayingLive.value = true
        }

        if (props.image.file_type === 'video') {
            await nextTick()
            await initPlayer()
        }

        if (!metadata.value || metadata.value.photo_id !== props.image.id) {
            await fetchMetadata(props.image.id)
        }

        // Show first-launch shortcut hint
        if (!localStorage.getItem(SHORTCUT_HINT_KEY)) {
          showShortcutHint.value = true
          if (shortcutHintTimer) clearTimeout(shortcutHintTimer)
          shortcutHintTimer = setTimeout(() => {
            showShortcutHint.value = false
          }, 3000)
        }
    } else {
        removeLightboxHistoryEntry()
        document.body.style.overflow = ''
        isEditing.value = false
        disposePlayer()
        isPlayingLive.value = false
        showPersonSelector.value = false
        showDescription.value = false
        showSidebar.value = false
        showOCR.value = false
        showShortcutHint.value = false
        showShortcutHelp.value = false
        stopDrag()
        stopTouch()
        if (shortcutHintTimer) {
          clearTimeout(shortcutHintTimer)
          shortcutHintTimer = null
        }
    }
})

// Methods
const close = () => {
    if (historyEntryActive && isCurrentLightboxHistoryEntry()) {
        if (!historyBackPending) {
            historyBackPending = true
            window.history.back()
        }
        return
    }

    historyEntryActive = false
    emit('close')
}

const handleMediaTap = () => {
    if (suppressNextTap.value) {
        suppressNextTap.value = false
        return
    }
    if (scale.value === 1 && !showSidebar.value && !showOCR.value) {
        controlsVisible.value = !controlsVisible.value
    }
}

useOverlayStack(computed(() => props.visible), close)

const toggleSidebar = () => {
    showSidebar.value = !showSidebar.value
    if (showSidebar.value) {
        showOCR.value = false // Close OCR if Sidebar opens
    }
}

const handleCommand = (command: string) => {
    if (command === 'ocr') {
        toggleOCR()
    } else if (command === 'addToAlbum' && props.allowAddToAlbum) {
        emit('add-to-album', props.image)
    } else if (command === 'addToPerson' && props.allowAddToPerson) {
        showPersonSelector.value = true
    } else if (command === 'moveToFolder' && props.allowMoveToFolder) {
        emit('transfer', 'move')
    } else if (command === 'adjustLocation' && props.allowEdit) {
        showSidebar.value = true
        forceOpenLocationEdit.value = true
        nextTick(() => { forceOpenLocationEdit.value = false })
    } else if (command === 'viewDescription') {
        if (props.image) {
            fetchDescription(props.image.id)
        }
    }
}

const photoProcessingOperationLabel = (operation: PhotoProcessingOperation) =>
    photoProcessingOperations.find(item => item.operation === operation)?.label ?? operation

const refreshPhotoProcessingResult = async (tracker: PhotoProcessingTracker) => {
    if (props.image?.id !== tracker.photoId) return

    if (tracker.operation === 'OCR') {
        showSidebar.value = false
        showOCR.value = true
        await fetchOCR(tracker.photoId)
    } else if (tracker.operation === 'VISUAL_DESCRIPTION') {
        await fetchDescription(tracker.photoId)
    } else if (tracker.operation === 'RECOGNIZE_FACE' || tracker.operation === 'CLASSIFY_IMAGE') {
        await fetchMetadata(tracker.photoId)
        emit('update', {
            photoId: tracker.photoId,
            taskType: tracker.operation,
        })
    }
}

let photoProcessingPollRunning = false

const pollPhotoProcessingTasks = async () => {
    if (photoProcessingPollRunning) return
    const activeTrackers = Object.values(photoProcessingTrackers.value).filter(
        tracker => tracker.taskId && (tracker.status === 'pending' || tracker.status === 'processing'),
    )
    if (!activeTrackers.length) {
        if (photoProcessingPollTimer) {
            clearInterval(photoProcessingPollTimer)
            photoProcessingPollTimer = null
        }
        return
    }

    photoProcessingPollRunning = true
    try {
        await Promise.all(activeTrackers.map(async (tracker) => {
            try {
                const task = await tasksApi.getTask(tracker.taskId)
                const status = String(task.status || '').toLowerCase()
                const key = processingTrackerKey(tracker.photoId, tracker.operation)
                const latest = photoProcessingTrackers.value[key]
                if (!latest || latest.taskId !== tracker.taskId) return

                photoProcessingTrackers.value[key] = { ...latest, status }
                if (status === 'completed') {
                    await refreshPhotoProcessingResult(photoProcessingTrackers.value[key])
                    ElMessage.success(`${photoProcessingOperationLabel(tracker.operation)}完成`)
                } else if (status === 'failed') {
                    ElMessage.error(`${photoProcessingOperationLabel(tracker.operation)}失败${task.error ? `：${task.error}` : ''}`)
                }
            } catch (error) {
                // The live notification stream remains the primary global
                // status channel. A transient polling error is retried so a
                // short network interruption does not turn the task into a
                // false failure in the lightbox.
                console.debug('Polling photo processing task failed', error)
            }
        }))
    } finally {
        photoProcessingPollRunning = false
    }
}

const ensurePhotoProcessingPolling = () => {
    if (!photoProcessingPollTimer) {
        photoProcessingPollTimer = setInterval(() => {
            void pollPhotoProcessingTasks()
        }, 1500)
    }
    void pollPhotoProcessingTasks()
}

const startPhotoProcessing = async (operation: PhotoProcessingOperation) => {
    const photo = props.image
    if (!photo || photo.file_type === 'video') return

    const key = processingTrackerKey(photo.id, operation)
    if (isPhotoProcessingActive(operation)) {
        ElMessage.info('该任务已经在处理中')
        return
    }

    photoProcessingTrackers.value[key] = {
        taskId: '',
        photoId: photo.id,
        operation,
        status: 'submitting',
    }
    processingMenuVisible.value = false

    try {
        const result = await tasksApi.createPhotoProcessingTask(photo.id, operation, true)
        photoProcessingTrackers.value[key] = {
            taskId: result.task.id,
            photoId: photo.id,
            operation,
            status: String(result.task.status || 'pending').toLowerCase(),
        }
        ElMessage.success(result.reused ? '该任务已在队列中' : '已加入优先处理队列')
        ensurePhotoProcessingPolling()
    } catch (error) {
        console.error('Failed to create photo processing task', error)
        photoProcessingTrackers.value[key] = {
            taskId: '',
            photoId: photo.id,
            operation,
            status: 'failed',
        }
        ElMessage.error('创建处理任务失败')
    }
}

// Description State
const showDescription = ref(false)
const descriptionLoading = ref(false)
const imageDescription = ref<any>(null)

const fetchDescription = async (photoId: string) => {
    descriptionLoading.value = true
    showDescription.value = true
    imageDescription.value = null
    try {
        const res = await albumService.getImageDescription(photoId)
        imageDescription.value = res
    } catch (e) {
        console.error(e)
        // ElMessage.error('获取描述失败') // Fail silently or show empty state
    } finally {
        descriptionLoading.value = false
    }
}

// Person Selector State
const showPersonSelector = ref(false)
const isAddingPerson = ref(false)

const handlePersonSelected = async (person: any) => {
  if (!props.image) return
  try {
    isAddingPerson.value = true
    await faceApi.addPhotosToIdentity(person.id, [props.image.id])
    ElMessage.success('添加成功')
    showPersonSelector.value = false
    // Refresh metadata if needed
    fetchMetadata(props.image.id)
  } catch (e) {
    console.error(e)
    ElMessage.error('添加失败')
  } finally {
    isAddingPerson.value = false
  }
}

const fetchMetadata = async (photoId: string) => {
    loading.value = true
    try {
        const data = await albumService.getMetadata(photoId)
        metadata.value = data
    } catch (error) {
        console.error("Failed to fetch metadata", error)
    } finally {
        loading.value = false
    }
}

// OCR Methods
const toggleOCR = async () => {
    showOCR.value = !showOCR.value
    if (showOCR.value) {
        showSidebar.value = false // Close Sidebar if OCR opens
        if (props.image) {
            await fetchOCR(props.image.id)
        }
    }
}

const fetchOCR = async (photoId: string) => {
    ocrLoading.value = true
    try {
        const res = await ocrApi.getOCR(photoId)
        ocrRecords.value = res.records
    } catch (error) {
        console.error("Failed to fetch OCR records", error)
        ElMessage.error("获取OCR记录失败")
    } finally {
        ocrLoading.value = false
    }
}

const getPolygonPoints = (polygon: number[][]) => {
    return polygon.map(p => p.join(',')).join(' ')
}

const onPolygonClick = (record: OCRRecord) => {
    highlightedOCR.value = record
    if (!showOCR.value) {
        showOCR.value = true
        // Fetch OCR if not already (though if records exist, we likely fetched)
    }
}

const onOCRRecordClick = (record: OCRRecord) => {
    highlightedOCR.value = record
}

// Face Highlight Methods
const highlightedFace = ref<CoverPhotoInfo | null>(null)
const highlightedFaceName = ref('')
const highlightedFaceConfidence = ref<number | null>(null)
const highlightedFaceRecognitionConfidence = ref<number | null>(null)

const handleHighlightFace = (payload: { face: CoverPhotoInfo | null, name: string } | null) => {
    if (!payload || !payload.face) {
        highlightedFace.value = null
        highlightedFaceName.value = ''
        highlightedFaceConfidence.value = 0
        return
    }
    highlightedFace.value = payload.face
    highlightedFaceName.value = payload.name
    
    // Prefer recognize_confidence, fallback to face_confidence
    const conf = payload.face.face_confidence
    highlightedFaceConfidence.value = conf ? Math.round(conf * 100) : null
    highlightedFaceRecognitionConfidence.value = payload.face.recognize_confidence ? Math.round(payload.face.recognize_confidence * 100) : null
}

const faceBoxStyle = computed(() => {
    const face = highlightedFace.value
    if (!face || !face.face_rect) return null

    // face_rect is [x1, y1, x2, y2]
    const [x1, y1, x2, y2] = face.face_rect

    const left = x1 * 100
    const top = y1 * 100
    const width = (x2 - x1) * 100
    const height = (y2 - y1) * 100
    return {
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`
    }
})

// Sidebar Event Handlers
const handleSidebarUpdate = (updates: any) => {
    if (metadata.value && updates.id === metadata.value.photo_id) {
        // Update local metadata
        metadata.value = { ...metadata.value, ...updates }
        emit('update', updates)
    }
}

// Zoom & Pan Methods
const resetZoom = () => {
    scale.value = 1
    translateX.value = 0
    translateY.value = 0
    isDragging.value = false
}

const zoomIn = () => {
    scale.value = Math.min(scale.value + 0.5, 5)
}

const zoomOut = () => {
    scale.value = Math.max(scale.value - 0.5, 1)
    if (scale.value === 1) {
        translateX.value = 0
        translateY.value = 0
    }
}

const handleWheel = (e: WheelEvent) => {
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    const newScale = Math.max(1, Math.min(5, scale.value + delta))
    scale.value = newScale
    if (scale.value === 1) {
        translateX.value = 0
        translateY.value = 0
    }
}

const startDrag = (e: MouseEvent) => {
    if (scale.value > 1) {
        isDragging.value = true
        startX.value = e.clientX - translateX.value
        startY.value = e.clientY - translateY.value
        window.addEventListener('mousemove', onDrag)
        window.addEventListener('mouseup', stopDrag)
    }
}

const onDrag = (e: MouseEvent) => {
    if (isDragging.value) {
        e.preventDefault()
        translateX.value = e.clientX - startX.value
        translateY.value = e.clientY - startY.value
    }
}

const stopDrag = () => {
    isDragging.value = false
    window.removeEventListener('mousemove', onDrag)
    window.removeEventListener('mouseup', stopDrag)
}

// Touch Support (Pinch & Drag)
const startTouch = (e: TouchEvent) => {
    if (isSwipeAnimating.value) return
    // Only handle pinch or drag if needed
    if (e.touches.length === 2) {
        // Pinch start
        const touch1 = e.touches[0]
        const touch2 = e.touches[1]
        initialDistance.value = Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY)
        window.addEventListener('touchmove', onTouchMove, { passive: false })
        window.addEventListener('touchend', stopTouch)
        window.addEventListener('touchcancel', stopTouch)
    } else if (e.touches.length === 1 && scale.value > 1) {
        // Drag start
        isDragging.value = true
        startX.value = e.touches[0].clientX - translateX.value
        startY.value = e.touches[0].clientY - translateY.value
        window.addEventListener('touchmove', onTouchMove, { passive: false })
        window.addEventListener('touchend', stopTouch)
        window.addEventListener('touchcancel', stopTouch)
    } else if (e.touches.length === 1) {
        // At the default zoom level, a horizontal gesture navigates between photos.
        // Keep vertical movement inert so a slightly diagonal swipe does not switch accidentally.
        touchStartX.value = e.touches[0].clientX
        touchStartY.value = e.touches[0].clientY
        touchStartTime.value = performance.now()
        touchDeltaX.value = 0
        touchDeltaY.value = 0
        window.addEventListener('touchmove', onTouchMove, { passive: false })
        window.addEventListener('touchend', stopTouch)
        window.addEventListener('touchcancel', stopTouch)
    }
}

const onTouchMove = (e: TouchEvent) => {
    if (e.touches.length === 2) {
        // Pinch move
        e.preventDefault()
        const touch1 = e.touches[0]
        const touch2 = e.touches[1]
        const currentDistance = Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY)
        if (initialDistance.value > 0) {
            const delta = currentDistance / initialDistance.value
            // Smooth zoom adjustment
            const newScale = scale.value * delta
            scale.value = Math.max(1, Math.min(5, newScale))
            initialDistance.value = currentDistance // Reset for continuous zoom
        }
    } else if (e.touches.length === 1 && isDragging.value) {
        // Drag move
        e.preventDefault()
        translateX.value = e.touches[0].clientX - startX.value
        translateY.value = e.touches[0].clientY - startY.value
    } else if (e.touches.length === 1 && scale.value === 1 && touchStartTime.value > 0) {
        touchDeltaX.value = e.touches[0].clientX - touchStartX.value
        touchDeltaY.value = e.touches[0].clientY - touchStartY.value
        if (Math.abs(touchDeltaX.value) > Math.abs(touchDeltaY.value)) {
            e.preventDefault()
            const atStart = touchDeltaX.value > 0 && !props.hasPrev
            const atEnd = touchDeltaX.value < 0 && !props.hasNext
            swipeOffset.value = (atStart || atEnd) ? touchDeltaX.value * 0.22 : touchDeltaX.value
        }
    }
}

const prefersReducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

const finishSwipeAnimation = (callback?: () => void) => {
    if (swipeAnimationTimer) clearTimeout(swipeAnimationTimer)
    const duration = prefersReducedMotion() ? 0 : 240
    if (duration === 0) {
        callback?.()
        swipeOffset.value = 0
        isSwipeAnimating.value = false
        return
    }
    swipeAnimationTimer = setTimeout(() => {
        callback?.()
        nextTick(() => {
            isSwipeAnimating.value = false
            swipeOffset.value = 0
            swipeAnimationTimer = null
        })
    }, duration)
}

const animateSwipeBack = () => {
    if (swipeOffset.value === 0) return
    isSwipeAnimating.value = true
    swipeOffset.value = 0
    finishSwipeAnimation()
}

const animateNavigation = (direction: 'prev' | 'next', callback: () => void) => {
    if (isSwipeAnimating.value) return
    const adjacent = direction === 'prev' ? previousImage.value : nextImage.value
    const width = mediaViewport.value?.clientWidth || window.innerWidth
    if (!adjacent || prefersReducedMotion()) {
        callback()
        swipeOffset.value = 0
        return
    }
    isSwipeAnimating.value = true
    swipeOffset.value = direction === 'next' ? -width : width
    finishSwipeAnimation(callback)
}

const stopTouch = () => {
    const elapsed = performance.now() - touchStartTime.value
    const isHorizontalSwipe = scale.value === 1
        && Math.abs(touchDeltaX.value) >= 50
        && Math.abs(touchDeltaX.value) > Math.abs(touchDeltaY.value) * 1.25
        && elapsed <= 700

    if (isHorizontalSwipe && ((touchDeltaX.value < 0 && props.hasNext) || (touchDeltaX.value > 0 && props.hasPrev))) {
        if (touchDeltaX.value < 0) next()
        if (touchDeltaX.value > 0) prev()
        suppressNextTap.value = true
        if (suppressTapTimer) clearTimeout(suppressTapTimer)
        suppressTapTimer = setTimeout(() => {
            suppressNextTap.value = false
            suppressTapTimer = null
        }, 350)
    } else animateSwipeBack()
    isDragging.value = false
    initialDistance.value = 0
    touchStartTime.value = 0
    touchDeltaX.value = 0
    touchDeltaY.value = 0
    window.removeEventListener('touchmove', onTouchMove)
    window.removeEventListener('touchend', stopTouch)
    window.removeEventListener('touchcancel', stopTouch)
}

const downloadImage = async () => {
    if (!props.image) return
    try {
        const response = await fetch(props.image.url)
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${props.image.filename}` || `photo_${props.image.id}.jpg` // Simple filename
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        ElMessage.success('下载开始')
    } catch (e) {
        console.error('Download failed', e)
        ElMessage.error('下载失败')
    }
}

const prev = () => {
    if (!props.hasPrev) return
    animateNavigation('prev', () => emit('prev'))
}
const next = () => {
    if (!props.hasNext) return
    animateNavigation('next', () => emit('next'))
}

const navigateToIndex = (index: number) => {
    const current = resolvedCurrentIndex.value
    if (current < 0 || index === current || index < 0 || index >= props.images.length) return
    animateNavigation(index < current ? 'prev' : 'next', () => emit('select', index))
}

const handleDelete = () => {
    if (!props.image || !props.allowDelete) return
    const emitDelete = () => {
        if (props.image) emit('delete', props.image.id)
    }
    if (!props.confirmDelete) {
        emitDelete()
        return
    }
    ElMessageBox.confirm(
        props.deleteMessage,
        props.deleteTitle,
        {
            confirmButtonText: '删除',
            cancelButtonText: '取消',
            type: 'warning',
        }
    )
    .then(emitDelete)
}

// Edit Mode
const enterEditMode = () => {
    isEditing.value = true
    showSidebar.value = false
    showOCR.value = false
}

const exitEditMode = () => {
    isEditing.value = false
}

const handleEditorSave = async (blob: Blob, filename: string, mode: 'replace' | 'new') => {
    if (!props.image) return
    try {
        if (mode === 'replace') {
            const file = new File([blob], filename, { type: blob.type || 'image/jpeg' })
            await albumService.replacePhotoFile(props.image.id, file, filename)
            ElMessage.success('已替换原图')
            // Bust cache by updating image URLs
            const t = Date.now()
            if (props.image.url) props.image.url = `${props.image.url.split('?')[0]}?t=${t}`
            if (props.image.thumbnail) props.image.thumbnail = `${props.image.thumbnail.split('?')[0]}?t=${t}`
            if (props.image.preview) props.image.preview = `${props.image.preview.split('?')[0]}?t=${t}`
            emit('update', { id: props.image.id, edited: true })
        } else {
            const file = new File([blob], filename, { type: blob.type || 'image/jpeg' })
            await albumService.uploadPhoto(file)
            ElMessage.success('已另存为新图')
        }
        exitEditMode()
    } catch (e: any) {
        console.error('Save failed', e)
        ElMessage.error('保存失败: ' + (e.message || '未知错误'))
    }
}

</script>

<style scoped>
.viewer-controls-enter-active,
.viewer-controls-leave-active {
    transition: opacity 180ms ease, transform 180ms ease;
}
.viewer-controls-enter-from,
.viewer-controls-leave-to {
    opacity: 0;
    transform: translateY(-0.75rem);
}

.viewer-thumbnails-enter-active,
.viewer-thumbnails-leave-active {
    transition: opacity 180ms ease, transform 180ms ease;
}
.viewer-thumbnails-enter-from,
.viewer-thumbnails-leave-to {
    opacity: 0;
    transform: translateY(1rem);
}

@media (prefers-reduced-motion: reduce) {
    .viewer-controls-enter-active,
    .viewer-controls-leave-active,
    .viewer-thumbnails-enter-active,
    .viewer-thumbnails-leave-active {
        transition-duration: 0ms;
    }
}
</style>
