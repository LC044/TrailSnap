<template>
  <CleanupTaskShell
    title="相似照片清理"
    color="blue"
    :can-rescan="!loading && groups.length > 0"
    :can-bulk-action="groups.length > 0"
    bulk-action-label="保留最佳"
    :is-running="!!task && (task.status === 'pending' || task.status === 'processing')"
    running-title="正在分析相似照片"
    :processed-items="task?.processed_items ?? 0"
    :total-items="task?.total_items ?? 0"
    :show-start="!task || task.status === 'failed' || task.status === 'cancelled'"
    start-icon="👯"
    start-title="开始相似照片分析"
    start-description="系统将扫描您的相册，找出画面高度相似的照片（如连拍），帮助您筛选保留最佳瞬间。"
    :show-empty="task?.status === 'completed' && groups.length === 0"
    empty-title="未发现相似照片分组"
    empty-hint="您的相册很整洁！"
    :task-status="task?.status ?? null"
    :task-error="task?.error ?? null"
    @back="goBack"
    @rescan="startNewScan"
    @bulk-action="handleDeleteAll"
    @cancel="cancelTask"
    @start="startNewScan"
  >
    <!-- Result Content -->
    <div class="flex-1 overflow-y-auto space-y-6 pb-20 scrollbar-hide" ref="containerRef">
        <div v-for="(group, gIndex) in groups" :key="gIndex" class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-100 dark:border-gray-700">
            <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                <span class="text-sm font-medium text-gray-600 dark:text-gray-300">
                    分组 {{ gIndex + 1 }} ({{ group.length }} 张)
                </span>
                <div class="flex items-center gap-3">
                    <button
                        type="button"
                        @click="openComparison(gIndex)"
                        class="rounded-md bg-primary-500 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:focus-visible:ring-offset-gray-800"
                    >
                        <i class="mgc_pic_2_line mr-1"></i>
                        {{ compareGroupIndex === gIndex && comparisonIds.size > 0 ? `开始对比 (${comparisonIds.size}/4)` : '对比照片' }}
                    </button>
                    <button
                        type="button"
                        @click="toggleGroupSelection(gIndex)"
                        class="text-sm text-primary-500 hover:text-primary-600 font-medium focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:focus-visible:ring-offset-gray-800"
                    >
                        {{ isGroupAllSelected(gIndex) ? '取消全选' : '全选' }}
                    </button>
                </div>
            </div>
            
            <!-- Horizontal Scroll Container -->
            <div class="relative group-scroll-container group/scroll">
                 <!-- Scroll Buttons (Desktop) -->
                 <button 
                    v-if="canScrollLeft(gIndex)"
                    @click="scroll(gIndex, -1)"
                    class="absolute left-0 top-1/2 -translate-y-1/2 z-10 p-2 bg-white/90 dark:bg-gray-700/90 rounded-full shadow-md hover:bg-white dark:hover:bg-gray-600 hidden md:flex items-center justify-center text-gray-700 dark:text-gray-200 opacity-0 group-hover/scroll:opacity-100 transition-opacity duration-300"
                 >
                    <i class="mgc_left_line"></i>
                 </button>
                 <button 
                    v-if="canScrollRight(gIndex)"
                    @click="scroll(gIndex, 1)"
                    class="absolute right-0 top-1/2 -translate-y-1/2 z-10 p-2 bg-white/90 dark:bg-gray-700/90 rounded-full shadow-md hover:bg-white dark:hover:bg-gray-600 hidden md:flex items-center justify-center text-gray-700 dark:text-gray-200 opacity-0 group-hover/scroll:opacity-100 transition-opacity duration-300"
                 >
                    <i class="mgc_right_line"></i>
                 </button>

                <div 
                    :ref="el => setScrollRef(el, gIndex)"
                    class="flex gap-4 overflow-x-auto scrollbar-hide snap-x snap-mandatory py-2 px-1"
                    @scroll="updateScrollState(gIndex)"
                >
                    <div 
                        v-for="(photo, pIndex) in group" 
                        :key="photo.id"
                        class="relative flex-shrink-0 w-32 sm:w-40 snap-start"
                    >
                        <!-- Photo Card -->
                        <div 
                            class="relative aspect-square rounded-lg overflow-hidden cursor-pointer border-2 transition-colors bg-gray-100 dark:bg-gray-700"
                            :class="selectedPhotos.has(photo.id) || comparisonIds.has(photo.id) ? 'border-primary-500' : 'border-transparent'"
                            @click="openLightbox(gIndex, pIndex)"
                        >
                            <img 
                                :src="photo.thumbnail" 
                                class="w-full h-full object-cover transition-transform duration-300 hover:scale-105"
                                loading="lazy"
                            />
                            <!-- Best Badge -->
                            <div v-if="pIndex === 0" class="absolute bottom-1 left-1 bg-green-500/90 backdrop-blur-sm text-white text-[10px] px-1.5 py-0.5 rounded shadow-sm">
                                最佳
                            </div>
                            <!-- Selection Checkbox -->
                            <div 
                                class="absolute top-1 left-1 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors z-10"
                                :class="selectedPhotos.has(photo.id) ? 'bg-primary-500 border-primary-500' : 'bg-black/30 border-white hover:bg-black/50'"
                                @click.stop="togglePhotoSelection(photo.id)"
                            >
                                <i v-if="selectedPhotos.has(photo.id)" class="mgc_check_line text-white text-sm"></i>
                            </div>
                            <!-- Video Indicator (List View) -->
                            <div v-if="photo.file_type === 'video'" class="flex mb-1 absolute top-1 right-2 justify-center pointer-events-none z-10 items-center">
                                <div class="text-white text-sm">
                                {{ photo.duration}}
                                </div>
                                <PlayCircle class="w-4 h-4 text-white drop-shadow-md opacity-90" />
                            </div>
                            <div v-else-if="photo.file_type === 'live_photo'" class="flex mb-1 absolute top-2 right-2 justify-center pointer-events-none z-10 items-center">
                                <span class="icon-[tabler--live-photo] w-4 h-4 text-white drop-shadow-md opacity-90"></span>
                            </div>
                        </div>
                        <div class="mt-1.5 px-1">
                            <div class="text-xs text-gray-700 dark:text-gray-300 truncate text-center font-medium">
                                {{ photo.filename }}
                            </div>
                            <button
                                type="button"
                                class="mt-1.5 w-full rounded-md px-2 py-1.5 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:focus-visible:ring-offset-gray-800"
                                :class="compareGroupIndex === gIndex && comparisonIds.has(photo.id)
                                    ? 'bg-primary-500 text-white hover:bg-primary-600'
                                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'"
                                :aria-pressed="compareGroupIndex === gIndex && comparisonIds.has(photo.id)"
                                @click="toggleComparisonPhoto(gIndex, photo.id)"
                            >
                                <i :class="compareGroupIndex === gIndex && comparisonIds.has(photo.id) ? 'mgc_check_line' : 'mgc_add_line'"></i>
                                {{ compareGroupIndex === gIndex && comparisonIds.has(photo.id) ? '已加入对比' : '加入对比' }}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
             <!-- Group Action -->
             <div v-if="getGroupSelectionCount(gIndex) > 0" class="mt-3 flex justify-end border-t border-gray-100 dark:border-gray-700 pt-3">
                <button 
                    type="button"
                    @click="deleteGroupSelection(gIndex)"
                    class="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-1.5 rounded-md hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors flex items-center gap-1 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:focus-visible:ring-offset-gray-800"
                >
                    <i class="mgc_delete_2_line"></i>
                    删除选中 ({{ getGroupSelectionCount(gIndex) }}张)
                </button>
             </div>
        </div>
        
        <!-- Load More Spinner -->
        <div v-if="isLoadingMore" class="flex justify-center py-4">
             <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500"></div>
        </div>
        <div v-if="!hasMore && groups.length > 0" class="text-center text-gray-400 text-sm py-4">
             没有更多了
        </div>
    </div>

    <!-- Photo Lightbox -->
    <PhotoLightbox
        :image="currentLightboxImage"
        :has-prev="lightbox.index > 0"
        :has-next="lightbox.index < lightbox.photos.length - 1"
        :visible="lightbox.show"
        @close="lightbox.show = false"
        @prev="lightbox.index--"
        @next="lightbox.index++"
    />

    <SimilarPhotoCompareDialog
        :visible="comparisonVisible"
        :photos="comparisonPhotos"
        :selected-for-deletion="selectedPhotos"
        @close="comparisonVisible = false"
        @toggle-delete="togglePhotoSelection"
        @remove="removeComparisonPhoto"
        @open-photo="openComparisonLightbox"
    />
  </CleanupTaskShell>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed, onUnmounted } from 'vue';
