<template>
  <div
    class="photo-gallery min-h-screen relative"
    :class="{ 'photo-gallery--pinching': isGridPinching, 'ts-photo-selecting': isSelectionMode }"
    ref="galleryEl"
    @touchstart="handleGridTouchStart"
    @click.capture="handleGridClickCapture"
  >
    <!-- Skeleton Loader (Initial Load) -->
    <GalleryChrome :loading="loading" :error="error" :photos="photos" @retry="$emit('retry')" />

    <PhotoContextMenu
      ref="contextMenu" :selected-ids="localSelectedIds" :is-downloading="isDownloading"
      allow-add-to-album :album-context="!!removeLabel && store?.currentContext?.type === 'album'"
      :remove-label="removeLabel"
      :delete-label="deleteLabel === '删除' ? '移到回收站' : deleteLabel"
      @view="(photo, details) => emit('click-photo', photo, details)"
      @download="downloadPhotos"
      @add-to-album="(ids, preserve) => emit('add-to-album', ids, preserve)"
      @set-cover="ids => emit('set-album-cover', ids)"
      @remove="(ids, preserve) => emit('remove-association', ids, preserve)"
      @delete="(ids, preserve) => emit('batch-delete', ids, preserve)"
    />

    <PhotoBatchActionBar
      :visible="isSelectionMode && showActionBar" :selected-ids="localSelectedIds"
      :is-all-selected="isAllSelected" :is-downloading="isDownloading" :delete-label="deleteLabel"
      :album-context="store?.currentContext?.type === 'album'" allow-transfer
      :remove-label="removeLabel"
      @cancel="exitSelectionMode" @select-all="toggleSelectAll" @download="handleDownload"
      @delete="handleDelete" @person="openPersonSelector"
      @remove-association="ids => $emit('remove-association', ids)"
      @add-to-album="ids => $emit('add-to-album', ids)"
      @remove-from-album="ids => $emit('remove-from-album', ids)"
      @set-album-cover="ids => $emit('set-album-cover', ids)"
      @batch-edit-time="ids => $emit('batch-edit-time', ids)"
      @batch-edit-location="ids => $emit('batch-edit-location', ids)"
      @transfer="(action, ids) => $emit('transfer', action, ids)"
    >
      <template v-if="$slots['batch-actions']" #batch-actions="scope"><slot name="batch-actions" v-bind="scope" /></template>
    </PhotoBatchActionBar>

    <PersonSelector 
      v-model:visible="showPersonSelector"
      :submitting="isAddingPerson"
      @select="handlePersonSelected"
    />
    <!-- Virtual Scroll Container -->
    <div ref="virtualContentEl" :style="{ height: totalHeight + 'px', position: 'relative' }">
      <div
        v-for="block in monthBlocks"
        :key="block.key"
        :style="{ 
          position: 'absolute', 
          top: block.top + 'px', 
          left: 0, 
          width: '100%',
          height: block.height + 'px'
        }"
        class="month-block px-4"
        :data-month="block.key"
      >
        <!-- Render month content only if visible -->
        <template v-if="visibleBlockKeys.has(block.key)">
            <!-- Days Container -->
            <div
                v-for="(day, dayIdx) in block.days"
                :key="day.key"
                :style="{
                    position: 'absolute',
                    top: day.top + 'px',
                    left: 0,
                    width: '100%',
                    height: day.height + 'px',
                    zIndex: block.days.length - dayIdx
                }"
                class="day-block"
                :data-day-key="day.key"
            >
                <template v-if="visibleDayRanges.has(day.key)">
                    <!-- Day Header：杂志式日期标尺 -->
                    <div
                      v-if="layoutMode !== 'moments' && shouldShowDateHeader(day, dayIdx)"
                      data-testid="photo-date-header"
                      :data-date-mode="mobileDateHeaderMode"
                      class="lm-day-head sticky top-[calc(var(--photo-page-header-height,80px)_+_6px)] z-20 pointer-events-none"
                      :class="dateHeaderContainerClass"
                    >
                        <div
                          v-glass-refraction.rim="!isSelectionMode"
                          class="lm-day-date ts-liquid-glass ts-photo-date pointer-events-auto"
                          :class="[dateHeaderContentClass, { 'is-selectable': mobileDateHeaderMode === 'day' && isSelectionMode }]"
                          @click="mobileDateHeaderMode === 'day' && isSelectionMode && toggleDaySelection(day)"
                        >
                             <span v-if="day.year === 0" class="lm-day-unknown">时间未知</span>
                             <template v-else-if="mobileDateHeaderMode === 'day'">
                               <div
                                  v-if="isSelectionMode"
                                  data-testid="photo-date-checkbox"
                                  class="lm-day-check"
                                  :class="isDaySelected(day) ? 'is-checked' : ''"
                                  aria-hidden="true"
                               >
                                  <Check v-if="isDaySelected(day)" class="h-3 w-3 text-white" />
                               </div>
                               <span class="lm-day-num lm-num">{{ String(day.day).padStart(2, '0') }}</span>
                               <span class="lm-day-copy">
                                 <span class="lm-day-month">{{ day.year }} 年 {{ day.month }} 月<template v-if="weekdayText(day)"> · {{ weekdayText(day) }}</template></span>
                                 <span class="lm-day-sub">{{ day.count }} 帧<template v-if="dayPlace(day)"> · {{ dayPlace(day) }}</template></span>
                               </span>
                             </template>
                             <span v-else-if="mobileDateHeaderMode === 'month'" class="lm-day-month lm-num">
                               {{ day.year }} 年 {{ String(day.month).padStart(2, '0') }} 月
                             </span>
                             <span v-else class="lm-day-month lm-num">{{ day.year }} 年</span>
                             <el-popover v-if="isYearStart(day) && chapterLinks[String(day.year)]?.length" placement="bottom" :width="230" trigger="click">
                               <template #reference><button class="lm-day-chapter pointer-events-auto" @click.stop>这一阶段</button></template>
                               <RouterLink v-for="chapter in chapterLinks[String(day.year)]" :key="chapter.id" :to="`/chapters/${chapter.id}`" class="lm-day-chapter-link">{{ chapter.title }}</RouterLink>
                             </el-popover>
                        </div>
                        <span class="lm-day-rule" aria-hidden="true"></span>
                    </div>

                    <!-- Moments Layout Block -->
                    <div v-if="layoutMode === 'moments'" class="flex gap-3 mb-10 md:mb-8 relative">
                        <!-- Avatar placeholder -->
                        <div class="w-10 h-10 rounded-lg bg-gray-200 dark:bg-gray-700 flex-shrink-0 flex items-center justify-center text-gray-400 font-bold overflow-hidden">
                            <img v-if="userStore.userInfo?.avatar" :src="toServerUrl(userStore.userInfo.avatar)" class="w-full h-full object-cover" />
                            <ImageIcon v-else class="w-5 h-5 opacity-50" />
                        </div>
                        
                        <!-- Content -->
                        <div class="flex-grow min-w-0" :class="expandedDays.has(day.key) ? 'max-w-full' : 'max-w-[600px]'">
                            <!-- Name -->
                            <div class="text-sm font-bold text-[#576b95] dark:text-primary-400 mb-1">
                                {{ userStore.userInfo?.nickname || userStore.userInfo?.username || '行影集用户' }}
                            </div>
                            
                            <!-- Simulated Text Placeholder -->
                            <div class="mb-4 md:mb-3 group/caption">
                                <!-- 思考过程：仅 streaming 期间展示，完成后随 reasoning 清空自动消失 -->
                                <div v-if="dayCaptions[day.key]?.streaming && dayCaptions[day.key]?.reasoning"
                                     class="mb-2 rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 overflow-hidden">
                                    <div class="flex items-center gap-1.5 px-2 py-1 cursor-pointer select-none text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                                         @click.stop="toggleReasoningCollapse(day.key)">
                                        <Brain class="w-3.5 h-3.5" />
                                        <span>思考过程</span>
                                        <Loader2 class="w-3 h-3 animate-spin ml-auto" />
                                        <ChevronDown class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-180': !collapsedReasoningDays.has(day.key) }" />
                                    </div>
                                    <div v-show="!collapsedReasoningDays.has(day.key)"
                                         :ref="(el) => setReasoningRef(day.key, el)"
                                         class="px-2 py-1.5 max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-gray-500 dark:text-gray-400 border-t border-gray-200 dark:border-gray-700">
                                        <span>{{ dayCaptions[day.key].reasoning }}</span><span class="inline-block w-0.5 h-3 align-middle ml-0.5 bg-primary-400 animate-pulse"></span>
                                    </div>
                                </div>
                                <div class="text-[15px] leading-[22px] text-gray-800 dark:text-gray-200 whitespace-pre-wrap break-words">
                                    <template v-if="editingCaptionDay === day.key">
                                        <textarea
                                            v-model="captionDraft"
                                            class="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md p-2 text-[15px] text-gray-800 dark:text-gray-200 outline-none focus:border-primary-400"
                                            rows="3"
                                            maxlength="500"
                                            @keydown.esc.stop="cancelEditCaption"
                                            @keydown.ctrl.enter.stop="commitEditCaption(day)"
                                            @keydown.meta.enter.stop="commitEditCaption(day)"
                                        ></textarea>
                                        <div class="flex items-center gap-2 mt-1 text-xs">
                                            <button class="px-2 py-1 rounded bg-primary-500 text-white hover:bg-primary-600" @click="commitEditCaption(day)">保存</button>
                                            <button class="px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200" @click="cancelEditCaption">取消</button>
                                            <span class="text-gray-400">Ctrl / ⌘ + Enter 保存 · Esc 取消</span>
                                        </div>
                                    </template>
                                    <template v-else-if="dayCaptions[day.key]?.caption">
                                        <span>{{ dayCaptions[day.key].caption }}</span>
                                        <span v-if="dayCaptions[day.key]?.streaming" class="inline-block ml-1 w-1.5 h-4 align-middle bg-primary-400 animate-pulse"></span>
                                    </template>
                                    <template v-else-if="dayCaptions[day.key]?.streaming">
                                        <span class="inline-block w-1.5 h-4 align-middle bg-primary-400 animate-pulse"></span>
                                    </template>
                                    <template v-else-if="showMomentCaption && !dayHasPhotoTime(day.key)">
                                        <span class="text-amber-600 dark:text-amber-500">
                                            <span class="iconify" data-icon="mdi:clock-alert-outline" style="display:inline-block;vertical-align:-2px;margin-right:4px;"></span>
                                            这一天的照片没有拍摄时间（EXIF 缺失），AI 无法自动生成文案。你可以点右边的「编辑」手动写一段。
                                        </span>
                                    </template>
                                    <template v-else>
                                        <span class="text-gray-400">这是 {{ day.year }}年{{ day.month }}月{{ day.day }}日 的美好回忆。</span>
                                    </template>
                                </div>

                                <div
                                    v-if="showMomentCaption && editingCaptionDay !== day.key"
                                    class="relative z-20 flex items-center gap-3 mt-2 md:mt-1 text-xs text-gray-400 dark:text-gray-500 md:opacity-0 md:group-hover/caption:opacity-100 transition-opacity"
                                    :class="{ 'md:opacity-100': loadingDays.has(day.key) }"
                                >
                                    <!-- AI 生成：当天至少一张照片有真实拍摄时间时才允许，否则后端会直接报错 -->
                                    <button
                                        v-if="dayHasPhotoTime(day.key)"
                                        type="button"
                                        class="flex items-center gap-1 hover:text-primary-500 bg-transparent cursor-pointer"
                                        :disabled="loadingDays.has(day.key)"
                                        :title="dayCaptions[day.key]?.caption ? '重新生成文案' : 'AI 生成文案'"
                                        @click.stop="$emit('generate-caption', { day, force: !!dayCaptions[day.key]?.caption })"
                                    >
                                        <Loader2 v-if="loadingDays.has(day.key)" class="w-3.5 h-3.5 animate-spin" />
                                        <Sparkles v-else class="w-3.5 h-3.5" />
                                        <span>{{ loadingDays.has(day.key) ? '生成中…' : (dayCaptions[day.key]?.caption ? '重新生成' : 'AI 生成') }}</span>
                                    </button>
                                    <!-- 编辑：无论当前是否已有文案都允许手动编辑，方便无 EXIF 时间的天手写文案 -->
                                    <button
                                        v-if="!loadingDays.has(day.key)"
                                        type="button"
                                        class="flex items-center gap-1 hover:text-primary-500 bg-transparent cursor-pointer"
                                        :title="dayCaptions[day.key]?.caption ? '编辑文案' : '手动写文案'"
                                        @click.stop="startEditCaption(day)"
                                    >
                                        <Pencil class="w-3.5 h-3.5" />
                                        <span>{{ dayCaptions[day.key]?.caption ? '编辑' : '手动写' }}</span>
                                    </button>
                                    <button
                                        v-if="dayCaptions[day.key]?.caption && !loadingDays.has(day.key)"
                                        type="button"
                                        class="flex items-center gap-1 hover:text-red-500 bg-transparent cursor-pointer"
                                        title="清除文案"
                                        @click.stop="$emit('clear-caption', { day })"
                                    >
                                        <RotateCcw class="w-3.5 h-3.5" />
                                        <span>清除</span>
                                    </button>
                                </div>
                            </div>
                            
                            <!-- Photos Grid for Moments -->
                            <div 
                                class="grid gap-1.5 sm:gap-2 mb-2" 
                                :style="{
                                    gridTemplateColumns: getGridColumns(day.key, expandedDays.has(day.key)),
                                    maxWidth: getGridMaxWidth(day.key, expandedDays.has(day.key))
                                }"
                            >
                                <template v-for="(img, idx) in (expandedDays.has(day.key) ? getPhotos(day.key) : getMomentPhotos(day.key))" :key="img.id">
                                     <div
                                         :data-photo-id="img.id"
                                         class="relative group bg-gray-100 dark:bg-gray-800 overflow-hidden cursor-pointer rounded-sm"
                                         :class="{
                                             'aspect-square': (expandedDays.has(day.key) ? getPhotos(day.key).length : getMomentPhotos(day.key).length) > 1,
                                             'flex justify-start': (expandedDays.has(day.key) ? getPhotos(day.key).length : getMomentPhotos(day.key).length) === 1
                                         }"
                                         :style="(expandedDays.has(day.key) ? getPhotos(day.key).length : getMomentPhotos(day.key).length) === 1 ? singlePhotoBoxStyle(img) : {}"
                                         @click="handlePhotoClick(img, $event)"
                                         @contextmenu="openContextMenu(img, $event)"
                                         @vue:mounted="loadImage(img)"
                                         @vue:unmounted="cancelImageLoad(img.id)"
                                     >
                                         <img
                                              :src="loadedImages[img.id] || placeholderSrc"
                                              class="w-full h-full transition-opacity duration-300"
                                              :class="[(expandedDays.has(day.key) ? getPhotos(day.key).length : getMomentPhotos(day.key).length) === 1 ? 'object-contain object-left' : 'object-cover', loadedImages[img.id] ? 'is-developed' : '']"
                                              :alt="img.filename"
                                          />
                                          
                                          <!-- Video/Live Photo Indicators -->
                                          <span v-if="img.panorama_projection" class="absolute top-2 left-10 z-10 rounded bg-black/70 px-2 py-1 text-xs text-white pointer-events-none">360°</span>
                                          <div v-if="img.file_type === 'video'" class="flex mb-1 absolute top-1 right-2 justify-center pointer-events-none z-10 items-center">
                                            <div class="text-white text-sm drop-shadow-md mr-1">
                                              {{ img.duration}}
                                            </div>
                                            <PlayCircle class="w-4 h-4 text-white drop-shadow-md opacity-90" />
                                          </div>
                                          <div v-else-if="img.file_type === 'live_photo'" class="flex mb-1 absolute top-2 right-2 justify-center pointer-events-none z-10 items-center">
                                               <span class="icon-[tabler--live-photo] w-4 h-4 text-white drop-shadow-md opacity-90"></span>
                                           </div>

                                           <!-- Selection Checkbox -->
                                           <div
                                               class="absolute top-1 left-1 z-30 transition-opacity duration-200 cursor-pointer"
                                               :class="(isSelectionMode || localSelectedIds.has(img.id)) ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none md:group-hover:opacity-100 md:group-hover:pointer-events-auto'"
                                               @click.stop="toggleSelection(img)"
                                           >
                                               <div
                                               class="ts-photo-selection-indicator w-5 h-5 rounded-full border flex items-center justify-center transition-all duration-200 backdrop-blur-sm shadow-sm"
                                               :class="localSelectedIds.has(img.id) ? 'bg-primary-500 border-primary-500' : 'bg-black/10 border-white/70 hover:bg-black/40'"
                                               >
                                               <Check v-if="localSelectedIds.has(img.id)" class="w-3 h-3 text-white" />
                                               </div>
                                           </div>
                                           
                                           <!-- Selected Overlay -->
                                           <div 
                                               v-if="localSelectedIds.has(img.id)"
                                               class="absolute inset-0 bg-black/10 z-10 pointer-events-none"
                                           ></div>
                                        
                                        <!-- "+N" Overlay for last collapsed photo when more photos exist -->
                                        <div 
                                            v-if="idx === getMomentPhotos(day.key).length - 1 && getPhotos(day.key).length > getMomentPhotos(day.key).length && !expandedDays.has(day.key)"
                                            class="absolute inset-0 bg-black/50 flex items-center justify-center cursor-pointer"
                                            @click.stop="toggleExpand(day.key)"
                                        >
                                            <span class="text-white text-xl font-medium">+{{ getPhotos(day.key).length - getMomentPhotos(day.key).length }}</span>
                                        </div>
                                    </div>
                                </template>
                            </div>

                            <!-- Collapse Button -->
                            <div v-if="expandedDays.has(day.key) && getPhotos(day.key).length > getMomentPhotos(day.key).length" class="mt-2 mb-2">
                                <span class="text-sm text-[#576b95] dark:text-primary-400 cursor-pointer hover:opacity-80" @click="toggleExpand(day.key)">收起</span>
                            </div>
                            
                            <!-- Date & Action -->
                            <div class="flex items-center justify-between text-xs text-gray-400 dark:text-gray-500 mt-2">
                                <div class="flex items-center gap-2 min-w-0">
                                    <span class="flex-shrink-0">{{ day.year }}-{{ String(day.month).padStart(2, '0') }}-{{ String(day.day).padStart(2, '0') }}</span>
                                    <template v-if="dayLocations[day.key]?.locations?.length">
                                        <span class="flex-shrink-0" aria-hidden="true">·</span>
                                        <span
                                            class="truncate text-[#576b95] dark:text-primary-400"
                                            :title="dayLocations[day.key].locations.map(l => l.name).join(' · ')"
                                        >{{ dayLocations[day.key].locations.map(l => l.name).join(' · ') }}</span>
                                    </template>
                                </div>
                                <div class="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-700 flex-shrink-0">
                                    <MoreHorizontal class="w-4 h-4" />
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Photos Grid (Standard) -->
                    <div 
                        v-if="layoutMode !== 'moments'"
                        data-testid="photo-grid"
                        :class="layoutMode === 'waterfall' ? 'flex flex-wrap' : 'grid w-full'" 
                        :style="layoutMode === 'waterfall' ? { gap: gap + 'px' } : {
                            gridTemplateColumns: `repeat(${dayColumns(day)}, minmax(0, 1fr))`,
                            gap: gap + 'px'
                        }"
                    >
                        <!-- Top Spacer -->
                        <div v-if="getRange(day.key).topH > 0" 
                             :style="layoutMode === 'waterfall' ? { width: '100%', height: getRange(day.key).topH + 'px' } : { gridColumn: '1 / -1', height: getRange(day.key).topH + 'px' }">
                        </div>

                        <!-- Actual Photos -->
                        <template v-if="getPhotos(day.key).length > 0">
                            <div
                                v-for="img in getPhotos(day.key).slice(getRange(day.key).start, getRange(day.key).end)"
                                :key="img.id"
                                :data-photo-id="img.id"
                                class="lm-photo relative group overflow-hidden cursor-pointer flex items-center justify-center"
                                :class="{
                                  'rounded-lg': !useSquareMobileThumbnails,
                                  'rounded-none': useSquareMobileThumbnails,
                                  'aspect-square bg-gray-100 dark:bg-gray-800': layoutMode === 'grid',
                                  'aspect-[3/2] bg-gray-100 dark:bg-gray-800': layoutMode === 'masonry',
                                  'flex-grow bg-gray-100 dark:bg-gray-800': layoutMode === 'waterfall',
                                  'shrink-animation grayscale opacity-70': pendingRemoveIds.has(img.id)
                                }"
                                :style="layoutMode === 'waterfall' ? {
                                    height: rowHeight + 'px',
                                    width: (img.width && img.height ? (img.width / img.height * rowHeight) : (rowHeight * 1.5)) + 'px',
                                    minWidth: '50px',maxWidth: '400px'
                                } : {}"
                                @click="handlePhotoClick(img, $event)"
                                @contextmenu="openContextMenu(img, $event)"
                                @vue:mounted="loadImage(img)"
                                @vue:unmounted="cancelImageLoad(img.id)"
                            >
                                <img
                                    :src="loadedImages[img.id] || placeholderSrc"
                                    class="lm-photo-img w-full h-full object-cover"
                                    :class="loadedImages[img.id] ? 'is-developed' : ''"
                                    :alt="img.filename"
                                />
                                
                                <!-- Selection Checkbox (Top Left) -->
                                <div
                                    class="lm-photo-check absolute top-2 left-2 z-30 cursor-pointer"
                                    :class="(isSelectionMode || localSelectedIds.has(img.id)) ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none md:group-hover:opacity-100 md:group-hover:pointer-events-auto'"
                                    @click.stop="toggleSelection(img)"
                                >
                                    <div
                                    class="lm-photo-check-dot ts-photo-selection-indicator"
                                    :class="localSelectedIds.has(img.id) ? 'is-checked' : ''"
                                    >
                                    <Check v-if="localSelectedIds.has(img.id)" class="w-3.5 h-3.5 text-white" />
                                    </div>
                                </div>
                                
                                <!-- Selected Overlay (Darken) -->
                                <div 
                                    v-if="localSelectedIds.has(img.id)"
                                    class="absolute inset-0 bg-black/10 z-10 pointer-events-none"
                                ></div>
                                <!-- Video Indicator (List View) -->
                                <span v-if="img.panorama_projection" class="lm-photo-badge absolute top-2 left-10 z-10">360°</span>
                                <div v-if="img.file_type === 'video'" class="lm-photo-badge absolute top-2 right-2 z-10">
                                  <span class="text-[11px]">{{ img.duration }}</span>
                                  <PlayCircle class="w-3.5 h-3.5" />
                                </div>
                                <div v-else-if="img.file_type === 'live_photo'" class="absolute top-2 right-2 z-10 pointer-events-none">
                                    <span class="icon-[tabler--live-photo] w-4 h-4 text-white drop-shadow-md opacity-90"></span>
                                </div>
                                <!-- Info Overlay：指针停留时浮现的一条说明 -->
                                <div class="lm-photo-info absolute inset-x-0 bottom-0 z-20">
                                    <p class="lm-photo-name">
                                      {{ img.filename || formatTime(img.timestamp) }}
                                    </p>
                                    <slot name="overlay-actions" :photo="img"></slot>
                                </div>
                            </div>
                        </template>

                        <!-- Placeholders for missing photos -->
                         <template v-else>
                             <div
                                v-for="n in (getRange(day.key).end - getRange(day.key).start)"
                                :key="`ph-${day.key}-${getRange(day.key).start + n}`"
                                class="aspect-[3/2] bg-gray-50 dark:bg-gray-900/50 rounded-lg animate-pulse"
                            ></div>
                         </template>

                         <!-- Bottom Spacer -->
                        <div v-if="getRange(day.key).bottomH > 0" 
                             :style="{ gridColumn: '1 / -1', height: getRange(day.key).bottomH + 'px' }">
                        </div>
                    </div>
                </template>
            </div>
        </template>
        <template v-else>
            <!-- Invisible Placeholder -->
             <div class="w-full h-full bg-gray-50/50 dark:bg-gray-900/20 rounded-lg border border-transparent"></div>
        </template>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="totalHeight === 0 && !loading && !error" class="flex flex-col items-center justify-center py-20 text-gray-400">
        <slot name="empty">
          <ImageIcon class="w-16 h-16 mb-4 opacity-20" />
          <p>暂无照片</p>
        </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ref, computed, watch, onMounted, onUnmounted, nextTick, toRef, reactive
} from 'vue'
import { CalendarDays, PlayCircle, Image as ImageIcon, MapPin, Check, Loader2, MoreHorizontal, Sparkles, Pencil, RotateCcw, Brain, ChevronDown } from 'lucide-vue-next'
import { format } from 'date-fns'
import { timelineParts } from '@/utils/photoTimeline'
import { aspectOf, flyPhotoIntoViewer } from '@/utils/photoFlight'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import { useUserStore } from '@/stores/user'
import { toServerUrl } from '@/config/server'
import type { TimelineStats, AlbumImage } from '@/types/album'
import { useVirtualLayout, type MonthBlock, type DayBlock } from '@/composables/useVirtualLayout'
import { getMomentPhotos as selectMomentPhotos, getMomentSinglePhotoSize } from '@/utils/momentLayout'
import { useSelection } from '@/composables/useSelection'
import { useSwipeSelect } from '@/composables/useSwipeSelect'
import { useScroll } from '@vueuse/core'
import PersonSelector from './PersonSelector.vue'
import PhotoBatchActionBar from './PhotoBatchActionBar.vue'
import PhotoContextMenu from './PhotoContextMenu.vue'
import { usePhotoBatchActions } from '@/composables/usePhotoBatchActions'
import GalleryChrome from './GalleryChrome.vue'
import { chapterApi } from '@/api/chapter'
import {
  MOBILE_GRID_COLUMNS,
  getMobileDateHeaderMode,
  getMobileGridGap,
  getNearestMobileGridColumns,
} from '@/utils/photoGridLayout'

