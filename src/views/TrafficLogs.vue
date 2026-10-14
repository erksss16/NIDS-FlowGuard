<template>
  <div class="traffic-logs">
    <div v-if="dbConnected">
      <div class="toolbar">
        <div>
          <h3>完整流量检测日志</h3>
          <span>支持按 IP、时间段、协议、服务、标志和检测结果组合查询</span>
        </div>
      </div>

      <section class="filter-panel">
        <div class="filter-grid">
          <input v-model="filters.q" placeholder="关键词" @keyup.enter="fetchFilteredFlows" />
          <input v-model="filters.ip" placeholder="任意 IP" @keyup.enter="fetchFilteredFlows" />
          <input v-model="filters.srcIp" placeholder="源 IP" @keyup.enter="fetchFilteredFlows" />
          <input v-model="filters.dstIp" placeholder="目的 IP" @keyup.enter="fetchFilteredFlows" />
          <input v-model="filters.protocol" placeholder="协议，如 tcp" @keyup.enter="fetchFilteredFlows" />
          <input v-model="filters.service" placeholder="服务，如 http" @keyup.enter="fetchFilteredFlows" />
          <input v-model="filters.flag" placeholder="标志，如 SF" @keyup.enter="fetchFilteredFlows" />
          <input v-model="filters.startTime" type="datetime-local" title="开始时间" />
          <input v-model="filters.endTime" type="datetime-local" title="结束时间" />
          <select v-model="filters.result">
            <option value="all">全部结果</option>
            <option value="attack">异常</option>
            <option value="normal">正常</option>
          </select>
          <select v-model.number="filters.limit">
            <option :value="100">100 条</option>
            <option :value="200">200 条</option>
            <option :value="500">500 条</option>
            <option :value="1000">1000 条</option>
          </select>
        </div>
        <div class="filter-actions">
          <button class="filter-action" @click="fetchFilteredFlows" :disabled="loading">{{ loading ? '查询中' : '查询' }}</button>
          <button class="filter-action secondary" @click="resetFilters">重置</button>
        </div>
      </section>

      <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

      <div class="table-panel">
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th @click="setSort('id')">ID {{ sortIndicator('id') }}</th>
                <th @click="setSort('time')">时间 {{ sortIndicator('time') }}</th>
                <th @click="setSort('src_ip')">源 IP {{ sortIndicator('src_ip') }}</th>
                <th @click="setSort('dst_ip')">目的 IP {{ sortIndicator('dst_ip') }}</th>
                <th @click="setSort('protocol')">协议 {{ sortIndicator('protocol') }}</th>
                <th @click="setSort('service')">服务 {{ sortIndicator('service') }}</th>
                <th @click="setSort('flag')">标志 {{ sortIndicator('flag') }}</th>
                <th @click="setSort('src_bytes')">源字节 {{ sortIndicator('src_bytes') }}</th>
                <th @click="setSort('dst_bytes')">目的字节 {{ sortIndicator('dst_bytes') }}</th>
                <th @click="setSort('duration')">时长 {{ sortIndicator('duration') }}</th>
                <th>风险识别</th>
                <th>处置状态</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="pkt in visiblePackets" :key="pkt.id">
                <tr :class="{ 'row-bad': pkt.result === '异常', 'row-new': pkt.isNew }" @click="expandedId = expandedId === pkt.id ? null : pkt.id">
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
                <tr v-if="expandedId === pkt.id" class="expand-row">
                  <td colspan="12">
                    <div class="expand-box">
                      <span>批次 #{{ pkt.iteration }}</span>
                      <span>源 {{ pkt.src_ip }} -> 目的 {{ pkt.dst_ip }}</span>
                      <span>总传输 {{ formatBytes(Number(pkt.src_bytes || 0) + Number(pkt.dst_bytes || 0)) }}</span>
                      <span>风险识别：{{ pkt.result }}</span>
                      <span>处置状态：{{ dispositionLabel(pkt.disposition) }}</span>
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-if="visiblePackets.length === 0">
                <td colspan="12" class="empty-cell">{{ loading ? '正在查询...' : '暂无匹配流量' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="table-footer">
          <span>第 {{ currentPage }} / {{ totalPages }} 页，当前显示 {{ pageStart }}-{{ pageEnd }} 条</span>
          <div class="pagination-controls">
            <button class="page-btn" @click="prevPage" :disabled="currentPage <= 1">上一页</button>
            <button class="page-btn" @click="nextPage" :disabled="currentPage >= totalPages">下一页</button>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="clean-state">
      <div class="clean-card">
        <h3>完整流量日志</h3>
        <p>请先连接检测结果数据库，系统会展示所有流量检测记录。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'

const dbConnected = inject('dbConnected')
const backendUrl = inject('backendUrl')

const defaultFilters = () => ({
  q: '',
  ip: '',
  srcIp: '',
  dstIp: '',
  protocol: '',
  service: '',
  flag: '',
  startTime: '',
  endTime: '',
  result: 'all',
  limit: 200,
})

const packets = ref([])
const lastSeenId = ref(0)
const filters = ref(defaultFilters())
const sortKey = ref('id')
const sortDir = ref('desc')
const expandedId = ref(null)
const loading = ref(false)
const errorMessage = ref('')
const pageSize = 40
const currentPage = ref(1)
let ticker = null

const sortedPackets = computed(() => {
  return [...packets.value].sort((a, b) => {
    const av = a[sortKey.value]
    const bv = b[sortKey.value]
    const result = typeof av === 'number' ? av - bv : String(av || '').localeCompare(String(bv || ''))
    return sortDir.value === 'asc' ? result : -result
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(sortedPackets.value.length / pageSize)))
const visiblePackets = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return sortedPackets.value.slice(start, start + pageSize)
})
const pageStart = computed(() => sortedPackets.value.length === 0 ? 0 : (currentPage.value - 1) * pageSize + 1)
const pageEnd = computed(() => Math.min(currentPage.value * pageSize, sortedPackets.value.length))

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
function setSort(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortKey.value = key; sortDir.value = 'desc' }
  resetPagination()
}
function sortIndicator(key) {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? '↑' : '↓'
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
    src_ip: row.src_ip || '-',
    dst_ip: row.dst_ip || '-',
    src_bytes: Number(row.src_bytes || 0),
    dst_bytes: Number(row.dst_bytes || 0),
    duration: Number(row.duration || 0),
    disposition: row.disposition,
    predicted_label: row.predicted_label,
    result: isAttack ? '异常' : '正常',
    isNew,
  }
}
function appendQuery(params, key, value) {
  if (value !== undefined && value !== null && String(value).trim() !== '') {
    params.set(key, value)
  }
}
function buildFlowQuery() {
  const params = new URLSearchParams()
  params.set('limit', filters.value.limit)
  appendQuery(params, 'q', filters.value.q)
  appendQuery(params, 'ip', filters.value.ip)
  appendQuery(params, 'src_ip', filters.value.srcIp)
  appendQuery(params, 'dst_ip', filters.value.dstIp)
  appendQuery(params, 'protocol', filters.value.protocol)
  appendQuery(params, 'service', filters.value.service)
  appendQuery(params, 'flag', filters.value.flag)
  appendQuery(params, 'start_time', filters.value.startTime)
  appendQuery(params, 'end_time', filters.value.endTime)
  if (filters.value.result !== 'all') params.set('result', filters.value.result)
  return params.toString()
}
function hasActiveFilters() {
  const f = filters.value
  return Boolean(f.q || f.ip || f.srcIp || f.dstIp || f.protocol || f.service || f.flag || f.startTime || f.endTime || f.result !== 'all')
}
function resetPagination() {
  currentPage.value = 1
  expandedId.value = null
}
function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value -= 1
    expandedId.value = null
  }
}
function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value += 1
    expandedId.value = null
  }
}

