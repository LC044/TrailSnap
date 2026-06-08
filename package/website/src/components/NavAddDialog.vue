<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="添加快捷导航"
    width="480px"
    :close-on-click-modal="true"
    class="nav-add-dialog"
  >
    <el-tabs v-model="activeTab" class="mb-2">
      <el-tab-pane label="相册" name="album">
        <div class="max-h-72 overflow-y-auto space-y-0.5 custom-scrollbar">
          <div v-if="loadingAlbums" class="py-8 text-center text-sm text-slate-400">加载中...</div>
          <div v-else-if="albums.length === 0" class="py-8 text-center text-sm text-slate-400">暂无相册</div>
          <div
            v-for="album in albums"
            :key="album.id"
            @click="add('album', album.id)"
            class="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer transition-colors"
            :class="{ 'opacity-50 cursor-default': isNavAdded('album', album.id) }"
          >
            <div class="w-9 h-9 rounded-lg overflow-hidden bg-slate-200 dark:bg-slate-600 shrink-0">
              <img v-if="album.cover?.id" :src="`/api/medias/${album.cover.id}/thumbnail`" class="w-full h-full object-cover" loading="lazy" />
              <Images v-else class="w-5 h-5 m-auto text-slate-400 mt-2" />
            </div>
            <span class="text-sm text-slate-700 dark:text-slate-200 truncate flex-1">{{ album.name }}</span>
            <span class="text-xs text-slate-400">{{ album.num_photos }}张</span>
            <span v-if="isNavAdded('album', album.id)" class="text-xs text-primary-500">已添加</span>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="人物" name="person">
        <div class="max-h-72 overflow-y-auto space-y-0.5 custom-scrollbar">
          <div v-if="loadingPeople" class="py-8 text-center text-sm text-slate-400">加载中...</div>
          <div v-else-if="people.length === 0" class="py-8 text-center text-sm text-slate-400">暂无人物</div>
          <div
            v-for="person in people"
            :key="person.id"
            @click="add('person', person.id)"
            class="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer transition-colors"
            :class="{ 'opacity-50 cursor-default': isNavAdded('person', person.id) }"
          >
            <div class="w-9 h-9 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-600 shrink-0">
              <img v-if="person.cover_photo?.photo_id" :src="`/api/medias/${person.cover_photo.photo_id}/thumbnail?size=medium`" class="w-full h-full object-cover" loading="lazy" />
              <User v-else class="w-5 h-5 m-auto text-slate-400 mt-2" />
            </div>
            <span class="text-sm text-slate-700 dark:text-slate-200 truncate flex-1">{{ person.identity_name }}</span>
            <span class="text-xs text-slate-400">{{ person.face_count }}张</span>
            <span v-if="isNavAdded('person', person.id)" class="text-xs text-primary-500">已添加</span>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="地点" name="location">
        <div class="max-h-72 overflow-y-auto space-y-0.5 custom-scrollbar">
          <div v-if="loadingLocations" class="py-8 text-center text-sm text-slate-400">加载中...</div>
          <div v-else-if="locations.length === 0" class="py-8 text-center text-sm text-slate-400">暂无地点</div>
          <div
            v-for="loc in locations"
            :key="loc.name"
            @click="add('location', loc.name)"
            class="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer transition-colors"
            :class="{ 'opacity-50 cursor-default': isNavAdded('location', loc.name) }"
          >
            <div class="w-9 h-9 rounded-lg overflow-hidden bg-slate-200 dark:bg-slate-600 shrink-0">
              <img v-if="loc.cover?.id" :src="`/api/medias/${loc.cover.id}/thumbnail`" class="w-full h-full object-cover" loading="lazy" />
              <MapPin v-else class="w-5 h-5 m-auto text-slate-400 mt-2" />
            </div>
            <span class="text-sm text-slate-700 dark:text-slate-200 truncate flex-1">{{ loc.name }}</span>
            <span class="text-xs text-slate-400">{{ loc.count }}张</span>
            <span v-if="isNavAdded('location', loc.name)" class="text-xs text-primary-500">已添加</span>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="分类" name="classification">
        <div class="max-h-72 overflow-y-auto space-y-0.5 custom-scrollbar">
          <div v-if="loadingTags" class="py-8 text-center text-sm text-slate-400">加载中...</div>
          <div v-else-if="tags.length === 0" class="py-8 text-center text-sm text-slate-400">暂无分类</div>
          <div
            v-for="tag in tags"
            :key="tag.id"
            @click="add('classification', tag.id)"
            class="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer transition-colors"
            :class="{ 'opacity-50 cursor-default': isNavAdded('classification', tag.id) }"
          >
            <div class="w-9 h-9 rounded-lg overflow-hidden bg-slate-200 dark:bg-slate-600 shrink-0">
              <img v-if="tag.cover?.id" :src="`/api/medias/${tag.cover.id}/thumbnail`" class="w-full h-full object-cover" loading="lazy" />
              <TagIcon v-else class="w-5 h-5 m-auto text-slate-400 mt-2" />
            </div>
            <span class="text-sm text-slate-700 dark:text-slate-200 truncate flex-1">{{ tag.tag_name }}</span>
            <span class="text-xs text-slate-400">{{ tag.count }}张</span>
            <span v-if="isNavAdded('classification', tag.id)" class="text-xs text-primary-500">已添加</span>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { User, MapPin, Tag as TagIcon, Images } from 'lucide-vue-next'
import { albumService } from '@/api/album'
import type { ApiAlbum } from '@/types/album'
import { faceApi } from '@/api/face'
import type { FaceIdentity } from '@/types/album'
import { locationService } from '@/api/location'
import type { Location } from '@/types/location'
import { classificationService, type TagStats } from '@/api/classification'
import { injectNavItems, type NavEntityType } from '@/composables/useNavItems'

defineProps<{ visible: boolean }>()
defineEmits<{ 'update:visible': [value: boolean] }>()

const { isAdded: isNavAdded, addItem: addNavItem } = injectNavItems()
const activeTab = ref('album')

const albums = ref<ApiAlbum[]>([])
const people = ref<FaceIdentity[]>([])
const locations = ref<Location[]>([])
const tags = ref<TagStats[]>([])

const loadingAlbums = ref(false)
const loadingPeople = ref(false)
const loadingLocations = ref(false)
const loadingTags = ref(false)

// Fetch data when dialog opens
watch(() => ({ /* watch visible prop via parent */ }), () => {}, { immediate: true })

const fetchData = async () => {
  loadingAlbums.value = true
  loadingPeople.value = true
  loadingLocations.value = true
  loadingTags.value = true

  albumService.getAlbums().then(res => { albums.value = res || [] }).catch(() => {}).finally(() => { loadingAlbums.value = false })
  faceApi.listIdentities(1, 200, ['named']).then(res => { people.value = res || [] }).catch(() => {}).finally(() => { loadingPeople.value = false })
  locationService.getLocations('city', 0, 200).then(res => { locations.value = res || [] }).catch(() => {}).finally(() => { loadingLocations.value = false })
  classificationService.getTags(0, 200).then(res => { tags.value = res || [] }).catch(() => {}).finally(() => { loadingTags.value = false })
}

// Expose fetchData so parent can call it when opening the dialog
defineExpose({ fetchData })

const add = async (entityType: NavEntityType, entityId: string) => {
  if (isNavAdded(entityType, entityId)) return
  await addNavItem({ entity_type: entityType, entity_id: entityId })
}
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 4px;
}
.dark .custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #475569;
}
</style>
