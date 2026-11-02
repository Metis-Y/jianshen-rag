import axios from 'axios'

// baseURL 为 /api；开发环境由 Vite proxy 转发到 http://127.0.0.1:8000
const api = axios.create({
  baseURL: '/api',
  timeout: 15000
})

// 请求拦截器：自动携带 token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：后端统一结构 { code, message, data }，code === 1 才算成功
api.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && body.code === 1) {
      // 业务成功：直接返回 data 部分
      return body.data
    }
    // 业务失败（HTTP 200 但 code 非 1）：alert 后端 message 原文并抛错
    const msg = (body && body.message) || '请求失败'
    alert(msg)
    return Promise.reject(new Error(msg))
  },
  (error) => {
    // HTTP 层错误（401/400/500 等）：body 里同样是 { code, message }
    const body = error.response && error.response.data
    const msg = (body && body.message) || error.message || '网络错误'
    alert(msg)
    return Promise.reject(error)
  }
)

export default api