// Props
interface Props {
  singleSelect?: boolean
  photos: AlbumImage[]
  active?: boolean
  timelineStats?: TimelineStats
  loading?: boolean
  hasMore?: boolean
  layoutMode?: 'grid' | 'masonry' | 'waterfall' | 'list' | 'moments'
  viewSize?: 'sm' | 'md' | 'lg'
  groupByDate?: boolean
  deleteLabel?: string
  // 「从相册/人物中移除」菜单项的文案；非空时主删除按钮由外部恢复为默认「删除」
  removeLabel?: string
  activeDate?: string // v-model
  pendingRemoveIds?: Set<string>
  error?: string | null
  store?: any
  scrollContainer?: HTMLElement | null,
  showActionBar?: boolean
  // moments 布局下的日文案外部注入。key 为 day.key（同 groupedPhotos 中的 dayKey 格式）
  dayCaptions?: Record<string, { caption: string; source?: string; streaming?: boolean; updated_at?: string; reasoning?: string }>
  // moments 布局下每天的位置（景区优先 → city → district → province，实时聚合不落库）。
  // key 为 day.key（同 groupedPhotos 中的 dayKey 格式，月/日不补零）
  dayLocations?: Record<string, { primary: string; level: string; locations: Array<{ name: string; level: string; count: number }> }>
  // moments 布局下每天的"精选照片 ID 列表"（服务端已做相似去重 + 分数排序，顺序即展示顺序）。
  // key 为 day.key（同 groupedPhotos 中的 dayKey 格式，月/日不补零）
  // 未提供 / 空数组 时，moments 布局回退到"当天前 9 张"的原始行为。
  dayHighlights?: Record<string, { photoIds: string[]; totalCandidates?: number }>
  // 是否显示 moments 布局中的 AI 文案区（生成/编辑/清除按钮）
  showMomentCaption?: boolean
  loadingDays?: Set<string>
}

