import axios from 'axios'
import { API_BASE_URL } from '../runtimeBase'

export const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})

client.interceptors.request.use(config => {
  try {
    const token = localStorage.getItem('rp_token')
    if (token) config.headers.Authorization = `Bearer ${token}`
  } catch { /* Anonymous feedback works without browser storage. */ }
  return config
})

export async function call<T>(
  method: string,
  url: string,
  data?: unknown,
  headers?: Record<string, string>,
): Promise<T> {
  const response = await client.request({ method, url, data, headers })
  return response.data.data as T
}
