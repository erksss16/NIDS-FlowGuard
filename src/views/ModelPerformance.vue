<template>
  <div class="model-performance">
    <div v-if="dbConnected">
      <div class="toolbar">
        <div>
          <h3>模型性能监控</h3>
          <span>实时监测检测模型的准确性与可靠性指标</span>
        </div>
      </div>

      <div class="metrics-grid">
        <div v-for="item in modelMetrics" :key="item.label" class="metric-card">
          <div class="metric-header">
            <span class="metric-label">{{ item.label }}</span>
            <span class="metric-value" :style="{ color: item.color }">{{ item.value }}%</span>
          </div>
          <p class="metric-desc">{{ item.desc }}</p>
          <div class="metric-bar">
            <i :style="{ width: item.value + '%', background: item.color }"></i>
          </div>
          <div class="metric-footer">
            <span>{{ item.footer }}</span>
          </div>
        </div>
      </div>

      <div class="charts-row">
        <div class="chart-card">
          <h4>模型指标趋势</h4>
          <div ref="trendChartRef" class="chart-body"></div>
        </div>
        <div class="chart-card">
          <h4>漂移检测统计</h4>
          <div class="drift-stats">
            <div class="drift-item">
              <span class="drift-label">总检测批次</span>
              <span class="drift-value">{{ driftStats.totalBatches }}</span>
            </div>
            <div class="drift-item">
              <span class="drift-label">检测到漂移</span>
              <span class="drift-value danger">{{ driftStats.driftBatches }}</span>
            </div>
            <div class="drift-item">
              <span class="drift-label">漂移占比</span>
              <span class="drift-value warning">{{ driftStats.driftRate }}%</span>
            </div>
            <div class="drift-item">
              <span class="drift-label">Wasserstein均值</span>
              <span class="drift-value">{{ driftStats.avgScore }}</span>
            </div>
            <div class="drift-item">
              <span class="drift-label">Wasserstein峰值</span>
              <span class="drift-value danger">{{ driftStats.maxScore }}</span>
            </div>
            <div class="drift-info">
              <p>模型会自动检测数据分布漂移，并触发自适应更新以保持检测准确性。</p>
            </div>
          </div>
        </div>
      </div>

      <div class="confusion-section">
        <h4>混淆矩阵分析</h4>
        <div class="confusion-grid">
          <div class="confusion-cell header"></div>
          <div class="confusion-cell header">预测：正常</div>
          <div class="confusion-cell header">预测：攻击</div>

          <div class="confusion-cell header">实际：正常</div>
          <div class="confusion-cell tn">
            <span class="cell-label">真负例 (TN)</span>
            <span class="cell-value">{{ confusion.tn }}</span>
            <span class="cell-desc">正确识别的正常流量</span>
          </div>
          <div class="confusion-cell fp">
            <span class="cell-label">假正例 (FP)</span>
            <span class="cell-value">{{ confusion.fp }}</span>
            <span class="cell-desc">误报：正常流量被判为攻击</span>
          </div>

          <div class="confusion-cell header">实际：攻击</div>
          <div class="confusion-cell fn">
            <span class="cell-label">假负例 (FN)</span>
            <span class="cell-value">{{ confusion.fn }}</span>
            <span class="cell-desc">漏报：攻击未被检测到</span>
          </div>
          <div class="confusion-cell tp">
            <span class="cell-label">真正例 (TP)</span>
            <span class="cell-value">{{ confusion.tp }}</span>
            <span class="cell-desc">正确识别的攻击流量</span>
          </div>
        </div>
      </div>

    </div>

    <div v-else class="clean-state">
      <div class="clean-card">
        <h3>模型性能</h3>
        <p>请先连接检测结果数据库，系统会展示模型的实时性能指标与分析。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'

const dbConnected = inject('dbConnected')
const backendUrl = inject('backendUrl')

const loading = ref(false)
const stats = ref({ accuracy: 0, precision: 0, recall: 0, f1: 0, falsePositiveRate: 0 })
const driftStats = ref({ totalBatches: 0, driftBatches: 0, driftRate: 0, avgScore: '0.0000', maxScore: '0.0000' })
const confusion = ref({ tp: 0, fp: 0, tn: 0, fn: 0 })
const metricHistory = ref([])
const trendChartRef = ref(null)
let trendChart = null
let ticker = null

