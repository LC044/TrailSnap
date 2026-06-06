<template>
  <CleanupTaskShell
    title="重复照片清理"
    color="orange"
    :can-rescan="!loading && groups.length > 0"
    :can-bulk-action="groups.length > 0"
    bulk-action-label="一键清理冗余"
    :is-running="!!task && (task.status === 'pending' || task.status === 'processing')"
    running-title="正在扫描重复照片"
    running-hint="系统正在比对照片MD5值，请耐心等待...<br>退出之后任务将在后台继续运行。"
    :processed-items="task?.processed_items ?? 0"
    :total-items="task?.total_items ?? 0"
    :show-start="!loading && groups.length === 0 && (!task || task.status === 'failed' || task.status === 'cancelled')"
    start-icon="🧹"
    start-title="扫描重复照片"
    start-description="系统将扫描您的相册，找出完全相同的照片（MD5一致），帮助您清理多余副本，释放存储空间。"
    :show-empty="!loading && task?.status === 'completed' && groups.length === 0"
    empty-title="未发现重复照片"
    empty-hint="您的相册很整洁，没有多余的副本！"
    :task-status="task?.status ?? null"
    :task-error="task?.error ?? null"
    @back="$router.back()"
    @rescan="startNewScan"
    @bulk-action="handleDeleteAll"
    @cancel="cancelTask"
    @start="startNewScan"
  >
    <!-- Result Content -->
    <div class="flex-1 overflow-y-auto space-y-6 pb-20 scrollbar-hide" ref="containerRef">
        <div v-for="(group, gIndex) in groups" :key="gIndex" class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-100 dark:border-gray-700">
            <div class="flex items-center justify-between mb-3">
                <span class="text-sm font-medium text-gray-600 dark:text-gray-300">
                    重复组 {{ gIndex + 1 }} ({{ group.photos.length }} 张)
                </span>
                <button 
                    @click="toggleGroupSelection(gIndex)"
                    class="text-sm text-primary-500 hover:text-primary-600 font-medium dark:bg-gray-900"
                >
                    {{ isGroupAllSelected(gIndex) ? '取消全选' : '选择冗余项' }}
                </button>
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
                        v-for="(photo, pIndex) in group.photos" 
                        :key="photo.id"
                        class="relative flex-shrink-0 w-32 sm:w-40 snap-start"
                    >
                        <!-- Photo Card -->
                        <div 
                            class="relative aspect-square rounded-lg overflow-hidden cursor-pointer border-2 transition-colors bg-gray-100 dark:bg-gray-700"
                            :class="selectedPhotos.has(photo.id) ? 'border-orange-500' : 'border-transparent'"
                            @click="openLightbox(gIndex, pIndex)"
                        >
                            <img 
                                :src="photo.thumbnail" 
                                class="w-full h-full object-cover transition-transform duration-300 hover:scale-105"
                                loading="lazy"
                            />
                            <!-- Keep Badge -->
                            <div v-if="pIndex === 0" class="absolute bottom-1 left-1 bg-green-500/90 backdrop-blur-sm text-white text-[10px] px-1.5 py-0.5 rounded shadow-sm">
                                建议保留
                            </div>
                            <!-- Selection Checkbox -->
                            <div 
                                class="absolute top-1 left-1 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors z-10"
                                :class="selectedPhotos.has(photo.id) ? 'bg-orange-500 border-orange-500' : 'bg-black/30 border-white hover:bg-black/50'"
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
                        </div>
                        <!-- File Path -->
                        <div v-if="photo.file_path" class="text-xs text-gray-500 dark:text-gray-400 truncate text-center " :title="photo.file_path">
                            {{ photo.file_path }}
                        </div>
                    </div>
                </div>
            </div>
             <!-- Group Action -->
             <div v-if="getGroupSelectionCount(gIndex) > 0" class="mt-3 flex justify-end border-t border-gray-100 dark:border-gray-700 pt-3">
                <button 
                    @click="deleteGroupSelection(gIndex)"
                    class="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-1.5 rounded-md hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors flex items-center gap-1"
                >
                    <i class="mgc_delete_2_line"></i>
                    删除选中 ({{ getGroupSelectionCount(gIndex) }}张)
                </button>
             </div>
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
  </CleanupTaskShell>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed, onUnmounted } from 'vue';
