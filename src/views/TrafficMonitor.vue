<template>
  <div class="traffic-monitor">
    <div v-if="dbConnected" class="monitor-grid">
      <section class="stream-panel wide">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">实时流量监测</h3>
            <p class="panel-subtitle">按小批次接收网络流量，实时展示异常检测结果与流量特征</p>
          </div>
          <span class="live-indicator" :class="{ paused: !liveActive }"><span class="live-dot"></span>{{ liveActive ? '实时接收中' : '等待新流量' }}</span>
        </div>
        <div class="metrics-row">
          <div class="metric"><span class="metric-value">{{ flowRate }}</span><span class="metric-label">flows/s</span></div>
          <div class="metric"><span class="metric-value danger">{{ formatNum(flowStats.attackCount) }}</span><span class="metric-label">异常流量</span></div>
          <div class="metric"><span class="metric-value">{{ formatBytes(byteStats.totalBytes) }}</span><span class="metric-label">总字节量</span></div>
          <div class="metric"><span class="metric-value">{{ formatDuration(byteStats.avgDuration) }}</span><span class="metric-label">平均连接时长</span></div>
          <div class="metric"><span class="metric-value warning">{{ formatBytes(byteStats.maxTransfer) }}</span><span class="metric-label">最大单次传输</span></div>
        </div>
      </section>

      <TrafficChart
        title="正常 / 异常流量时序"
        description="纵轴单位为 rps，表示每秒接收到的流量记录数；绿色为正常流量，红色为异常流量。"
        live
        :option="flowTrendOption"
      />
      <TrafficChart
        title="源 / 目标字节分布"
        description="蓝色表示源端发送字节数，黄色表示目标端返回字节数，用于观察单次连接的双向数据量差异。"
        :option="byteOption"
      />

      <section class="table-panel wide">
        <div class="panel-header table-tools">
          <div>
            <h3 class="panel-title">流量检测日志（最近10条）</h3>
            <p class="panel-subtitle">实时展示最新的网络流量检测结果</p>
          </div>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>时间</th>
                <th>源IP</th>
                <th>目的IP</th>
                <th>协议</th>
                <th>服务</th>
                <th>标志</th>
                <th>源字节</th>
                <th>目标字节</th>
                <th>时长</th>
                <th>风险识别</th>
                <th>处置状态</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="pkt in packets.slice(0, 10)" :key="pkt.id">
                <tr :class="{ 'row-bad': pkt.result === '异常', 'row-new': pkt.isNew }">
                  <td class="td-mono">#{{ pkt.id }}</td>
                  <td>{{ pkt.time }}</td>
                  <td class="td-mono">{{ pkt.src_ip }}</td>
                  <td class="td-mono">{{ pkt.dst_ip }}</td>
                  <td><span class="type-badge">{{ pkt.protocol || '-' }}</span></td>
                  <td>{{ pkt.service || '-' }}</td>
                  <td>{{ pkt.flag || '-' }}</td>
                  <td>{{ formatNum(pkt.src_bytes) }}</td>
                  <td>{{ formatNum(pkt.dst_bytes) }}</td>
                  <td>{{ formatDuration(pkt.duration) }}</td>
                  <td><span class="result-tag" :class="pkt.result === '异常' ? 'res-bad' : 'res-ok'">{{ pkt.result }}</span></td>
                  <td><span class="disposition-tag" :class="`disp-${pkt.disposition}`">{{ dispositionLabel(pkt.disposition) }}</span></td>
                </tr>
              </template>
              <tr v-if="packets.length === 0"><td colspan="12" class="empty-cell">暂无流量数据</td></tr>
            </tbody>
          </table>
        </div>
        <div class="table-footer">
          <button class="view-all-btn" @click="$router.push('/app/traffic-logs')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
            </svg>
            查看完整日志
          </button>
        </div>
      </section>
    </div>

    <div v-else class="clean-state">
      <div class="clean-card">
        <h3>实时流量监测</h3>
        <p>请先连接后端数据库。模型流式写入检测结果后，本页会自动显示最新网络数据包及异常判断。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, inject, watch } from 'vue'
import TrafficChart from '../components/TrafficChart.vue'

