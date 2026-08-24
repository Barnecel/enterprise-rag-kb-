<template>
  <div class="document-container">
    <!-- 批量上传实时进度条（提交后关闭对话框，常驻页面顶部） -->
    <div v-if="batchBarVisible" class="batch-upload-bar">
      <span class="batch-bar-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      </span>
      <div class="batch-bar-info">
        <div class="batch-bar-title">
          {{ batchCancelling ? '正在取消...' : (batchPaused ? '批量上传已暂停' : '批量上传中') }}
        </div>
        <div class="batch-bar-file">{{ batchCurrentFile || '准备中...' }}{{ batchDetail ? ' · ' + batchDetail : '' }}</div>
      </div>
      <el-progress
        :percentage="batchProgress"
        :status="batchProgressStatus"
        :stroke-width="8"
        class="batch-bar-progress"
      />
      <span class="batch-bar-count">成功 {{ batchSuccess }} / 共 {{ batchTotal }}</span>
      <div v-if="batchActive" class="batch-bar-actions">
        <el-button v-if="!batchPaused" size="small" :disabled="batchCancelling" @click="pauseBatch">
          暂停
        </el-button>
        <el-button v-else size="small" type="warning" :disabled="batchCancelling" @click="resumeBatch">
          恢复
        </el-button>
        <el-button size="small" type="danger" plain :disabled="batchCancelling" @click="confirmCancelBatch('pending')">
          取消未上传的
        </el-button>
        <el-button size="small" type="danger" :disabled="batchCancelling" @click="confirmCancelBatch('all')">
          取消全部
        </el-button>
      </div>
    </div>

    <div class="page-header">
      <div>
        <h2 class="page-title">知识库文档</h2>
        <p class="page-sub">管理、上传并检索企业知识库中的文档</p>
      </div>
      <div class="header-actions">
        <el-button class="btn-ghost" @click="showBatchUploadDialog">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          批量上传
        </el-button>
        <el-button class="btn-apple" @click="showUploadDialog">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          上传文档
        </el-button>
      </div>
    </div>

    <!-- 搜索和筛选 -->
    <div class="filter-bar">
      <el-input v-model="searchKeyword" placeholder="搜索文档标题" clearable @change="loadDocuments" class="filter-search">
        <template #prefix>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </template>
      </el-input>
      <el-select v-model="filterCategory" placeholder="选择分类" clearable @change="loadDocuments" class="filter-select">
        <el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" />
      </el-select>
    </div>

    <!-- 文档列表 -->
    <div class="document-list">
      <el-empty v-if="documents.length === 0" description="暂无文档" />

      <div v-else class="doc-grid">
        <div v-for="doc in documents" :key="doc.id" class="doc-card">
          <div class="doc-icon" :style="fileStyle(doc.file_type)">
            {{ fileMeta(doc.file_type).letter }}
          </div>
          <div class="doc-info" @click="openDetail(doc)">
            <h4 class="doc-title" :title="doc.title">{{ doc.title }}</h4>
            <p class="doc-meta">
              <span>{{ doc.category_name || '未分类' }}</span>
              <span class="dot">·</span>
              <span>{{ formatFileSize(doc.file_size) }}</span>
              <span class="dot">·</span>
              <span>{{ doc.view_count }} 次浏览</span>
            </p>
            <div class="doc-tags">
              <span class="tag" :class="'lv' + (doc.min_level || 1)">
                {{ clearanceLevels[doc.min_level] || '公开' }}
              </span>
              <span v-if="doc.doc_level === 'private'" class="tag private">私密</span>
            </div>
            <p class="doc-time">上传于 {{ doc.created_at }}</p>
          </div>
          <div class="doc-actions">
            <button class="act-btn" @click="openDetail(doc)">查看</button>
            <button class="act-btn" @click="downloadDocument(doc)">下载</button>
            <button v-if="canDelete(doc)" class="act-btn danger" @click="deleteDocument(doc)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination" v-if="total > 0">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadDocuments"
        @current-change="loadDocuments"
      />
    </div>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadDialogVisible" title="上传文档" width="500px" @close="handleDialogClose">
      <el-form ref="uploadFormRef" :model="uploadForm" label-width="80px">
        <el-form-item label="文档标题" prop="title">
          <el-input v-model="uploadForm.title" placeholder="请输入文档标题" />
        </el-form-item>
        <el-form-item label="所属分类" prop="category_id">
          <el-select v-model="uploadForm.category_id" placeholder="选择分类" style="width: 100%;">
            <el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="文档级别" prop="doc_level">
          <el-radio-group v-model="uploadForm.doc_level">
            <el-radio label="public">公开</el-radio>
            <el-radio label="private">私密</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="文档密级" prop="min_level">
          <el-select v-model="uploadForm.min_level" style="width: 100%;">
            <el-option v-for="(label, level) in clearanceLevels" :key="level" :label="label" :value="level" />
          </el-select>
          <div class="upload-tip">低于该密级的用户不可见/不可检索此文档（同级及以上可见）</div>
        </el-form-item>
        <el-form-item label="选择文件" prop="file">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-remove="clearFiles"
            :file-list="fileList"
            accept=".txt,.pdf,.doc,.docx,.ppt,.pptx,.wps,.rtf,.md"
          >
            <el-button class="btn-ghost">选择文件</el-button>
            <template #tip>
              <div class="upload-tip">支持 txt, pdf, doc, docx, ppt, pptx, wps, rtf, md 格式</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleDialogClose">取消</el-button>
        <el-button class="btn-apple" :loading="uploading" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 批量上传对话框 -->
    <el-dialog v-model="batchUploadDialogVisible" title="批量上传文档" width="500px" @close="handleBatchDialogClose">
      <el-form ref="batchUploadFormRef" :model="batchUploadForm" label-width="80px">
        <el-form-item label="所属分类" prop="category_id">
          <el-select v-model="batchUploadForm.category_id" placeholder="选择分类" style="width: 100%;">
            <el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="文档级别" prop="doc_level">
          <el-radio-group v-model="batchUploadForm.doc_level">
            <el-radio label="public">公开</el-radio>
            <el-radio label="private">私密</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="文档密级" prop="min_level">
          <el-select v-model="batchUploadForm.min_level" style="width: 100%;">
            <el-option v-for="(label, level) in clearanceLevels" :key="level" :label="label" :value="level" />
          </el-select>
          <div class="upload-tip">批量上传所有文件共用此密级</div>
        </el-form-item>
        <el-form-item label="选择文件夹" prop="files">
          <div class="batch-folder-upload">
            <input
              ref="batchFolderInput"
              type="file"
              webkitdirectory
              multiple
              class="folder-input"
              @change="handleBatchFolderChange"
            />
            <el-button class="btn-apple" @click="batchFolderInput.click()">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              选择文件夹
            </el-button>
            <el-button v-if="batchFileList.length" class="btn-ghost danger-text" @click="clearBatchFiles">
              清空 ({{ batchFileList.length }})
            </el-button>
            <div class="upload-tip">选择一个文件夹，自动收集其中所有支持的文档（txt, pdf, doc, docx, ppt, pptx, wps, rtf, md，单次最多200个）</div>
            <div v-if="batchFileList.length" class="batch-file-preview">
              <el-tag v-for="(f, i) in batchFileList" :key="i" size="small" closable @close="removeBatchFile(i)">
                {{ f.name }}
              </el-tag>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <div v-if="batchUploading" class="batch-progress">
        <el-progress :percentage="batchProgress" :stroke-width="14" :status="batchProgressStatus" />
        <div class="batch-progress-text">
          <span v-if="batchCurrentFile">正在处理：{{ batchCurrentFile }}</span>
          <span>成功 {{ batchSuccess }} / 失败 {{ batchFail }} / 共 {{ batchTotal }}</span>
        </div>
      </div>
      <template #footer>
        <el-button :disabled="batchUploading" @click="handleBatchDialogClose">取消</el-button>
        <el-button class="btn-apple" :loading="batchUploading" @click="handleBatchUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
