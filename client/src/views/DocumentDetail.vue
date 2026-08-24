<template>
  <div class="detail-container">
    <!-- 顶部工具条 -->
    <div class="detail-toolbar">
      <button class="tb-btn" @click="goBack" title="返回">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>
        <span>返回</span>
      </button>

      <div class="tb-title" :title="doc.title">
        <span class="icon-mini" :style="fileStyle(doc.file_type)">{{ fileMeta(doc.file_type).letter }}</span>
        <span class="tb-name">{{ doc.title || doc.file_name || '文档详情' }}</span>
        <span class="tb-tag" :class="'lv' + (doc.min_level || 1)">{{ clearanceLevels[doc.min_level] || '公开' }}</span>
      </div>

      <div class="tb-actions">
        <button class="tb-btn" @click="openInNewTab" title="在新标签页打开">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        </button>
        <button class="tb-btn" @click="downloadDoc" title="下载原文件">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        </button>
      </div>
    </div>

    <!-- 内容区：
         ppt/pptx -> 纯文本面板（不能安全内嵌原文件）
         小文档   -> 文本面板 + 原文件双视图
         大文档   -> 原文件预览 + 顶部摘要条 -->
    <div class="detail-body">
      <!-- 加载中 -->
      <div v-if="loading" class="detail-status">
        <div class="spinner"></div>
        <p>正在解析文档...</p>
      </div>

      <!-- 错误 -->
      <div v-else-if="error" class="detail-status">
        <p class="status-icon">!</p>
        <p>{{ error }}</p>
      </div>

      <template v-else>
        <!-- 大文档：顶部摘要条 -->
        <div v-if="parsed && !parsed.small && doc.file_type === 'pdf'" class="summary-bar">
          <div class="summary-title">文档摘要</div>
          <div class="summary-text">{{ parsed.text }}</div>
          <div v-if="parsed.truncated" class="summary-more">（内容较长，仅显示开头部分）</div>
        </div>

        <!-- 双视图模式（小文档且有 PDF/网页预览 + 文本）：左右分栏 -->
        <template v-if="showBoth">
          <div class="dual-pane">
            <div class="pane">
              <div class="pane-label">文本内容</div>
              <div class="text-viewer" ref="textPaneRef">
                <pre class="pre-text">{{ parsed.text }}</pre>
              </div>
            </div>
            <div class="pane preview-pane">
              <div class="pane-label">原文件预览</div>
              <div v-if="viewerUrl" class="preview-frame-wrap">
                <iframe :src="viewerUrl" class="preview-frame"></iframe>
              </div>
              <div v-else class="pane-empty">该格式暂不支持内嵌预览，可下载原文件查看</div>
            </div>
          </div>
        </template>

        <!-- 单视图：纯文本（ppt/pptx 或无法内嵌的小文档） -->
        <template v-else-if="isTextOnly">
          <div class="text-only">
            <div class="text-only-head">
              <div class="pane-label" style="margin:0">文本内容</div>
              <template v-if="doc.file_type === 'pdf'">
                <span class="hint">（该 PDF 无法内嵌预览，已解析为文本）</span>
              </template>
              <template v-else-if="pptLike">
                <span class="hint">（演示文稿已解析为文字内容）</span>
              </template>
            </div>
            <div class="text-viewer text-only-body" ref="textPaneRef">
              <pre class="pre-text">{{ parsed.text }}</pre>
            </div>
          </div>
        </template>

        <!-- 单视图：纯预览（大 PDF 直接内嵌） -->
        <template v-else>
          <div v-if="viewerUrl" class="preview-full">
            <iframe :src="viewerUrl" class="preview-frame"></iframe>
          </div>
          <div v-else class="detail-status">
            <p>该文档格式暂不支持在线预览，可点击右上角下载后查看</p>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'DocumentDetail' })
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { documentAPI } from '../api'

const route = useRoute()
const router = useRouter()

