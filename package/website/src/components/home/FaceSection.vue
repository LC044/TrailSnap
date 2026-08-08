<template>
  <div class="bg-white dark:bg-neutral-900 rounded-lg py-3 my-3">
    <!-- Header -->
    <div class="flex justify-between items-center px-4 mb-3">
      <h3 class="text-base font-bold text-gray-800 dark:text-gray-100">人物相册</h3>
      <span 
        class="text-xs text-blue-500 cursor-pointer"
        @click="$router.push('/album/people')"
      >
        {{ data.total_identified }}位已识别
      </span>
    </div>

    <!-- Top 3 Faces -->
    <div class="flex overflow-x-auto px-4 space-x-4 pb-2 no-scrollbar">
      <div 
        v-for="face in data.top_faces"
        :key="face.id"
        class="flex flex-col items-center cursor-pointer min-w-[60px]"
        @click="$router.push(`/album/people/${face.id}`)"
      >
        <PersonAvatar :person="face" class="" />
        <span class="text-xs text-gray-600 dark:text-gray-400 truncate w-full text-center">{{ face.identity_name }}</span>
        <span class="text-[10px] text-gray-400">{{ face.face_count }}张</span>
      </div>
    </div>

    <!-- Pending Alert -->
    <div class="px-4 mt-2">
      <div 
        v-if="data.pending_faces_count > 0"
        class="bg-[#FFF7E8] dark:bg-orange-900/20 rounded-md p-2 flex items-center justify-between"
      >
        <div class="flex items-center space-x-2 overflow-hidden">
          <span class="text-orange-500">❓</span>
          <span class="text-xs text-gray-600 dark:text-gray-300 truncate">
            {{ data.pending_faces_count }}位待确认 / {{ data.unidentified_photos_count }}张未识别
          </span>
        </div>
        <button 
          class="text-xs text-orange-500 border border-orange-500 rounded px-2 py-0.5 whitespace-nowrap ml-2"
          @click="$router.push('/album/people')"
        >
          快速标注
        </button>
      </div>
      <div 
        v-else
        class="flex items-center justify-center p-2 text-xs text-green-500"
      >
        ✅ 所有人脸已识别
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PropType } from 'vue';
import { DashboardFace } from '@/api/dashboard';
import PersonAvatar from '@/components/PersonAvatar.vue';

defineProps({
  data: {
    type: Object as PropType<DashboardFace>,
    required: true,
    default: () => ({ total_identified: 0, top_faces: [], pending_faces_count: 0, unidentified_photos_count: 0 })
  }
});
</script>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
