import request from '@/utils/request';

export interface UpdateCheckResult {
  current_version: string
  latest_version: string | null
  has_update: boolean
  update_info: string | null
  download_url: string | null
  error?: string
}

export interface AppUpdateCheckResult {
  platform: string
  current_version: string
  latest_version: string | null
  has_update: boolean
  update_info: string
  /** 当前自部署 Server 上的 APK 同源下载路径 */
  download_url: string | null
  file_name: string | null
  /** 服务端已知的安装包大小；为 0 表示未知，客户端跳过大小校验 */
  size: number
  release_page_url: string | null
  error?: string
}

export const systemApi = {
  async getVersion(): Promise<{version: string}> {
    const data = await request.get<{version: string}>('/api/system/version')
    return data.data
  },
  async checkUpdate(): Promise<UpdateCheckResult> {
    const data = await request.get<UpdateCheckResult>('/api/system/update-check')
    return data.data
  },
  async checkAppUpdate(version: string, platform = 'android'): Promise<AppUpdateCheckResult> {
    const data = await request.get<AppUpdateCheckResult>('/api/system/app-update-check', {
      params: { version, platform },
    })
    return data.data
  }
}