const modelMetrics = computed(() => [
  {
    label: '检测准确率',
    value: stats.value.accuracy,
    color: '#f6821f',
    desc: '模型正确分类的流量占总流量的比例',
    footer: '越高越好，表示整体检测能力'
  },
  {
    label: '攻击识别率',
    value: stats.value.recall,
    color: '#059669',
    desc: '成功检测到的攻击占所有真实攻击的比例',
    footer: '越高越好，降低漏报风险'
  },
  {
    label: '系统精确度',
    value: stats.value.precision,
    color: '#0284c7',
    desc: '告警中真实攻击的占比，反映告警可信度',
    footer: '越高越好，提高告警质量'
  },
  {
    label: '模型 F1 分数',
    value: stats.value.f1,
    color: '#7c3aed',
    desc: '精确度和召回率的调和平均数，综合评估模型性能',
    footer: '越高越好，平衡精确度与召回率'
  },
])

function pct(v) { return Number((Number(v || 0) * 100).toFixed(1)) }
function focusedPercentAxis(values) {
  const nums = values.map(v => Number(v || 0)).filter(Number.isFinite)
  if (!nums.length) return { min: 0, max: 100 }
  const low = Math.min(...nums)
  const high = Math.max(...nums)
  const span = Math.max(high - low, 2)
  const padding = Math.max(span * 0.35, 0.8)
  return {
    min: Math.max(0, Math.floor((low - padding) * 10) / 10),
    max: Math.min(100, Math.ceil((high + padding) * 10) / 10),
  }
}

function initTrendChart() {
  if (!trendChartRef.value) return
  trendChart = echarts.init(trendChartRef.value)
  updateTrendChart()
}

function updateTrendChart() {
  if (!trendChart) return
  const metricValues = metricHistory.value.flatMap(m => [m.accuracy, m.recall, m.precision, m.f1])
  const metricAxis = focusedPercentAxis(metricValues)
  trendChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: metricHistory.value.map(m => m.time),
      axisLabel: { color: '#78716c', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      min: metricAxis.min,
      max: metricAxis.max,
      splitNumber: 4,
      splitLine: { lineStyle: { color: '#f0eeea' } },
      axisLabel: { color: '#78716c', fontSize: 11, formatter: '{value}%' }
    },
    series: [
      { name: '准确率', type: 'line', smooth: true, data: metricHistory.value.map(m => m.accuracy), lineStyle: { color: '#f6821f', width: 2 }, itemStyle: { color: '#f6821f' } },
      { name: '识别率', type: 'line', smooth: true, data: metricHistory.value.map(m => m.recall), lineStyle: { color: '#059669', width: 2 }, itemStyle: { color: '#059669' } },
      { name: '精确度', type: 'line', smooth: true, data: metricHistory.value.map(m => m.precision), lineStyle: { color: '#0284c7', width: 2 }, itemStyle: { color: '#0284c7' } },
      { name: 'F1分数', type: 'line', smooth: true, data: metricHistory.value.map(m => m.f1), lineStyle: { color: '#7c3aed', width: 2 }, itemStyle: { color: '#7c3aed' } },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#fff',
      borderColor: '#e6e4df',
      textStyle: { color: '#1a1816', fontSize: 12 }
    },
    legend: {
      data: ['准确率', '识别率', '精确度', 'F1分数'],
      top: 0,
      textStyle: { color: '#78716c', fontSize: 11 }
    }
  })
}

async function fetchData() {
  loading.value = true
  try {
    const res = await fetch(`${backendUrl.value}/api/stats`)
    const s = await res.json()

    const totalAlerts = s.attack_count
    const falsePositives = totalAlerts > 0 ? Math.round((1 - s.precision) * totalAlerts) : 0
    const falsePositiveRate = totalAlerts > 0 ? Number(((falsePositives / totalAlerts) * 100).toFixed(1)) : 0

    stats.value = {
      accuracy: pct(s.accuracy),
      precision: pct(s.precision),
      recall: pct(s.recall),
      f1: pct(s.f1),
      falsePositiveRate: falsePositiveRate,
    }

    driftStats.value = {
      totalBatches: s.total_flows > 0 ? Math.ceil(s.total_flows / 100) : 0,
      driftBatches: s.drift_detected || 0,
      driftRate: s.total_flows > 0 ? Number(((s.drift_detected || 0) / Math.ceil(s.total_flows / 100) * 100).toFixed(1)) : 0,
      avgScore: Number(s.drift_score_avg || 0).toFixed(4),
      maxScore: Number(s.drift_score_max || 0).toFixed(4),
    }

    // Calculate confusion matrix
    const totalFlows = s.total_flows
    const attackCount = s.attack_count
    const normalCount = totalFlows - attackCount

    const tp = Math.round(s.recall * attackCount)
    const fp = falsePositives
    const fn = attackCount - tp
    const tn = normalCount - fp

    confusion.value = { tp, fp, tn, fn }

    const now = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    metricHistory.value = [...metricHistory.value, {
      time: now,
      accuracy: stats.value.accuracy,
      precision: stats.value.precision,
      recall: stats.value.recall,
      f1: stats.value.f1,
    }].slice(-12)

    updateTrendChart()
  } catch (e) {
    console.error('数据刷新失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (dbConnected.value) {
    fetchData()
    nextTick(() => {
      initTrendChart()
    })
    ticker = setInterval(fetchData, 2000)
  }
})

