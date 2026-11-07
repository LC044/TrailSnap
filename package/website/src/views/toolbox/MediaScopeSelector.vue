<template>
  <section class="space-y-5">
    <div>
      <h2 class="ts-section-title">这次处理哪些影像？</h2>
      <p class="ts-muted mt-1 text-sm">范围与整理规则独立。不会默认处理整个图库。</p>
    </div>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-5" role="group" aria-label="范围来源">
      <button v-for="source in sources" :key="source.value" type="button"
        class="ts-button ts-button-secondary" :aria-pressed="scope.source === source.value"
        :class="scope.source === source.value ? 'border-primary-500 text-primary-600 dark:text-primary-400' : ''"
        @click="update({ source: source.value, excluded_ids: [] })">
        <component :is="source.icon" class="h-4 w-4" />{{ source.label }}
      </button>
    </div>

    <el-form label-position="top">
      <el-form-item v-if="scope.source === 'albums'" label="选择一个或多个普通相册">
        <el-select :model-value="scope.album_ids" multiple filterable remote :remote-method="searchAlbums"
          :loading="albumsLoading" placeholder="输入相册名称搜索" class="w-full" @update:model-value="update({ album_ids: $event })"
          @visible-change="value => value && searchAlbums('')">
          <el-option v-for="album in albums" :key="album.id" :value="album.id" :label="`${album.name} · ${album.num_photos} 项`" />
        </el-select>
        <p v-if="albumError" class="mt-2 text-sm text-red-600 dark:text-red-400" role="alert">
          {{ albumError }} <button type="button" class="underline" @click="searchAlbums('')">重试</button>
        </p>
        <p class="ts-muted mt-2 text-xs">仅支持你拥有的普通相册。选择相册不会修改其成员。</p>
      </el-form-item>

      <div v-if="scope.source === 'folders'" class="space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <el-button @click="folderPicker = true">选择文件夹</el-button>
          <el-checkbox :model-value="scope.include_children" @update:model-value="update({ include_children: !!$event })">包含子文件夹</el-checkbox>
        </div>
        <div v-for="path in scope.folders" :key="path" class="ts-divider flex min-w-0 items-center gap-2 rounded-xl border p-3">
          <Folder class="h-4 w-4 shrink-0 text-primary-500" />
          <span class="min-w-0 flex-1 break-all text-sm">{{ path }}</span>
          <button type="button" class="ts-icon-button" :aria-label="`移除 ${path}`" @click="update({ folders: scope.folders.filter(p => p !== path) })"><X class="h-4 w-4" /></button>
        </div>
        <p class="ts-muted text-xs">这些是服务器或桌面图库中的实际目录，不是手机本地相册。</p>
      </div>

      <div v-if="scope.source === 'selected'" class="flex flex-wrap items-center gap-3">
        <el-button @click="photoPicker = true">手动选择影像</el-button>
        <span class="ts-muted text-sm">已明确选择 {{ scope.photo_ids.length }} 项</span>
      </div>
      <el-alert v-if="scope.source === 'all'" title="你已主动选择全部影像，请特别注意执行前的影响范围。" type="warning" :closable="false" show-icon />

      <div class="mt-5 border-t pt-5 ts-divider">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <span class="text-sm font-semibold">附加条件{{ scope.source === 'filter' ? '（请至少指定日期）' : '（可选）' }}</span>
          <div class="flex flex-wrap gap-2">
            <el-button v-for="year in years" :key="year" size="small" @click="update({ start_date: `${year}-01-01`, end_date: `${year}-12-31` })">{{ year }} 年</el-button>
            <el-button size="small" @click="update({ start_date: null, end_date: null })">清除日期</el-button>
          </div>
        </div>
        <el-form-item label="拍摄日期">
          <UnifiedDatePicker :model-value="dateRange" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期"
            end-placeholder="结束日期" class="w-full max-w-md" @update:model-value="setDates" />
        </el-form-item>
        <el-checkbox :model-value="scope.upload_time_fallback" @update:model-value="update({ upload_time_fallback: !!$event })">
          缺少拍摄时间时，按上传时间筛选
        </el-checkbox>
        <el-form-item label="媒体类型" class="mt-4">
          <el-select :model-value="scope.media_type" class="w-full max-w-md" @update:model-value="update({ media_type: $event })">
            <el-option label="照片（默认）" value="image" />
            <el-option label="全部影像，预览会列出不支持的项目" value="all" />
            <el-option label="仅视频（本版不支持文件操作）" value="video" disabled />
          </el-select>
        </el-form-item>
        <p class="ts-muted mt-2 text-xs">本版文件操作仅处理静态照片；视频、动态照片及检测到的关联文件会跳过。</p>
      </div>
    </el-form>
    <div class="ts-divider flex flex-wrap items-center justify-between gap-3 border-t pt-4">
      <p v-if="count !== null" class="text-sm"><strong class="text-primary-600 dark:text-primary-400">{{ count.toLocaleString() }}</strong> 项符合当前范围</p>
      <p v-else class="ts-muted text-sm">选择后核对范围与数量</p>
      <el-button :loading="checking" :disabled="!valid" @click="$emit('check')">查看范围内影像</el-button>
    </div>

    <DirectoryPickerDialog v-model:visible="folderPicker" :model-value="chosenFolder" @update:model-value="addFolder" />
    <PhotoSelectorDialog v-model="photoPicker" title="明确选择本次处理的影像" :store="selectionStore"
      @select="ids => { update({ photo_ids: ids }); photoPicker = false }" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Calendar, Folder, Images, CheckSquare, Library, X } from 'lucide-vue-next'
