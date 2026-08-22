<template>
  <div class="admin-docs-container">
    <div class="page-header">
      <h2 class="page-title">文档管理</h2>
      <p class="page-sub">审核与管理知识库中的全部文档</p>
    </div>

    <div class="filter-bar">
      <el-input v-model="searchKeyword" placeholder="搜索文档标题" clearable @change="loadDocuments" class="filter-search">
        <template #prefix>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </template>
      </el-input>
      <el-select v-model="filterStatus" placeholder="文档状态" clearable @change="loadDocuments" class="filter-select">
        <el-option label="待处理" value="pending" />
        <el-option label="处理中" value="processing" />
        <el-option label="已完成" value="completed" />
        <el-option label="失败" value="failed" />
      </el-select>
    </div>

    <div class="table-card">
      <el-table :data="documents" class="apple-table">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="cell-title">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category_name" label="分类" width="110" />
        <el-table-column prop="file_name" label="文件名" width="140" show-overflow-tooltip />
        <el-table-column prop="file_size" label="大小" width="90" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <span class="status-pill" :class="row.status">
              {{ getStatusText(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="doc_level" label="级别" width="80">
          <template #default="{ row }">
            {{ row.doc_level === 'public' ? '公开' : '私密' }}
          </template>
        </el-table-column>
        <el-table-column prop="min_level" label="密级" width="90">
          <template #default="{ row }">
            <span class="level-pill" :class="'lv' + (row.min_level || 1)">
              {{ clearanceLevels[row.min_level] || '公开' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="tenant_name" label="部门" width="100" />
        <el-table-column prop="view_count" label="浏览" width="70" />
        <el-table-column prop="upload_by_name" label="上传人" width="100" />
        <el-table-column prop="created_at" label="上传时间" width="160" />
        <el-table-column label="操作" width="270" fixed="right">
          <template #default="{ row }">
            <el-button class="table-act" size="small" text type="primary" @click="openDetail(row)">打开</el-button>
            <el-button class="table-act" size="small" text type="primary" @click="viewDocument(row)">查看</el-button>
            <el-button class="table-act" size="small" text type="warning" @click="openAclDialog(row)">授权/密级</el-button>
            <el-button class="table-act" size="small" text type="danger" @click="deleteDocument(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pagination">
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

    <el-dialog v-model="detailDialogVisible" title="文档详情" width="600px">
      <div v-if="selectedDoc" class="doc-detail">
        <div class="detail-head">
          <div class="doc-icon" :style="fileStyle(selectedDoc.file_type)">
            {{ fileMeta(selectedDoc.file_type).letter }}
          </div>
          <div>
            <h3>{{ selectedDoc.title }}</h3>
            <div class="detail-info">
              <span>{{ selectedDoc.category_name || '未分类' }}</span>
              <span class="dot">·</span>
              <span>{{ selectedDoc.file_size }}</span>
              <span class="dot">·</span>
              <span>{{ selectedDoc.view_count }} 次浏览</span>
            </div>
          </div>
        </div>
        <div class="detail-list">
          <p><strong>文件名：</strong>{{ selectedDoc.file_name }}</p>
          <p><strong>状态：</strong>{{ getStatusText(selectedDoc.status) }}</p>
          <p><strong>上传人：</strong>{{ selectedDoc.upload_by_name }}</p>
          <p><strong>上传时间：</strong>{{ selectedDoc.created_at }}</p>
        </div>
        <div class="detail-content">
          <h4>文档摘要</h4>
          <p>{{ selectedDoc.content || '暂无摘要' }}</p>
        </div>
      </div>
    </el-dialog>

    <!-- 授权/密级对话框 -->
    <el-dialog v-model="aclDialogVisible" title="文档授权 / 密级设置" width="560px" @open="handleAclDialogOpen">
      <div v-if="aclDoc" class="acl-dialog">
        <el-form label-width="90px">
          <el-form-item label="文档">
            <span class="acl-doc-title">{{ aclDoc.title }}</span>
          </el-form-item>
          <el-form-item label="文档密级">
            <div class="acl-level-row">
              <el-select v-model="aclMinLevel" style="width: 200px;">
                <el-option v-for="(label, level) in clearanceLevels" :key="level" :label="label" :value="level" />
              </el-select>
              <el-button class="btn-ghost" @click="saveAclMinLevel">保存密级</el-button>
              <span class="acl-hint">低于此密级的用户不可见/不可检索</span>
            </div>
          </el-form-item>
        </el-form>

        <el-divider />
        <div class="acl-add-row">
          <el-select v-model="aclUserSelect" placeholder="选择要授权的用户" filterable style="width: 240px;">
            <el-option
              v-for="u in availableUsers"
              :key="u.id"
              :label="`${u.real_name || u.username}（${u.username}）`"
              :value="u.id"
            />
          </el-select>
          <el-button class="btn-apple" :disabled="!aclUserSelect" @click="grantAcl">添加授权</el-button>
        </div>
        <div class="acl-tip">授权用户可访问此文档（不受部门/密级限制），授权即时生效</div>

        <el-table :data="aclUsers" size="small" class="acl-table" style="width: 100%; margin-top: 12px;">
          <el-table-column prop="username" label="用户名" width="120" />
          <el-table-column prop="real_name" label="姓名" width="120" />
          <el-table-column prop="created_at" label="授权时间" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button class="table-act" size="small" text type="danger" @click="revokeAcl(row)">撤销</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { documentAPI, userAPI } from '../api'

const router = useRouter()

// 密级定义（与后端 settings.CLEARANCE_LEVELS 一致）
const clearanceLevels = { 1: '公开', 2: '内部', 3: '机密', 4: '绝密' }
const levelTagType = (level) => {
  return { 1: 'success', 2: 'primary', 3: 'warning', 4: 'danger' }[level] || 'info'
}

// 文件类型 → 彩色字母块元数据
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
const searchKeyword = ref('')
const filterStatus = ref('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

const detailDialogVisible = ref(false)
const selectedDoc = ref(null)

// 授权/密级对话框
const aclDialogVisible = ref(false)
const aclDoc = ref(null)
const aclMinLevel = ref(1)
const aclUsers = ref([])
const aclUserSelect = ref(null)
const allUsers = ref([])
// 已授权用户在下拉中过滤掉
const availableUsers = computed(() => {
  const grantedIds = new Set(aclUsers.value.map(u => u.user_id))
  return allUsers.value.filter(u => !grantedIds.has(u.id))
})

const loadDocuments = async () => {
  try {
    const res = await documentAPI.getList({
      page: page.value,
      limit: pageSize.value,
      keyword: searchKeyword.value,
      status: filterStatus.value
    })
    documents.value = res.data.list
    total.value = res.data.total
  } catch (error) {
    console.error('加载文档失败:', error)
  }
}

const getStatusType = (status) => {
  const types = { pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = { pending: '待处理', processing: '处理中', completed: '已完成', failed: '失败' }
  return texts[status] || status
}

// 打开文档全屏详情页（预览 + 元数据）
const openDetail = (doc) => {
  router.push(`/document/${doc.id}`)
}

const viewDocument = (doc) => {
  selectedDoc.value = doc
  detailDialogVisible.value = true
}

// 打开授权/密级对话框
const openAclDialog = (doc) => {
  aclDoc.value = doc
  aclMinLevel.value = doc.min_level || 1
  aclUserSelect.value = null
  loadAclUsers()
  loadAllUsers()
  aclDialogVisible.value = true
}

const handleAclDialogOpen = () => {
  loadAclUsers()
  loadAllUsers()
}

// 加载已授权用户列表
const loadAclUsers = async () => {
  if (!aclDoc.value) return
  try {
    const res = await documentAPI.getAcl(aclDoc.value.id)
    aclUsers.value = res.data || []
  } catch (error) {
    console.error('加载授权列表失败:', error)
  }
}

// 加载全部用户（供授权下拉选择）
const loadAllUsers = async () => {
  try {
    const res = await userAPI.getUserList({ page: 1, limit: 100 })
    allUsers.value = res.data.list || []
  } catch (error) {
    console.error('加载用户列表失败:', error)
  }
}

// 授权用户
const grantAcl = async () => {
  if (!aclUserSelect.value || !aclDoc.value) return
  try {
    await documentAPI.grantAcl(aclDoc.value.id, aclUserSelect.value)
    ElMessage.success('授权成功')
    aclUserSelect.value = null
    loadAclUsers()
  } catch (error) {
    console.error('授权失败:', error)
  }
}

// 撤销授权
const revokeAcl = async (row) => {
  if (!aclDoc.value) return
  try {
    await ElMessageBox.confirm(`确定撤销 ${row.real_name || row.username} 的访问授权吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await documentAPI.revokeAcl(aclDoc.value.id, row.user_id)
    ElMessage.success('撤销成功')
    loadAclUsers()
  } catch (error) {
    if (error !== 'cancel') console.error('撤销失败:', error)
  }
}

// 保存密级
const saveAclMinLevel = async () => {
  if (!aclDoc.value) return
  try {
    await documentAPI.update(aclDoc.value.id, { min_level: aclMinLevel.value })
    ElMessage.success('密级已更新')
    aclDoc.value.min_level = aclMinLevel.value
    loadDocuments()
  } catch (error) {
    console.error('更新密级失败:', error)
  }
}

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
    if (error !== 'cancel') console.error('删除失败:', error)
  }
}

onMounted(() => {
  loadDocuments()
})
</script>

<style scoped>
.admin-docs-container {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  padding: var(--space-7) var(--space-6);
}

.filter-bar {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.filter-search { width: 300px; }
.filter-select { width: 160px; }
.filter-bar :deep(.el-input__wrapper),
.filter-bar :deep(.el-select__wrapper) {
  border-radius: 980px;
  background: var(--bg);
  box-shadow: 0 0 0 1px var(--border) inset;
  transition: box-shadow .2s;
}
.filter-bar :deep(.el-input__wrapper.is-focus),
.filter-bar :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1.5px var(--primary) inset, 0 0 0 4px var(--primary-soft);
}
.filter-bar :deep(.el-input__inner) { color: var(--text); }
.filter-bar :deep(.el-input__prefix) { color: var(--text3); display: flex; align-items: center; }
.filter-bar :deep(.el-select__selected-item) { color: var(--text2); }

/* 表格卡片：宽表横向滚动，列不挤压 */
.table-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow-x: auto;
  background: var(--card);
}
.apple-table { width: 100%; min-width: 1510px; }
.apple-table :deep(.el-table__header th.el-table__cell) {
  background: var(--bg);
  color: var(--text3);
  font-weight: 600;
  font-size: 12.5px;
}
.apple-table :deep(.el-table__body td.el-table__cell) {
  color: var(--text2);
}
.apple-table :deep(.el-table__row:hover > td.el-table__cell) {
  background: var(--row-hover) !important;
}
.apple-table :deep(.el-table__inner-wrapper) { background: transparent; }

.cell-title { color: var(--text); font-weight: 500; }

.status-pill {
  font-size: 11.5px;
  padding: var(--space-1) var(--space-3);
  border-radius: 980px;
  font-weight: 500;
  background: var(--hover);
  color: var(--text2);
}
.status-pill.completed { background: var(--el-color-success-light-9); color: var(--el-color-success); }
.status-pill.processing { background: var(--el-color-warning-light-9); color: var(--el-color-warning); }
.status-pill.failed { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }

.level-pill {
  font-size: 11px;
  padding: var(--space-1) var(--space-3);
  border-radius: 980px;
  font-weight: 500;
  background: var(--primary-soft);
  color: var(--primary);
}
.level-pill.lv3 { background: var(--el-color-warning-light-9); color: var(--el-color-warning); }
.level-pill.lv4 { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }

.table-act { border-radius: 980px; }

/* 窄屏隐藏低价值 ID 列，降低横向压力 */
@media (max-width: 860px) {
  .apple-table :deep(th.el-table__cell:nth-child(1)),
  .apple-table :deep(td.el-table__cell:nth-child(1)) {
    display: none;
  }
}

.pagination {
  margin-top: var(--space-4);
  display: flex;
  justify-content: center;
}

/* 详情 */
.doc-detail .detail-head {
  display: flex;
  gap: var(--space-4);
  align-items: center;
  padding-bottom: var(--space-4);
  margin-bottom: var(--space-4);
  border-bottom: 1px solid var(--border);
}
.doc-detail h3 {
  margin: 0 0 var(--space-2) 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}
.doc-icon {
  width: 52px;
  height: 52px;
  flex: none;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
}
.detail-info {
  display: flex;
  gap: 6px;
  align-items: center;
  color: var(--text3);
  font-size: 13px;
}
.dot { opacity: .6; }
.detail-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2) var(--space-6);
  margin-bottom: var(--space-4);
  padding: var(--space-4);
  background: var(--bg);
  border-radius: 12px;
}
.detail-list p { margin: 0; color: var(--text2); font-size: 13px; }
.detail-list strong { color: var(--text3); font-weight: 500; }
.detail-content h4 {
  color: var(--text2);
  margin: 0 0 var(--space-3) 0;
  font-size: 13px;
  font-weight: 600;
}
.detail-content p {
  color: var(--text2);
  line-height: 1.7;
  margin: 0;
  font-size: 14px;
}

/* ACL */
.acl-doc-title { color: var(--text); font-weight: 500; }
.acl-level-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.acl-hint { color: var(--text3); font-size: 12px; }
.acl-add-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.acl-tip { color: var(--text3); font-size: 12px; margin-top: 8px; }
.acl-table :deep(.el-table__header th.el-table__cell) {
  background: var(--bg);
  color: var(--text3);
  font-weight: 600;
  font-size: 12.5px;
}
.acl-table :deep(.el-table__row:hover > td.el-table__cell) {
  background: var(--row-hover) !important;
}

.btn-apple {
  border: none;
  background: var(--grad-btn);
  color: #fff;
  font-weight: 600;
  height: 38px;
  padding: 0 20px;
  border-radius: 980px;
}
.btn-apple:hover { filter: brightness(1.06); color: #fff; }
.btn-apple:disabled { opacity: .6; }
.btn-ghost {
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text2);
  font-weight: 500;
  height: 38px;
  border-radius: 980px;
}
.btn-ghost:hover { border-color: var(--primary); color: var(--primary); background: var(--card); }
</style>
