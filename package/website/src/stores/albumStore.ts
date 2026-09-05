// src/stores/albumStore.ts
// 定义相册相关的状态管理

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { albumService } from '@/api/album'
import { mapPhotoToImage } from '@/stores/photoStore'
import type { ApiAlbum, Album, AlbumImage } from '@/types/album'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const useAlbumStore = defineStore('album', () => {
  // --- 状态 ---
  const apiAlbums = ref<ApiAlbum[]>([])
  // --- 动作 ---
  const fetchAlbums = async () => {
      try {
          const albumsData = await albumService.getAlbums();
          apiAlbums.value = albumsData;
      } catch (e) {
          console.error("获取相册失败", e)
      }
  }

  const createCustomAlbum = async (title: string, description?: string) => {
      const newAlbum = await albumService.createAlbum({ name: title, description: description || '' });
      apiAlbums.value.push(newAlbum);
      return newAlbum.id;
  }

  const deleteAlbum = async (albumId: string) => {
      await albumService.deleteAlbum(albumId);
      apiAlbums.value = apiAlbums.value.filter(a => a.id !== albumId);
  }

  const addPhotoToAlbum = async (albumId: string, file: File) => {
      await albumService.uploadPhoto(file, albumId);
  }

  const removePhotoFromAlbum = async (albumId: string, photoId: string) => {
      await albumService.removePhotoFromAlbum(albumId, photoId);
  }

  const removePhotosFromAlbum = async (albumId: string, photoIds: string[]) => {
      await albumService.batchUpdatePhotos({
          photo_ids: photoIds,
          action: 'remove_from_album',
          album_id: albumId
      });
  }

  const addPhotosToAlbum = async (photoIds: string[], action: 'add_to_album', targetAlbumId: string) => {
    await albumService.batchUpdatePhotos({
      photo_ids: photoIds,
      action,
      album_id: targetAlbumId
    })
  }

  // --- 计算属性相册 ---
  const allAlbums = computed<Album[]>(() => {
    return apiAlbums.value.map(album => {
      const cover: AlbumImage = album.cover ? mapPhotoToImage(album.cover) : {
        id: '',
        // Empty covers are rendered by the component fallback.  A data URL
        // keeps the native app fully local instead of leaking to placehold.co.
        url: 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=',
        thumbnail: 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=',
        preview: 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=',
        srcset: '',
        timestamp: Date.now(),
        albumIds: [],
        width: 400,
        height: 300,
        size: 0,
        filename: '',
        file_type: 'image',
        duration: '00:00'
      }

      return {
        id: album.id,
        name: album.name,
        title: album.name,
        type: album.type,
        cover,
        count: album.num_photos,
        description: album.description || `${album.num_photos}张照片`,
        createdAt: new Date(album.create_time).getTime(),
        condition: album.condition,
        threshold: album.threshold !== undefined ? album.threshold : 0.25
      }
    })
  })

  // --- 获取器 ---
  const getAlbumDetails = (albumId: string): Album | undefined => {
    return allAlbums.value.find(a => a.id === albumId)
  }

  return {
    allAlbums,
    fetchAlbums,
    createCustomAlbum,
    deleteAlbum,
    addPhotoToAlbum,
    getAlbumDetails,
    removePhotoFromAlbum,
    removePhotosFromAlbum,
    addPhotosToAlbum
  }
})