watch(dbConnected, (conn) => {
  if (ticker) { clearInterval(ticker); ticker = null }
  if (trendChart) { trendChart.dispose(); trendChart = null }
  if (conn) {
    fetchData()
    nextTick(() => {
      initTrendChart()
    })
    ticker = setInterval(fetchData, 2000)
  }
})

onBeforeUnmount(() => {
  if (ticker) clearInterval(ticker)
  if (trendChart) { trendChart.dispose(); trendChart = null }
})
</script>

<style scoped>
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding: 14px 18px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.toolbar h3 { font-size: 16px; color: #292524; margin-bottom: 3px; }
.toolbar span { font-size: 12px; color: #78716c; }

.metrics-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-bottom: 16px; }
.metric-card { padding: 20px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.metric-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.metric-label { font-size: 14px; color: #292524; font-weight: 600; }
.metric-value { font-size: 32px; font-weight: 800; }
.metric-desc { font-size: 12px; color: #78716c; margin-bottom: 12px; line-height: 1.5; }
.metric-bar { height: 8px; border-radius: 99px; overflow: hidden; background: #f1f5f9; margin-bottom: 10px; }
.metric-bar i { display: block; height: 100%; border-radius: inherit; transition: width 0.3s ease; }
.metric-footer { font-size: 11px; color: #a8a29e; }

.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
.chart-card { padding: 18px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.chart-card h4 { font-size: 14px; color: #292524; font-weight: 600; margin-bottom: 14px; }
.chart-body { width: 100%; height: 280px; }

.drift-stats { display: flex; flex-direction: column; gap: 16px; }
.drift-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: #fafafa; border: 1px solid #f1f5f9; border-radius: 6px; }
.drift-label { font-size: 13px; color: #78716c; }
.drift-value { font-size: 24px; font-weight: 800; color: #292524; }
.drift-value.danger { color: #dc2626; }
.drift-value.warning { color: #f59e0b; }
.drift-info { padding: 14px; background: #eff6ff; border: 1px solid #dbeafe; border-radius: 6px; }
.drift-info p { font-size: 12px; color: #1e40af; line-height: 1.6; margin: 0; }

.confusion-section { padding: 20px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; margin-bottom: 16px; }
.confusion-section h4 { font-size: 14px; color: #292524; font-weight: 600; margin-bottom: 16px; }
.confusion-grid { display: grid; grid-template-columns: 120px 1fr 1fr; gap: 10px; }
.confusion-cell { padding: 16px; border-radius: 6px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
.confusion-cell.header { background: #f5f5f4; color: #292524; font-size: 13px; font-weight: 600; }
.confusion-cell.tp { background: rgba(5,150,105,0.08); border: 2px solid #059669; }
.confusion-cell.tn { background: rgba(5,150,105,0.05); border: 2px solid #a8a29e; }
.confusion-cell.fp { background: rgba(220,38,38,0.08); border: 2px solid #dc2626; }
.confusion-cell.fn { background: rgba(245,158,11,0.08); border: 2px solid #f59e0b; }
.cell-label { font-size: 11px; color: #78716c; margin-bottom: 6px; }
.cell-value { font-size: 28px; font-weight: 800; color: #292524; margin-bottom: 4px; }
.cell-desc { font-size: 11px; color: #a8a29e; }

.clean-state { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 120px); }
.clean-card { text-align: center; max-width: 460px; padding: 42px 30px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.clean-card h3 { font-size: 18px; color: #292524; margin-bottom: 8px; }
.clean-card p { color: #78716c; line-height: 1.7; font-size: 14px; }

@media (max-width: 1200px) {
  .metrics-grid, .charts-row { grid-template-columns: 1fr; }
  .confusion-grid { grid-template-columns: 100px 1fr 1fr; }
}
</style>
