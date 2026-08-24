<template>
  <div class="admin-models">
    <div class="page-header">
      <div>
        <h1>模型接入</h1>
        <p class="subtitle">接入局域网 / 互联网的 OpenAI 兼容 API（oMLX · LM Studio · Ollama · vLLM · DeepSeek · 通义 · Kimi · OpenAI）</p>
      </div>
      <div class="header-actions">
        <el-button v-if="rebuildRunning" size="small" type="warning" plain loading>重建中 {{ rebuildDetail }}</el-button>
        <el-button v-else-if="hasPendingRebuild" size="small" type="danger" @click="doRebuild">重建向量库</el-button>
        <el-button type="primary" size="small" @click="openAdd('llm')">
          + 接入生成模型
        </el-button>
        <el-button type="success" size="small" @click="openAdd('embedding')">
          + 接入嵌入模型
        </el-button>
      </div>
    </div>

    <!-- 运行时生效概览 -->
    <div class="runtime-cards">
      <div class="runtime-card">
        <span class="rt-label">当前生成模型</span>
        <span class="rt-value">{{ runtime.llm?.model_name || '-' }}</span>
        <span class="rt-base">{{ runtime.llm?.api_base }}</span>
      </div>
      <div class="runtime-card">
        <span class="rt-label">当前嵌入模型</span>
        <span class="rt-value">{{ runtime.embedding?.model_name || '-' }}</span>
        <span class="rt-base">{{ runtime.embedding?.api_base }}</span>
      </div>
    </div>

    <el-table :data="models" stripe border v-loading="loading" style="width:100%">
      <el-table-column label="名称" min-width="150">
        <template #default="{ row }">
          <b>{{ row.name }}</b>
          <el-tag v-if="row.is_active" size="small" type="success" effect="light" style="margin-left:6px">启用中</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="角色" width="90">
        <template #default="{ row }">
          <el-tag :type="row.model_type === 'llm' ? 'primary' : 'warning'" size="small" effect="plain">
            {{ row.model_type === 'llm' ? '生成' : '嵌入' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="model_name" label="模型名" min-width="180" show-overflow-tooltip />
      <el-table-column prop="api_base" label="端点" min-width="220" show-overflow-tooltip />
      <el-table-column label="密钥" width="130">
        <template #default="{ row }">{{ row.api_key_masked || '-' }}</template>
      </el-table-column>
      <el-table-column label="测试结果" min-width="170">
        <template #default="{ row }">
          <template v-if="testResults[row.id]">
            <span v-if="testResults[row.id].testing" class="t-testing">测试中...</span>
            <span v-else-if="testResults[row.id].ok" class="t-ok">
              ✅ {{ testResults[row.id].latency_ms }}ms
              <span v-if="testResults[row.id].dim != null">· {{ testResults[row.id].dim }}维</span>
              <span v-else-if="testResults[row.id].sample">· {{ testResults[row.id].sample }}</span>
            </span>
            <span v-else class="t-bad" :title="testResults[row.id].error">❌ {{ (testResults[row.id].error || '').slice(0, 30) }}</span>
          </template>
          <span v-else class="t-idle">未测试</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="runTest(row)" :loading="testResults[row.id]?.testing">测试</el-button>
          <el-button v-if="!row.is_active" size="small" type="primary" plain @click="activate(row)">启用</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑接入' : '接入新模型'" width="560px">
      <el-form label-width="92px">
        <el-form-item label="模型角色">
          <el-radio-group v-model="form.model_type" :disabled="!!editingId">
            <el-radio value="llm">生成 LLM</el-radio>
            <el-radio value="embedding">嵌入 Embedding</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="快速填入">
          <el-select v-model="presetKey" placeholder="选择服务商自动填充端点" style="width:100%" @change="applyPreset" clearable>
            <el-option v-for="p in presets" :key="p.label" :label="p.label" :value="p.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如：DeepSeek-V3 线上 / 车间LM Studio" maxlength="100" />
        </el-form-item>
        <el-form-item label="端点地址">
          <el-input v-model="form.api_base" placeholder="http://127.0.0.1:8000/v1（含 /v1）" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password placeholder="本地服务可留空或任意值" />
        </el-form-item>
        <el-form-item label="模型名">
          <el-input v-model="form.model_name" placeholder="与服务端 /v1/models 列表一致，如 qwen2.5-7b-instruct" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" maxlength="255" placeholder="可选" />
        </el-form-item>
        <el-alert v-if="form.model_type === 'embedding'" type="warning" :closable="false" show-icon
                  title="更换嵌入模型后向量空间不通用，启用时若维度不一致将要求重建向量库" />
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存{{ editingId ? '' : '并测连通' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelAPI } from '../api'

const loading = ref(false)
const models = ref([])
const runtime = ref({})
const testResults = ref({})   // id -> {testing|ok|error, latency_ms, sample?, dim?}
const hasPendingRebuild = ref(false)
const rebuildRunning = ref(false)
const rebuildDetail = ref('')

const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const presetKey = ref('')
const form = ref({ model_type: 'llm', name: '', api_base: '', api_key: '', model_name: '', remark: '' })

// 服务商预设（OpenAI兼容）
const presets = [
  { label: 'oMLX 本地(Mac)', base: 'http://127.0.0.1:8000/v1', key: '' },
  { label: 'LM Studio 本地', base: 'http://localhost:1234/v1', key: '' },
  { label: 'Ollama 本地', base: 'http://localhost:11434/v1', key: '' },
  { label: 'vLLM 局域网', base: '', key: '' },
  { label: 'DeepSeek', base: 'https://api.deepseek.com/v1', key: '' },
  { label: '通义千问(兼容模式)', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', key: '' },
  { label: 'Kimi 月之暗面', base: 'https://api.moonshot.cn/v1', key: '' },
  { label: 'OpenAI', base: 'https://api.openai.com/v1', key: '' }
]
const applyPreset = (label) => {
  const p = presets.find(x => x.label === label)
  if (p && p.base) form.value.api_base = p.base
}

const loadAll = async () => {
  loading.value = true
  try {
    const [listRes, rt] = await Promise.all([modelAPI.list(), modelAPI.activeRuntime()])
    models.value = listRes.data || []
    runtime.value = rt.data || {}
    hasPendingRebuild.value = models.value.some(m => m.pending_rebuild)
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const openAdd = (type) => {
  editingId.value = null
  presetKey.value = ''
  form.value = { model_type: type, name: '', api_base: '', api_key: '', model_name: '', remark: '' }
  dialogVisible.value = true
}
const openEdit = (row) => {
  editingId.value = row.id
  presetKey.value = ''
  form.value = {
    model_type: row.model_type, name: row.name, api_base: row.api_base,
    api_key: '', model_name: row.model_name, remark: row.remark || ''
  }
  dialogVisible.value = true
}

const save = async () => {
  if (!form.value.name || !form.value.api_base || !form.value.model_name) {
    ElMessage.warning('名称、端点、模型名不能为空')
    return
  }
  saving.value = true
  try {
    let res
    if (editingId.value) {
      res = await modelAPI.update(editingId.value, form.value)
    } else {
      res = await modelAPI.add(form.value)
      // 新增成功后立即做一次连通测试，把结果直接展示出来
      const newId = res.data?.id
      if (newId) runTest({ id: newId })
    }
    ElMessage.success(res.message || '已保存')
    dialogVisible.value = false
    await loadAll()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

const runTest = async (row) => {
  testResults.value = { ...testResults.value, [row.id]: { testing: true } }
  try {
    const res = await modelAPI.test(row.id)
    testResults.value = { ...testResults.value, [row.id]: { ...res.data } }
  } catch (e) {
    const err = e?.response?.data?.error || e?.message || '连接失败'
    testResults.value = { ...testResults.value, [row.id]: { ok: false, error: err } }
  }
}

const activate = async (row) => {
  if (row.model_type === 'embedding') {
    try {
      await ElMessageBox.confirm(
        '切换嵌入模型会影响全部已有向量的可比性。系统会先做维度校验：若维度不一致需要重建向量库后才能生效。继续？',
        '启用嵌入模型', { confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning' }
      )
    } catch { return }
  }
  try {
    const res = await modelAPI.activate(row.id)
    await loadAll()
    if (res.data?.rebuild_required) {
      try {
        await ElMessageBox.confirm(
          `${res.message}。现在就触发全量重建吗？（期间问答检索不可用）`,
          '需要重建向量库', { confirmButtonText: '立即重建', cancelButtonText: '稍后手动', type: 'warning' }
        )
        doRebuild()
      } catch { /* 稍后手动 */ }
    } else {
      ElMessage.success(res.message || '已启用')
    }
  } catch (e) { /* 拦截器已提示 */ }
}

const remove = async (row) => {
  try {
    await ElMessageBox.confirm(`删除接入「${row.name}」？`, '删除', { type: 'warning' })
  } catch { return }
  await modelAPI.remove(row.id)
  ElMessage.success('已删除')
  loadAll()
}

let rebuildTimer = null
const doRebuild = async () => {
  try {
    await modelAPI.rebuildVectors()
    rebuildRunning.value = true
    ElMessage.info('重建任务已启动')
    pollRebuild()
  } catch (e) { /* 拦截器已提示 */ }
}
const pollRebuild = () => {
  stopRebuildPolling()
  rebuildTimer = setInterval(async () => {
    try {
      const res = await modelAPI.rebuildStatus()
      const s = res.data || {}
      rebuildDetail.value = s.status === 'running' ? '...' : ''
      if (s.status !== 'running') {
        stopRebuildPolling()
        rebuildRunning.value = false
        if (s.status === 'done') {
          ElMessage.success('向量库重建完成，新嵌入模型已全面生效')
          hasPendingRebuild.value = false
        } else if (s.status === 'failed') {
          ElMessage.error('重建失败：' + s.detail)
        }
        loadAll()
      }
    } catch { /* ignore */ }
  }, 3000)
}
const stopRebuildPolling = () => { if (rebuildTimer) { clearInterval(rebuildTimer); rebuildTimer = null } }

onMounted(async () => {
  await loadAll()
  const rs = await modelAPI.rebuildStatus().catch(() => null)
  if (rs?.data?.status === 'running') { rebuildRunning.value = true; pollRebuild() }
})
onUnmounted(stopRebuildPolling)
</script>

<style scoped>
.admin-models { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; gap:16px; flex-wrap:wrap; }
.page-header h1 { font-size:24px; font-weight:700; margin:0 0 6px; color:var(--text); }
.subtitle { color:var(--text3); font-size:13px; margin:0; max-width:560px; }
.header-actions { display:flex; gap:8px; flex-wrap:wrap; }

.runtime-cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:14px; margin-bottom:18px; }
.runtime-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px 18px; display:flex; flex-direction:column; gap:4px; }
.rt-label { font-size:12px; color:var(--text3); }
.rt-value { font-size:15px; font-weight:600; color:var(--text); }
.rt-base { font-size:12px; color:var(--text3); word-break:break-all; }

.t-ok { color:#52c41a; font-size:12px; }
.t-bad { color:#ff4d4f; font-size:12px; cursor:help; }
.t-testing,.t-idle { color:var(--text3); font-size:12px; }
</style>
