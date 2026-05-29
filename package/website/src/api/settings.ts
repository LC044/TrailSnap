import request from '@/utils/request';

export const settingsApi = {
  async getStorageRoot() {
    const { data } = await request.get('/api/settings/storage-root')
    return data
  },
  async updateStorageRoot(storageRoot: string) {
    const { data } = await request.put('/api/settings/storage-root', { storage_root: storageRoot })
    return data
  },
  async rebuildIndex() {
    const { data } = await request.post('/api/index/rebuild')
    return data
  },
  async getIndexStatus() {
    const { data } = await request.get('/api/index/status')
    return data
  },
  async getIndexLogs(limit = 100) {
    const { data } = await request.get('/api/index/logs', { params: { limit } })
    return data
  },
  async getDirectories(user_id?: string) {
    const { data } = await request.get('/api/settings/directories', { params: { user_id } })
    return data
  },
  async getDirectoryTree(path?: string) {
    const { data } = await request.get('/api/settings/directories/tree', { params: { path } })
    return data
  },
  async addDirectory(path: string, user_id?: string) {
    const { data } = await request.post('/api/settings/directories', { path, user_id })
    return data
  },
  async removeDirectory(path: string, user_id?: string) {
    const { data } = await request.delete('/api/settings/directories', { data: { path, user_id } })
    return data
  },
  async getSettings() {
    const { data } = await request.get('/api/settings/')
    return data
  },
  async getSystemConfig() {
    const { data } = await request.get('/api/system/config')
    return data
  },
  async updateSystemConfig(config: any) {
    const { data } = await request.put('/api/system/config', config)
    return data
  },
  async updateSettings(config: any) {
    const { data } = await request.put('/api/settings/', config)
    return data
  },
  async exportSettings() {
    const { data } = await request.get('/api/settings/export')
    return data
  },
  async importSettings(config: any) {
    const { data } = await request.post('/api/settings/import', config)
    return data
  },
  async getMapCountries() {
    const { data } = await request.get('/api/settings/map/countries')
    return data
  },
  async getDownloadedMapData() {
    const { data } = await request.get('/api/settings/map/downloaded')
    return data
  },
  async downloadMapData(code: string) {
    const { data } = await request.post('/api/settings/map/download', { code })
    return data
  },
  async uploadMapData(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await request.post('/api/settings/map/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return data
  },
  async downloadMapFile(filename: string) {
    // responseType: 'blob' makes axios return the blob as data
    const { data } = await request.get(`/api/settings/map/files/${filename}`, {
      responseType: 'blob'
    })
    return data
  },
  async deleteMapData(filename: string) {
    const { data } = await request.delete(`/api/settings/map/files/${filename}`)
    return data
  },
  async applyFilter() {
    const { data } = await request.post('/api/settings/filter/apply')
    return data
  },
  async getModels() {
    const { data } = await request.get('/api/settings/models')
    return data
  },
  async verifyConnection(apiBase: string, apiKey: string) {
    const { data } = await request.post('/api/settings/verify-connection', { api_base: apiBase, api_key: apiKey })
    return data
  }
}