import { useAppBack } from '@/composables/useAppBack';
import { photoApi } from '@/api/photo';
import type { Task as TaskResponse } from '@/api/tasks'
import type { Photo, AlbumImage } from '@/types/album';
import { ElMessage, ElMessageBox } from 'element-plus';
import PhotoLightbox from '@/components/PhotoLightbox.vue';
import SimilarPhotoCompareDialog from '@/components/SimilarPhotoCompareDialog.vue';
import CleanupTaskShell from '@/components/CleanupTaskShell.vue';
import request from '@/utils/request';
import { mapPhotoToImage } from '@/stores/photoStore'
import { useInfiniteScroll } from '@vueuse/core';

const goBack = useAppBack('/toolbox')

const groups = ref<AlbumImage[][]>([]);
const loading = ref(false);
const error = ref('');
const selectedPhotos = ref<Set<string>>(new Set());
const comparisonIds = ref<Set<string>>(new Set());
const compareGroupIndex = ref<number | null>(null);
const comparisonVisible = ref(false);
const task = ref<TaskResponse | null>(null);
const pollTimer = ref<number | null>(null);

// Pagination
const currentPage = ref(0);
const pageSize = 20;
const hasMore = ref(true);
const containerRef = ref<HTMLElement | null>(null);
const isLoadingMore = ref(false);

