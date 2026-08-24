<template>
  <div class="admin-feedback">
    <div class="page-header">
      <h1>反馈统计</h1>
      <p class="subtitle">用户点赞/点踩数据统计，用于 Badcase 复盘</p>
    </div>

    <div class="stats-cards">
      <el-card class="stat-card" shadow="never">
        <div class="stat-icon primary">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats?.likes || 0 }}</div>
          <div class="stat-label">点赞总数</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="never">
        <div class="stat-icon danger">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M5 3l7 5 7-5v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"/>
          </svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats?.dislikes || 0 }}</div>
          <div class="stat-label">点踩总数</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="never">
        <div class="stat-icon warning">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M12 9v4m0 4h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/>
          </svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats?.total || 0 }}</div>
          <div class="stat-label">反馈总量</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="never">
        <div class="stat-icon success">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/>
            <path d="M8 12l3 3 5-5"/>
          </svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ satisfaction }}%</div>
          <div class="stat-label">好评率</div>
        </div>
      </el-card>
    </div>

    <el-divider style="margin: 24px 0;"></el-divider>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h2>最近差评列表</h2>
          <el-button type="primary" size="small" @click="loadStats">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            刷新
          </el-button>
        </div>
      </template>

      <el-table :data="recentDislikes" stripe border style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="反馈ID" width="80" />
        <el-table-column prop="history_id" label="历史ID" width="100" />
        <el-table-column prop="username" label="用户" width="120" />
        <el-table-column prop="question" label="问题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="answer" label="回答" min-width="250" show-overflow-tooltip />
        <el-table-column prop="reason" label="踩的原因" min-width="180" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="scope">
            {{ formatTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" link @click="viewHistory(scope.row.history_id)">
              查看完整记录
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { qaAPI } from '../api'

const loading = ref(false)
const stats = ref(null)
const recentDislikes = ref([])

const satisfaction = computed(() => {
  if (!stats.value || stats.value.total === 0) return 0
  return ((stats.value.likes / stats.value.total) * 100).toFixed(1)
})

const loadStats = async () => {
  loading.value = true
  try {
    const res = await qaAPI.getFeedbackStats()
    stats.value = res.data || res
    recentDislikes.value = (res.data?.recent_dislikes || res.recent_dislikes || []).map(d => ({
      ...d,
      created_at: d.created_at
    }))
  } catch (error) {
    console.error('加载反馈统计失败:', error)
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const formatTime = (timeStr) => {
  if (!timeStr) return '-'
  try {
    return new Date(timeStr).toLocaleString()
  } catch {
    return timeStr
  }
}

const viewHistory = (historyId) => {
  // 可以跳转到历史记录详情页，或者弹窗显示
  ElMessage.info(`查看历史 ID: ${historyId}`)
  // router.push(`/qa/history/${historyId}`) // 如果有历史详情页
}

onMounted(() => {
  loadStats()
})
</script>

<style scoped>
.admin-feedback {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}
.page-header h1 {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 8px;
  color: var(--text);
}
.subtitle {
  color: var(--text3);
  font-size: 14px;
  margin: 0;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 8px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
}
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.stat-icon.primary { background: var(--grad-btn); }
.stat-icon.danger { background: linear-gradient(135deg, #ff4d4f, #ff7875); }
.stat-icon.warning { background: linear-gradient(135deg, #faad14, #ffd666); }
.stat-icon.success { background: linear-gradient(135deg, #52c41a, #95de64); }
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
}
.stat-label {
  font-size: 13px;
  color: var(--text3);
  margin-top: 4px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
</style>