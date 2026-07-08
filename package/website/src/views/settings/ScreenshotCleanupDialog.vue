<template>
  <el-dialog
    v-model="visible"
    title="截图与表情包清理"
    fullscreen
    custom-class="!m-0 h-full flex flex-col"
    destroy-on-close
    :show-close="true"
    @open="handleOpen"
  >
    <div class="h-full flex flex-col bg-gray-50 dark:bg-gray-900 -mx-5 -mb-5 -mt-[1px]">
      <!-- Header / Tools -->
      <div class="p-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center z-10 sticky top-0">
        <div>
          <h3 class="text-lg font-bold text-gray-800 dark:text-gray-100">管理截图与表情包</h3>
          <p class="text-sm text-gray-500">共 {{ photos.length }} 张截图，占用 {{ formatSize(totalSize) }}</p>
        </div>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto relative p-4" ref="scrollContainer">
        <FlatPhotoGallery
          v-if="photos.length > 0"
          :photos="photos"
          :loading="loading"
          :scroll-container="scrollContainer"
          delete-label="删除截图"
          @batch-delete="handleBatchDelete"
          @click-photo="handlePhotoClick"
        >
          <template #batch-actions="{ selectedIds, clearSelection }">
            <el-dropdown-item @click="handleMoveToNonArchive(Array.from(selectedIds), clearSelection)">
              <div class="flex items-center gap-2 text-primary-500">
                <FolderDown class="w-4 h-4" />
                <span>移出图库不归档</span>
              </div>
            </el-dropdown-item>
          </template>
        </FlatPhotoGallery>
        
        <div v-else-if="!loading" class="flex flex-col items-center justify-center h-full text-gray-400">
          <Smartphone class="w-16 h-16 mb-4 opacity-20" />
          <p>太棒了，没有找到截图！</p>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { Smartphone, FolderDown } from 'lucide-vue-next';
import { ElMessage, ElMessageBox } from 'element-plus';
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue';
import { storageApi } from '@/api/storage';
import { photoApi } from '@/api/photo';
import type { AlbumImage } from '@/types/album';

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits(['update:modelValue']);

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
});

const scrollContainer = ref<HTMLElement | null>(null);
const loading = ref(false);
const photos = ref<AlbumImage[]>([]);

const totalSize = computed(() => {
  return photos.value.reduce((acc, p) => acc + (p.size || 0), 0);
});

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const fetchScreenshots = async () => {
  loading.value = true;
  try {
    const res = await storageApi.getScreenshots(0, 1000); // Fetch up to 1000 for now
    photos.value = res.data || [];
  } catch (error) {
    console.error(error);
    ElMessage.error('加载截图失败');
  } finally {
    loading.value = false;
  }
};

const handleOpen = () => {
  fetchScreenshots();
};

const handlePhotoClick = (photo: AlbumImage) => {
  // Lightbox preview could be implemented here
  console.log('Clicked', photo.id);
};

const handleBatchDelete = async (ids: string[]) => {
  try {
    await ElMessageBox.confirm(`确定要彻底删除这 ${ids.length} 张截图吗？`, '警告', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    
    // Call photoApi to delete
    await photoApi.batchDelete(ids);
    ElMessage.success('删除成功');
    photos.value = photos.value.filter(p => !ids.includes(p.id));
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
};

const handleMoveToNonArchive = async (ids: string[], clearSelection: () => void) => {
  try {
    await ElMessageBox.confirm(`确定要将这 ${ids.length} 张截图移到不归档目录吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'info',
    });
    
    await storageApi.moveToNonArchive(ids);
    ElMessage.success('操作成功');
    photos.value = photos.value.filter(p => !ids.includes(p.id));
    clearSelection();
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('操作失败');
    }
  }
};
</script>