async function fetchFilteredFlows() {
  loading.value = true
  errorMessage.value = ''
  try {
    const res = await fetch(`${backendUrl.value}/api/flows?${buildFlowQuery()}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const rows = await res.json()
    packets.value = rows.map(row => mapFlow(row, false))
    lastSeenId.value = rows.reduce((maxId, row) => Math.max(maxId, row.id), 0)
    resetPagination()
  } catch (e) {
    errorMessage.value = '流量查询失败，请确认后端服务正在运行。'
  } finally {
    loading.value = false
  }
}
function resetFilters() {
  filters.value = defaultFilters()
  fetchFilteredFlows()
}
async function fetchLiveFlows() {
  if (hasActiveFilters()) return
  try {
    const res = await fetch(`${backendUrl.value}/api/live-flows?since_id=${lastSeenId.value}&limit=100`)
    const rows = await res.json()
    if (rows.length > 0) {
      lastSeenId.value = Math.max(...rows.map(row => row.id), lastSeenId.value)
      packets.value = [...rows.map(row => mapFlow(row, true)).reverse(), ...packets.value].slice(0, 500)
      setTimeout(() => { packets.value = packets.value.map(row => ({ ...row, isNew: false })) }, 900)
    }
  } catch (e) {
    console.error('Failed to fetch live flows', e)
  }
}
async function startMonitor() {
  await fetchFilteredFlows()
  ticker = setInterval(fetchLiveFlows, 2000)
}

watch(dbConnected, (conn) => {
  if (ticker) { clearInterval(ticker); ticker = null }
  if (conn) startMonitor()
}, { immediate: true })

watch(totalPages, (pages) => {
  if (currentPage.value > pages) currentPage.value = pages
})

onBeforeUnmount(() => { if (ticker) clearInterval(ticker) })
</script>

<style scoped>
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding: 14px 18px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.toolbar h3 { font-size: 16px; color: #292524; margin-bottom: 3px; }
.toolbar span { font-size: 12px; color: #78716c; }
.filter-panel { margin-bottom: 14px; padding: 14px 18px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.filter-grid { display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 8px; }
.filter-grid input, .filter-grid select { height: 32px; min-width: 0; border: 1px solid #e7e5e4; border-radius: 6px; padding: 0 10px; background: #fff; color: #292524; font-size: 13px; }
.filter-actions { display: flex; gap: 8px; margin-top: 10px; justify-content: flex-end; }
.filter-action { height: 32px; padding: 0 14px; border: 1px solid #2563eb; border-radius: 6px; background: #2563eb; color: #fff; font-size: 13px; font-weight: 700; cursor: pointer; }
.filter-action:disabled { opacity: 0.65; cursor: wait; }
.filter-action.secondary { color: #44403c; background: #fff; border-color: #e7e5e4; }
.error-banner { margin-bottom: 14px; padding: 10px 14px; border: 1px solid #fecaca; border-radius: 8px; color: #b91c1c; background: #fef2f2; font-size: 13px; }
.table-panel { background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; overflow: hidden; }
.table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { text-align: left; padding: 9px 14px; color: #78716c; font-size: 11px; font-weight: 700; white-space: nowrap; border-bottom: 1px solid #f5f5f4; cursor: pointer; user-select: none; }
.data-table th:hover { background: #fafaf9; }
.data-table td { padding: 10px 14px; color: #44403c; border-bottom: 1px solid #fafaf9; white-space: nowrap; }
.data-table tbody tr { cursor: pointer; }
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
.table-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 18px; border-top: 1px solid #f5f5f4; background: #fafafa; font-size: 12px; color: #78716c; }
.pagination-controls { display: flex; align-items: center; gap: 8px; }
.page-btn { height: 30px; min-width: 72px; padding: 0 12px; border: 1px solid #e7e5e4; border-radius: 6px; background: #fff; color: #44403c; font-size: 12px; font-weight: 700; cursor: pointer; }
.page-btn:not(:disabled):hover { border-color: #2563eb; color: #2563eb; }
.page-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.clean-state { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 120px); }
.clean-card { text-align: center; max-width: 460px; padding: 42px 30px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.clean-card h3 { font-size: 18px; color: #292524; margin-bottom: 8px; }
.clean-card p { color: #78716c; line-height: 1.7; font-size: 14px; }
@media (max-width: 1180px) { .filter-grid { grid-template-columns: repeat(3, minmax(120px, 1fr)); } }
@media (max-width: 700px) { .filter-grid { grid-template-columns: 1fr; } .filter-actions { justify-content: stretch; } .filter-action { flex: 1; } .table-footer { align-items: stretch; flex-direction: column; } .pagination-controls { justify-content: space-between; } .page-btn { flex: 1; } }
</style>