const props = withDefaults(defineProps<Props>(), {
  layoutMode: 'masonry',
  viewSize: 'md',
  active: true,
  groupByDate: true,
  deleteLabel: '删除',
  removeLabel: '',
  loading: false,
  hasMore: false,
  pendingRemoveIds: () => new Set(),
  error: null,
  showActionBar: true,
  dayCaptions: () => ({}),
  dayLocations: () => ({}),
  dayHighlights: () => ({}),
  showMomentCaption: false,
  loadingDays: () => new Set()
})

const emit = defineEmits(['click-photo', 'load-more', 'load-range', 'update:activeDate', 'batch-delete', 'remove-association', 'add-to-album', 'remove-from-album', 'set-album-cover', 'retry', 'selection-change', 'transfer', 'batch-edit-time', 'batch-edit-location', 'generate-caption', 'save-caption', 'clear-caption', 'visible-months-change'])

// --- Selection State ---
const {
  isSelectionMode,
  selectedIds: localSelectedIds,
  selectionAnchorId,
  enterSelectionMode,
  exitSelectionMode,
  toggleSelect: toggleSelectionId,
  selectAll: selectAllIds,
  selectRange: selectRangeIds,
  isSelected
} = useSelection()

// Sync selection with parent if needed
watch(() => Array.from(localSelectedIds), () => {
  emit('selection-change', Array.from(localSelectedIds))
})