useInfiniteScroll(containerRef, async () => {
    if (hasMore.value && !isLoadingMore.value && task.value?.status === 'completed') {
        await loadMore();
    }
}, { distance: 10 });

// Scroll refs and state
const scrollRefs = ref<HTMLElement[]>([]);
const scrollState = reactive<Record<number, { left: boolean; right: boolean }>>({});

const setScrollRef = (el: any, index: number) => {
    if (el) scrollRefs.value[index] = el;
};

const updateScrollState = (index: number) => {
    const el = scrollRefs.value[index];
    if (!el) return;
    scrollState[index] = {
        left: el.scrollLeft > 0,
        right: el.scrollLeft + el.clientWidth < el.scrollWidth - 1 // -1 for rounding
    };
};

const canScrollLeft = (index: number) => scrollState[index]?.left ?? false;
const canScrollRight = (index: number) => scrollState[index]?.right ?? true;

const scroll = (index: number, direction: number) => {
    const el = scrollRefs.value[index];
    if (!el) return;
    const scrollAmount = el.clientWidth * 0.8;
    el.scrollBy({ left: scrollAmount * direction, behavior: 'smooth' });
};

// Data Fetching
const fetchLatestTask = async () => {
    loading.value = true;
    try {
        const latestTask = await photoApi.getLatestSimilarTask();
        task.value = latestTask;
        
        if (latestTask) {
            if (latestTask.status === 'completed') {
                await loadMore(true); // Initial Load
            } else if (['pending', 'processing'].includes(latestTask.status)) {
                startPolling();
            }
        }
    } catch (err) {
        console.error(err);
        error.value = '加载任务状态失败';
    } finally {
        loading.value = false;
    }
};

