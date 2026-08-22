<template>
  <div class="dashboard-container">
    <div class="page-header">
      <div>
        <h2 class="page-title">控制台</h2>
        <p class="page-sub">系统运行数据总览</p>
      </div>
      <el-button class="btn-ghost" @click="reloadVectors">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg>
        重新加载向量库
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon" :style="{ background: 'var(--primary-soft)', color: 'var(--primary)' }">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_users }}</div>
          <div class="stat-label">用户总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" :style="{ background: 'var(--el-color-danger-light-9)', color: 'var(--el-color-danger)' }">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_documents }}</div>
          <div class="stat-label">文档总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" :style="{ background: 'var(--el-color-success-light-9)', color: 'var(--el-color-success)' }">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-1.9-5.3 8.5 8.5 0 0 1 8.5-8.5 8.38 8.38 0 0 1 8.5 8.5z"/></svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_questions }}</div>
          <div class="stat-label">问答总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" :style="{ background: 'var(--el-color-warning-light-9)', color: 'var(--el-color-warning)' }">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_tokens }}</div>
          <div class="stat-label">Token消耗</div>
        </div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="charts-grid">
      <div class="chart-card">
        <h3>每日问答趋势</h3>
        <div ref="dailyChartRef" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <h3>用户活跃度 Top10</h3>
        <div ref="userActivityChartRef" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <h3>文档分类分布</h3>
        <div ref="categoryChartRef" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <h3>Token消耗趋势</h3>
        <div ref="tokenChartRef" class="chart-container"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { adminAPI, qaAPI } from '../api'

const dailyChartRef = ref(null)
const userActivityChartRef = ref(null)
const categoryChartRef = ref(null)
const tokenChartRef = ref(null)

let dailyChart = null
let userActivityChart = null
let categoryChart = null
let tokenChart = null
let themeObserver = null

// 统计数据
const stats = reactive({
  total_users: 0,
  admin_count: 0,
  normal_user_count: 0,
  total_documents: 0,
  completed_documents: 0,
  total_categories: 0,
  total_questions: 0,
  total_tokens: 0
})

// 读取当前主题下的 CSS 变量（图表文字/轴线跟随明暗主题）
const chartTheme = () => {
  const el = document.documentElement
  const cs = getComputedStyle(el)
  return {
    dark: el.getAttribute('data-theme') === 'dark',
    text: cs.getPropertyValue('--text').trim() || '#1d1d1f',
    text3: cs.getPropertyValue('--text3').trim() || '#86868b',
    grid: cs.getPropertyValue('--border').trim() || 'rgba(0,0,0,.08)',
    primary: cs.getPropertyValue('--primary').trim() || '#0071e3'
  }
}

// 加载统计数据
const loadStats = async () => {
  try {
    const res = await adminAPI.getDashboard()
    Object.assign(stats, res.data)
  } catch (error) {
    console.error('加载统计失败:', error)
  }
}

// 加载并渲染图表
const loadCharts = async () => {
  await Promise.all([
    loadDailyChart(),
    loadUserActivityChart(),
    loadCategoryChart(),
    loadTokenChart()
  ])
}

// 每日问答趋势图
const loadDailyChart = async () => {
  try {
    const res = await adminAPI.getDailyStats(30)
    const dates = res.data.map(item => item.date)
    const questionCounts = res.data.map(item => item.questions)
    const t = chartTheme()

    if (!dailyChart) dailyChart = echarts.init(dailyChartRef.value)
    dailyChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['问答数量'], textStyle: { color: t.text3 } },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { rotate: 45, color: t.text3 },
        axisLine: { lineStyle: { color: t.grid } }
      },
      yAxis: { type: 'value', axisLabel: { color: t.text3 }, splitLine: { lineStyle: { color: t.grid } } },
      series: [{
        name: '问答数量',
        type: 'line',
        data: questionCounts,
        smooth: true,
        lineStyle: { color: t.primary },
        itemStyle: { color: t.primary },
        areaStyle: { opacity: .08 }
      }],
      grid: { bottom: 60 }
    })
  } catch (error) {
    console.error('加载每日趋势失败:', error)
  }
}