const photoStore = usePhotoStore()
const userStore = useUserStore()
const store = computed(() => props.store || photoStore)
const chapterLinks = ref<Record<string, Array<{ id: string; title: string }>>>({})

// --- Image Loading Logic ---
const loadedImages = reactive<Record<string, string>>({})
const placeholderSrc = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

// Assign the URL directly to <img>. The previous probe fetch did not consume
// its body and then caused <img> to request the same thumbnail a second time.
const loadImage = (image: AlbumImage) => {
    loadedImages[image.id] = image.thumbnail
}

const cancelImageLoad = (imageId: string) => {
    delete loadedImages[imageId]
}
watch(() => props.photos, photos => {
    for (const photo of photos) {
        if (loadedImages[photo.id] && loadedImages[photo.id] !== photo.thumbnail) loadImage(photo)
    }
})

// Ensure cleanup on component unmount
onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    if (resizeObserver) resizeObserver.disconnect()
    if (scrollFrame) cancelAnimationFrame(scrollFrame)
    stopGridPinch()
    cancelSwipeSelect()
    if (suppressGridClickTimer) clearTimeout(suppressGridClickTimer)
})
// --- End Image Loading Logic ---

// --- Virtual Scroll & Layout ---
const galleryEl = ref<HTMLElement | null>(null)
const virtualContentEl = ref<HTMLElement | null>(null)
const containerWidth = ref(1000)

const scrollContainerRef = ref<HTMLElement | Window | null>(null)
const { y: containerScrollTop } = useScroll(scrollContainerRef)

const scrollTop = computed(() => containerScrollTop.value)

// Month block coordinates are relative to the virtual content, which may sit
// below a page header or an album introduction inside the scroll container.
const virtualContentTop = () => {
  const container = scrollContainerRef.value
  const viewportTop = container && container !== window
    ? (container as HTMLElement).getBoundingClientRect().top
    : 0
  return scrollTop.value + (virtualContentEl.value?.getBoundingClientRect().top ?? 0) - viewportTop
}

const viewportHeight = ref(window.innerHeight)

const handleResize = () => {
  const container = scrollContainerRef.value
  if (container && container !== window) {
    viewportHeight.value = (container as HTMLElement).clientHeight
  } else {
    viewportHeight.value = window.innerHeight
  }
  updateVisibleBlocks()
}

watch(scrollContainerRef, (container, _, onCleanup) => {
  if (container && container !== window) {
    viewportHeight.value = (container as HTMLElement).clientHeight
    const ro = new ResizeObserver(handleResize)
    ro.observe(container as HTMLElement)
    onCleanup(() => ro.disconnect())
  } else {
    viewportHeight.value = window.innerHeight
  }
}, { immediate: true })

// 父级可能传入一个挂载后才就绪的内部滚动容器（如 PhotoSelector 在弹窗内的 scrollContainer），
// 此时 onMounted 里拿到的还是 null，会错误地回退到 window / <main>，
// 导致弹窗内滚动时 scrollTop 不更新、虚拟列表只渲染首屏、向下滚动出现空白。
// 这里在 prop 真正就绪后再切换过去。
watch(() => props.scrollContainer, (c) => {
  if (c) {
    scrollContainerRef.value = c
    nextTick(() => updateVisibleBlocks())
  }
})

const expandedDays = ref(new Set<string>())

const toggleExpand = (dayKey: string) => {
    if (expandedDays.value.has(dayKey)) {
        expandedDays.value.delete(dayKey)
    } else {
        expandedDays.value.add(dayKey)
    }
    // trigger recalculate
    expandedDays.value = new Set(expandedDays.value)
}

const getGridColumns = (dayKey: string, isExpanded: boolean) => {
    const count = isExpanded ? getPhotos(dayKey).length : getMomentPhotos(dayKey).length
    if (isExpanded && count > 9) {
        // 向右展开，移动端最小80px，PC端最小120px
        const minWidth = window.innerWidth < 640 ? '80px' : '120px'
        return `repeat(auto-fill, minmax(${minWidth}, 1fr))`
    }
    if (count === 1) return 'auto'
    if (count === 4) return 'repeat(2, minmax(0, 1fr))'
    return 'repeat(3, minmax(0, 1fr))'
}

// 单图渲染和虚拟列表预留高度共用同一尺寸计算。
const singlePhotoBoxStyle = (img: { width?: number; height?: number }) => {
  const { width, height } = getMomentSinglePhotoSize(img)
  return { width: `${width}px`, height: `${height}px` }
}

const getGridMaxWidth = (dayKey: string, isExpanded: boolean) => {
    const count = isExpanded ? getPhotos(dayKey).length : getMomentPhotos(dayKey).length
    if (isExpanded && count > 9) {
        return '100%' // 占满剩余可用空间
    }
    if (count === 1) return 'min(100%, 240px)'
    if (count === 4) return 'min(100%, 240px)' // 2列
    return 'min(100%, 360px)' // 3列
}

// iOS Photos-style grid density pinch. Spreading fingers makes thumbnails
// larger; pinching inward reveals more photos in each row.
const GRID_COLUMNS_STORAGE_KEY = 'trailsnap_mobile_grid_columns'
const storedGridColumns = Number(localStorage.getItem(GRID_COLUMNS_STORAGE_KEY))
const mobileGridColumns = ref<number | null>(
  MOBILE_GRID_COLUMNS.includes(storedGridColumns as typeof MOBILE_GRID_COLUMNS[number])
    ? storedGridColumns
    : null,
)
const isGridPinching = ref(false)
const suppressGridClick = ref(false)
let pinchStartDistance = 0
let pinchStartColumns = 3
let pinchAnchorId = ''
let pinchAnchorViewportTop = 0
let pinchAnchorDayKey = ''
let pinchAnchorIndex = 0
let pinchAnchorCenterY = 0
let pinchFrame = 0
let suppressGridClickTimer: ReturnType<typeof setTimeout> | null = null

const suppressClickAfterGesture = () => {
  suppressGridClick.value = true
  if (suppressGridClickTimer) clearTimeout(suppressGridClickTimer)
  suppressGridClickTimer = setTimeout(() => {
    suppressGridClick.value = false
    suppressGridClickTimer = null
  }, 350)
}

// 移动端滑选：长按进入选择模式（沿用原语义），不松手继续拖动即按视觉顺序
// 整段选择/取消；选择模式内再次长按已选中照片拖动则整段取消。
const applySwipeSelection = (photoId: string, shouldSelect: boolean) => {
  if (shouldSelect) localSelectedIds.add(photoId)
  else localSelectedIds.delete(photoId)
  if (localSelectedIds.size > 0 && !isSelectionMode.value) enterSelectionMode()
}

const {
  onTouchstart: startSwipeSelect,
  cancel: cancelSwipeSelect,
} = useSwipeSelect({
  // 仅移动端（<768px）启用；PhotoSelector 弹窗内单选场景只保留长按，不滑选。
  canStart: () => containerWidth.value < 768,
  canSweep: () => !props.singleSelect,
  isSelected: (id) => localSelectedIds.has(id),
  onLongPressActivate: (photoId) => {
    const photo = props.photos.find(item => item.id === photoId)
    if (!photo) return
    toggleSelection(photo)
    navigator.vibrate?.(10)
  },
  onSwipePhoto: (photoId, shouldSelect) => applySwipeSelection(photoId, shouldSelect),
  onSuppressClick: suppressClickAfterGesture,
})

const effectiveGridColumns = computed(() => {
  if (containerWidth.value >= 768 || !['grid', 'masonry'].includes(props.layoutMode)) return null
  return mobileGridColumns.value
})

