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
    @back="goBack"
    @rescan="startNewScan"
    @bulk-action="handleDeleteAll"
    @cancel="cancelTask"
    @start="startNewScan"
  >
    <!-- Result Content -->
    <div class="flex-1 space-y-4 overflow-y-auto pb-24 pt-4 scrollbar-hide md:space-y-6 md:pt-2" ref="containerRef">
        <PhotoCleanupGroup v-for="(group, gIndex) in groups" :key="group.md5"
          :title="`重复组 ${gIndex + 1}`" :photos="group.photos"
          :selected-ids="selectedPhotos" :all-selected="isGroupAllSelected(gIndex)"
          first-badge="建议保留" select-label="选择冗余项" show-paths
          @toggle-group="toggleGroupSelection(gIndex)" @toggle-photo="togglePhotoSelection"
          @open-photo="index => openLightbox(gIndex, index)" @delete-selection="deleteGroupSelection(gIndex)"
        >        </PhotoCleanupGroup>
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
import { useAppBack } from '@/composables/useAppBack';
import { tasksApi, type Task } from '@/api/tasks';
import { toolboxApi } from '@/api/toolbox';
import type { AlbumImage } from '@/types/album';
import { ElMessage, ElMessageBox } from 'element-plus';
import PhotoLightbox from '@/components/PhotoLightbox.vue';
import CleanupTaskShell from '@/components/CleanupTaskShell.vue';
import PhotoCleanupGroup from '@/components/PhotoCleanupGroup.vue';
import { photoApi } from '@/api/photo';
import { mapPhotoToImage } from '@/stores/photoStore';

const goBack = useAppBack('/toolbox')

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

// Data Fetching
const fetchGroups = async () => {
    loading.value = true;
    try {
        const result = await toolboxApi.getDuplicatePhotos();
        groups.value = result.map(g => ({
            md5: g.md5,
            photos: g.photos.map(mapPhotoToImage)
        }));
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

const deletePhotos = async (ids: string[]) => {
    try {
        await photoApi.deletePhotos(ids);
        
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
