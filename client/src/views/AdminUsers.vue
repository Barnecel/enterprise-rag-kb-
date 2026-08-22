<template>
  <div class="users-container">
    <div class="page-header">
      <h2 class="page-title">用户管理</h2>
      <p class="page-sub">管理系统用户、角色、部门与密级</p>
    </div>

    <div class="filter-bar">
      <el-input v-model="searchKeyword" placeholder="搜索用户名或姓名" clearable @change="loadUsers" class="filter-search">
        <template #prefix>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </template>
      </el-input>
    </div>

    <div class="table-card">
      <el-table :data="users" class="apple-table">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="120">
          <template #default="{ row }">
            <span class="cell-user">{{ row.username }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="real_name" label="真实姓名" width="120" />
        <el-table-column prop="email" label="邮箱" width="180" />
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="tenant_name" label="部门" width="120">
          <template #default="{ row }">{{ row.tenant_name || '未分配' }}</template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">
            <span class="role-pill" :class="row.role === 'admin' ? 'admin' : 'user'">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="clearance_level" label="密级" width="130">
          <template #default="{ row }">
            <el-select
              :model-value="row.clearance_level || 1"
              size="small"
              class="table-select"
              @change="(val) => handleClearanceChange(row, val)"
            >
              <el-option v-for="(label, level) in clearanceLevels" :key="level" :label="label" :value="level" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-switch
              v-model="row.status"
              :active-value="1"
              :inactive-value="0"
              @change="handleStatusChange(row)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="180" />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button class="table-act" size="small" text type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button class="table-act" size="small" text type="danger" @click="deleteUser(row)">删除</el-button>
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
        @size-change="loadUsers"
        @current-change="loadUsers"
      />
    </div>

    <!-- 编辑用户对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑用户" width="420px">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="用户名">
          <el-input :model-value="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="editForm.role" style="width: 100%;">
            <el-option label="普通用户" value="user" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属部门">
          <el-select v-model="editForm.tenant_id" style="width: 100%;">
            <el-option v-for="t in tenants" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="密级">
          <el-select v-model="editForm.clearance_level" style="width: 100%;">
            <el-option v-for="(label, level) in clearanceLevels" :key="level" :label="label" :value="level" />
          </el-select>
          <div class="edit-tip">密级变更需用户重新登录后生效</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button class="btn-apple" @click="handleEditSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userAPI } from '../api'

// 密级定义（与后端 settings.CLEARANCE_LEVELS 一致）
const clearanceLevels = { 1: '公开', 2: '内部', 3: '机密', 4: '绝密' }

const users = ref([])
const tenants = ref([])
const searchKeyword = ref('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

// 编辑用户对话框
const editDialogVisible = ref(false)
const editForm = ref({})

// 获取当前用户ID
const currentUserId = JSON.parse(localStorage.getItem('userInfo') || '{}').id || 0

// 加载用户列表
const loadUsers = async () => {
  try {
    const res = await userAPI.getUserList({
      page: page.value,
      limit: pageSize.value,
      keyword: searchKeyword.value
    })
    users.value = res.data.list
    total.value = res.data.total
  } catch (error) {
    console.error('加载用户失败:', error)
  }
}

// 加载部门租户列表
const loadTenants = async () => {
  try {
    const res = await userAPI.getTenants()
    tenants.value = res.data || []
  } catch (error) {
    console.error('加载部门失败:', error)
  }
}

// 打开编辑对话框
const openEditDialog = (user) => {
  editForm.value = {
    id: user.id,
    username: user.username,
    role: user.role,
    tenant_id: user.tenant_id,
    clearance_level: user.clearance_level || 1
  }
  editDialogVisible.value = true
}

// 保存编辑
const handleEditSubmit = async () => {
  try {
    await userAPI.updateUser(editForm.value.id, {
      role: editForm.value.role,
      tenant_id: editForm.value.tenant_id,
      clearance_level: editForm.value.clearance_level
    })
    ElMessage.success('更新成功')
    editDialogVisible.value = false
    loadUsers()
  } catch (error) {
    console.error('更新用户失败:', error)
  }
}

// 表格内直接修改密级
const handleClearanceChange = async (user, val) => {
  const oldVal = user.clearance_level || 1
  user.clearance_level = val
  try {
    await userAPI.updateUser(user.id, { clearance_level: val })
    ElMessage.success(`已将 ${user.username} 密级设为 ${clearanceLevels[val]}`)
  } catch (error) {
    user.clearance_level = oldVal
    console.error('更新密级失败:', error)
  }
}

// 修改用户状态
const handleStatusChange = async (user) => {
  try {
    await userAPI.updateUserStatus(user.id, user.status)
    ElMessage.success('状态更新成功')
  } catch (error) {
    // 恢复原状态
    user.status = user.status === 1 ? 0 : 1
    console.error('更新状态失败:', error)
  }
}

// 删除用户
const deleteUser = async (user) => {
  try {
    await ElMessageBox.confirm('确定要删除该用户吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await userAPI.deleteUser(user.id)
    ElMessage.success('删除成功')
    loadUsers()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
    }
  }
}

onMounted(() => {
  loadUsers()
  loadTenants()
})
</script>

<style scoped>
.users-container {
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

/* 表格卡片：宽表横向滚动，列不挤压 */
.table-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow-x: auto;
  background: var(--card);
}
.apple-table { width: 100%; min-width: 1410px; }
.apple-table :deep(.el-table__header th.el-table__cell) {
  background: var(--bg);
  color: var(--text3);
  font-weight: 600;
  font-size: 12.5px;
}
.apple-table :deep(.el-table__body td.el-table__cell) {
  color: var(--text2);
}
.apple-table :deep(.el-table__row) { background: transparent; }
.apple-table :deep(.el-table__row--striped) { background: transparent; }
.apple-table :deep(.el-table__row:hover > td.el-table__cell) {
  background: var(--row-hover) !important;
}
.apple-table :deep(.el-table__inner-wrapper) { background: transparent; }

.cell-user { color: var(--text); font-weight: 500; }

.role-pill {
  font-size: 11.5px;
  padding: var(--space-1) var(--space-3);
  border-radius: 980px;
  font-weight: 500;
  background: var(--hover);
  color: var(--text2);
}
.role-pill.admin {
  background: var(--primary-soft);
  color: var(--primary);
}

.table-select { width: 100px; }
.table-act { border-radius: 980px; }

.pagination {
  margin-top: var(--space-4);
  display: flex;
  justify-content: center;
}

.edit-tip {
  color: var(--text3);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 4px;
}

/* 窄屏隐藏低价值 ID 列，降低横向压力 */
@media (max-width: 860px) {
  .apple-table :deep(th.el-table__cell:nth-child(1)),
  .apple-table :deep(td.el-table__cell:nth-child(1)) {
    display: none;
  }
}

.btn-apple {
  border: none;
  background: var(--grad-btn);
  color: #fff;
  font-weight: 600;
  height: 38px;
  padding: 0 var(--space-5);
  border-radius: 980px;
}
.btn-apple:hover { filter: brightness(1.06); color: #fff; }
</style>
