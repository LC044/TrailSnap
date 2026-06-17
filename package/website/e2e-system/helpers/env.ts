import fs from 'node:fs'
import path from 'node:path'

export const runtimeDir = path.resolve(process.cwd(), '.playwright-system')
export const authStatePath = path.join(runtimeDir, 'storage-state.json')
export const bootstrapStatePath = path.join(runtimeDir, 'bootstrap-state.json')

export const apiBaseUrl = process.env.TS_API_BASE_URL || 'http://localhost:8800'
export const webBaseUrl = process.env.TS_WEB_BASE_URL || 'http://localhost:8082'
export const photoDirectory = process.env.TS_PHOTO_DIR || '/testdata/photos'

export const adminUser = {
  username: process.env.TS_ADMIN_USERNAME || 'e2e-admin',
  email: process.env.TS_ADMIN_EMAIL || 'e2e-admin@example.com',
  password: process.env.TS_ADMIN_PASSWORD || 'Passw0rd!123',
  securityQuestion: process.env.TS_ADMIN_SECURITY_QUESTION || '测试问题',
  securityAnswer: process.env.TS_ADMIN_SECURITY_ANSWER || '测试答案',
}

export interface BootstrapState {
  accessToken: string
  username: string
  email: string
  photoDirectory: string
}

export function ensureRuntimeDir() {
  fs.mkdirSync(runtimeDir, { recursive: true })
}

export function readBootstrapState(): BootstrapState {
  return JSON.parse(fs.readFileSync(bootstrapStatePath, 'utf8')) as BootstrapState
}