const effectiveGridGap = computed(() => {
  const columns = effectiveGridColumns.value
  return columns ? getMobileGridGap(columns) : null
})

const mobileDateHeaderMode = computed(() =>
  isSelectionMode.value
    ? 'day'
    : containerWidth.value < 768
    ? getMobileDateHeaderMode(effectiveGridColumns.value ?? colCount.value)
    : 'day',
)
const useSquareMobileThumbnails = computed(() =>
  containerWidth.value < 768 && (effectiveGridColumns.value ?? colCount.value) >= 6,
)
const dateHeaderContainerClass = computed(() => {
  if (mobileDateHeaderMode.value === 'day') return 'lm-day-head--day'
  if (mobileDateHeaderMode.value === 'month') return 'lm-day-head--month'
  return 'lm-day-head--year'
})
const dateHeaderContentClass = computed(() => (mobileDateHeaderMode.value === 'day' ? '' : 'lm-day-date--compact'))

const WEEKDAY_LABELS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
function weekdayText(day: DayBlock) {
  if (!day.year || !day.month || !day.day) return ''
  const date = new Date(day.year, day.month - 1, day.day)
  return Number.isNaN(date.getTime()) ? '' : WEEKDAY_LABELS[date.getDay()]
}

function dayPlace(day: DayBlock) {
  const names = props.dayLocations?.[day.key]?.locations?.map(item => item.name).filter(Boolean) ?? []
  return names.slice(0, 2).join(' · ')
}

/* 正方形/自适应布局始终按列数排版，保证画框尺寸一致。 */
function dayColumns(_day: DayBlock) {
  return colCount.value || 1
}

const shouldShowDateHeader = (day: DayBlock, dayIndex: number) => {
  if (day.year === 0) return Boolean(props.timelineStats?.timeline?.some(item => item.year === 0))
  if (mobileDateHeaderMode.value === 'day') return true
  if (dayIndex !== 0) return false
  if (mobileDateHeaderMode.value === 'month') return true
  const blockIndex = monthBlocks.value.findIndex(block => block.key === `${day.year}-${day.month}`)
  return blockIndex === 0 || monthBlocks.value[blockIndex - 1]?.year !== day.year
}
const isYearStart = (day: DayBlock) => {
  if (store.value?.currentContext?.type !== 'all') return false
  const blockIndex = monthBlocks.value.findIndex(block => block.key === `${day.year}-${day.month}`)
  return blockIndex >= 0 && (blockIndex === 0 || monthBlocks.value[blockIndex - 1]?.year !== day.year)
    && monthBlocks.value[blockIndex]?.days[0]?.key === day.key
}

const touchDistance = (touches: TouchList) => Math.hypot(
  touches[1].clientX - touches[0].clientX,
  touches[1].clientY - touches[0].clientY,
)

const visiblePhotoRects = () => new Map(
  Array.from(galleryEl.value?.querySelectorAll<HTMLElement>('[data-photo-id]') ?? [])
    .map(element => [element.dataset.photoId ?? '', element.getBoundingClientRect()] as const),
)

const animateGridReflow = (before: Map<string, DOMRect>) => {
  requestAnimationFrame(() => {
    for (const element of Array.from(galleryEl.value?.querySelectorAll<HTMLElement>('[data-photo-id]') ?? [])) {
      const previous = before.get(element.dataset.photoId ?? '')
      if (!previous) continue
      const current = element.getBoundingClientRect()
      const scaleX = previous.width / current.width
      const scaleY = previous.height / current.height
      element.getAnimations().forEach(animation => animation.cancel())
      element.animate([
        {
          transform: `translate3d(${previous.left - current.left}px, ${previous.top - current.top}px, 0) scale(${scaleX}, ${scaleY})`,
          transformOrigin: 'top left',
        },
        { transform: 'translate3d(0, 0, 0) scale(1)', transformOrigin: 'top left' },
      ], {
        duration: 280,
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
      })
    }
  })
}

const setGridScrollTop = (top: number) => {
  const container = scrollContainerRef.value
  if (container && container !== window) {
    ;(container as HTMLElement).scrollTop = top
  } else {
    window.scrollTo({ top, behavior: 'auto' })
  }
}

const restoreGridPinchAnchor = () => {
  const anchorId = pinchAnchorId
  const block = monthBlocks.value.find(month => month.days.some(day => day.key === pinchAnchorDayKey))
  const day = block?.days.find(item => item.key === pinchAnchorDayKey)
  if (!block || !day) return
  const container = scrollContainerRef.value
  const viewportTop = container && container !== window
    ? (container as HTMLElement).getBoundingClientRect().top
    : 0
  const galleryContentTop = scrollTop.value + (galleryEl.value?.getBoundingClientRect().top ?? 0) - viewportTop
  const row = Math.floor(pinchAnchorIndex / Math.max(1, colCount.value))
  const anchorLocalTop = block.top + day.top + getDateHeaderHeight(day, block)
    + row * (rowHeight.value + gap.value)
    + rowHeight.value / 2
  const targetTop = galleryContentTop + anchorLocalTop - (pinchAnchorCenterY - viewportTop)
  setGridScrollTop(Math.max(0, targetTop))

  requestAnimationFrame(() => {
    updateVisibleBlocks()
    requestAnimationFrame(() => {
    const anchor = galleryEl.value?.querySelector<HTMLElement>(`[data-photo-id="${CSS.escape(anchorId)}"]`)
    if (!anchor) return
    const delta = anchor.getBoundingClientRect().top - pinchAnchorViewportTop
    setGridScrollTop(Math.max(0, scrollTop.value + delta))
    })
  })
}

const applyGridPinch = (distance: number) => {
  pinchFrame = 0
  if (!pinchStartDistance) return
  const nextColumns = getNearestMobileGridColumns(pinchStartColumns * pinchStartDistance / distance)
  if (mobileGridColumns.value === nextColumns) return

  const before = visiblePhotoRects()
  mobileGridColumns.value = nextColumns
  localStorage.setItem(GRID_COLUMNS_STORAGE_KEY, String(nextColumns))
  nextTick(() => {
    recalculateLayout()
    restoreGridPinchAnchor()
    animateGridReflow(before)
  })
}

const handleGridTouchMove = (event: TouchEvent) => {
  if (!isGridPinching.value || event.touches.length !== 2) return
  event.preventDefault()
  const distance = touchDistance(event.touches)
  if (!pinchFrame) pinchFrame = requestAnimationFrame(() => applyGridPinch(distance))
}

const stopGridPinch = () => {
  if (!isGridPinching.value) return
  isGridPinching.value = false
  pinchStartDistance = 0
  if (pinchFrame) cancelAnimationFrame(pinchFrame)
  pinchFrame = 0
  window.removeEventListener('touchmove', handleGridTouchMove)
  window.removeEventListener('touchend', stopGridPinch)
  window.removeEventListener('touchcancel', stopGridPinch)

  suppressClickAfterGesture()
}

const handleGridTouchStart = (event: TouchEvent) => {
  if (event.touches.length === 1) {
    startSwipeSelect(event)
    return
  }
  cancelSwipeSelect()
  if (event.touches.length !== 2 || containerWidth.value >= 768) return
  if (!['grid', 'masonry'].includes(props.layoutMode) || isSelectionMode.value) return

  event.preventDefault()
  isGridPinching.value = true
  pinchStartDistance = touchDistance(event.touches)
  pinchStartColumns = effectiveGridColumns.value ?? colCount.value

  const centerX = (event.touches[0].clientX + event.touches[1].clientX) / 2
  const centerY = (event.touches[0].clientY + event.touches[1].clientY) / 2
  const anchor = document.elementFromPoint(centerX, centerY)?.closest<HTMLElement>('[data-photo-id]')
  pinchAnchorId = anchor?.dataset.photoId ?? ''
  pinchAnchorViewportTop = anchor?.getBoundingClientRect().top ?? centerY
  pinchAnchorCenterY = centerY
  const anchorDay = anchor?.closest<HTMLElement>('.day-block')
  pinchAnchorDayKey = anchorDay?.dataset.dayKey ?? ''
  pinchAnchorIndex = Math.max(0, getPhotos(pinchAnchorDayKey).findIndex(photo => photo.id === pinchAnchorId))

  window.addEventListener('touchmove', handleGridTouchMove, { passive: false })
  window.addEventListener('touchend', stopGridPinch)
  window.addEventListener('touchcancel', stopGridPinch)
}

const handleGridClickCapture = (event: MouseEvent) => {
  if (!suppressGridClick.value) return
  event.preventDefault()
  event.stopPropagation()
}

const layoutOptions = {
    timelineStats: toRef(props, 'timelineStats'),
    containerWidth,
    layoutMode: toRef(props, 'layoutMode'),
    viewSize: toRef(props, 'viewSize'),
    columnCount: effectiveGridColumns,
    gridGap: effectiveGridGap,
    dateHeaderMode: mobileDateHeaderMode,
    photos: toRef(props, 'photos'),
    expandedDays,
    dayCaptions: toRef(props, 'dayCaptions'),
    dayHighlights: toRef(props, 'dayHighlights')
}

const { monthBlocks, totalHeight, getVisibleBlocks, recalculateLayout, colCount, rowHeight, gap } = useVirtualLayout(layoutOptions)