const loadMore = async (reset = false) => {
    if (!task.value) return;
    if (reset) {
        currentPage.value = 0;
        groups.value = [];
        hasMore.value = true;
    }
    if (!hasMore.value) return;

    isLoadingMore.value = true;
    try {
        const skip = currentPage.value * pageSize;
        const result = await photoApi.getSimilarTaskResult(task.value.id, skip, pageSize);
        
        if (result.length < pageSize) {
            hasMore.value = false;
        }
        
        if (reset) {
            groups.value = result.map(group => group.map(mapPhotoToImage));
        } else {
            groups.value.push(...result.map(group => group.map(mapPhotoToImage)));
        }
        
        currentPage.value++;
        
        // Initialize scroll states for new items
        setTimeout(() => {
            groups.value.forEach((_, i) => updateScrollState(i));
        }, 100);
    } catch (err) {
        console.error(err);
        ElMessage.error('加载更多失败');
    } finally {
        isLoadingMore.value = false;
    }
};

const startNewScan = async () => {
    try {
        const newTask = await photoApi.createSimilarTask(0.9);
        task.value = newTask;
        groups.value = [];
        selectedPhotos.value.clear();
        comparisonIds.value.clear();
        compareGroupIndex.value = null;
        comparisonVisible.value = false;
        hasMore.value = true;
        currentPage.value = 0;
        startPolling();
    } catch (err) {
        console.error(err);
        ElMessage.error('创建任务失败');
    }
};

const startPolling = () => {
    if (pollTimer.value) clearInterval(pollTimer.value);
    pollTimer.value = window.setInterval(async () => {
        if (!task.value) return;
        try {
            const updatedTask = await photoApi.getSimilarTask(task.value.id);
            task.value = updatedTask;
            
            if (updatedTask && updatedTask.status === 'completed') {
                stopPolling();
                await loadMore(true);
                ElMessage.success('分析完成');
            } else if (updatedTask && (updatedTask.status === 'failed' || updatedTask.status === 'cancelled')) {
                stopPolling();
            }
        } catch (err) {
            console.error("Polling error", err);
        }
    }, 2000); // Poll every 2s
};

const stopPolling = () => {
    if (pollTimer.value) {
        clearInterval(pollTimer.value);
        pollTimer.value = null;
    }
};

const cancelTask = async () => {
    if (!task.value) return;
    try {
        await photoApi.cancelSimilarTask(task.value.id);
        task.value.status = 'cancelled'; // Optimistic update
        stopPolling();
        ElMessage.info('任务已取消');
    } catch (err) {
        console.error(err);
        ElMessage.error('取消任务失败');
    }
};

onMounted(() => {
    fetchLatestTask();
});

onUnmounted(() => {
    stopPolling();
});

// Selection Logic (Same as before)
const togglePhotoSelection = (id: string) => {
    if (selectedPhotos.value.has(id)) {
        selectedPhotos.value.delete(id);
    } else {
        selectedPhotos.value.add(id);
    }
};

const comparisonPhotos = computed(() => {
    return groups.value
        .flatMap(group => group)
        .filter(photo => comparisonIds.value.has(photo.id))
        .slice(0, 4);
});

const syncComparisonGroupIndex = () => {
    if (comparisonIds.value.size === 0) {
        compareGroupIndex.value = null;
        return;
    }
    compareGroupIndex.value = groups.value.findIndex(group =>
        group.some(photo => comparisonIds.value.has(photo.id))
    );
    if (compareGroupIndex.value < 0) compareGroupIndex.value = null;
};

const toggleComparisonPhoto = (groupIndex: number, id: string) => {
    if (compareGroupIndex.value !== groupIndex) {
        compareGroupIndex.value = groupIndex;
        comparisonIds.value.clear();
    }

    if (comparisonIds.value.has(id)) {
        comparisonIds.value.delete(id);
        return;
    }

    if (comparisonIds.value.size >= 4) {
        ElMessage.warning('一次最多对比 4 张照片，请先移出一张');
        return;
    }
    comparisonIds.value.add(id);
};

const openComparison = (groupIndex: number) => {
    if (compareGroupIndex.value !== groupIndex || comparisonIds.value.size === 0) {
        compareGroupIndex.value = groupIndex;
        comparisonIds.value.clear();
        groups.value[groupIndex].slice(0, 4).forEach(photo => comparisonIds.value.add(photo.id));
    }
    comparisonVisible.value = comparisonPhotos.value.length > 0;
};