const clearanceLevels = { 1: '公开', 2: '内部', 3: '机密', 4: '绝密' }
const fileTypeMeta = {
  pdf: { letter: 'PDF', color: '#ff3b30', bg: '#ffe9e8' },
  doc: { letter: 'DOC', color: '#0071e3', bg: '#e6f1ff' },
  docx: { letter: 'DOC', color: '#0071e3', bg: '#e6f1ff' },
  ppt: { letter: 'PPT', color: '#ff9500', bg: '#fff3e2' },
  pptx: { letter: 'PPT', color: '#ff9500', bg: '#fff3e2' },
  txt: { letter: 'TXT', color: '#8e8e93', bg: '#f2f2f7' },
  md: { letter: 'MD', color: '#34c759', bg: '#e8f9ec' },
  wps: { letter: 'WPS', color: '#5856d6', bg: '#efedfb' },
  rtf: { letter: 'RTF', color: '#af52de', bg: '#f9ecff' }
}
const fileMeta = (type) => fileTypeMeta[(type || '').toLowerCase()] || fileTypeMeta.docx
const fileStyle = (type) => {
  const m = fileMeta(type)
  return { color: m.color, background: m.bg }
}

const docId = Number(route.params.id)
const doc = ref({ title: '', file_name: '', file_type: '', min_level: 1, file_size: 0 })
const viewerUrl = ref('')      // token 化的预览直链
const parsed = ref(null)
const loading = ref(true)
const error = ref('')
const textPaneRef = ref(null)

// token 化的预览 URL（/document/view/:id 需要 Bearer 鉴权，且此 Blob URL 可避开 Content-Disposition）
// PDF 用浏览器内置查看器直接内嵌；文本型预览包一层带主题的内联 HTML，
// 避免深色模式下被浏览器自动反转成"白字"、而背景仍是浅色 → 白字白底。
const escapeHtml = (s) => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')

const viewerKind = ref('') // 'pdf' | 'text'
const setViewerUrl = (u) => {
  const old = viewerUrl.value
  viewerUrl.value = u
  if (old) URL.revokeObjectURL(old)
}