const dbConnected = inject('dbConnected')
const backendUrl = inject('backendUrl')

const flowStats = ref({ totalFlows: 0, attackCount: 0, normalPct: 0 })
const cachedMonitor = JSON.parse(sessionStorage.getItem('nids_traffic_monitor') || '{}')
const packets = ref(cachedMonitor.packets || [])
const flowTrend = ref(cachedMonitor.flowTrend || [])
const lastSeenId = ref(cachedMonitor.lastSeenId || 0)
const flowRatePerSecond = ref(0)
const liveActive = ref(false)
let ticker = null
let liveTimer = null

const COLORS = ['#f6821f','#059669','#0284c7','#dc2626','#d97706','#7c3aed','#0891b2','#65a30d']

const flowRate = computed(() => flowRatePerSecond.value.toFixed(1))
const byteStats = computed(() => {
  const rows = packets.value
  const totals = rows.map(r => Number(r.src_bytes || 0) + Number(r.dst_bytes || 0))
  return {
    totalBytes: totals.reduce((sum, v) => sum + v, 0),
    maxTransfer: totals.length ? Math.max(...totals) : 0,
    avgDuration: rows.length ? rows.reduce((sum, r) => sum + Number(r.duration || 0), 0) / rows.length : 0,
  }
})

function formatNum(n) { return Number(n ?? 0).toLocaleString() }
function formatBytes(n) {
  const value = Number(n || 0)
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${Math.round(value)} B`
}
function formatDuration(d) {
  const value = Number(d || 0)
  if (value <= 0) return '<1s'
  if (value < 1) return `${Math.round(value * 1000)}ms`
  if (value < 60) return `${value.toFixed(1)}s`
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`
}
function dispositionLabel(status) {
  return ({ pending_review: '待研判', confirmed: '确认入侵', watch: '持续观察', resolved: '已处置', not_required: '无需处置' })[status] || '待研判'
}
function persistMonitor() {
  sessionStorage.setItem('nids_traffic_monitor', JSON.stringify({
    packets: packets.value.slice(0, 200).map(row => ({ ...row, isNew: false })),
    flowTrend: flowTrend.value.slice(-24),
    lastSeenId: lastSeenId.value,
  }))
}
function mapFlow(row, isNew = false) {
  const isAttack = row.predicted_label === 'attack'
  return {
    id: row.id,
    time: row.run_time,
    iteration: row.iteration,
    drift_detected: row.drift_detected,
    protocol: row.protocol,
    service: row.service,
    flag: row.flag,
    src_ip: isAttack ? (row.src_ip || '-') : '-',
    dst_ip: isAttack ? (row.dst_ip || '-') : '-',
    src_bytes: Number(row.src_bytes || 0),
    dst_bytes: Number(row.dst_bytes || 0),
    duration: Number(row.duration || 0),
    disposition: row.disposition,
    predicted_label: row.predicted_label,
    result: isAttack ? '异常' : '正常',
    isNew,
  }
}

const flowTrendOption = computed(() => ({
  grid: { left: 48, right: 18, top: 28, bottom: 30 },
  xAxis: { type: 'category', data: flowTrend.value.map(p => p.time), axisLabel: { color: '#78716c', fontSize: 11 }, axisTick: { show: false } },
  yAxis: {
    type: 'value',
    name: 'rps',
    minInterval: 1,
    nameTextStyle: { color: '#78716c', fontSize: 11, padding: [0, 0, 4, 0] },
    splitLine: { lineStyle: { color: '#f1f5f9' } },
    axisLabel: { color: '#78716c', fontSize: 11 },
  },
  series: [
    { name: '正常', type: 'line', smooth: true, data: flowTrend.value.map(p => p.normal), lineStyle: { width: 3, color: '#16a34a' }, itemStyle: { color: '#16a34a' }, areaStyle: { color: 'rgba(22,163,74,0.10)' } },
    { name: '异常', type: 'line', smooth: true, data: flowTrend.value.map(p => p.attack), lineStyle: { width: 3, color: '#ef4444' }, itemStyle: { color: '#ef4444' }, areaStyle: { color: 'rgba(239,68,68,0.10)' } },
  ],
  tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e7e5e4', textStyle: { color: '#292524', fontSize: 12 } },
}))