// 用户活跃度柱状图
const loadUserActivityChart = async () => {
  try {
    const res = await adminAPI.getUserActivity(10)
    const names = res.data.map(item => item.real_name || item.username)
    const counts = res.data.map(item => item.question_count)
    const t = chartTheme()

    if (!userActivityChart) userActivityChart = echarts.init(userActivityChartRef.value)
    userActivityChart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'value', axisLabel: { color: t.text3 }, splitLine: { lineStyle: { color: t.grid } } },
      yAxis: { type: 'category', data: names.reverse(), axisLabel: { color: t.text3 }, axisLine: { lineStyle: { color: t.grid } } },
      series: [{
        name: '问答数量',
        type: 'bar',
        data: counts.reverse(),
        barMaxWidth: 18,
        itemStyle: { color: t.primary, borderRadius: [0, 6, 6, 0] }
      }],
      grid: { left: 90 }
    })
  } catch (error) {
    console.error('加载用户活跃度失败:', error)
  }
}

// 文档分类分布饼图
const loadCategoryChart = async () => {
  try {
    const res = await adminAPI.getCategoryStats()
    const data = res.data.filter(item => item.document_count > 0)
    const t = chartTheme()
    const palette = [t.primary, '#ff9500', '#34c759', '#ff3b30', '#af52de', '#5856d6', '#ffcc00', '#5ac8fa']

    if (!categoryChart) categoryChart = echarts.init(categoryChartRef.value)
    categoryChart.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, textStyle: { color: t.text3 } },
      series: [{
        type: 'pie',
        radius: ['40%', '68%'],
        center: ['50%', '44%'],
        itemStyle: { borderColor: 'transparent' },
        data: data.map((item, i) => ({
          name: item.name,
          value: item.document_count,
          itemStyle: { color: palette[i % palette.length] }
        })),
        label: { color: t.text3 },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.3)'
          }
        }
      }]
    })
  } catch (error) {
    console.error('加载分类统计失败:', error)
  }
}

// Token消耗趋势图
const loadTokenChart = async () => {
  try {
    const res = await adminAPI.getTokenUsage(7)
    const dates = res.data.map(item => item.date)
    const tokens = res.data.map(item => item.total_tokens || 0)
    const t = chartTheme()

    if (!tokenChart) tokenChart = echarts.init(tokenChartRef.value)
    tokenChart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: dates, axisLabel: { color: t.text3 }, axisLine: { lineStyle: { color: t.grid } } },
      yAxis: { type: 'value', axisLabel: { color: t.text3 }, splitLine: { lineStyle: { color: t.grid } } },
      series: [{
        name: 'Token消耗',
        type: 'bar',
        data: tokens,
        barMaxWidth: 22,
        itemStyle: { color: '#ff9500', borderRadius: [6, 6, 0, 0] }
      }],
      grid: { bottom: 40 }
    })
  } catch (error) {
    console.error('加载Token统计失败:', error)
  }
}

// 重新加载向量库
const reloadVectors = async () => {
  try {
    await qaAPI.reloadVectors()
    ElMessage.success('向量库重载完成')
  } catch (error) {
    console.error('重载向量库失败:', error)
  }
}

// 窗口调整时重新渲染图表
const handleResize = () => {
  dailyChart?.resize()
  userActivityChart?.resize()
  categoryChart?.resize()
  tokenChart?.resize()
}

onMounted(async () => {
  await loadStats()
  await loadCharts()
  window.addEventListener('resize', handleResize)
  // 明暗主题切换时重渲染图表（跟随 data-theme 变化）
  themeObserver = new MutationObserver((mutations) => {
    if (mutations.some(m => m.type === 'attributes' && m.attributeName === 'data-theme')) {
      loadCharts()
    }
  })
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  themeObserver?.disconnect()
  dailyChart?.dispose()
  userActivityChart?.dispose()
  categoryChart?.dispose()
  tokenChart?.dispose()
})
</script>

<style scoped>
.dashboard-container {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  padding: var(--space-7) var(--space-6);
}

.btn-ghost {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text2);
  font-weight: 500;
  height: 38px;
  border-radius: 980px;
  padding: 0 var(--space-5);
}
.btn-ghost:hover { border-color: var(--primary); color: var(--primary); background: var(--card); }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  transition: box-shadow .22s, transform .22s;
}
.stat-card:hover {
  box-shadow: var(--shadow-hover);
  transform: translateY(-2px);
}

.stat-icon {
  width: 50px;
  height: 50px;
  flex: none;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.stat-value {
  font-size: 27px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--text);
  line-height: 1.1;
}
.stat-label {
  font-size: 13px;
  color: var(--text3);
  margin-top: 3px;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
}

.chart-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}
.chart-card h3 {
  margin: 0 0 var(--space-4) 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.chart-container {
  height: 250px;
}
</style>
