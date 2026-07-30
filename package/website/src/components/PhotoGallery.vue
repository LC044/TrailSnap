<template>
  <div class="photo-gallery min-h-screen relative" ref="galleryEl">
    <!-- Skeleton Loader (Initial Load) -->
    <GalleryChrome :loading="loading" :error="error" :photos="photos" @retry="$emit('retry')" />

    <!-- Batch Action Bar -->
    <transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform -translate-y-full opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform -translate-y-full opacity-0"
    >
      <div v-if="isSelectionMode && showActionBar" class="fixed bottom-[20px] left-0 right-0 z-40 flex justify-center pointer-events-none px-4">
        <div class="bg-white/90 dark:bg-gray-900/90 backdrop-blur-md border border-gray-200 dark:border-gray-700 shadow-lg rounded-full px-3 py-1 md:py-1 flex items-center gap-2 sm:gap-6 pointer-events-auto min-w-fit max-w-full overflow-x-auto scrollbar-hide">
          <div class="flex items-center gap-1 md:gap-3 flex-shrink-0">
            <button @click="exitSelectionMode" class="p-1.5 sm:p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors dark:text-gray-300 bg-transparent" title="取消选择">
              <X class="w-5 h-5 text-gray-600 dark:text-gray-300" />
            </button>
            <span class="font-medium text-gray-900 dark:text-white whitespace-nowrap text-sm sm:text-base">
              <span class="sm:hidden">{{ localSelectedIds.size }}</span>
              <span class="hidden sm:inline">已选 {{ localSelectedIds.size }} 项</span>
            </span>
          </div>

          <div class="h-6 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>

          <div class="flex items-center gap-1 sm:gap-2 flex-nowrap">
            <button @click="toggleSelectAll" class="p-2 sm:px-3 sm:py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors bg-transparent" :title="isAllSelected ? '取消全选' : '全选'">
              <span class="hidden sm:inline">{{ isAllSelected ? '取消全选' : '全选' }}</span>
              <CheckSquare class="w-5 h-5 sm:hidden" />
            </button>
            
            <button
                @click="$emit('add-to-album', Array.from(localSelectedIds))"
                :disabled="localSelectedIds.size === 0"
                class="bg-transparent flex items-center gap-2 p-2 sm:px-4 sm:py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                title="添加到相册"
                >
                <ImagePlusIcon class="w-5 h-5" />
            </button>

            <!-- Download Action -->
            <button
              @click="handleDownload"
              :disabled="localSelectedIds.size === 0 || isDownloading"
              class="bg-transparent p-2 text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed relative group"
              title="保存到本地"
            >
              <Loader2 v-if="isDownloading" class="w-5 h-5 animate-spin" />
              <Download v-else class="w-5 h-5" />
            </button>

            <!-- Delete/Remove Action -->
            <button 
              @click="handleDelete" 
              :disabled="localSelectedIds.size === 0"
              class="bg-transparent p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              :title="deleteLabel"
            >
              <Trash2 class="w-5 h-5" />
            </button>

            <!-- More Actions -->
            <el-dropdown trigger="click" placement="top-end">
              <button class="bg-transparent p-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
                <MoreHorizontal class="w-5 h-5" />
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="openPersonSelector">
                    <div class="flex items-center gap-2">
                      <UserPlus class="w-4 h-4" />
                      <span>添加到人物</span>
                    </div>
                  </el-dropdown-item>

                  <el-dropdown-item 
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('transfer', 'move', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <FolderOutput class="w-4 h-4" />
                        <span>移动到目录</span>
                     </div>
                  </el-dropdown-item>
                  
                  <el-dropdown-item 
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('transfer', 'copy', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <Copy class="w-4 h-4" />
                        <span>复制到目录</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item 
                    v-if="store?.currentContext?.type === 'album'"
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('remove-from-album', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <ImageMinusIcon class="w-4 h-4" />
                        <span>移出相册</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item
                    v-if="store?.currentContext?.type === 'album' && localSelectedIds.size===1"
                    @click="$emit('set-album-cover', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <ImageIcon class="w-4 h-4" />
                        <span>设为封面</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('batch-edit-location', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <MapPin class="w-4 h-4" />
                        <span>批量修正位置</span>
                     </div>
                  </el-dropdown-item>

                  <div class="border-t border-gray-100 dark:border-gray-800 my-1 mx-2" v-if="$slots['batch-actions']"></div>
                  <slot name="batch-actions" :selected-ids="localSelectedIds" :clear-selection="exitSelectionMode"></slot>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>
    </transition>

    <PersonSelector 
      v-model:visible="showPersonSelector"
      :submitting="isAddingPerson"
      @select="handlePersonSelected"
    />
    <!-- Virtual Scroll Container -->
    <div :style="{ height: totalHeight + 'px', position: 'relative' }">
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
            >
                <template v-if="visibleDayRanges.has(day.key)">
                    <!-- Day Header -->
                    <div v-if="layoutMode !== 'moments'" class="h-[50px] flex items-center mb-0 sticky top-[80px] z-20 py-2 transition-opacity duration-300 pointer-events-none">
                        <div class="flex items-center gap-3 group cursor-pointer text-sm font-bold text-gray-800 dark:text-gray-200 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm px-4 py-1.5 rounded-full shadow-sm border border-gray-100 dark:border-gray-800 flex items-center gap-2 pointer-events-auto cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800" @click="toggleDaySelection(day)">
                             <div 
                                class="w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all duration-200"
                                :class="isDaySelected(day) ? 'bg-primary-500 border-primary-500' : 'border-gray-300 dark:border-gray-600 group-hover:border-primary-400'"
                             >
                                <Check v-if="isDaySelected(day)" class="w-3 h-3 text-white" />
                             </div>
                             <span class="">
                                {{ day.year }}-{{ String(day.month).padStart(2, '0') }}-{{ String(day.day).padStart(2, '0') }}
                             </span>
                            <CalendarDays class="w-4 h-4 text-primary-500" />
                        </div>
                    </div>

                    <!-- Moments Layout Block -->
                    <div v-if="layoutMode === 'moments'" class="flex gap-3 mb-10 md:mb-8 relative">
                        <!-- Avatar placeholder -->
                        <div class="w-10 h-10 rounded-lg bg-gray-200 dark:bg-gray-700 flex-shrink-0 flex items-center justify-center text-gray-400 font-bold overflow-hidden">
                            <img v-if="userStore.userInfo?.avatar" :src="userStore.userInfo.avatar" class="w-full h-full object-cover" />
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
                                         class="relative group bg-gray-100 dark:bg-gray-800 overflow-hidden cursor-pointer rounded-sm"
                                         :class="{
                                             'aspect-square': (expandedDays.has(day.key) ? getPhotos(day.key).length : getMomentPhotos(day.key).length) > 1,
                                             'flex justify-start': (expandedDays.has(day.key) ? getPhotos(day.key).length : getMomentPhotos(day.key).length) === 1
                                         }"
                                         :style="(expandedDays.has(day.key) ? getPhotos(day.key).length : getMomentPhotos(day.key).length) === 1 ? singlePhotoBoxStyle(img) : {}"
                                         @click="handlePhotoClick(img)"
                                         @vue:mounted="loadImage(img)"
                                         @vue:unmounted="cancelImageLoad(img.id)"
                                     >
                                         <img
                                              :src="loadedImages[img.id] || placeholderSrc"
                                              class="w-full h-full transition-opacity duration-300"
                                              :class="(expandedDays.has(day.key) ? getPhotos(day.key).length : getMomentPhotos(day.key).length) === 1 ? 'object-contain object-left' : 'object-cover'"
                                              :alt="img.filename"
                                          />
                                          
                                          <!-- Video/Live Photo Indicators -->
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
                                               class="w-5 h-5 rounded-full border flex items-center justify-center transition-all duration-200 backdrop-blur-sm shadow-sm"
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
                        :class="layoutMode === 'waterfall' ? 'flex flex-wrap' : 'grid w-full'" 
                        :style="layoutMode === 'waterfall' ? { gap: gap + 'px' } : {
                            gridTemplateColumns: `repeat(${colCount}, minmax(0, 1fr))`,
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
                                class="relative group rounded-lg overflow-hidden cursor-pointer transform transition-all duration-300 hover:scale-[1.02] hover:shadow-lg hover:z-10 flex items-center justify-center"
                                :class="{
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
                                @click="handlePhotoClick(img)"
                                @vue:mounted="loadImage(img)"
                                @vue:unmounted="cancelImageLoad(img.id)"
                            >
                                <img
                                    :src="loadedImages[img.id] || placeholderSrc"
                                    class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                                    :alt="img.filename"
                                />
                                
                                <!-- Selection Checkbox (Top Left) -->
                                <div
                                    class="absolute top-2 left-2 z-30 transition-opacity duration-200 cursor-pointer"
                                    :class="(isSelectionMode || localSelectedIds.has(img.id)) ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none md:group-hover:opacity-100 md:group-hover:pointer-events-auto'"
                                    @click.stop="toggleSelection(img)"
                                >
                                    <div
                                    class="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all duration-200 backdrop-blur-sm shadow-sm"
                                    :class="localSelectedIds.has(img.id) ? 'bg-primary-500 border-primary-500' : 'bg-black/10 border-white/70 hover:bg-black/40'"
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
                                <div v-if="img.file_type === 'video'" class="flex mb-1 absolute top-1 right-2 justify-center pointer-events-none z-10 items-center">
                                  <div class="text-white text-sm">
                                    {{ img.duration}}
                                  </div>
                                  <PlayCircle class="w-4 h-4 text-white drop-shadow-md opacity-90" />
                                </div>
                                <div v-else-if="img.file_type === 'live_photo'" class="flex mb-1 absolute top-2 right-2 justify-center pointer-events-none z-10 items-center">
                                    <span class="icon-[tabler--live-photo] w-4 h-4 text-white drop-shadow-md opacity-90"></span>
                                </div>
                                <!-- Info Overlay -->
                                <div class="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/60 to-transparent opacity-0 md:group-hover:opacity-100 transition-opacity duration-300 flex justify-between items-end">
                                    <p class="text-white text-xs font-medium truncate flex items-center gap-1">
                                      <MapPin v-if="img.filename" class="w-3 h-3 text-white/80" />
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
    <div v-if="totalHeight === 0 && !loading" class="flex flex-col items-center justify-center py-20 text-gray-400">
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
import { ElMessageBox, ElMessage } from 'element-plus'
import { CalendarDays, PlayCircle, Image as ImageIcon, MapPin, Check, X, Download, Trash2, FolderMinus, Loader2, PlaySquare, Play, PlayIcon, PlayCircleIcon, Plus, FolderPlus, PhoneOutgoingIcon, PictureInPicture, CloverIcon, ImageMinusIcon, ImagePlusIcon, Aperture, MoreHorizontal, UserPlus, CheckSquare, FolderOutput, Copy, Sparkles, Pencil, RotateCcw } from 'lucide-vue-next'
import { format } from 'date-fns'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import { useUserStore } from '@/stores/user'
import type { TimelineStats, AlbumImage } from '@/types/album'
import { useVirtualLayout, type MonthBlock, type DayBlock } from '@/composables/useVirtualLayout'
import { useSelection } from '@/composables/useSelection'
import { useWindowScroll, useScroll, useDebounceFn } from '@vueuse/core'
import PersonSelector from './PersonSelector.vue'
import GalleryChrome from './GalleryChrome.vue'
import { faceApi } from '@/api/face'
import { photoApi } from '@/api/photo'

// Props
interface Props {
  photos: AlbumImage[]
  timelineStats?: TimelineStats
  loading?: boolean
  hasMore?: boolean
  layoutMode?: 'grid' | 'masonry' | 'waterfall' | 'list' | 'moments'
  viewSize?: 'sm' | 'md' | 'lg'
  groupByDate?: boolean
  deleteLabel?: string
  activeDate?: string // v-model
  pendingRemoveIds?: Set<string>
  error?: string | null
  store?: any
  scrollContainer?: HTMLElement | null,
  showActionBar?: boolean
  // moments 布局下的日文案外部注入。key 为 day.key（同 groupedPhotos 中的 dayKey 格式）
  dayCaptions?: Record<string, { caption: string; source?: string; streaming?: boolean; updated_at?: string }>
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
  groupByDate: true,
  deleteLabel: '删除',
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

const emit = defineEmits(['click-photo', 'load-more', 'load-range', 'update:activeDate', 'batch-delete', 'add-to-album', 'remove-from-album', 'set-album-cover', 'retry', 'selection-change', 'transfer', 'batch-edit-location', 'generate-caption', 'save-caption', 'clear-caption', 'visible-months-change'])

    // --- Selection State ---
const { 
  isSelectionMode, 
  selectedIds: localSelectedIds, 
  enterSelectionMode, 
  exitSelectionMode, 
  toggleSelect: toggleSelectionId,
  selectAll: selectAllIds,
  isSelected
} = useSelection()

// Sync selection with parent if needed
watch(() => localSelectedIds.size, () => {
  emit('selection-change', Array.from(localSelectedIds))
})

const isDownloading = ref(false)
const downloadProgress = ref(0)
const isAddingPerson = ref(false)

const photoStore = usePhotoStore()
const userStore = useUserStore()
const store = computed(() => props.store || photoStore)

// --- Image Loading Logic ---
const loadedImages = reactive<Record<string, string>>({})
const imageLoaders = new Map<string, AbortController>()
const placeholderSrc = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
// 缓存Request对象，避免重复创建导致连接重建
const requestCache = new Map<string, Request>();

const loadImage = async (image: AlbumImage) => {
    if (loadedImages[image.id]) return;
    if (imageLoaders.has(image.id)) return;

    // 复用Request对象
    let request = requestCache.get(image.id);
    if (!request) {
        request = new Request(image.thumbnail, {
            method: 'GET',
            headers: {
                'Connection': 'keep-alive'  // 显式要求keep-alive
            }
        });
        requestCache.set(image.id, request);
    }

    const controller = new AbortController();
    imageLoaders.set(image.id, controller);

    try {
      // loadedImages[image.id] = image.thumbnail;
      const response = await fetch(request, { signal: controller.signal });
      if (response.ok) {
          loadedImages[image.id] = image.thumbnail;
      }
    } catch (e: any) {
        if (e.name !== 'AbortError') {
            console.error('Image load failed', e);
        }
    } finally {
        imageLoaders.delete(image.id);
    }
};

const cancelImageLoad = (imageId: string) => {
    const controller = imageLoaders.get(imageId)
    if (controller) {
        controller.abort()
        imageLoaders.delete(imageId)
    }
}

// Ensure cleanup on component unmount
onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    imageLoaders.forEach(c => c.abort())
    imageLoaders.clear()
    if (resizeObserver) resizeObserver.disconnect()
})
// --- End Image Loading Logic ---

// --- Virtual Scroll & Layout ---
const galleryEl = ref<HTMLElement | null>(null)
const containerWidth = ref(1000)

const scrollContainerRef = ref<HTMLElement | Window | null>(null)
const { y: containerScrollTop } = useScroll(scrollContainerRef)

const scrollTop = computed(() => containerScrollTop.value)

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

watch(scrollContainerRef, (container) => {
  if (container && container !== window) {
    viewportHeight.value = (container as HTMLElement).clientHeight
    const ro = new ResizeObserver(handleResize)
    ro.observe(container as HTMLElement)
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
    // 展开态看当天全部照片；折叠态只看精选后的数量
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

// 朋友圈单图：按照片真实比例在 240×250 边界框内计算盒子尺寸，
// 使容器与图片同比例，object-contain 不再留出灰色 letterbox。
const SINGLE_MAX_W = 240
const SINGLE_MAX_H = 250
const singlePhotoBoxStyle = (img: { width?: number; height?: number }) => {
  const w = img?.width
  const h = img?.height
  if (w && h) {
    const ratio = w / h
    let dw = SINGLE_MAX_W
    let dh = SINGLE_MAX_W / ratio
    if (dh > SINGLE_MAX_H) {
      dh = SINGLE_MAX_H
      dw = SINGLE_MAX_H * ratio
    }
    return { width: `${Math.round(dw)}px`, height: `${Math.round(dh)}px` }
  }
  // 无尺寸元数据时退化为固定边界框（object-contain 保比例）
  return { width: `${SINGLE_MAX_W}px`, maxHeight: `${SINGLE_MAX_H}px` }
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

const layoutOptions = {
    timelineStats: toRef(props, 'timelineStats'),
    containerWidth,
    layoutMode: toRef(props, 'layoutMode'),
    viewSize: toRef(props, 'viewSize'),
    photos: toRef(props, 'photos'),
    expandedDays,
    dayCaptions: toRef(props, 'dayCaptions')
}

const { monthBlocks, totalHeight, getVisibleBlocks, recalculateLayout, colCount, rowHeight, gap } = useVirtualLayout(layoutOptions)

// Visible Blocks Calculation
const visibleBlockKeys = ref(new Set<string>())
// Map<dayKey, { start: number, end: number, topH: number, bottomH: number }>
const visibleDayRanges = ref(new Map<string, { start: number, end: number, topH: number, bottomH: number }>())
// We keep a reference to visible blocks for active date calculation
const visibleBlocksList = ref<MonthBlock[]>([])

const DAY_HEADER_HEIGHT = 40

const getRange = (key: string) => {
  return visibleDayRanges.value.get(key) || { start: 0, end: 0, topH: 0, bottomH: 0 }
}

const updateVisibleBlocks = () => {
    const buffer = 1000 // Month Buffer
    const visibleMonths = getVisibleBlocks(scrollTop.value, viewportHeight.value, buffer)
    visibleBlocksList.value = visibleMonths

    const newMonthKeys = new Set<string>()
    const newDayRanges = new Map<string, { start: number, end: number, topH: number, bottomH: number }>()

    // Dynamic Buffer for Rows: (hn + 2 + 2) * wn -> 2 rows buffer
    // But here we calculate based on pixels
    const rHeight = rowHeight.value || 200
    const rGap = gap.value || 0
    const rowUnit = rHeight + rGap
    const rowBuffer = rowUnit * 2 
    
    const startY = scrollTop.value - rowBuffer
    const endY = scrollTop.value + viewportHeight.value + rowBuffer

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
                const photosTopAbs = dayTopAbs + DAY_HEADER_HEIGHT
                
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

    visibleBlockKeys.value = newMonthKeys
    visibleDayRanges.value = newDayRanges
}

// Throttle scroll updates
const handleScroll = useDebounceFn(() => {
    updateVisibleBlocks()
    // Update active date based on first visible block
    if (visibleBlocksList.value.length > 0) {
        const center = scrollTop.value + viewportHeight.value / 2
        const current = visibleBlocksList.value.find(b => {
             return (b.top <= center) && (b.top + b.height >= center)
        }) || visibleBlocksList.value[0]
        const dateStr = `${current.year}年${String(current.month).padStart(2, '0')}月`
        if (props.activeDate !== dateStr) {
            emit('update:activeDate', dateStr)
        }
    }
}, 50, { maxWait: 100 }) // More aggressive update for row virtualization

watch(scrollTop, handleScroll)

// Watch for layout changes to update visibility immediately
watch(monthBlocks, () => {
    updateVisibleBlocks()
    checkAndLoadVisibleMonths()
}, { deep: true })

// Resize Observer for Container Width
let resizeObserver: ResizeObserver | null = null
onMounted(() => {
    if (props.scrollContainer) {
      scrollContainerRef.value = props.scrollContainer
    } else {
      const mainEl = document.querySelector('main')
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
    updateVisibleBlocks()
    setTimeout(() => {
      updateVisibleBlocks()
    }, 1000);
})

// --- Data Fetching Logic ---
const checkAndLoadVisibleMonths = (refresh = false) => {
    const context = store.value.currentContext
    const albumId = context.type === 'album' ? context.id : undefined
    visibleBlocksList.value.forEach(block => {
        const key = `${block.year}-${block.month}`
        // Check if we have photos for this month
        // store uses "YYYY-MM" format in loadPhotosByMonth
        // Note: hasPhotos(key) checks props.photos. 
        if (!hasPhotosForMonth(key) || refresh) {
             store.value.loadPhotosByMonth(block.year, block.month, albumId, refresh)
        }
    })
}

watch(visibleBlockKeys, () => {
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
        const d = new Date(p.timestamp)
        const dayKey = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
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
        return `${d.getFullYear()}-${d.getMonth() + 1}` === monthKey
    })
}

const getPhotos = (dayKey: string) => {
    return groupedPhotos.value.get(dayKey) || []
}

/**
 * moments 布局下"折叠态"要展示的精选照片列表。
 *
 * - 若 props.dayHighlights[dayKey] 提供了 photoIds：按该顺序在当天已加载的照片里过滤取值
 *   （视频等未被后端选中的照片自然被排除）；
 * - 若未提供 / 空数组：回退到当天前 9 张，保持精选接口挂了/未加载时的兜底行为。
 *
 * 不做数量截断（截断由后端 limit 完成），如果后端给了 15 张这里就展示 15 张。
 */
const getMomentPhotos = (dayKey: string) => {
    const ids = props.dayHighlights?.[dayKey]?.photoIds
    if (ids && ids.length > 0) {
        const all = getPhotos(dayKey)
        const idSet = new Set(ids)
        const byId = new Map(all.filter(p => idSet.has(p.id)).map(p => [p.id, p]))
        // 按 ids 顺序（后端已排好序）恢复展示顺序，避免受本地 groupedPhotos 顺序影响
        const ordered: AlbumImage[] = []
        ids.forEach(id => {
            const p = byId.get(id)
            if (p) ordered.push(p)
        })
        return ordered
    }
    return getPhotos(dayKey).slice(0, 9)
}

// --- Interaction Helpers ---
const scrollToDate = (date: string) => {
    // date format "YYYY年MM月" or "YYYY-MM-DD"
    const match = date.match(/(\d+)年(\d+)月/) || date.match(/(\d+)-(\d+)/)
    if (match) {
        const year = parseInt(match[1])
        const month = parseInt(match[2])
        const block = monthBlocks.value.find(b => b.year === year && b.month === month)
        if (block) {
            const container = scrollContainerRef.value
            if (container && container !== window) {
                (container as HTMLElement).scrollTo({ top: block.top + 60, behavior: 'smooth' })
            } else {
                window.scrollTo({ top: block.top + 60, behavior: 'smooth' })
            }
        }
    }
}

const formatTime = (ts: number) => format(new Date(ts), 'yyyy-MM-dd HH:mm')

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
  toggleSelectionId(photo.id)
  if (localSelectedIds.size > 0) {
      if (!isSelectionMode.value) enterSelectionMode()
  } else {
      // exitSelectionMode() // Don't auto exit usually
  }
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

const handlePhotoClick = (photo: AlbumImage) => {
  if (isSelectionMode.value) {
    toggleSelection(photo)
  } else {
    emit('click-photo', photo)
  }
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

const handlePersonSelected = async (person: any) => {
  if (localSelectedIds.size === 0) return
  
  isAddingPerson.value = true
  try {
    const ids = Array.from(localSelectedIds)
    const res = await faceApi.addPhotosToIdentity(person.id, ids)
    ElMessage.success(`成功添加 ${res.count} 张照片到 ${person.identity_name}`)
    showPersonSelector.value = false
    exitSelectionMode()
  } catch (e: any) {
    console.error(e)
    ElMessage.error('添加失败')
  } finally {
    isAddingPerson.value = false
  }
}

const showPersonSelector = ref(false)

const openPersonSelector = () => {
  showPersonSelector.value = true
}

// --- Moment Caption Editing State（moments 布局） ---
const editingCaptionDay = ref<string | null>(null)
const captionDraft = ref('')

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

const handleDownload = async () => {
  if (localSelectedIds.size === 0) return

  isDownloading.value = true
  downloadProgress.value = 0
  
  try {
    const ids = Array.from(localSelectedIds)
    if (ids.length === 1) {
      const photo = props.photos.find(p => p.id === ids[0])
      if (photo) {
        const response = await fetch(photo.url)
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = photo.filename || `photo-${photo.id}.jpg`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        window.URL.revokeObjectURL(url)
      }
    } else {
      await photoApi.batchDownload(ids)
    }
  } catch (error) {
    console.error('Failed to download photo:', error)
  } finally {
    isDownloading.value = false
    downloadProgress.value = 0
    exitSelectionMode()
  }
}

defineExpose({
  scrollToDate,
  enterSelectionMode,
  exitSelectionMode,
  updateVisibleBlocks,
  checkAndLoadVisibleMonths
})
</script>

<style scoped>
/* No scrollbar style needed as we use window scroll */
  /* Existing styles */
  .shrink-animation {
    animation: shrink 0.25s forwards ease-in-out;
  }
  
  @keyframes shrink {
    0% { transform: scale(1); }
    100% { transform: scale(0.8); opacity: 0.5; }
  }
</style>