const byteOption = computed(() => {
  const sample = packets.value.slice(0, 30).reverse()
  return {
    color: ['#2563eb', '#f59e0b'],
    legend: { top: 4, right: 12, itemWidth: 10, itemHeight: 10, textStyle: { color: '#57534e', fontSize: 11 } },
    grid: { left: 56, right: 18, top: 42, bottom: 34 },
    xAxis: { type: 'category', data: sample.map(r => `#${r.id}`), axisLabel: { color: '#78716c', fontSize: 10, rotate: 35 } },
    yAxis: {
      type: 'value',
      name: 'bytes',
      nameTextStyle: { color: '#78716c', fontSize: 11, padding: [0, 0, 4, 0] },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
      axisLabel: { color: '#78716c', fontSize: 11 },
    },
    series: [
      { name: '源字节（蓝色）', type: 'bar', stack: 'bytes', data: sample.map(r => r.src_bytes), itemStyle: { color: '#2563eb' } },
      { name: '目标字节（黄色）', type: 'bar', stack: 'bytes', data: sample.map(r => r.dst_bytes), itemStyle: { color: '#f59e0b' } },
    ],
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e7e5e4', textStyle: { color: '#292524', fontSize: 12 } },
  }
})

async function fetchStatsAndCharts() {
  const statsRes = await fetch(`${backendUrl.value}/api/stats`)
  const stats = await statsRes.json()
  flowStats.value = { totalFlows: stats.total_flows, attackCount: stats.attack_count, normalPct: stats.total_flows ? Math.round(stats.normal_count / stats.total_flows * 100) : 0 }
}
async function fetchInitialFlows() {
  const res = await fetch(`${backendUrl.value}/api/flows?limit=80`)
  const rows = await res.json()
  if (packets.value.length === 0) {
    packets.value = rows.map(row => mapFlow(row, false))
    lastSeenId.value = rows.reduce((maxId, row) => Math.max(maxId, row.id), 0)
    persistMonitor()
  }
}
async function fetchLiveFlows() {
  try {
    const res = await fetch(`${backendUrl.value}/api/live-flows?since_id=${lastSeenId.value}&limit=100`)
    const rows = await res.json()
    const now = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    const attack = rows.filter(row => row.predicted_label === 'attack').length
    const normal = rows.length - attack

    // Calculate flow rate per second based on actual data received
    flowRatePerSecond.value = rows.length / 2  // divided by 2 because we poll every 2 seconds

    liveActive.value = rows.length > 0
    if (liveTimer) clearTimeout(liveTimer)
    liveTimer = setTimeout(() => { liveActive.value = false }, 1800)
    flowTrend.value = [...flowTrend.value, { time: now, normal, attack }].slice(-24)
    if (rows.length > 0) {
      lastSeenId.value = Math.max(...rows.map(row => row.id), lastSeenId.value)
      packets.value = [...rows.map(row => mapFlow(row, true)).reverse(), ...packets.value].slice(0, 200)
      setTimeout(() => { packets.value = packets.value.map(row => ({ ...row, isNew: false })) }, 900)
    }
    persistMonitor()
  } catch (e) {
    liveActive.value = false
  }
}
async function startMonitor() {
  await fetchInitialFlows()
  await fetchStatsAndCharts()
  await fetchLiveFlows()
  ticker = setInterval(async () => {
    await fetchLiveFlows()
    await fetchStatsAndCharts()
  }, 2000)
}
watch(dbConnected, (conn) => {
  if (ticker) { clearInterval(ticker); ticker = null }
  if (liveTimer) { clearTimeout(liveTimer); liveTimer = null }
  if (conn) startMonitor()
}, { immediate: true })
onBeforeUnmount(() => {
  if (ticker) clearInterval(ticker)
  if (liveTimer) clearTimeout(liveTimer)
})
</script>