watch(() => [...new Set(monthBlocks.value.map(block => block.year))].sort().join(','), async value => {
  if (!value || store.value?.currentContext?.type !== 'all') { chapterLinks.value = {}; return }
  try { chapterLinks.value = await chapterApi.yearLinks(value.split(',').map(Number)) }
  catch { chapterLinks.value = {} }
}, { immediate: true })

const getDateHeaderHeight = (day: DayBlock, block: MonthBlock) => {
  if (!shouldShowDateHeader(day, block.days.indexOf(day))) return 0
  if (mobileDateHeaderMode.value === 'day') return 50
  return mobileDateHeaderMode.value === 'month' ? 34 : 38
}

// Visible Blocks Calculation
const visibleBlockKeys = ref(new Set<string>())
// Map<dayKey, { start: number, end: number, topH: number, bottomH: number }>
const visibleDayRanges = ref(new Map<string, { start: number, end: number, topH: number, bottomH: number }>())
// We keep a reference to visible blocks for active date calculation
const visibleBlocksList = ref<MonthBlock[]>([])

const getRange = (key: string) => {
  return visibleDayRanges.value.get(key) || { start: 0, end: 0, topH: 0, bottomH: 0 }
}

const updateVisibleBlocks = () => {
    if (!props.active || !galleryEl.value?.isConnected || !galleryEl.value.clientWidth) return
    const buffer = 1000 // Month Buffer
    const relativeScrollTop = scrollTop.value - virtualContentTop()
    const visibleMonths = getVisibleBlocks(relativeScrollTop, viewportHeight.value, buffer)
    visibleBlocksList.value = visibleMonths

    const newMonthKeys = new Set<string>()
    const newDayRanges = new Map<string, { start: number, end: number, topH: number, bottomH: number }>()

    // Dynamic Buffer for Rows: (hn + 2 + 2) * wn -> 2 rows buffer
    // But here we calculate based on pixels
    const rHeight = rowHeight.value || 200
    const rGap = gap.value || 0
    const rowUnit = rHeight + rGap
    const rowBuffer = rowUnit * 2 
    
    const startY = relativeScrollTop - rowBuffer
    const endY = relativeScrollTop + viewportHeight.value + rowBuffer

    visibleMonths.forEach(m => {
        newMonthKeys.add(m.key)
        
        // Check Days visibility
        m.days.forEach(d => {
            // Calculate absolute top of the day block
            const dayTopAbs = m.top + d.top
            const dayBottomAbs = dayTopAbs + d.height
            
            // Check if day is within buffer
            if (dayBottomAbs > startY && dayTopAbs < endY) {
                // Calculate visible rows within the day
                // The photos start after the header
                const photosTopAbs = dayTopAbs + getDateHeaderHeight(d, m)
                
                // Relative to photos start
                const relStart = startY - photosTopAbs
                const relEnd = endY - photosTopAbs
                
                if (props.layoutMode === 'waterfall' || props.layoutMode === 'moments') {
                     // In waterfall and moments modes, disable row virtualization within day for simplicity
                     newDayRanges.set(d.key, { start: 0, end: d.count, topH: 0, bottomH: 0 })
                } else {
                    let startRow = Math.floor(relStart / rowUnit)
                    let endRow = Math.ceil(relEnd / rowUnit)
                    
                    // Clamp rows
                    startRow = Math.max(0, startRow)
                    endRow = Math.min(d.rows, endRow) // d.rows is total rows in day
                    
                    if (startRow < d.rows && endRow > 0) {
                         const startIndex = startRow * colCount.value
                         const endIndex = Math.min(d.count, endRow * colCount.value)
                         
                         const topH = startRow * rowUnit
                         const bottomH = Math.max(0, d.rows - endRow) * rowUnit
                         
                         newDayRanges.set(d.key, { start: startIndex, end: endIndex, topH, bottomH })
                    }
                }
            }
        })
    })

    if (newMonthKeys.size !== visibleBlockKeys.value.size || visibleMonths.some(month => !visibleBlockKeys.value.has(month.key))) {
        visibleBlockKeys.value = newMonthKeys
    }
    const previousRanges = visibleDayRanges.value
    if (newDayRanges.size !== previousRanges.size || Array.from(newDayRanges).some(([key, range]) => {
        const previous = previousRanges.get(key)
        return !previous || previous.start !== range.start || previous.end !== range.end
            || previous.topH !== range.topH || previous.bottomH !== range.bottomH
    })) {
        visibleDayRanges.value = newDayRanges
    }
}

let scrollFrame = 0
const updateScrollViewport = () => {
    scrollFrame = 0
    if (!props.active) return
    updateVisibleBlocks()
    // Update active date based on first visible block
    if (visibleBlocksList.value.length > 0) {
        const center = scrollTop.value - virtualContentTop() + viewportHeight.value / 2
        const current = visibleBlocksList.value.find(b => {
             return (b.top <= center) && (b.top + b.height >= center)
        }) || visibleBlocksList.value[0]
        const dateStr = current.year ? `${current.year}年${String(current.month).padStart(2, '0')}月` : '时间未知'
        if (props.activeDate !== dateStr) {
            emit('update:activeDate', dateStr)
        }
    }
}

// Keep the virtual window current during continuous wheel and touch scrolling.
watch(scrollTop, () => {
    if (!scrollFrame && props.active) scrollFrame = requestAnimationFrame(updateScrollViewport)
})

// Watch for layout changes to update visibility immediately
watch(monthBlocks, updateVisibleBlocks, { flush: 'post' })

// Resize Observer for Container Width
let resizeObserver: ResizeObserver | null = null
onMounted(() => {
    if (props.scrollContainer) {
      scrollContainerRef.value = props.scrollContainer
    } else {
      const mainEl = galleryEl.value?.closest('main')
      if (mainEl && window.getComputedStyle(mainEl).overflowY === 'auto') {
        scrollContainerRef.value = mainEl
      } else {
        scrollContainerRef.value = window
      }
    }

    window.addEventListener('resize', handleResize)
    if (galleryEl.value) {
        containerWidth.value = galleryEl.value.clientWidth
        resizeObserver = new ResizeObserver((entries) => {
            const entry = entries[0]
            if (entry) {
                containerWidth.value = entry.contentRect.width
                recalculateLayout()
                updateVisibleBlocks()
            }
        })
        resizeObserver.observe(galleryEl.value)
    }
    // The scroll target and its viewport height are committed by the time this runs.
    void nextTick(handleResize)
})

// --- Data Fetching Logic ---
const checkAndLoadVisibleMonths = (refresh = false) => {
    if (!props.active) return
    const context = store.value.currentContext
    const albumId = context.type === 'album' ? context.id : undefined
    visibleBlocksList.value.forEach(block => {
        const key = `${block.year}-${block.month}`
        // Check if we have photos for this month
        // store uses "YYYY-MM" format in loadPhotosByMonth
        // Note: hasPhotos(key) checks props.photos. 
        if (!hasPhotosForMonth(key) || store.value.isPartialPhotoMonth?.(block.year, block.month) || refresh) {
             store.value.loadPhotosByMonth(block.year, block.month, albumId, refresh)
        }
    })
}

watch([visibleBlockKeys, () => props.layoutMode, () => props.showMomentCaption], () => {
    checkAndLoadVisibleMonths()
    // 广播当前可见月份，用于外部按月批量拉取附加数据（如朋友圈日文案）
    if (props.layoutMode === 'moments' && props.showMomentCaption) {
        const months = visibleBlocksList.value.map(b => ({ year: b.year, month: b.month }))
        emit('visible-months-change', months)
    }
}, { deep: true, immediate: true })


// --- Photo Grouping ---
const groupedPhotos = computed(() => {
    const map = new Map<string, AlbumImage[]>()
    
    // Check if we are in dummy mode (no timeline stats)
    // If no timeline stats provided, we assume flat list mode
    // We check if monthBlocks has 'all' key (which comes from useVirtualLayout handling)
    // But monthBlocks is derived from useVirtualLayout.
    // A simpler check is if timelineStats prop is missing/empty
    if (!props.timelineStats?.timeline) {
         // Create a single group with key 'all'
         // We must filter out invalid dates if needed, but for 'all' we take everything
         map.set('all', props.photos)
         return map
    }

    // Group by Day Key: YYYY-MM-DD
    props.photos.forEach(p => {
        const dayKey = timelineParts(p.timestamp).dayKey
        if (!map.has(dayKey)) map.set(dayKey, [])
        map.get(dayKey)!.push(p)
    })
    return map
})

const hasPhotosForMonth = (monthKey: string) => {
    // If flat mode, we don't load by month
    if (!props.timelineStats?.timeline) return true
    
    const block = monthBlocks.value.find(b => b.key === monthKey)
    if (!block || block.count === 0) return true // No need to load
    // Check if we have at least one photo for this month
    return props.photos.some(p => {
        const d = new Date(p.timestamp)
        return (Number.isFinite(p.timestamp) ? `${d.getFullYear()}-${d.getMonth() + 1}` : '0-0') === monthKey
    })
}

const getPhotos = (dayKey: string) => {
    return groupedPhotos.value.get(dayKey) || []
}

/**
 * moments 布局折叠态展示的精选照片。
 * 有 dayHighlights 则按后端顺序返回；否则回退为当天前 9 张。
 */
