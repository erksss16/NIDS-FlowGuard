<template>
  <div class="statistics">
    <div v-if="dbConnected">
      <div class="toolbar">
        <div>
          <h3>统计分析</h3>
          <span>保留关键流量图表，突出协议、服务、标志和攻击趋势</span>
        </div>
      </div>

      <div class="charts-row">
        <TrafficChart
          title="协议分布"
          description="展示 TCP、UDP、ICMP 等协议的流量占比。"
          :option="protocolPieOption"
        />
        <section class="traffic-overview">
          <div class="overview-head"><div><h3>流量概览</h3><p>当前检测窗口的运行摘要</p></div><span>实时</span></div>
          <div class="overview-metrics"><div><strong>{{ formatNum(stats.totalFlows) }}</strong><span>检测流量</span></div><div><strong class="danger">{{ formatNum(stats.attackCount) }}</strong><span>异常告警</span></div><div><strong>{{ attackRate }}%</strong><span>异常占比</span></div></div>
          <div class="service-ranking"><div class="ranking-title">高频服务</div><div v-for="(service, index) in serviceData.slice(0, 4)" :key="service.name" class="service-row"><span class="rank">{{ index + 1 }}</span><strong>{{ service.name }}</strong><i><b :style="{ width: `${servicePercent(service.value)}%` }"></b></i><em>{{ formatNum(service.value) }}</em></div></div>
        </section>
      </div>

      <div class="charts-row">
        <TrafficChart
          title="服务极坐标图"
          description="按服务类型统计流量数量，径向长度越长表示该服务出现越频繁。"
          :option="polarBarOption"
        />
        <TrafficChart
          title="标志分布柱状图"
          description="统计连接标志的出现次数，例如 SF、REJ、S0 等。"
          :option="flagBarOption"
        />
      </div>

      <div class="charts-row single">
        <TrafficChart
          title="攻击趋势渐变"
          description="按时间展示累计异常流量变化，纵轴单位为条，用于观察攻击数量是否持续上升。"
          live
          :option="gradientAreaOption"
        />
      </div>
    </div>

    <div v-else class="clean-state">
      <div class="clean-card">
        <h3>统计分析</h3>
        <p>请先连接检测结果数据库，系统会展示详细的流量统计与攻击分布分析。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import TrafficChart from '../components/TrafficChart.vue'

const dbConnected = inject('dbConnected')
const backendUrl = inject('backendUrl')

const loading = ref(false)
const attackTrend = ref([])
const protocolData = ref([])
const attackTypeData = ref([])
const serviceData = ref([])
const flagData = ref([])
const stats = ref({ totalFlows: 0, attackCount: 0, normalCount: 0 })
let ticker = null

const COLORS = ['#f6821f', '#0284c7', '#059669', '#dc2626', '#7c3aed', '#d97706', '#0891b2', '#65a30d']
const ATTACK_GRADIENT = {
  type: 'linear',
  x: 0,
  y: 0,
  x2: 1,
  y2: 0,
  colorStops: [
    { offset: 0, color: '#f6821f' },
    { offset: 1, color: '#dc2626' },
  ],
}

function focusedAxis(values, minWindow = 20, minFloor = 0) {
  const nums = values.map(v => Number(v || 0)).filter(Number.isFinite)
  if (!nums.length) return { min: minFloor, max: minFloor + minWindow }
  const low = Math.min(...nums)
  const high = Math.max(...nums)
  const span = Math.max(high - low, minWindow)
  const padding = Math.max(span * 0.18, 2)
  return {
    min: Math.max(minFloor, Math.floor(low - padding)),
    max: Math.ceil(high + padding),
  }
}

function buildChartData(rows, nameKey = 'name', valueKey = 'cnt') {
  return rows.map((r, i) => ({
    value: r[valueKey],
    name: r[nameKey] || 'unknown',
    itemStyle: { color: COLORS[i % COLORS.length] },
  }))
}
function formatNum(n) { return Number(n || 0).toLocaleString() }
const attackRate = computed(() => stats.value.totalFlows ? (stats.value.attackCount / stats.value.totalFlows * 100).toFixed(1) : '0.0')
function servicePercent(value) { return Math.round(Number(value || 0) / Math.max(...serviceData.value.map(item => item.value), 1) * 100) }

const attackTypePieOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    backgroundColor: '#fff',
    borderColor: '#e7e5e4',
    textStyle: { color: '#292524', fontSize: 12 },
    formatter: '{b}<br/>数量：{c}<br/>占比：{d}%',
  },
  legend: {
    bottom: 6,
    itemWidth: 10,
    itemHeight: 10,
    textStyle: { color: '#57534e', fontSize: 11 },
  },
  series: [{
    type: 'pie',
    radius: ['38%', '66%'],
    center: ['50%', '44%'],
    data: attackTypeData.value,
    label: { color: '#292524', fontSize: 12, formatter: '{b}\n{d}%' },
    labelLine: { length: 12, length2: 8 },
    itemStyle: { borderColor: '#fff', borderWidth: 2 },
  }],
}))

const protocolPieOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    backgroundColor: '#fff',
    borderColor: '#e7e5e4',
    textStyle: { color: '#292524', fontSize: 12 },
    formatter: '{b}<br/>数量：{c}<br/>占比：{d}%',
  },
  legend: {
    bottom: 6,
    itemWidth: 10,
    itemHeight: 10,
    textStyle: { color: '#57534e', fontSize: 11 },
  },
  series: [{
    type: 'pie',
    radius: '62%',
    center: ['50%', '44%'],
    data: protocolData.value,
    label: { color: '#292524', fontSize: 12, formatter: '{b}\n{d}%' },
    itemStyle: { borderColor: '#fff', borderWidth: 2 },
  }],
}))

const polarBarOption = computed(() => ({
  angleAxis: {
    type: 'category',
    data: serviceData.value.map(s => s.name),
    axisLabel: { color: '#78716c', fontSize: 10 },
  },
  radiusAxis: { axisLabel: { color: '#78716c', fontSize: 10 } },
  polar: { radius: ['18%', '76%'] },
  tooltip: {
    trigger: 'item',
    backgroundColor: '#fff',
    borderColor: '#e7e5e4',
    textStyle: { color: '#292524', fontSize: 12 },
  },
  series: [{
    type: 'bar',
    name: '服务数量',
    coordinateSystem: 'polar',
    barWidth: '72%',
    data: serviceData.value.map((s, i) => ({
      value: s.value,
      itemStyle: { color: COLORS[i % COLORS.length] },
    })),
  }],
}))

const flagBarOption = computed(() => ({
  grid: { left: 70, right: 24, top: 24, bottom: 34 },
  xAxis: {
    type: 'value',
    minInterval: 1,
    splitLine: { lineStyle: { color: '#f1f5f9' } },
    axisLabel: { color: '#78716c', fontSize: 11 },
  },
  yAxis: {
    type: 'category',
    data: flagData.value.map(f => f.name),
    axisLabel: { color: '#78716c', fontSize: 11 },
    inverse: true,
  },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#fff',
    borderColor: '#e7e5e4',
    textStyle: { color: '#292524', fontSize: 12 },
  },
  series: [{
    name: '标志数量',
    type: 'bar',
    data: flagData.value.map((f, i) => ({
      value: f.value,
      itemStyle: { color: COLORS[i % COLORS.length], borderRadius: [0, 4, 4, 0] },
    })),
    barMaxWidth: 18,
  }],
}))

const gradientAreaOption = computed(() => {
  const values = attackTrend.value.map(p => p.attacks)
  const axis = focusedAxis(values, 30)
  return {
  grid: { left: 54, right: 30, top: 34, bottom: 40 },
  xAxis: {
    type: 'category',
    data: attackTrend.value.map(p => p.time),
    boundaryGap: false,
    axisLabel: { color: '#78716c', fontSize: 10 },
    axisTick: { show: false },
  },
  yAxis: {
    type: 'value',
    name: '条',
    min: axis.min,
    max: axis.max,
    splitNumber: 4,
    minInterval: 1,
    nameTextStyle: { color: '#78716c', fontSize: 11, padding: [0, 0, 4, 0] },
    splitLine: { lineStyle: { color: '#f1f5f9' } },
    axisLabel: { color: '#78716c', fontSize: 10 },
  },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#fff',
    borderColor: '#e7e5e4',
    textStyle: { color: '#292524', fontSize: 12 },
  },
  series: [{
    name: '异常流量',
    type: 'line',
    smooth: true,
    data: values,
    lineStyle: { width: 3, color: ATTACK_GRADIENT },
    areaStyle: {
      color: {
        type: 'linear',
        x: 0,
        y: 0,
        x2: 0,
        y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(246, 130, 31, 0.36)' },
          { offset: 1, color: 'rgba(246, 130, 31, 0.04)' },
        ],
      },
    },
    itemStyle: { color: '#f6821f', borderWidth: 2, borderColor: '#fff' },
  }],
  }
})