const removeComparisonPhoto = (id: string) => {
    comparisonIds.value.delete(id);
    if (comparisonIds.value.size === 0) comparisonVisible.value = false;
};

const openComparisonLightbox = (photo: AlbumImage) => {
    const index = comparisonPhotos.value.findIndex(item => item.id === photo.id);
    lightbox.photos = comparisonPhotos.value;
    lightbox.index = Math.max(0, index);
    lightbox.show = true;
};

const isGroupAllSelected = (groupIndex: number) => {
    const group = groups.value[groupIndex];
    if (group.length <= 1) return false;
    const redundantPhotos = group.slice(1);
    return redundantPhotos.every(p => selectedPhotos.value.has(p.id));
};

const toggleGroupSelection = (groupIndex: number) => {
    const group = groups.value[groupIndex];
    if (group.length <= 1) return;
    
    const redundantPhotos = group.slice(1);
    const allSelected = redundantPhotos.every(p => selectedPhotos.value.has(p.id));
    
    if (allSelected) {
        redundantPhotos.forEach(p => selectedPhotos.value.delete(p.id));
    } else {
        redundantPhotos.forEach(p => selectedPhotos.value.add(p.id));
    }
};

const getGroupSelectionCount = (groupIndex: number) => {
    const group = groups.value[groupIndex];
    return group.filter(p => selectedPhotos.value.has(p.id)).length;
};

// Delete Logic
const deletePhotos = async (ids: string[]) => {
    try {
        await request.delete('/api/photos/batch', {
            data: { photo_ids: ids }
        });
        
        // Remove from local state
        const idSet = new Set(ids);
        groups.value = groups.value.map(group => group.filter(p => !idSet.has(p.id))).filter(group => group.length > 1);
        
        // Clear selection
        ids.forEach(id => selectedPhotos.value.delete(id));
        ids.forEach(id => comparisonIds.value.delete(id));
        syncComparisonGroupIndex();
        if (comparisonIds.value.size === 0) comparisonVisible.value = false;
        
        ElMessage.success(`成功删除 ${ids.length} 张照片`);
    } catch (err) {
        console.error(err);
        ElMessage.error('删除失败');
    }
};

const deleteGroupSelection = (groupIndex: number) => {
    const group = groups.value[groupIndex];
    const idsToDelete = group.filter(p => selectedPhotos.value.has(p.id)).map(p => p.id);
    if (idsToDelete.length === 0) return;
    
    ElMessageBox.confirm(
        `确定删除选中的 ${idsToDelete.length} 张照片吗？此操作不可恢复。`,
        '确认删除',
        {
            confirmButtonText: '删除',
            cancelButtonText: '取消',
            type: 'warning',
        }
    ).then(() => {
        deletePhotos(idsToDelete);
    });
};

const handleDeleteAll = () => {
    const idsToDelete: string[] = [];
    groups.value.forEach(group => {
        if (group.length > 1) {
            group.slice(1).forEach(p => idsToDelete.push(p.id));
        }
    });
    
    if (idsToDelete.length === 0) return;

    ElMessageBox.confirm(
        `确定删除所有分组的冗余照片（共 ${idsToDelete.length} 张）吗？每个分组将只保留第一张。`,
        '确认删除所有',
        {
            confirmButtonText: '全部删除',
            cancelButtonText: '取消',
            type: 'warning',
        }
    ).then(() => {
        deletePhotos(idsToDelete);
    });
};

// Lightbox Logic
const lightbox = reactive({
    show: false,
    index: 0,
    photos: [] as AlbumImage[]
});



const openLightbox = (groupIndex: number, photoIndex: number) => {
    const group = groups.value[groupIndex];
    lightbox.photos = group;
    lightbox.index = photoIndex;
    lightbox.show = true;
};

const currentLightboxImage = computed(() => {
    return lightbox.photos[lightbox.index] || null;
});

</script>

<style scoped>
.scrollbar-hide::-webkit-scrollbar {
    display: none;
}
.scrollbar-hide {
    -ms-overflow-style: none;
    scrollbar-width: none;
}
</style>