const getMomentPhotos = (dayKey: string) => {
    return selectMomentPhotos(getPhotos(dayKey), props.dayHighlights?.[dayKey]?.photoIds)
}

// --- Interaction Helpers ---
const scrollToDate = (date: string, behavior: ScrollBehavior = 'smooth') => {
    // date format "YYYY年MM月" or "YYYY-MM-DD"
    if (date === '时间未知') {
      const photo = props.photos.find(p => !Number.isFinite(p.timestamp))
      if (photo) void scrollToPhoto(photo)
      return
    }
    const dayMatch = date.match(/(\d+)-(\d+)-(\d+)/)
    const match = dayMatch || date.match(/(\d+)年(\d+)月/) || date.match(/(\d+)-(\d+)/)
    if (match) {
        const year = parseInt(match[1])
        const month = parseInt(match[2])
        const block = monthBlocks.value.find(b => b.year === year && b.month === month)
        if (block) {
            const day = dayMatch ? block.days.find(item => item.day === parseInt(dayMatch[3])) : null
            const targetTop = Math.max(0, virtualContentTop() + block.top + (day?.top ?? 0) - 80)
            const container = scrollContainerRef.value
            if (container && container !== window) {
                (container as HTMLElement).scrollTo({ top: targetTop, behavior })
            } else {
                window.scrollTo({ top: targetTop, behavior })
            }
        }
    }
}

watch(() => props.active, async active => {
    if (!active) return
    await nextTick()
    if (galleryEl.value?.clientWidth) containerWidth.value = galleryEl.value.clientWidth
    recalculateLayout()
    updateVisibleBlocks()
    checkAndLoadVisibleMonths()
})

const scrollToPhoto = async (photo: AlbumImage, viewportTop?: number) => {
    await nextTick()
    if (galleryEl.value?.clientWidth) containerWidth.value = galleryEl.value.clientWidth
    recalculateLayout()
    const parts = timelineParts(photo.timestamp)
    const block = monthBlocks.value.find(b => b.year === parts.year && b.month === parts.month)
    const day = block?.days.find(d => d.key === parts.dayKey)
    if (!block || !day) return
    const index = Math.max(0, getPhotos(parts.dayKey).findIndex(p => p.id === photo.id))
    const row = Math.floor(index / Math.max(1, colCount.value))
    const container = scrollContainerRef.value
    const mainTop = container && container !== window ? (container as HTMLElement).getBoundingClientRect().top : 0
    const headerHeight = Number.parseFloat(getComputedStyle(galleryEl.value!).getPropertyValue('--photo-page-header-height')) || 80
    const targetViewport = Math.max(viewportTop ?? 0, mainTop + headerHeight + 12)
    const rowTop = props.layoutMode === 'waterfall' || props.layoutMode === 'moments'
      ? day.height * index / Math.max(1, day.count) : row * (rowHeight.value + gap.value)
    const targetTop = Math.max(0, virtualContentTop() + block.top + day.top + getDateHeaderHeight(day, block) + rowTop - (targetViewport - mainTop))
    ;(container || window).scrollTo({ top: targetTop, behavior: 'auto' })
    updateVisibleBlocks()
    await nextTick()
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    const element = galleryEl.value?.querySelector<HTMLElement>(`[data-photo-id="${CSS.escape(photo.id)}"]`)
    if (element) {
      ;(container || window).scrollBy({ top: element.getBoundingClientRect().top - targetViewport, behavior: 'auto' })
      element.tabIndex = -1
      element.focus({ preventScroll: true })
      element.animate?.([{ outline: '3px solid var(--theme-primary)', outlineOffset: '2px' }, { outline: '3px solid transparent', outlineOffset: '2px' }], { duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 800 })
    }
}

const formatTime = (ts: number) => Number.isFinite(ts) ? format(new Date(ts), 'yyyy-MM-dd HH:mm') : '时间未知'

// Selection Helpers


/*
const enterSelectionMode = (photo?: AlbumImage) => {
  // if (photo) localSelectedIds.value.add(photo.id) // Hover doesn't select automatically usually
  // But legacy code did. Let's keep manual selection.
  isSelectionMode.value = true
}
*/

/*
const exitSelectionMode = () => {
  isSelectionMode.value = false
  localSelectedIds.clear()
  emit('selection-change', [])
}
*/

const toggleSelection = (photo: AlbumImage) => {
  if (props.singleSelect && !localSelectedIds.has(photo.id)) localSelectedIds.clear()
  toggleSelectionId(photo.id)
  // 普通点击移动 Shift 范围选择的锚点
  selectionAnchorId.value = photo.id
  if (localSelectedIds.size > 0) {
      if (!isSelectionMode.value) enterSelectionMode()
  } else {
      // exitSelectionMode() // Don't auto exit usually
  }
}

// 按各日期实际展示的卡片顺序取范围，包含虚拟滚动视口之外的卡片。
const orderedPhotoIds = computed(() => monthBlocks.value.flatMap(block =>
  block.days.flatMap(day => {
    const photos = props.layoutMode === 'moments' && !expandedDays.value.has(day.key)
      ? getMomentPhotos(day.key)
      : getPhotos(day.key)
    return photos.map(photo => photo.id)
  }),
))

// PC 端 Shift 点击范围选择/取消选择：从锚点到点击照片整段置为单一状态。
// 未进入选择模式时同样可用（整段直接置为选中并进入选择模式）。
// Shift 点击本身不移动锚点（与 macOS Finder 一致）：连续 Shift 点击同一段
// 会在「整段选中/整段取消」间切换；普通点击才移动锚点。
const handleRangeClick = (photo: AlbumImage) => {
  if (props.singleSelect) return false
  const targetSelected = localSelectedIds.has(photo.id)
  if (!isSelectionMode.value && !targetSelected) enterSelectionMode()
  selectRangeIds(orderedPhotoIds.value, photo.id)
  return true
}

const isDaySelected = (day: DayBlock) => {
    const photos = getPhotos(day.key)
    if (photos.length === 0) return false
    return photos.every(p => localSelectedIds.has(p.id))
}

const toggleDaySelection = (day: DayBlock) => {
    const photos = getPhotos(day.key)
    if (photos.length === 0) return

    const allSelected = isDaySelected(day)
    const ids = photos.map(p => p.id)
    
    if (allSelected) {
        ids.forEach(id => localSelectedIds.delete(id))
        if (localSelectedIds.size === 0) exitSelectionMode()
    } else {
        ids.forEach(id => localSelectedIds.add(id))
        enterSelectionMode()
    }
}

const contextMenu = ref<InstanceType<typeof PhotoContextMenu> | null>(null)
const openContextMenu = (photo: AlbumImage, event: MouseEvent) => {
  if (props.showActionBar && !props.singleSelect) void contextMenu.value?.open(event, photo)
  else event.preventDefault()
}

const { isDownloading, isAddingPerson, showPersonSelector, openPersonSelector, handlePersonSelected, handleDownload, downloadPhotos } = usePhotoBatchActions({
  selectedIds: () => localSelectedIds,
  photos: () => props.photos,
  clearSelection: () => exitSelectionMode(),
  exitAfterDownload: true,
})

const handlePhotoClick = (photo: AlbumImage, event?: MouseEvent) => {
  if (isSelectionMode.value) {
    // PC 端 Shift 点击走范围选择（整段置为同一状态），普通点击仍是单张 toggle
    if (event?.shiftKey && handleRangeClick(photo)) return
    toggleSelection(photo)
    return
  }
  // Shift 点击快速范围选择：无需先进入选择模式
  if (event?.shiftKey && handleRangeClick(photo)) return
  // Only still images can be carried across the screen; videos keep their
  // player's own entrance.
  if (photo.file_type && photo.file_type !== 'image' && photo.file_type !== 'live_photo') {
    emit('click-photo', photo)
    return
  }
  flyPhotoIntoViewer(event?.currentTarget as HTMLElement | null, aspectOf(photo.width, photo.height), () => emit('click-photo', photo))
}

const isAllSelected = computed(() => {
    return props.photos.length > 0 && props.photos.every(p => localSelectedIds.has(p.id))
})

const toggleSelectAll = () => {
    if (isAllSelected.value) {
        exitSelectionMode()
    } else {
        const ids = props.photos.map(p => p.id)
        selectAllIds(ids)
        enterSelectionMode()
    }
}

const editingCaptionDay = ref<string | null>(null)
const captionDraft = ref('')
// 思考过程折叠态：默认展开，用户可点击折叠以专注看正文；生成结束 reasoning 清空后整块自动消失。
const collapsedReasoningDays = ref<Set<string>>(new Set())
const toggleReasoningCollapse = (dayKey: string) => {
  const next = new Set(collapsedReasoningDays.value)
  if (next.has(dayKey)) next.delete(dayKey)
  else next.add(dayKey)
  collapsedReasoningDays.value = next
}