async function fetchData() {
  loading.value = true
  try {
    const [statsRes, protoRes, atkRes, serviceRes, flagRes] = await Promise.all([
      fetch(`${backendUrl.value}/api/stats`),
      fetch(`${backendUrl.value}/api/protocol-distribution`),
      fetch(`${backendUrl.value}/api/attack-types`),
      fetch(`${backendUrl.value}/api/service-distribution`),
      fetch(`${backendUrl.value}/api/flag-distribution`),
    ])

    const s = await statsRes.json()
    stats.value = {
      totalFlows: s.total_flows,
      attackCount: s.attack_count,
      normalCount: s.total_flows - s.attack_count,
    }

    const now = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    attackTrend.value = [...attackTrend.value, { time: now, attacks: s.attack_count, total: s.total_flows }].slice(-12)

    const protos = await protoRes.json()
    protocolData.value = buildChartData(protos, 'protocol')

    const atks = await atkRes.json()
    attackTypeData.value = buildChartData(atks, 'name')

    const services = await serviceRes.json()
    serviceData.value = services.map(r => ({ name: r.service || 'unknown', value: r.cnt }))

    const flags = await flagRes.json()
    flagData.value = buildChartData(flags, 'flag')
  } catch (e) {
    console.error('数据刷新失败', e)
  } finally {
    loading.value = false
  }
}

watch(dbConnected, (conn) => {
  if (ticker) { clearInterval(ticker); ticker = null }
  if (conn) {
    fetchData()
    ticker = setInterval(fetchData, 2000)
  }
}, { immediate: true })

onBeforeUnmount(() => { if (ticker) clearInterval(ticker) })
</script>

<style scoped>
.statistics { padding: 0; }
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
  padding: 18px 24px;
  background: #fff;
  border: 1px solid #e7e5e4;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.toolbar h3 {
  font-size: 18px;
  color: #292524;
  margin-bottom: 4px;
  font-weight: 800;
}
.toolbar span {
  font-size: 13px;
  color: #78716c;
  font-weight: 500;
}
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  margin-bottom: 18px;
}
.charts-row.single {
  grid-template-columns: 1fr;
}
.traffic-overview { min-height:320px; padding:20px; background:#fff; border:1px solid #e7e5e4; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.04); }
.overview-head { display:flex; justify-content:space-between; align-items:flex-start; }.overview-head h3 { font-size:14px; color:#292524; }.overview-head p { margin-top:4px; font-size:12px; color:#78716c; }.overview-head span { padding:3px 8px; border-radius:12px; color:#047857; background:#f0fdf4; font-size:11px; font-weight:700; }.overview-metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:22px 0; }.overview-metrics div { padding:10px; background:#fafaf9; border-radius:6px; }.overview-metrics strong,.overview-metrics span { display:block; }.overview-metrics strong { font-size:18px; color:#292524; }.overview-metrics strong.danger { color:#dc2626; }.overview-metrics span { margin-top:5px; color:#78716c; font-size:11px; }.ranking-title { margin-bottom:8px; font-size:12px; font-weight:700; color:#292524; }.service-row { display:flex; align-items:center; gap:8px; min-height:29px; font-size:12px; }.service-row .rank { width:18px; color:#78716c; }.service-row strong { width:72px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.service-row i { flex:1; height:5px; overflow:hidden; background:#f1f5f9; border-radius:4px; }.service-row b { display:block; height:100%; background:#f97316; border-radius:4px; }.service-row em { width:45px; font-style:normal; color:#78716c; text-align:right; }
.clean-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 120px);
}
.clean-card {
  text-align: center;
  max-width: 460px;
  padding: 42px 30px;
  background: #fff;
  border: 1px solid #e7e5e4;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}
.clean-card h3 {
  font-size: 18px;
  color: #292524;
  margin-bottom: 8px;
  font-weight: 700;
}
.clean-card p {
  color: #78716c;
  line-height: 1.7;
  font-size: 14px;
}
@media (max-width: 1200px) {
  .charts-row {
    grid-template-columns: 1fr;
  }
}
</style>
