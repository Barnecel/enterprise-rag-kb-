<template>
  <div class="categories-container">
    <div class="page-header">
      <div>
        <h2 class="page-title">分类管理</h2>
        <p class="page-sub">维护知识库文档的分类层级</p>
      </div>
      <el-button class="btn-apple" @click="showAddDialog">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        添加分类
      </el-button>
    </div>

    <div class="table-card">
      <el-table :data="categories" class="apple-table" row-key="id" :tree-props="{ children: 'children' }">
        <el-table-column prop="name" label="分类名称" min-width="200">
          <template #default="{ row }">
            <span class="cat-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="cat-desc">{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="80" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button class="table-act" size="small" text type="primary" @click="showEditDialog(row)">编辑</el-button>
            <el-button class="table-act" size="small" text type="danger" @click="deleteCategory(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑分类' : '添加分类'" width="500px">
      <el-form ref="formRef" :model="form" label-width="80px">
        <el-form-item label="分类名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入分类名称" />
        </el-form-item>
        <el-form-item label="分类描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入分类描述" />
        </el-form-item>
        <el-form-item label="父分类" prop="parent_id">
          <el-select v-model="form.parent_id" placeholder="选择父分类(可选)" clearable style="width: 100%;">
            <el-option label="无（顶级分类）" :value="0" />
            <el-option v-for="cat in flatCategories" :key="cat.id" :label="cat.name" :value="cat.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button class="btn-apple" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { categoryAPI } from '../api'

const categories = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const saving = ref(false)

const form = reactive({
  id: null,
  name: '',
  description: '',
  parent_id: 0,
  sort_order: 0
})

// 扁平化分类用于父分类选择
const flatCategories = computed(() => {
  const result = []
  const flatten = (cats, prefix = '') => {
    cats.forEach(cat => {
      result.push({ id: cat.id, name: prefix + cat.name })
      if (cat.children && cat.children.length > 0) {
        flatten(cat.children, prefix + '— ')
      }
    })
  }
  flatten(categories.value)
  return result
})

const loadCategories = async () => {
  try {
    const res = await categoryAPI.getList()
    categories.value = res.data
  } catch (error) {
    console.error('加载分类失败:', error)
  }
}

const showAddDialog = () => {
  isEdit.value = false
  Object.assign(form, { id: null, name: '', description: '', parent_id: 0, sort_order: 0 })
  dialogVisible.value = true
}

const showEditDialog = (row) => {
  isEdit.value = true
  Object.assign(form, { id: row.id, name: row.name, description: row.description, parent_id: row.parent_id, sort_order: row.sort_order })
  dialogVisible.value = true
}

const handleSave = async () => {
  saving.value = true
  try {
    if (isEdit.value) {
      await categoryAPI.update(form.id, form)
    } else {
      await categoryAPI.create(form)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadCategories()
  } catch (error) {
    console.error('保存失败:', error)
  } finally {
    saving.value = false
  }
}

const deleteCategory = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除该分类吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await categoryAPI.delete(row.id)
    ElMessage.success('删除成功')
    loadCategories()
  } catch (error) {
    if (error !== 'cancel') console.error('删除失败:', error)
  }
}

onMounted(() => {
  loadCategories()
})
</script>

<style scoped>
.categories-container {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  padding: var(--space-7) var(--space-6);
}

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
.apple-table :deep(.el-table__indent) { padding-left: 8px; }

.cat-name { color: var(--text); font-weight: 500; }
.cat-desc { color: var(--text3); }
.table-act { border-radius: 980px; }

.btn-apple {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: none;
  background: var(--grad-btn);
  color: #fff;
  font-weight: 600;
  height: 38px;
  padding: 0 var(--space-5);
  border-radius: 980px;
}
.btn-apple:hover { filter: brightness(1.06); color: #fff; }
.btn-apple:active { transform: scale(.97); }
</style>
