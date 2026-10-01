import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { faceApi } from '@/api/face'
import { photoApi } from '@/api/photo'
import type { AlbumImage } from '@/types/album'

export function usePhotoBatchActions(options: {
  selectedIds: () => ReadonlySet<string>
  photos: () => AlbumImage[]
  clearSelection: () => void
  exitAfterDownload?: boolean
}) {
  const isDownloading = ref(false)
  const isAddingPerson = ref(false)
  const showPersonSelector = ref(false)
  const openPersonSelector = () => { if (options.selectedIds().size) showPersonSelector.value = true }
  const handlePersonSelected = async (person: { id: string; identity_name: string }) => {
    const ids = Array.from(options.selectedIds())
    if (!ids.length || isAddingPerson.value) return
    isAddingPerson.value = true
    try {
      const result = await faceApi.addPhotosToIdentity(person.id, ids)
      ElMessage.success(`成功添加 ${result.count} 张照片到 ${person.identity_name}`)
      showPersonSelector.value = false
      options.clearSelection()
    } catch { ElMessage.error('添加失败') }
    finally { isAddingPerson.value = false }
  }
  const handleDownload = async () => {
    const ids = Array.from(options.selectedIds())
    if (!ids.length || isDownloading.value) return
    isDownloading.value = true
    try {
      if (ids.length === 1) {
        const photo = options.photos().find(item => item.id === ids[0])
        if (!photo) return
        await photoApi.downloadPhoto(photo)
      } else await photoApi.batchDownload(ids)
      if (options.exitAfterDownload) options.clearSelection()
    } catch { ElMessage.error('下载失败，请重试') }
    finally { isDownloading.value = false }
  }
  return { isDownloading, isAddingPerson, showPersonSelector, openPersonSelector, handlePersonSelected, handleDownload }
}