<style scoped>
.monitor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.wide { grid-column: 1 / -1; }
.stream-panel, .table-panel { background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; overflow: hidden; }
.panel-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid #f5f5f4; }
.panel-title { font-size: 14px; font-weight: 700; color: #292524; }
.panel-subtitle { margin-top: 3px; font-size: 12px; color: #78716c; }
.live-indicator { display: inline-flex; align-items: center; gap: 6px; color: #16a34a; font-size: 12px; font-weight: 700; }
.live-indicator.paused { color: #a8a29e; }
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
.metrics-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; padding: 16px 18px; }
.metric { padding: 12px; border: 1px solid #f1f5f9; border-radius: 8px; background: #fafafa; }
.metric-value { display: block; font-size: 21px; line-height: 1.1; font-weight: 800; color: #292524; }
.metric-value.danger { color: #ef4444; }
.metric-value.warning { color: #2563eb; }
.metric-label { display: block; margin-top: 5px; font-size: 12px; color: #78716c; }
.table-tools { align-items: flex-end; }
.filters { display: flex; gap: 8px; }
.filters input, .filters select { height: 32px; border: 1px solid #e7e5e4; border-radius: 6px; padding: 0 10px; background: #fff; color: #292524; font-size: 13px; }
.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { text-align: left; padding: 9px 14px; color: #78716c; font-size: 11px; font-weight: 700; white-space: nowrap; border-bottom: 1px solid #f5f5f4; cursor: pointer; }
.data-table td { padding: 10px 14px; color: #44403c; border-bottom: 1px solid #fafaf9; white-space: nowrap; }
.data-table tbody tr:hover { background: #fafaf9; }
.data-table tbody tr.row-bad { background: rgba(239, 68, 68, 0.04); }
.data-table tbody tr.row-new { animation: flash 0.9s ease-out; }
@keyframes flash { 0% { background: rgba(37, 99, 235, 0.16); } 100% { background: transparent; } }
.expand-row td { background: #f8fafc; }
.expand-box { display: flex; flex-wrap: wrap; gap: 10px; color: #475569; font-size: 12px; }
.expand-box span { padding: 4px 8px; border-radius: 999px; background: #fff; border: 1px solid #e2e8f0; }
.td-mono, .type-badge { font-family: 'SF Mono', 'Fira Code', monospace; }
.type-badge { display: inline-block; min-width: 38px; padding: 2px 7px; border-radius: 4px; background: #f1f5f9; color: #334155; text-align: center; font-size: 12px; }
.result-tag { display: inline-block; min-width: 44px; padding: 2px 8px; border-radius: 999px; text-align: center; font-size: 12px; font-weight: 800; }
.res-ok { color: #16a34a; background: rgba(22, 163, 74, 0.09); }
.res-bad { color: #ef4444; background: rgba(239, 68, 68, 0.09); }
.disposition-tag { display:inline-block; min-width:58px; padding:2px 8px; border-radius:999px; text-align:center; font-size:12px; font-weight:800; }
.disp-pending_review { color:#b45309; background:#fffbeb; }
.disp-confirmed { color:#b91c1c; background:#fef2f2; }
.disp-watch { color:#1d4ed8; background:#eff6ff; }
.disp-resolved, .disp-not_required { color:#15803d; background:#f0fdf4; }
.empty-cell { text-align: center; color: #a8a29e; padding: 28px; }
.table-footer { padding: 12px 18px; border-top: 1px solid #f5f5f4; background: #fafafa; text-align: center; }
.view-all-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border: 1px solid #e7e5e4; border-radius: 6px; background: #fff; color: #292524; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.view-all-btn:hover { background: #f5f5f4; border-color: #d6d3d1; }
.view-all-btn svg { width: 16px; height: 16px; }
.clean-state { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 120px); }
.clean-card { text-align: center; max-width: 460px; padding: 42px 30px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.clean-card h3 { font-size: 18px; color: #292524; margin-bottom: 8px; }
.clean-card p { color: #78716c; line-height: 1.7; font-size: 14px; }
@media (max-width: 1100px) { .monitor-grid, .charts-row { grid-template-columns: 1fr; } .metrics-row { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px) { .metrics-row { grid-template-columns: 1fr; } .panel-header, .filters { align-items: flex-start; gap: 10px; flex-direction: column; } }
</style>
