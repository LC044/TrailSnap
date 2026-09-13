import axios from 'axios'

export const client = axios.create({
  baseURL: import.meta.env.VITE_REQUIREMENT_API_URL || '/api',
  timeout: 20000,
})

client.interceptors.request.use(config => {
  const token = localStorage.getItem('rp_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
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