const viewerFetch = async (id) => {
  const url = `/api/document/view/${id}`
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` }
  })
  if (!resp.ok) throw new Error(`http ${resp.status}`)
  const ftype = (doc.value.file_type || '').toLowerCase()
  if (ftype === 'pdf') {
    // PDF：浏览器内置查看器自渲染（白底黑字），不受页面主题影响
    const blob = await resp.blob()
    if (blob.size === 0) return ''
    setViewerUrl(URL.createObjectURL(blob))
    viewerKind.value = 'pdf'
    return viewerUrl.value
  }
  // 文本型（txt/md/doc/docx/wps/rtf）：按当前主题包成内联 HTML
  const text = await resp.text()
  if (!text.trim()) return ''
  const dark = document.documentElement.getAttribute('data-theme') === 'dark'
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;padding:0}
    body{background:${dark ? '#1d1d1f' : '#ffffff'};color:${dark ? '#e5e5ea' : '#1d1d1f'};
      font-family:-apple-system,"PingFang SC","SF Pro Text",Menlo,monospace;
      font-size:13.5px;line-height:1.8;padding:16px 20px;
      white-space:pre-wrap;word-break:break-word}
  </style></head><body>${escapeHtml(text)}</body></html>`
  setViewerUrl(URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' })))
  viewerKind.value = 'text'
  return viewerUrl.value
}

// 主题切换后重新包装文本预览（PDF 由内置查看器自渲染，无需重载）
let themeObserver = null
onMounted(() => {
  themeObserver = new MutationObserver(() => {
    if (viewerKind.value === 'text' && doc.value.file_type) viewerFetch(docId).catch(() => {})
  })
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})
onUnmounted(() => {
  if (themeObserver) themeObserver.disconnect()
})

const SHORT_LIMIT = 0.5 * 1024 * 1024
const pptLike = computed(() => ['ppt', 'pptx'].includes(doc.value.file_type))
const isPreviewable = computed(() => ['pdf', 'txt', 'md', 'doc', 'docx', 'wps', 'rtf'].includes(doc.value.file_type))

const showBoth = computed(() => parsed.value && parsed.value.small && !pptLike.value)
const isTextOnly = computed(() => parsed.value && (pptLike.value || (parsed.value.small && !isPreviewable.value)))

const goBack = () => {
  if (window.history.length > 1) router.back()
  else router.push('/document')
}

const openInNewTab = () => {
  if (viewerUrl.value) window.open(viewerUrl.value)
  else ElMessage.warning('该文档暂不支持在线打开')
}

const downloadDoc = async () => {
  try {
    const res = await documentAPI.download(docId)
    const u = window.URL.createObjectURL(new Blob([res]))
    const a = document.createElement('a')
    a.href = u
    a.download = doc.value.file_name || `document_${docId}`
    a.click()
    window.URL.revokeObjectURL(u)
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

const init = async () => {
  loading.value = true
  error.value = ''
  try {
    const [d, p] = await Promise.all([
      documentAPI.getDetail(docId).then(r => r.data).catch(() => null),
      documentAPI.parsed(docId).then(r => r.data).catch(() => null)
    ])
    if (d) {
      doc.value = d
      if (typeof d.file_size === 'number') {
        doc.value.file_size = d.file_size
      }
      document.title = `${d.title || d.file_name} - 企业知识库`
    }
    parsed.value = p && p.text ? p : null

    const needsPreview = isPreviewable.value && !pptLike.value
    if (needsPreview) {
      viewerFetch(docId).catch(() => {})
    }
    await nextTick()
    if (textPaneRef.value) {
      textPaneRef.value.scrollTop = textPaneRef.value.scrollHeight
    }
  } catch (e) {
    error.value = '文档加载失败，可能已被删除或无权访问'
  } finally {
    loading.value = false
  }
}

init()
</script>

<style scoped>
.detail-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ===== 顶部工具条 ===== */
.detail-toolbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--border);
  background: var(--card);
}
.tb-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  font-family: inherit;
  font-size: 13px;
  color: var(--text2);
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.tb-btn:hover { background: var(--hover); color: var(--text); }

.tb-title {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}
.icon-mini {
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
}
.tb-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tb-tag {
  font-size: 11px;
  padding: 2px 9px;
  border-radius: 980px;
  flex: none;
  background: var(--hover);
  color: var(--text2);
}
.tb-tag.lv1 { background: var(--primary-soft); color: var(--primary); }
.tb-tag.lv2 { background: var(--primary-soft); color: var(--primary); }
.tb-tag.lv3 { background: #fff4e5; color: var(--el-color-warning); }
.tb-tag.lv4 { background: #ffeded; color: var(--el-color-danger); }

.tb-actions {
  display: flex;
  gap: var(--space-1);
  flex: none;
}

/* ===== 内容区 ===== */
.detail-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-status {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  color: var(--text3);
  font-size: 14px;
}
.status-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--hover);
  color: var(--text3);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 700;
  margin: 0;
}
.spinner {
  width: 26px;
  height: 26px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 摘要条（大 PDF）：背景用卡片色而非软主色，保证暗色主题下文字对比度 */
.summary-bar {
  flex: none;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  padding: var(--space-4) var(--space-6);
}
.summary-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
  margin-bottom: var(--space-2);
}
.summary-text {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);
  white-space: pre-wrap;
}
.summary-more {
  font-size: 12px;
  color: var(--text3);
  margin-top: var(--space-1);
}

/* 双视图分栏 */
.dual-pane {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
}
.pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.pane-label {
  flex: none;
  padding: var(--space-3) var(--space-4);
  font-size: 12px;
  font-weight: 600;
  color: var(--text2);
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}

.text-viewer {
  flex: 1;
  overflow: auto;
  padding: var(--space-4) var(--space-5);
}
.pre-text {
  margin: 0;
  font-family: -apple-system, "PingFang SC", "SF Pro Text", Menlo, monospace;
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--text2);
  white-space: pre-wrap;
  word-break: break-word;
}
.preview-frame-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bg);
}
.preview-frame {
  width: 100%;
  height: 100%;
  min-height: 100%;
  border: none;
}
.pane-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text3);
  font-size: 13px;
}

/* 纯文本（ppt/pptx 等） */
.text-only {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-4) var(--space-5);
}
.text-only-head {
  width: 100%;
  max-width: 860px;
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  padding: 0 var(--space-2);
}
.text-only-head .pane-label { border: none; padding: 0; background: transparent; }
.hint { font-size: 12px; color: var(--text3); }
.text-only-body {
  width: 100%;
  max-width: 860px;
  flex: 1;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}

/* 纯预览（大 PDF） */
.preview-full {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bg);
}
.preview-full .preview-frame {
  width: 100%;
  height: 100%;
  min-height: 100%;
  border: none;
}
</style>