import { tasksApi, type Task } from '@/api/tasks';
import { toolboxApi } from '@/api/toolbox';
import type { AlbumImage } from '@/types/album';
import { ElMessage, ElMessageBox } from 'element-plus';
import { PlayCircle } from 'lucide-vue-next';
import PhotoLightbox from '@/components/PhotoLightbox.vue';
import CleanupTaskShell from '@/components/CleanupTaskShell.vue';
import request from '@/utils/request';
import { mapPhotoToImage } from '@/stores/photoStore';

interface DuplicateGroup {
    md5: string;
    photos: AlbumImage[];
}

const groups = ref<DuplicateGroup[]>([]);
const loading = ref(false);
const error = ref('');
const selectedPhotos = ref<Set<string>>(new Set());
const task = ref<Task | null>(null);
const pollTimer = ref<number | null>(null);
const containerRef = ref<HTMLElement | null>(null);

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
const fetchGroups = async () => {
    loading.value = true;
    try {
        const result = await toolboxApi.getDuplicatePhotos();
        groups.value = result.map(g => ({
            md5: g.md5,
            photos: g.photos.map(mapPhotoToImage)
        }));
        setTimeout(() => {
            groups.value.forEach((_, i) => updateScrollState(i));
        }, 100);
    } catch (err) {
        console.error(err);
        ElMessage.error('加载重复照片列表失败');
    } finally {
        loading.value = false;
    }
};

const startNewScan = async () => {
    try {
        const newTask = await toolboxApi.scanDuplicatePhotos() as unknown as Task;
        task.value = newTask;
        groups.value = [];
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
            const updatedTask = await tasksApi.getTask(task.value.id);
            task.value = updatedTask;
            if (updatedTask && updatedTask.status === 'completed') {
                stopPolling();
                await fetchGroups();
                ElMessage.success('扫描完成');
            } else if (updatedTask && (updatedTask.status === 'failed' || updatedTask.status === 'cancelled')) {
                stopPolling();
            }
        } catch (err) {
            stopPolling();
            await fetchGroups();
            ElMessage.error('扫描失败');
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
        await tasksApi.cancelTask(task.value.id);
        if (task.value) task.value.status = 'cancelled';
        stopPolling();
        ElMessage.info('任务已取消');
    } catch (err) {
        console.error(err);
        ElMessage.error('取消任务失败');
    }
};

onMounted(() => {
    fetchGroups();
});

onUnmounted(() => {
    stopPolling();
});

// Selection Logic
const togglePhotoSelection = (id: string) => {
    if (selectedPhotos.value.has(id)) {
        selectedPhotos.value.delete(id);
    } else {
        selectedPhotos.value.add(id);
    }
};

const isGroupAllSelected = (groupIndex: number) => {
    const group = groups.value[groupIndex].photos;
    if (group.length <= 1) return false;
    const redundantPhotos = group.slice(1);
    return redundantPhotos.every(p => selectedPhotos.value.has(p.id));
};

const toggleGroupSelection = (groupIndex: number) => {
    const group = groups.value[groupIndex].photos;
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
    const group = groups.value[groupIndex].photos;
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
        groups.value = groups.value.map(group => ({
            ...group,
            photos: group.photos.filter(p => !idSet.has(p.id))
        })).filter(group => group.photos.length > 1);
        
        // Clear selection
        ids.forEach(id => selectedPhotos.value.delete(id));
        
        ElMessage.success(`成功删除 ${ids.length} 张重复照片`);
    } catch (err) {
        console.error(err);
        ElMessage.error('删除失败');
    }
};

const deleteGroupSelection = (groupIndex: number) => {
    const group = groups.value[groupIndex].photos;
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
        if (group.photos.length > 1) {
            group.photos.slice(1).forEach(p => idsToDelete.push(p.id));
        }
    });
    
    if (idsToDelete.length === 0) return;

    ElMessageBox.confirm(
        `确定删除所有分组的冗余副本（共 ${idsToDelete.length} 张）吗？每个分组将只保留第一张。`,
        '一键清理冗余',
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
    const group = groups.value[groupIndex].photos;
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