defineOptions({ name: 'Document' })
import { ref, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { documentAPI, categoryAPI } from '../api'

const router = useRouter()

// 密级定义（与后端 settings.CLEARANCE_LEVELS 一致）
const clearanceLevels = { 1: '公开', 2: '内部', 3: '机密', 4: '绝密' }
const levelTagType = (level) => {
  return { 1: 'success', 2: 'primary', 3: 'warning', 4: 'danger' }[level] || 'info'
}

// 文件类型 → 彩色字母块元数据（替代 emoji 图标）
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
const fileMeta = (type) => fileTypeMeta[(type || '').toLowerCase()] || { letter: 'DOC', color: '#0071e3', bg: '#e6f1ff' }
const fileStyle = (type) => {
  const m = fileMeta(type)
  return { color: m.color, background: m.bg }
}

const documents = ref([])
const categories = ref([])
const searchKeyword = ref('')
const filterCategory = ref(null)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

// 上传相关
const uploadDialogVisible = ref(false)
const uploadFormRef = ref(null)
const uploadRef = ref(null)
const uploading = ref(false)
const uploadForm = ref({
  title: '',
  category_id: null,
  doc_level: 'public',
  min_level: 1
})
const fileList = ref([])
const selectedFile = ref(null)

// 批量上传相关
const batchUploadDialogVisible = ref(false)
const batchUploadFormRef = ref(null)
const batchFolderInput = ref(null)
const batchUploading = ref(false)
const batchUploadForm = ref({
  category_id: null,
  doc_level: 'public',
  min_level: 1
})
const batchFileList = ref([])
const batchSelectedFiles = ref([])
// 异步批量上传进度
const batchPollTimer = ref(null)
const batchBarVisible = ref(false)   // 页面顶部进度条是否显示
const batchDetail = ref('')          // 页级进度详情（如"解析第87/319页"）
const batchSubmitted = ref(false)    // 是否已提交（提交后对话框关闭由进度流程管理）
const batchProgress = ref(0)
const batchProgressStatus = ref('')
const batchCurrentFile = ref('')
const batchSuccess = ref(0)
const batchFail = ref(0)
const batchTotal = ref(0)
const currentBatchId = ref('')       // 当前批量任务ID（控制按钮用）
const batchStatus = ref('running')   // running | paused | cancelled | done
const batchCancelling = ref(false)   // 取消请求是否已发出（清理中）

// 批量任务进行中（可暂停/取消）；已暂停单独判断
const batchActive = computed(() => batchStatus.value === 'running' || batchStatus.value === 'paused')
const batchPaused = computed(() => batchStatus.value === 'paused')

// 获取用户信息判断删除权限
const userInfo = JSON.parse(localStorage.getItem('userInfo') || '{}')

// 加载文档列表
const loadDocuments = async () => {
  try {
    const res = await documentAPI.getList({
      page: page.value,
      limit: pageSize.value,
      keyword: searchKeyword.value,
      category_id: filterCategory.value
    })
    documents.value = res.data.list
    total.value = res.data.total
  } catch (error) {
    console.error('加载文档失败:', error)
  }
}

// 加载分类列表
const loadCategories = async () => {
  try {
    const res = await categoryAPI.getList()
    categories.value = res.data
  } catch (error) {
    console.error('加载分类失败:', error)
  }
}

// 显示上传对话框
const showUploadDialog = () => {
  uploadForm.value = { title: '', category_id: null, doc_level: 'public', min_level: 1 }
  fileList.value = []
  selectedFile.value = null
  // 加载分类列表
  loadCategories()
  uploadDialogVisible.value = true
}

// 处理文件选择
const handleFileChange = (file, files) => {
  console.log('File changed:', file, files)
  console.log('File raw:', file.raw)
  console.log('File name:', file.name)
  console.log('File size:', file.size)
  selectedFile.value = file.raw
  fileList.value = files
  if (!uploadForm.value.title && file.name) {
    uploadForm.value.title = file.name.replace(/\.[^.]+$/, '')
  }
}

// 清除选择文件
const clearFiles = () => {
  fileList.value = []
  selectedFile.value = null
}

// 处理对话框关闭
const handleDialogClose = () => {
  clearFiles()
  uploadDialogVisible.value = false
}

// 上传文档
const handleUpload = async () => {
  console.log('Upload clicked')
  console.log('selectedFile:', selectedFile.value)
  console.log('uploadForm:', uploadForm.value)

  if (!selectedFile.value) {
    ElMessage.warning('请选择要上传的文件')
    return
  }

  if (!uploadForm.value.title) {
    ElMessage.warning('请输入文档标题')
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('title', uploadForm.value.title)
    // 只在有分类ID时才添加
    if (uploadForm.value.category_id) {
      formData.append('category_id', uploadForm.value.category_id)
    }
    formData.append('doc_level', uploadForm.value.doc_level)
    formData.append('min_level', uploadForm.value.min_level)

    console.log('FormData entries:')
    for (let [key, value] of formData.entries()) {
      console.log(`  ${key}:`, value)
    }

    const res = await documentAPI.upload(formData)

    // 大文件自动转后台异步：立即返回 batch_id，复用顶部进度条展示页级进度
    if (res.data?.async && res.data.batch_id) {
      ElMessage.info(res.message || '文件较大，已转入后台处理')
      handleDialogClose()
      loadDocuments()
      batchUploading.value = true
      batchSubmitted.value = true
      batchTotal.value = 1
      batchBarVisible.value = true
      pollBatchStatus(res.data.batch_id)
      return
    }

    console.log('Upload response:', res)
    ElMessage.success('上传成功')
    handleDialogClose()
    loadDocuments()
  } catch (error) {
    console.error('上传失败:', error)
    if (error.response) {
      console.error('Error response data:', error.response.data)
      console.error('Error response status:', error.response.status)
    }
  } finally {
    uploading.value = false
  }
}

// 显示批量上传对话框
const showBatchUploadDialog = () => {
  batchUploadForm.value = { category_id: null, doc_level: 'public', min_level: 1 }
  batchFileList.value = []
  batchSelectedFiles.value = []
  batchProgress.value = 0
  batchProgressStatus.value = ''
  batchCurrentFile.value = ''
  batchSuccess.value = 0
  batchFail.value = 0
  batchSubmitted.value = false
  currentBatchId.value = ''
  batchStatus.value = 'running'
  batchCancelling.value = false
  // 加载分类列表
  loadCategories()
  batchUploadDialogVisible.value = true
}

// 处理文件夹选择（webkitdirectory 递归收集目录内所有文件）
const handleBatchFolderChange = (event) => {
  const input = event.target
  const allFiles = Array.from(input.files || [])
  const allowed = ['.txt', '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.wps', '.rtf', '.md']
  const supported = allFiles.filter(f => {
    const ext = '.' + ((f.name.split('.').pop() || '').toLowerCase())
    return allowed.includes(ext)
  })
  // 限制批量大小（与后端 MAX_BATCH_SIZE=200 对齐）
  const capped = supported.slice(0, 200)
  if (supported.length > capped.length) {
    ElMessage.warning(`文件夹中支持的文档共${supported.length}个，单次仅上传前${capped.length}个`)
  }
  batchFileList.value = capped.map(f => ({
    name: f.webkitRelativePath || f.name,
    raw: f
  }))
  batchSelectedFiles.value = capped
  // 重置 input，保证再次选择同一文件夹也会触发 change
  input.value = ''
}

// 移除批量选择中的单个文件
const removeBatchFile = (index) => {
  batchFileList.value.splice(index, 1)
  batchSelectedFiles.value = batchFileList.value.map(f => f.raw)
}

// 清除批量选择文件
const clearBatchFiles = () => {
  batchFileList.value = []
  batchSelectedFiles.value = []
}

// 处理批量上传对话框关闭
const handleBatchDialogClose = () => {
  // 已提交：关闭动作由上传流程控制，状态交给顶部进度条管理
  if (batchSubmitted.value) {
    batchSubmitted.value = false
    return
  }
  stopBatchPolling()
  clearBatchFiles()
  batchUploading.value = false
  batchUploadDialogVisible.value = false
}

// 停止批量轮询
const stopBatchPolling = () => {
  if (batchPollTimer.value) {
    clearInterval(batchPollTimer.value)
    batchPollTimer.value = null
  }
}

// 轮询批量任务进度
const pollBatchStatus = (batchId) => {
  currentBatchId.value = batchId
  batchStatus.value = 'running'
  batchCancelling.value = false
  batchDetail.value = ''
  stopBatchPolling()
  batchPollTimer.value = setInterval(async () => {
    try {
      const res = await documentAPI.batchStatus(batchId)
      const state = res.data
      batchStatus.value = state.status || 'running'
      batchCurrentFile.value = state.current_file || ''
      batchDetail.value = state.detail || ''
      batchSuccess.value = state.success_count || 0
      batchFail.value = state.fail_count || 0
      batchTotal.value = state.total || 0
      batchProgress.value = state.total ? Math.round((state.processed / state.total) * 100) : 0

      if (state.status === 'paused') {
        // 暂停态：保持轮询，等待恢复或取消
        return
      }
      if (state.status === 'cancelled') {
        stopBatchPolling()
        batchUploading.value = false
        batchCancelling.value = false
        const r = state.cancel_result || {}
        let message = r.mode === 'all' ? '已取消此次全部上传' : '已取消未上传的文档'
        if (r.removed_rows > 0 || r.removed_from_vector > 0) {
          message += `（清理${r.removed_rows}条记录、${r.removed_from_vector}个文档的向量）`
        }
        ElMessage.warning(message)
        batchBarVisible.value = false
        clearBatchFiles()
        loadDocuments()
        return
      }
      if (state.status === 'done') {
        stopBatchPolling()
        batchProgress.value = 100
        batchProgressStatus.value = batchFail.value > 0 ? 'warning' : 'success'
        batchCurrentFile.value = ''
        batchUploading.value = false
        let message = `批量上传完成，成功${batchSuccess.value}个`
        if (batchFail.value > 0) message += `，失败${batchFail.value}个`
        if (state.stage_fail_count > 0) message += `（暂存阶段失败${state.stage_fail_count}个）`
        ElMessage[state.stage_fail_count > 0 || batchFail.value > 0 ? 'warning' : 'success'](message)
        // 短暂展示 100% 后再收起顶部进度条
        setTimeout(() => { batchBarVisible.value = false }, 1500)
        clearBatchFiles()
        loadDocuments()
      }
    } catch (error) {
      console.error('查询批量进度失败:', error)
      stopBatchPolling()
      batchUploading.value = false
      batchBarVisible.value = false
    }
  }, 2000)
}

// 暂停批量任务
const pauseBatch = async () => {
  if (!currentBatchId.value) return
  try {
    await documentAPI.batchControl(currentBatchId.value, 'pause')
    batchStatus.value = 'paused'
    ElMessage.success('已暂停，可稍后恢复')
  } catch (error) {
    console.error('暂停失败:', error)
  }
}

// 恢复批量任务
const resumeBatch = async () => {
  if (!currentBatchId.value) return
  try {
    await documentAPI.batchControl(currentBatchId.value, 'resume')
    batchStatus.value = 'running'
    ElMessage.success('已恢复上传')
  } catch (error) {
    console.error('恢复失败:', error)
  }
}

// 取消批量任务（mode: all=取消此次全部 / pending=取消未上传的）
const confirmCancelBatch = async (mode) => {
  const msg = mode === 'all'
    ? '将取消此次批量上传的全部文档，并抹除已上传文档在向量库中的数据。确定继续？'
    : '将取消尚未上传的文档（已上传的保留）。确定继续？'
  try {
    await ElMessageBox.confirm(msg, mode === 'all' ? '取消全部' : '取消未上传的', {
      type: 'warning',
      confirmButtonText: '确定取消',
      cancelButtonText: '再想想'
    })
  } catch {
    return
  }
  if (!currentBatchId.value) return
  batchCancelling.value = true
  try {
    await documentAPI.batchControl(currentBatchId.value, 'cancel', mode)
    // 后端可能异步清理：保持轮询直到状态变为 cancelled
    ElMessage.info('正在取消...')
  } catch (error) {
    console.error('取消失败:', error)
    batchCancelling.value = false
  }
}

// 批量上传文档（异步：提交后返回 batch_id，轮询进度）
const handleBatchUpload = async () => {
  if (batchSelectedFiles.value.length === 0) {
    ElMessage.warning('请选择至少一个文件夹')
    return
  }

  batchUploading.value = true
  batchProgress.value = 0
  batchProgressStatus.value = ''
  batchCurrentFile.value = ''
  batchSuccess.value = 0
  batchFail.value = 0
  batchTotal.value = batchSelectedFiles.value.length
  try {
    const formData = new FormData()
    batchSelectedFiles.value.forEach((file) => {
      formData.append('files', file)
    })
    if (batchUploadForm.value.category_id) {
      formData.append('category_id', batchUploadForm.value.category_id)
    }
    formData.append('doc_level', batchUploadForm.value.doc_level)
    formData.append('min_level', batchUploadForm.value.min_level)

    const res = await documentAPI.uploadBatch(formData)
    const { batch_id, total, stage_fail_count } = res.data
    batchTotal.value = total || 0
    // 提交完成：关闭对话框，改为页面顶部进度条实时显示
    batchSubmitted.value = true
    batchUploadDialogVisible.value = false
    if (!batch_id) {
      // 全部在暂存阶段失败，无待处理文件
      stopBatchPolling()
      batchUploading.value = false
      ElMessage.warning(`暂存失败${stage_fail_count || 0}个，没有可处理的文件`)
      clearBatchFiles()
      loadDocuments()
      return
    }
    batchBarVisible.value = true
    pollBatchStatus(batch_id)
  } catch (error) {
    console.error('批量上传提交失败:', error)
    if (error.response) {
      console.error('Error response data:', error.response.data)
      console.error('Error response status:', error.response.status)
    }
    stopBatchPolling()
    batchUploading.value = false
    batchBarVisible.value = false
  }
}

// 判断是否可以删除
const canDelete = (doc) => {
  return userInfo.role === 'admin' || doc.upload_by === userInfo.id
}

// 打开文档全屏详情页（预览 + 元数据）
const openDetail = (doc) => {
  router.push(`/document/${doc.id}`)
}

// 下载文档
const downloadDocument = async (doc) => {
  try {
    const res = await documentAPI.download(doc.id)
    const url = window.URL.createObjectURL(new Blob([res]))
    const link = document.createElement('a')
    link.href = url
    link.download = doc.file_name
    link.click()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error('下载失败')
  }
}

// 删除文档
const deleteDocument = async (doc) => {
  try {
    await ElMessageBox.confirm('确定要删除该文档吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await documentAPI.delete(doc.id)
    ElMessage.success('删除成功')
    loadDocuments()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
    }
  }
}

// 格式化文件大小
const formatFileSize = (size) => {
  if (!size || size === '0 B') return '0 B'
  // 如果已经是字符串格式，直接返回
  if (typeof size === 'string') return size
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let numSize = Number(size)
  while (numSize >= 1024 && i < units.length - 1) {
    numSize /= 1024
    i++
  }
  return `${numSize.toFixed(1)} ${units[i]}`
}

onMounted(() => {
  loadDocuments()
  loadCategories()
})

// keep-alive 重新激活（从其他页面切回知识库）时刷新列表，保持数据最新
onActivated(() => {
  loadDocuments()
  loadCategories()
})
</script>

<style scoped>
.document-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  overflow: hidden;
  padding: var(--space-7) var(--space-6);
}