// 思考过程滚动容器 ref（按天）：打字机效果——光标始终跟在最新文字后面，
// 容器随文字增长自动滚到底，保证尾部光标可见。
const reasoningScrollEls = new Map<string, HTMLElement>()
const setReasoningRef = (dayKey: string, el: any) => {
  if (el) reasoningScrollEls.set(dayKey, el as HTMLElement)
  else reasoningScrollEls.delete(dayKey)
}
const scrollReasoningToBottom = (dayKey: string) => {
  const el = reasoningScrollEls.get(dayKey)
  if (!el) return
  // 仅当用户已贴近底部时跟随滚动，避免抢走向上翻阅已生成思考的用户
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  if (nearBottom) el.scrollTop = el.scrollHeight
}
watch(() => props.dayCaptions, () => {
  for (const dayKey of Object.keys(props.dayCaptions)) {
    const c = props.dayCaptions[dayKey]
    if (c && c.streaming && c.reasoning) {
      nextTick(() => scrollReasoningToBottom(dayKey))
    }
  }
}, { deep: true })

/**
 * 判断某一天的照片是否至少有一张具备真实拍摄时间。
 * 后端 `_fetch_day_photos` 只把 `photo_time IS NOT NULL` 的照片纳入计算，
 * 如果这一天前端展示的照片全部靠 upload_time / Date.now() 兜底进入分组，
 * 后端会认为「这一天没有照片」并抛错。此时应禁用 AI 生成，
 * 但仍然允许用户手写文案。
 */
const dayHasPhotoTime = (dayKey: string): boolean => {
    const list = groupedPhotos.value.get(dayKey) || []
    if (list.length === 0) return false
    // 未提供 hasPhotoTime 字段的旧数据视为 true（向后兼容）
    return list.some(p => p.hasPhotoTime !== false)
}

const startEditCaption = (day: DayBlock) => {
    editingCaptionDay.value = day.key
    captionDraft.value = props.dayCaptions[day.key]?.caption || ''
}

const cancelEditCaption = () => {
    editingCaptionDay.value = null
    captionDraft.value = ''
}

const commitEditCaption = (day: DayBlock) => {
    const text = captionDraft.value.trim()
    if (!text) {
        // 视为清除
        emit('clear-caption', { day })
    } else {
        emit('save-caption', { day, text })
    }
    editingCaptionDay.value = null
    captionDraft.value = ''
}

const handleDelete = () => {
    if (localSelectedIds.size === 0) return
    
    const ids = Array.from(localSelectedIds)
    if (props.deleteLabel.includes('移除')) {
        emit('remove-from-album', ids)
    } else {
        emit('batch-delete', ids)
    }
}

defineExpose({
  scrollToDate,
  scrollToPhoto,
  enterSelectionMode,
  exitSelectionMode,
  isSelectionMode,
  updateVisibleBlocks,
  checkAndLoadVisibleMonths
})
</script>

<style scoped>
/* No scrollbar style needed as we use window scroll */
  [data-photo-id] {
    -webkit-touch-callout: none;
    user-select: none;
  }

  /* 已显影动画 */
  .shrink-animation {
    animation: shrink 0.25s forwards ease-in-out;
  }
  
  @keyframes shrink {
    0% { transform: scale(1); }
    100% { transform: scale(0.8); opacity: 0.5; }
  }

  /* ======================================================================
   * Lumen 照片墙
   *
   * 日期：不做成胶囊，而是一把「日期标尺」——大号日号 + 月份星期 + 帧数地点。
   * 画框：圆角、薄投影、指针进入时缓慢推近；说明条从底部浮起。
   * 空白：稀疏的一天用一张日期卡补齐整行。
   * ==================================================================== */
  .lm-day-head {
    display: flex;
    align-items: center;
    gap: 14px;
    margin: 0 0 8px;
    transition: opacity 200ms ease;
  }
  .lm-day-head--day { height: 50px; }
  .lm-day-head--month { height: 34px; }
  .lm-day-head--year { height: 38px; }

  .lm-day-date {
    display: flex;
    min-width: 0;
    align-items: baseline;
    gap: 10px;
    border-radius: 12px;
    padding: 2px 10px 2px 2px;
    color: var(--ts-color-text);
    transition: background-color 160ms ease;
  }
  .lm-day-date.is-selectable { cursor: pointer; }
  .lm-day-date.is-selectable:hover { background: var(--ts-color-surface-muted); }

  .lm-day-num {
    color: var(--ts-color-text);
    font-family: var(--lm-font-display);
    font-size: 26px;
    font-weight: 700;
    line-height: 1;
    letter-spacing: -.05em;
    font-variant-numeric: tabular-nums;
  }

  .lm-day-copy { display: flex; min-width: 0; flex-direction: column; gap: 1px; }
  .lm-day-month {
    color: var(--ts-color-text-secondary);
    font-size: 11px;
    font-weight: 650;
    letter-spacing: .12em;
    white-space: nowrap;
  }
  .lm-day-sub {
    overflow: hidden;
    color: var(--ts-color-text-tertiary);
    font-size: 11px;
    font-weight: 500;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .lm-day-unknown { font-size: 13px; font-weight: 650; letter-spacing: .06em; }
  .lm-day-date--compact { padding: 2px 12px; }
  .lm-day-date--compact .lm-day-month { font-size: 12px; color: var(--ts-color-text); }

  /* 标尺：从日期延伸出去的一条极淡的线 */
  .lm-day-rule {
    height: 1px;
    flex: 1;
    background: linear-gradient(to right, var(--ts-color-border), transparent 88%);
  }

  .lm-day-check {
    display: flex;
    width: 20px;
    height: 20px;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    align-self: center;
    border: 1.5px solid var(--ts-color-border);
    border-radius: 999px;
    transition: background-color 160ms ease, border-color 160ms ease;
  }
  .lm-day-check.is-checked { background: var(--theme-primary); border-color: var(--theme-primary); }

  .lm-day-chapter {
    align-self: center;
    border-radius: 999px;
    border: 1px solid var(--ts-color-border);
    padding: 2px 9px;
    color: var(--ts-color-text-secondary);
    font-size: 10.5px;
    font-weight: 650;
    white-space: nowrap;
  }
  .lm-day-chapter:hover { background: var(--ts-color-surface-muted); color: var(--ts-color-text); }
  .lm-day-chapter-link { display: block; border-radius: 10px; padding: 8px 10px; font-size: 13px; color: var(--ts-color-text); }
  .lm-day-chapter-link:hover { background: var(--ts-color-surface-muted); }

  /* ——— 画框 ——— */
  /* 圆角由模板的 rounded-lg / rounded-none（高密度方形模式）控制，这里不再覆写。 */
  .lm-photo {
    background: var(--ts-color-surface-muted);
    box-shadow: var(--ts-shadow-photo);
    transition: transform 320ms var(--ts-ease-paper), box-shadow 320ms var(--ts-ease-paper);
    contain: paint;
  }
  .lm-photo-img { transition: transform 760ms var(--ts-ease-paper); }
  @media (hover: hover) and (pointer: fine) {
    .lm-photo:hover { transform: translate3d(0, -2px, 0); box-shadow: var(--ts-shadow-floating); z-index: 5; }
    .lm-photo:hover .lm-photo-img { transform: scale(1.045); }
  }
  .lm-photo:active { transform: scale(.994); }

  .lm-photo-check { transition: opacity 180ms ease; }
  .lm-photo-check-dot {
    display: flex;
    width: 22px;
    height: 22px;
    align-items: center;
    justify-content: center;
    border: 1.5px solid rgb(255 255 255 / 78%);
    border-radius: 999px;
    background: rgb(10 12 16 / 18%);
    box-shadow: 0 1px 4px rgb(0 0 0 / 22%);
    -webkit-backdrop-filter: var(--ts-photo-check-filter, blur(6px));
    backdrop-filter: var(--ts-photo-check-filter, blur(6px));
    transition: background-color 160ms ease, border-color 160ms ease, transform 160ms var(--ts-ease-spring);
  }
  .lm-photo-check:hover .lm-photo-check-dot { transform: scale(1.08); background: rgb(10 12 16 / 34%); }
  .lm-photo-check-dot.is-checked { background: var(--theme-primary); border-color: var(--theme-primary); }

  .lm-photo-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border-radius: 999px;
    padding: 3px 8px;
    background: rgb(10 12 16 / 52%);
    color: #fff;
    font-size: 10.5px;
    font-weight: 650;
    line-height: 1.2;
    pointer-events: none;
    -webkit-backdrop-filter: blur(8px);
    backdrop-filter: blur(8px);
  }

  .lm-photo-info {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 8px;
    padding: 22px 10px 9px;
    background: linear-gradient(to top, rgb(6 8 12 / 70%), transparent);
    opacity: 0;
    transform: translateY(6px);
    transition: opacity 240ms ease, transform 300ms var(--ts-ease-paper);
    pointer-events: none;
  }
  @media (hover: hover) and (pointer: fine) {
    .lm-photo:hover .lm-photo-info { opacity: 1; transform: translateY(0); }
    .lm-photo:focus-within .lm-photo-info { opacity: 1; transform: none; }
  }
  .lm-photo-name {
    overflow: hidden;
    color: rgb(255 255 255 / 92%);
    font-size: 11.5px;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 767px) {
    .lm-day-head { margin-bottom: 6px; gap: 8px; }
    .lm-day-head--day { height: 46px; }
    .lm-day-date { gap: 8px; padding-right: 8px; }
    .lm-day-num { font-size: 23px; }
    .lm-day-sub { display: none; }
    .lm-photo-info { opacity: 0; }
  }

  @media (prefers-reduced-motion: reduce) {
    .lm-photo, .lm-photo-img, .lm-photo-info, .lm-day-date { transition: none !important; }
  }
</style>