import { albumService } from '@/api/album'
import type { ApiAlbum } from '@/types/album'
import type { MediaScope } from '@/api/toolboxWorkflows'
import { useUserStore } from '@/stores/user'
import { useSelectionStore } from '@/stores/selectionStore'
import DirectoryPickerDialog from '@/components/DirectoryPickerDialog.vue'
import PhotoSelectorDialog from '@/components/PhotoSelectorDialog.vue'
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'

const props = defineProps<{ scope: MediaScope; count: number | null; checking: boolean }>()
const emit = defineEmits<{ 'update:scope': [scope: MediaScope]; check: [] }>()
const update = (change: Partial<MediaScope>) => emit('update:scope', { ...props.scope, ...change })
const sources = [
  { value: 'albums', label: '相册', icon: Images }, { value: 'folders', label: '文件夹', icon: Folder },
  { value: 'filter', label: '条件', icon: Calendar }, { value: 'selected', label: '手动选', icon: CheckSquare },
  { value: 'all', label: '全部', icon: Library },
] as const
const valid = computed(() => {
  const s = props.scope
  return s.source === 'all' || (s.source === 'albums' && s.album_ids.length > 0)
    || (s.source === 'folders' && s.folders.length > 0) || (s.source === 'selected' && s.photo_ids.length > 0)
    || (s.source === 'filter' && !!(s.start_date || s.end_date))
})
const years = [new Date().getFullYear(), new Date().getFullYear() - 1, new Date().getFullYear() - 2]
const dateRange = computed(() => props.scope.start_date && props.scope.end_date ? [props.scope.start_date, props.scope.end_date] : null)
const setDates = (value: unknown) => {
  const range = Array.isArray(value) ? value as string[] : []
  update({ start_date: range[0] || null, end_date: range[1] || null })
}
const albums = ref<ApiAlbum[]>([])
const albumsLoading = ref(false)
const albumError = ref('')
const user = useUserStore()
let searchVersion = 0
const searchAlbums = async (search: string) => {
  const version = ++searchVersion
  albumsLoading.value = true
  albumError.value = ''
  try {
    const rows = await albumService.getAlbums(0, 1000)
    if (version !== searchVersion) return
    albums.value = rows.filter(a => a.type === 'user' && a.owner_id === user.userInfo?.id
      && (a.name.includes(search) || props.scope.album_ids.includes(a.id)))
  } catch { if (version === searchVersion) albumError.value = '相册加载失败' }
  finally { if (version === searchVersion) albumsLoading.value = false }
}
const folderPicker = ref(false)
const chosenFolder = ref('')
const addFolder = (path: string) => {
  chosenFolder.value = path
  if (path && !props.scope.folders.includes(path)) {
    update({ folders: [...props.scope.folders, path] })
  }
}
const photoPicker = ref(false)
const selectionStore = useSelectionStore()
</script>