.header-actions {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}
.header-actions .el-button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border-radius: 980px;
}

/* 全局按钮样式 */
.btn-apple {
  border: none;
  background: var(--grad-btn);
  color: #fff;
  font-weight: 600;
  height: 38px;
  padding: 0 20px;
  border-radius: 980px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.btn-apple:hover { filter: brightness(1.06); color: #fff; }
.btn-apple:active { transform: scale(.97); }
.btn-apple.is-loading { color: #fff; }
.btn-ghost {
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text2);
  font-weight: 500;
  height: 38px;
  border-radius: 980px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.btn-ghost:hover { border-color: var(--primary); color: var(--primary); background: var(--card); }
.btn-ghost.danger-text:hover { border-color: var(--el-color-danger); color: var(--el-color-danger); }

.filter-bar {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.filter-search { width: 300px; }
.filter-select { width: 200px; }
.filter-bar :deep(.el-input__wrapper) {
  border-radius: 980px;
  background: var(--bg);
  box-shadow: 0 0 0 1px var(--border) inset;
  padding: 4px 16px;
  transition: box-shadow .2s;
}
.filter-bar :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1.5px var(--primary) inset, 0 0 0 4px var(--primary-soft);
}
.filter-bar :deep(.el-input__inner) { color: var(--text); }
.filter-bar :deep(.el-input__prefix) { color: var(--text3); display: flex; align-items: center; }
.filter-bar :deep(.el-select__wrapper) {
  border-radius: 980px;
  background: var(--bg);
  box-shadow: 0 0 0 1px var(--border) inset;
  transition: box-shadow .2s;
}
.filter-bar :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1.5px var(--primary) inset, 0 0 0 4px var(--primary-soft);
}
.filter-bar :deep(.el-select__selected-item) { color: var(--text2); }

.document-list {
  flex: 1;
  overflow-y: auto;
  padding-right: var(--space-1);
}

.doc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: var(--space-4);
}

.doc-card {
  position: relative;
  display: flex;
  gap: var(--space-4);
  align-items: flex-start;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  background: var(--card);
  transition: box-shadow .22s, transform .22s, border-color .22s;
}
.doc-card:hover {
  box-shadow: var(--shadow-hover);
  transform: translateY(-2px);
  border-color: var(--border-strong, var(--border));
}

/* 彩色字母块文件图标 */
.doc-icon {
  width: 44px;
  height: 44px;
  flex: none;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .02em;
}
.doc-icon.lg { width: 52px; height: 52px; font-size: 14px; border-radius: 14px; }

.doc-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.doc-info:hover .doc-title { color: var(--primary); }
.doc-title {
  margin: 0 0 var(--space-2) 0;
  font-size: 15.5px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.doc-meta {
  margin: 0 0 var(--space-2) 0;
  font-size: 12.5px;
  color: var(--text3);
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.dot { opacity: .6; }

.doc-tags {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.tag {
  font-size: 11px;
  padding: var(--space-1) var(--space-3);
  border-radius: 980px;
  font-weight: 500;
  background: var(--hover);
  color: var(--text2);
}
.tag.lv1 { background: var(--primary-soft); color: var(--primary); }
.tag.lv2 { background: var(--primary-soft); color: var(--primary); }
.tag.lv3 { background: var(--warning-soft, #fff4e5); color: var(--el-color-warning); }
.tag.lv4 { background: var(--danger-soft, #ffeded); color: var(--el-color-danger); }
.tag.private { background: var(--el-color-warning-light-9, #fff4e5); color: var(--el-color-warning); }

.doc-time {
  margin: 0;
  font-size: 12px;
  color: var(--text3);
}

/* 动作：渐进式披露，hover 淡入上浮，不常显遮挡内容 */
.doc-actions {
  position: absolute;
  top: var(--space-4);
  right: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  opacity: 0;
  transform: translateY(-4px);
  transition: opacity .18s ease, transform .18s ease;
}
.doc-card:hover .doc-actions,
.doc-card:focus-within .doc-actions {
  opacity: 1;
  transform: none;
}
/* 触屏设备无 hover：动作常显兜底，保证可操作 */
@media (hover: none) {
  .doc-actions {
    opacity: 1;
    transform: none;
  }
}
.act-btn {
  border: none;
  background: transparent;
  font-size: 12.5px;
  font-family: inherit;
  color: var(--primary);
  padding: var(--space-1) var(--space-3);
  border-radius: 980px;
  cursor: pointer;
  transition: background .15s;
}
.act-btn:hover { background: var(--primary-soft); }
.act-btn.danger { color: var(--el-color-danger); }
.act-btn.danger:hover { background: var(--el-color-danger-light-9, #ffeded); }

.pagination {
  margin-top: var(--space-4);
  display: flex;
  justify-content: center;
}

.upload-tip {
  color: var(--text3);
  font-size: 12px;
  margin-top: var(--space-1);
  line-height: 1.6;
}

.batch-folder-upload { width: 100%; }
.folder-input { display: none; }
.batch-folder-upload .el-button { border-radius: 980px; }

.batch-file-preview {
  margin-top: var(--space-3);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  max-height: 140px;
  overflow-y: auto;
}

.batch-progress {
  padding: var(--space-3) 0 var(--space-1);
}
.batch-progress-text {
  display: flex;
  justify-content: space-between;
  color: var(--text3);
  font-size: 12px;
  margin-top: var(--space-2);
}

/* 页面顶部批量上传进度条 */
.batch-upload-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  background: var(--primary-soft);
  border: 1px solid var(--primary-border, var(--el-color-primary-light-5));
  border-radius: var(--radius-lg);
  padding: var(--space-4) var(--space-5);
  margin-bottom: var(--space-5);
}
.batch-bar-icon {
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: 10px;
  background: var(--card);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 113, 227, .12);
}
.batch-bar-info {
  flex: 1;
  min-width: 0;
}
.batch-bar-title {
  font-weight: 600;
  color: var(--primary);
  font-size: 14px;
}
.batch-bar-file {
  font-size: 12px;
  color: var(--text2);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.batch-bar-progress { flex: 2; min-width: 200px; }
.batch-bar-count {
  font-size: 12px;
  color: var(--text2);
  white-space: nowrap;
}
.batch-bar-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  white-space: nowrap;
}
.batch-bar-actions .el-button { border-radius: 980px; }
</style>
