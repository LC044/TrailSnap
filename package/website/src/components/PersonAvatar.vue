<template>
    <div
    class="relative w-12 aspect-square rounded-full overflow-hidden border-2 transition-all duration-300 bg-gray-100 dark:bg-gray-800"
    :class="['border-transparent group-hover:border-gray-300 dark:group-hover:border-gray-600']"
    >
        <img
            v-if="person.cover_photo"
            :src="getPhotoUrl(person.cover_photo.photo_id)"
            class="absolute max-w-none transition-transform duration-500 group-hover:scale-110"
            :style="getFaceCropStyle(person.cover_photo)"
            loading="lazy"
        />
        <div v-else class="w-full h-full flex items-center justify-center text-gray-400">
            <User class="w-1/2 h-1/2" />
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Search, Plus, User } from '@element-plus/icons-vue'
import type { PhotoMetadata, AlbumImage, CoverPhotoInfo, FaceIdentity } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'

const props = defineProps({
  person: {
    type: Object as () => FaceIdentity,
    required: true,
    default: () => ({})
  }
})

const getPhotoUrl = (photoId: string) => {
  return thumbnailUrl(photoId, 'medium')
}

/**
 * 核心算法：计算人脸裁切样式
 */
const getFaceCropStyle = (cover: CoverPhotoInfo) => {
  if (!cover.face_rect || cover.face_rect.length !== 4) {
    return {}
  }
  
  // face_rect: [x1, y1, x2, y2] (relative coordinates 0-1)
  const [rx1, ry1, rx2, ry2] = cover.face_rect
  
  const faceRelW = rx2 - rx1
  const faceRelH = ry2 - ry1
  
  if (faceRelW <= 0 || faceRelH <= 0) return {}

  // 1. 确定裁切基准：人脸区域需要占据容器的比例
  // 之前的逻辑是 cropSize = max(faceW, faceH) * 1.6
  // 这意味着人脸最大边长占容器的 1/1.6 ≈ 62.5%
  const scaleFactor = 1.6

  // 2. 计算需要的缩放百分比
  // 如果以宽度为基准：widthPct = 100 / (faceRelW * scaleFactor)
  // 如果以高度为基准：heightPct = 100 / (faceRelH * scaleFactor)
  const wPct = 100 / (faceRelW * scaleFactor)
  const hPct = 100 / (faceRelH * scaleFactor)

  // 3. 计算人脸中心点坐标（百分比）
  const leftPct = ((rx1 + rx2) / 2) * 100
  const topPct = ((ry1 + ry2) / 2) * 100

  const style: any = {
    left: '50%',
    top: '50%',
    transform: `translate(-${leftPct.toFixed(2)}%, -${topPct.toFixed(2)}%)`,
  }

  // 4. 选择较小的缩放比例以确保人脸完整显示（contain逻辑）
  // 并设置对应的宽或高，另一边设为 auto 以保持比例
  if (wPct < hPct) {
      style.width = `${wPct.toFixed(2)}%`
      style.height = 'auto'
  } else {
      style.width = 'auto'
      style.height = `${hPct.toFixed(2)}%`
  }

  return style
}
</script>
