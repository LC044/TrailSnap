import { defineStore } from 'pinia';
import { useStorage } from '@vueuse/core';
import { ref } from 'vue';

export const useLocationStore = defineStore('location', () => {
  // Persistent State
  const viewMode = useStorage<'grid' | 'map' | 'timeline' | 'trajectory' | 'statistics' | 'puzzle'>('trailsnap-location-view-mode', 'grid');
  const level = useStorage<'city' | 'province' | 'district' | 'scene' | 'photo-map'>('trailsnap-location-level', 'city');
  const filterStatus = useStorage<'all' | 'checked' | 'unchecked'>('trailsnap-location-filter-status', 'checked')
  // State for Map Selection
  const mapSelectedIds = ref<string[]>([]);

  const setMapSelection = (ids: string[]) => {
    mapSelectedIds.value = ids;
  };

  return {
    viewMode,
    level,
    mapSelectedIds,
    setMapSelection,
    filterStatus
  };
});
