import fs from 'node:fs'
import path from 'node:path'

import { e2eEnv } from '../../playwright/e2e-env'

export const runtimeDir = path.resolve(process.cwd(), '.playwright-system')
export const authStatePath = path.join(runtimeDir, 'storage-state.json')
export const bootstrapStatePath = path.join(runtimeDir, 'bootstrap-state.json')

/** 兼容旧引用：从 e2e-env 转发（与原行为完全一致） */
export const apiBaseUrl = e2eEnv.apiBaseUrl
export const webBaseUrl = e2eEnv.webBaseUrl
export const photoDirectory = e2eEnv.photoDirectory

export const adminUser = e2eEnv.adminUser

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
