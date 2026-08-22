<template>
  <div class="logs-container">
    <div class="page-header">
      <h2 class="page-title">登录日志</h2>
      <p class="page-sub">记录所有用户登录尝试</p>
    </div>

    <div class="filter-bar">
      <el-input v-model="searchKeyword" placeholder="搜索用户名" clearable @change="loadLogs" class="filter-search">
        <template #prefix>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </template>
      </el-input>
    </div>

    <div class="table-card">
      <el-table :data="logs" class="apple-table">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="120">
          <template #default="{ row }">
            <span class="cell-user">{{ row.username }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP地址" width="150" />
        <el-table-column prop="login_status" label="状态" width="100">
          <template #default="{ row }">
            <span class="status-pill" :class="row.login_status === 1 ? 'ok' : 'fail'">
              {{ row.login_status === 1 ? '成功' : '失败' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="login_message" label="消息" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="log-msg" :class="row.login_status === 1 ? 'ok' : 'fail'">{{ row.login_message }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="登录时间" width="180" />
      </el-table>
    </div>

    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadLogs"
        @current-change="loadLogs"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminAPI } from '../api'

const logs = ref([])
const searchKeyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const loadLogs = async () => {
  try {
    const res = await adminAPI.getLoginLogs({
      page: page.value,
      limit: pageSize.value,
      keyword: searchKeyword.value
    })
    logs.value = res.data.list
    total.value = res.data.total
  } catch (error) {
    console.error('加载日志失败:', error)
  }
}

onMounted(() => {
  loadLogs()
})
</script>

<style scoped>
.logs-container {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  padding: var(--space-7) var(--space-6);
}

.filter-bar {
  margin-bottom: var(--space-4);
}
.filter-search { width: 300px; }
.filter-search :deep(.el-input__wrapper) {
  border-radius: 980px;
  background: var(--bg);
  box-shadow: 0 0 0 1px var(--border) inset;
  padding: 4px 16px;
  transition: box-shadow .2s;
}
.filter-search :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1.5px var(--primary) inset, 0 0 0 4px var(--primary-soft);
}
.filter-search :deep(.el-input__inner) { color: var(--text); }
.filter-search :deep(.el-input__prefix) { color: var(--text3); display: flex; align-items: center; }

.table-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--card);
}
.apple-table { width: 100%; }
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

.cell-user { color: var(--text); font-weight: 500; }

.status-pill {
  font-size: 11.5px;
  padding: var(--space-1) var(--space-3);
  border-radius: 980px;
  font-weight: 500;
  background: var(--hover);
  color: var(--text2);
}
.status-pill.ok { background: var(--el-color-success-light-9); color: var(--el-color-success); }
.status-pill.fail { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }

.log-msg.ok { color: var(--text2); }
.log-msg.fail { color: var(--el-color-danger); }

.pagination {
  margin-top: var(--space-4);
  display: flex;
  justify-content: center;
}
</style>
