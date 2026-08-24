// -*- coding: utf-8 -*-
/**
 * API 请求工具模块
 * 封装 axios，提供统一的请求拦截和错误处理
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'

console.log('API module loaded, VITE_API_URL:', import.meta.env.VITE_API_URL)

// 创建 axios 实例
const api = axios.create({
  // API基础URL，根据环境配置
  baseURL: import.meta.env.VITE_API_URL || '/api',
  // 请求超时时间
  timeout: 30000,
  // 注意：不要在这里设置默认 Content-Type
  // 上传文件时需要 multipart/form-data，axios会自动处理
  headers: {
    // 'Content-Type': 'application/json'  // 删除这行，让axios自动处理
  }
})

// 请求拦截器 - 添加Token
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - 统一错误处理
api.interceptors.response.use(
  response => {
    // Blob 响应（下载/在线预览）直接透传，不做 JSON code 校验
    if (response.config.responseType === 'blob' || response.data instanceof Blob) {
      return response.data
    }
    // 统一处理响应数据
    const res = response.data
    // 允许成功状态码 200 和 201
    if (res.code !== 200 && res.code !== 201) {
      // 显示错误消息
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }
    return res
  },
  error => {
    // 处理HTTP错误
    if (error.response) {
      const status = error.response.status
      switch (status) {
        case 401:
          // Token过期，跳转登录
          ElMessage.error('登录已过期，请重新登录')
          localStorage.removeItem('token')
          localStorage.removeItem('userInfo')
          window.location.href = '/login'
          break
        case 403:
          ElMessage.error('权限不足')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 500:
          ElMessage.error('服务器错误')
          break
        default:
          ElMessage.error(error.message || '网络错误')
      }
    } else {
      ElMessage.error('网络连接失败')
    }
    return Promise.reject(error)
  }
)

// 认证相关API
export const authAPI = {
  // 用户登录
  login: (data) => api.post('/auth/login', data),
  // 用户注册
  register: (data) => api.post('/auth/register', data),
  // 用户登出
  logout: () => api.post('/auth/logout'),
  // 验证Token
  verify: () => api.get('/auth/verify'),
  // 修改密码
  changePassword: (data) => api.post('/auth/change_password', data)
}

// 用户相关API
export const userAPI = {
  // 获取用户信息
  getProfile: () => api.get('/user/profile'),
  // 更新用户信息
  updateProfile: (data) => api.put('/user/profile', data),
  // 获取用户列表
  getUserList: (params) => api.get('/user/list', { params }),
  // 删除用户
  deleteUser: (userId) => api.delete(`/user/${userId}`),
  // 更新用户状态
  updateUserStatus: (userId, status) => api.put(`/user/${userId}/status`, { status }),
  // 获取部门租户列表（管理端选部门用）
  getTenants: () => api.get('/user/tenants'),
  // 更新用户角色/部门/密级（admin）
  updateUser: (userId, data) => api.put(`/user/${userId}`, data)
}

// 文档相关API
export const documentAPI = {
  // 上传文档
  upload: (formData) => {
    // 不要手动设置Content-Type，让axios自动处理
    return api.post('/document/upload', formData)
  },
  // 批量上传文档（异步，返回 batch_id）
  uploadBatch: (formData) => {
    return api.post('/document/upload/batch', formData)
  },
  // 查询批量上传任务进度
  batchStatus: (batchId) => {
    return api.get('/document/upload/batch/status', { params: { batch_id: batchId } })
  },
  // 批量任务控制：action=pause|resume|cancel，cancel 时 mode=all|pending
  batchControl: (batchId, action, mode) => {
    return api.post('/document/upload/batch/control', { batch_id: batchId, action, mode })
  },
  // 获取文档列表
  getList: (params) => api.get('/document/list', { params }),
  // 获取文档详情
  getDetail: (docId) => api.get(`/document/${docId}`),
  // 删除文档
  delete: (docId) => api.delete(`/document/${docId}`),
  // 下载文档
  download: (docId) => api.get(`/document/download/${docId}`, { responseType: 'blob' }),
  // 在线预览内容（返回 blob：PDF/PPT 转 PDF 为原格式，文本文档为 UTF-8 文本）
  view: (docId) => api.get(`/document/view/${docId}`, { responseType: 'blob' }),
  // 文档内容/摘要（小文档全文、大文档摘要；用于全屏详情页文本区）
  parsed: (docId, params) => api.get(`/document/parsed/${docId}`, { params }),
  // 更新文档元数据（标题/分类/密级，admin或所有者）
  update: (docId, data) => api.put(`/document/${docId}`, data),
  // 获取文档ACL授权列表
  getAcl: (docId) => api.get(`/document/${docId}/acl`),
  // 授权用户访问文档
  grantAcl: (docId, userId) => api.post(`/document/${docId}/acl`, { user_id: userId }),
  // 撤销用户访问授权
  revokeAcl: (docId, userId) => api.delete(`/document/${docId}/acl`, { data: { user_id: userId } })
}

// 分类相关API
export const categoryAPI = {
  // 获取分类列表
  getList: () => api.get('/category/list'),
  // 获取分类详情
  getDetail: (categoryId) => api.get(`/category/${categoryId}`),
  // 创建分类
  create: (data) => api.post('/category', data),
  // 更新分类
  update: (categoryId, data) => api.put(`/category/${categoryId}`, data),
  // 删除分类
  delete: (categoryId) => api.delete(`/category/${categoryId}`)
}

// 问答相关API
export const qaAPI = {
  // 提问
  ask: (question, conversationId) => api.post('/qa/ask', { question, conversation_id: conversationId }),
  // 流式提问(SSE, fetch实现)：body 可为 {question, conversation_id} 或旧式 question 字符串
  askStream: (body, { onStatus, onToken, onDone, onError } = {}) => {
    const token = localStorage.getItem('token')
    const payload = typeof body === 'string' ? { question: body } : body
    return fetch(`${import.meta.env.VITE_API_URL || '/api'}/qa/ask/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    }).then(async (resp) => {
      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`)
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let sep
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const raw = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          const dataLine = raw.split('\n').find(l => l.startsWith('data:'))
          if (!dataLine) continue
          try {
            const event = JSON.parse(dataLine.slice(5).trim())
            if (event.type === 'status') onStatus && onStatus(event)
            else if (event.type === 'token') onToken && onToken(event.delta || '')
            else if (event.type === 'done') onDone && onDone(event)
            else if (event.type === 'error') onError && onError(new Error(event.message || '流式应答错误'))
          } catch (e) {
            console.warn('SSE parse error:', e)
          }
        }
      }
    })
  },
  // 获取问答历史
  getHistory: (params) => api.get('/qa/history', { params }),
  // 获取历史详情
  getHistoryDetail: (historyId) => api.get(`/qa/history/${historyId}`),
  // 文档检索
  search: (params) => api.get('/qa/search', { params }),
  // 重新加载向量库
  reloadVectors: () => api.post('/qa/reload_vectors'),
  // ===== 多会话 =====
  // 获取当前用户会话列表
  getConversations: () => api.get('/qa/conversations'),
  // 新建会话
  createConversation: (title) => api.post('/qa/conversations', { title }),
  // 重命名会话
  renameConversation: (id, title) => api.put(`/qa/conversations/${id}`, { title }),
  // 删除会话
  deleteConversation: (id) => api.delete(`/qa/conversations/${id}`),
  // 获取会话内全部消息
  getConversationMessages: (id) => api.get(`/qa/conversations/${id}/messages`),
  // ===== 用户反馈（点赞/点踩）=====
  // 提交/更新反馈
  submitFeedback: (data) => api.post('/qa/feedback', data),
  // 获取反馈统计（管理员）
  getFeedbackStats: () => api.get('/qa/feedback/stats'),
  // 差评批量转为 golden_set 候选标注（管理员）
  feedbackToGolden: (historyIds) => api.post('/qa/feedback/to_golden', { history_ids: historyIds })
}

// 管理员API
export const adminAPI = {  // 获取仪表盘统计
  getDashboard: () => api.get('/admin/dashboard'),
  // 获取每日统计
  getDailyStats: (days) => api.get('/admin/statistics/daily', { params: { days } }),
  // 获取分类统计
  getCategoryStats: () => api.get('/admin/statistics/category'),
  // 获取用户活跃度
  getUserActivity: (limit) => api.get('/admin/statistics/user_activity', { params: { limit } }),
  // 获取Token使用统计
  getTokenUsage: (days) => api.get('/admin/statistics/token_usage', { params: { days } }),
  // 获取登录日志
  getLoginLogs: (params) => api.get('/admin/login_logs', { params })
}

export default api
// 模型接入管理API（管理员，OpenAI兼容端点）
export const modelAPI = {
  // 配置列表（密钥打码）
  list: () => api.get('/model/list'),
  // 新增配置 {name, model_type:'llm'|'embedding', api_base, api_key, model_name, remark}
  add: (data) => api.post('/model', data),
  // 编辑
  update: (id, data) => api.put(`/model/${id}`, data),
  // 删除
  remove: (id) => api.delete(`/model/${id}`),
  // 连接测试：LLM试生成 / 嵌入探测维度
  test: (id) => api.post(`/model/${id}/test`),
  // 启用切换（嵌入维度不兼容时返回 rebuild_required）
  activate: (id) => api.post(`/model/${id}/activate`),
  // 当前运行时实际生效的模型
  activeRuntime: () => api.get('/model/active'),
  // 触发向量库全量重建 + 查询重建进度
  rebuildVectors: () => api.post('/model/rebuild_vectors'),
  rebuildStatus: () => api.get('/model/rebuild_status')
}
