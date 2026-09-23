<template>
  <div class="p-4 space-y-4">
    <!-- Source Group -->
    <div class="space-y-2">
      <button @click="toggleSection('source')" class="flex items-center justify-between w-full group dark:bg-gray-800">
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 group-hover:text-gray-700 dark:group-hover:text-gray-200 transition-colors">来源</h3>
          <ChevronDown class="w-4 h-4 text-gray-400 transition-transform duration-200" :class="{ 'rotate-180': !collapsed.source }" />
      </button>
      
      <div v-show="!collapsed.source" class="space-y-2 animate-in slide-in-from-top-1 duration-200 max-h-60 overflow-y-auto custom-scrollbar">
          <div class="flex flex-wrap gap-2">
            <button
              v-for="type in availableFilters?.image_types || []"
              :key="type"
              @click="toggleFilter('image_types', type)"
              class="px-3 py-1.5 rounded-full text-sm transition-all border"
              :class="isSelected('image_types', type) 
                ? 'bg-primary-500 text-white border-primary-500' 
                : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-primary-300'"
            >
              {{ formatImageType(type) }}
            </button>
          </div>
          
          <!-- Camera Make/Model (Only if Camera is selected) -->
          <div v-if="isSelected('image_types', 'Camera')" class="pl-4 mt-2 space-y-4 border-l-2 border-gray-100 dark:border-gray-800 animate-in slide-in-from-left-2 duration-200">
             <div v-if="availableFilters?.makes?.length">
                 <h4 class="text-xs font-medium text-gray-400 mb-2">相机品牌</h4>
                 <div class="flex flex-wrap gap-2">
                    <button
                      v-for="make in availableFilters.makes"
                      :key="make"
                      @click="toggleFilter('makes', make)"
                      class="px-2.5 py-1 rounded-md text-xs transition-all border"
                      :class="isSelected('makes', make)
                        ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 border-primary-200 dark:border-primary-800'
                        : 'bg-gray-50 dark:bg-gray-900 text-gray-600 dark:text-gray-400 border-gray-100 dark:border-gray-800 hover:border-gray-300'"
                    >
                      {{ make }}
                    </button>
                 </div>
             </div>
             <div v-if="availableFilters?.models?.length">
                 <h4 class="text-xs font-medium text-gray-400 mb-2">相机型号</h4>
                 <div class="flex flex-wrap gap-2">
                    <button
                      v-for="model in availableFilters.models"
                      :key="model"
                      @click="toggleFilter('models', model)"
                      class="px-2.5 py-1 rounded-md text-xs transition-all border"
                      :class="isSelected('models', model)
                        ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 border-primary-200 dark:border-primary-800'
                        : 'bg-gray-50 dark:bg-gray-900 text-gray-600 dark:text-gray-400 border-gray-100 dark:border-gray-800 hover:border-gray-300'"
                    >
                      {{ model }}
                    </button>
                 </div>
             </div>
          </div>
      </div>
    </div>

    <!-- Type Group -->
    <div class="space-y-2">
      <button @click="toggleSection('type')" class="flex items-center justify-between w-full group dark:bg-gray-800">
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 group-hover:text-gray-700 dark:group-hover:text-gray-200 transition-colors">类型</h3>
          <ChevronDown class="w-4 h-4 text-gray-400 transition-transform duration-200" :class="{ 'rotate-180': !collapsed.type }" />
      </button>
      <div v-show="!collapsed.type" class="flex flex-wrap gap-2 animate-in slide-in-from-top-1 duration-200 max-h-60 overflow-y-auto custom-scrollbar">
        <button
          v-for="type in availableFilters?.file_types || []"
          :key="type"
          @click="toggleFilter('file_types', type)"
          class="px-3 py-1.5 rounded-full text-sm transition-all border"
          :class="isSelected('file_types', type)
            ? 'bg-primary-500 text-white border-primary-500'
            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-primary-300'"
        >
          {{ formatFileType(type) }}
        </button>
      </div>
    </div>

    <!-- Year Group -->
    <div class="space-y-2" v-if="availableFilters?.years?.length">
      <button @click="toggleSection('year')" class="flex items-center justify-between w-full group dark:bg-gray-800">
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 group-hover:text-gray-700 dark:group-hover:text-gray-200 transition-colors">年份</h3>
          <ChevronDown class="w-4 h-4 text-gray-400 transition-transform duration-200" :class="{ 'rotate-180': !collapsed.year }" />
      </button>
      <div v-show="!collapsed.year" class="flex flex-wrap gap-2 animate-in slide-in-from-top-1 duration-200 max-h-60 overflow-y-auto custom-scrollbar">
        <button
          v-for="year in availableFilters.years"
          :key="year"
          @click="toggleFilter('years', year)"
          class="px-3 py-1.5 rounded-full text-sm transition-all border"
          :class="isSelected('years', year)
            ? 'bg-primary-500 text-white border-primary-500'
            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-primary-300'"
        >
          {{ year }}
        </button>
      </div>
    </div>

    <!-- Location Group -->
    <div class="space-y-2" v-if="availableFilters?.cities?.length">
      <button @click="toggleSection('location')" class="flex items-center justify-between w-full group dark:bg-gray-800">
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 group-hover:text-gray-700 dark:group-hover:text-gray-200 transition-colors">地点</h3>
          <ChevronDown class="w-4 h-4 text-gray-400 transition-transform duration-200" :class="{ 'rotate-180': !collapsed.location }" />
      </button>
      <div v-show="!collapsed.location" class="flex flex-wrap gap-2 animate-in slide-in-from-top-1 duration-200 max-h-60 overflow-y-auto custom-scrollbar">
        <button
          v-for="city in availableFilters.cities"
          :key="city"
          @click="toggleFilter('cities', city)"
          class="px-3 py-1.5 rounded-full text-sm transition-all border"
          :class="isSelected('cities', city)
            ? 'bg-primary-500 text-white border-primary-500'
            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-primary-300'"
        >
          {{ city }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { usePhotoStore, usePhotosPageStore } from '@/stores/photoStore';
import { computed, reactive } from 'vue';
import { ChevronDown } from 'lucide-vue-next';

const props = defineProps<{
  store?: ReturnType<typeof usePhotoStore> | ReturnType<typeof usePhotosPageStore>
}>();
const store = props.store || usePhotoStore();
const availableFilters = computed(() => store.availableFilters);
const selectedFilters = store.selectedFilters;

const collapsed = reactive({
    source: false,
    type: false,
    year: true,
    location: true
});

const toggleSection = (key: keyof typeof collapsed) => {
    collapsed[key] = !collapsed[key];
}

const isSelected = (key: keyof typeof selectedFilters, value: any) => {
    return (selectedFilters[key] as any[]).includes(value);
};

const toggleFilter = (key: keyof typeof selectedFilters, value: any) => {
    const list = selectedFilters[key] as any[];
    const index = list.indexOf(value);
    if (index === -1) {
        list.push(value);
    } else {
        list.splice(index, 1);
    }
    
    // Trigger reload
    store.loadPhotos(true);
};

const formatImageType = (type: string) => {
    const map: Record<string, string> = {
        'Camera': '相机',
        'Screenshot': '截屏',
        'Other': '其他'
    };
    return map[type] || type;
}

const formatFileType = (type: string) => {
    const map: Record<string, string> = {
        'image': '图片',
        'video': '视频',
        'live_photo': '实况图'
    };
    return map[type] || type;
}
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.5);
  border-radius: 20px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.8);
}
</style>
