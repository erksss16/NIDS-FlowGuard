<template>
  <div class="alert-center">
    <div v-if="dbConnected">
      <div class="alert-summary">
        <div class="summary-item pulse-when-hot" :class="{ hot: alertCounts.attack >= 5 }">
          <div class="summary-head">
            <span>异常告警</span>
            <em v-if="alertCounts.attack >= 5">已达提醒阈值</em>
          </div>
          <span class="summary-count danger">{{ alertCounts.attack }}</span>
          <span class="summary-label">{{ alertCounts.attack >= 5 ? '呼吸灯提醒中' : '达到 5 次后触发提醒' }}</span>
        </div>
        <div class="summary-item"><span class="summary-count info">{{ alertsTotal }}</span><span class="summary-label">待处置告警</span></div>
        <div class="summary-item"><span class="summary-count success">{{ handledCount }}</span><span class="summary-label">已研判记录</span></div>
        <div class="summary-item"><span class="summary-count accent">{{ riskSourceCount }}</span><span class="summary-label">高风险来源 IP</span></div>
      </div>

      <transition name="notice-pop">
        <div v-if="pageNotice" class="inline-alert-toast">
          <div>
            <strong>{{ pageNotice.title }}</strong>
            <span>{{ pageNotice.message }}</span>
          </div>
          <button @click="pageNotice = null">x</button>
        </div>
      </transition>

      <section class="mail-demo-panel">
        <div>
          <h3>管理员邮件告警</h3>
          <p>当系统出现多次危险告警时，向管理员邮箱发送一封风险提醒邮件。</p>
        </div>
        <div class="mail-demo-actions">
          <span class="mail-target">已配置的管理员邮箱</span>
          <button @click="sendAdminRiskAlert" :disabled="adminMailSending">
            {{ adminMailSending ? '发送中' : adminMailResult?.already_sent ? '已发送一封' : '发送告警邮件' }}
          </button>
        </div>
      </section>

      <div v-if="adminMailResult" class="mail-result" :class="{ failed: !adminMailResult.ok && adminMailResult.status !== 'below_threshold' }">
        <strong>{{ adminMailResult.already_sent ? '邮件已发送过' : adminMailResult.status === 'below_threshold' ? '未达到发送阈值' : '发送结果' }}</strong>
        <span>危险告警 {{ adminMailResult.attack_count }} 次，阈值 {{ adminMailResult.threshold }} 次；收件人：{{ adminMailResult.recipient_email }}</span>
        <p>{{ adminMailResult.message || (adminMailResult.provider === 'demo' ? '未配置 SMTP，已保存通知记录。' : '邮件发送完成。') }}</p>
        <pre v-if="adminMailResult.body">{{ adminMailResult.body }}</pre>
      </div>

      <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

      <section class="aggregation-panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">告警事件聚合</h3>
            <p class="panel-subtitle">按来源、协议、服务或时间聚合告警，便于定位流量来源、关联服务和集中发生时段</p>
          </div>
          <div class="filter-btns">
            <button
              v-for="mode in aggregationModes"
              :key="mode.key"
              class="filter-btn"
              :class="{ active: aggregationMode === mode.key }"
              @click="setAggregationMode(mode.key)"
            >
              {{ mode.label }}
            </button>
          </div>
        </div>
        <div class="aggregation-grid">
          <div v-for="item in aggregationRows.slice(0, 4)" :key="item.key" class="aggregation-card">
            <span>{{ aggregationModeLabel }}</span>
            <strong>{{ item.key }}</strong>
            <em>{{ item.cnt }} 次告警</em>
          </div>
        </div>
        <div class="table-wrap">
          <table class="data-table compact-table">
            <thead>
              <tr>
                <th>聚合项</th>
                <th>告警数</th>
                <th>主要协议</th>
                <th>主要服务</th>
                <th>主要来源</th>
                <th>首次出现</th>
                <th>最近出现</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in aggregationRows" :key="item.key">
                <td class="td-mono">{{ item.key }}</td>
                <td><span class="severity-tag sev-attack">{{ item.cnt }}</span></td>
                <td><span class="type-badge">{{ item.top_protocol }}</span></td>
                <td>{{ item.top_service }}</td>
                <td class="td-mono">{{ item.top_src_ip }}</td>
                <td>{{ item.first_time }}</td>
                <td>{{ item.last_time }}</td>
                <td><button class="review-batch-btn" @click="batchReview(item)">批量研判</button></td>
              </tr>
              <tr v-if="aggregationRows.length === 0">
                <td colspan="8" class="empty-cell">暂无聚合告警</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="table-panel">
        <div class="panel-header">
          <h3 class="panel-title">全部告警记录</h3>
          <span class="panel-subtitle">以下记录均为系统识别出的异常流量，处置状态需人工研判后更新</span>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>风险识别</th>
                <th>源 IP</th>
                <th>目的 IP</th>
                <th>协议</th>
                <th>服务</th>
                <th>源字节</th>
                <th>目的字节</th>
                <th>时间</th>
                <th>处置状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="alert in pagedAlerts"
                :key="alert.id"
                @click="openAlert(alert)"
                :class="{ 'row-sel': selectedAlert?.id === alert.id }"
              >
                <td class="td-mono">{{ alert.id }}</td>
                <td><span class="severity-tag" :class="'sev-' + alert.severity">{{ severityLabel(alert.severity) }}</span></td>
                <td class="td-mono">{{ alert.src_ip }}</td>
                <td class="td-mono">{{ alert.dst_ip }}</td>
                <td><span class="type-badge">{{ alert.protocol }}</span></td>
                <td>{{ alert.service }}</td>
                <td>{{ formatNum(alert.src_bytes) }}</td>
                <td>{{ formatNum(alert.dst_bytes) }}</td>
                <td>{{ alert.time }}</td>
                <td><span class="disposition-tag" :class="`disp-${alert.disposition}`">{{ dispositionLabel(alert.disposition) }}</span></td>
              </tr>
              <tr v-if="pagedAlerts.length === 0">
                <td colspan="10" class="empty-cell">暂无匹配告警</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="pagination-bar">
          <span>
            {{ alertsTotal === 0 ? '暂无记录' : `第 ${alertsPageStart}-${alertsPageEnd} 条，共 ${alertsTotal} 条` }}
          </span>
          <div class="pagination-actions">
            <button @click="setAlertPage(1)" :disabled="alertsPage <= 1">首页</button>
            <button @click="setAlertPage(alertsPage - 1)" :disabled="alertsPage <= 1">上一页</button>
            <strong>{{ alertsPage }} / {{ alertsTotalPages }}</strong>
            <button @click="setAlertPage(alertsPage + 1)" :disabled="alertsPage >= alertsTotalPages">下一页</button>
            <button @click="setAlertPage(alertsTotalPages)" :disabled="alertsPage >= alertsTotalPages">末页</button>
          </div>
        </div>
      </div>

      <transition name="slide-over">
        <div v-if="selectedAlert" class="detail-overlay" @click.self="selectedAlert = null">
          <div class="detail-panel">
            <div class="detail-header">
              <h3>告警详情 #{{ selectedAlert.id }}</h3>
              <button class="close-btn" @click="selectedAlert = null">x</button>
            </div>
            <div class="detail-body">
              <div class="action-row">
                <button @click="copyAlert">复制摘要</button>
                <button @click="sendEmailDemo" :disabled="emailSending">{{ emailSending ? '发送中' : '邮件通知' }}</button>
                <button>标记已处理</button>
                <button>加入白名单</button>
              </div>
              <div v-if="emailDemo" class="email-demo" :class="{ failed: emailDemo.status === 'failed' }">
                <div class="email-demo-head">
                  <span>邮件通知</span>
                  <strong>{{ emailDemo.provider === 'demo' ? '已保存通知记录' : emailDemo.status }}</strong>
                </div>
                <p>收件人：{{ emailDemo.recipient_email }}</p>
                <p>主题：{{ emailDemo.subject }}</p>
                <pre>{{ emailDemo.body }}</pre>
              </div>
              <div class="detail-row"><span>风险识别</span><span class="severity-tag" :class="'sev-' + selectedAlert.severity">{{ severityLabel(selectedAlert.severity) }}</span></div>
              <div class="detail-row"><span>处置状态</span><span class="disposition-tag" :class="`disp-${selectedAlert.disposition}`">{{ dispositionLabel(selectedAlert.disposition) }}</span></div>
              <div class="detail-row"><span>来源 / 目的</span><strong>{{ selectedAlert.src_ip }} -> {{ selectedAlert.dst_ip }}</strong></div>
              <div class="detail-row"><span>协议 / 服务</span><strong>{{ selectedAlert.protocol }} / {{ selectedAlert.service || '-' }}</strong></div>
              <div class="detail-row"><span>标志</span><strong>{{ selectedAlert.flag || '-' }}</strong></div>
              <div class="detail-row"><span>检测时间</span><strong>{{ selectedAlert.time }}</strong></div>
              <div class="feature-box">
                <h4>流量特征对比</h4>
                <div class="feature-line"><span>源字节</span><i><b :style="{ width: featureWidth(selectedAlert.src_bytes) }"></b></i><em>{{ formatNum(selectedAlert.src_bytes) }}</em></div>
                <div class="feature-line"><span>目的字节</span><i><b :style="{ width: featureWidth(selectedAlert.dst_bytes) }"></b></i><em>{{ formatNum(selectedAlert.dst_bytes) }}</em></div>
              </div>
              <div class="related">
                <h4>关联告警最近记录</h4>
                <div v-for="item in relatedAlerts" :key="item.id" class="related-item">
                  <span>#{{ item.id }}</span><strong>{{ item.protocol }}</strong><em>{{ item.time }}</em>
                </div>
              </div>
            </div>
          </div>
        </div>
      </transition>

      <transition name="review-modal">
        <div v-if="batchReviewDialog" class="batch-review-overlay" @click.self="closeBatchReview">
          <section class="batch-review-dialog" role="dialog" aria-modal="true" aria-labelledby="batch-review-title">
            <header class="batch-review-header">
              <div>
                <span class="batch-review-eyebrow">批量告警研判</span>
                <h3 id="batch-review-title">{{ aggregationModeLabel }}：{{ batchReviewDialog.item.key }}</h3>
                <p>本次操作将更新该聚合下的 {{ batchReviewDialog.item.cnt }} 条告警。</p>
              </div>
              <button class="close-btn" title="关闭" @click="closeBatchReview">x</button>
            </header>

            <div class="batch-review-body">
              <section class="evidence-section">
                <div class="section-heading">
                  <div>
                    <h4>研判证据</h4>
                    <p>展示最近 {{ batchReviewDialog.evidence.length }} 条关联流量</p>
                  </div>
                  <span class="evidence-count">{{ batchReviewDialog.item.cnt }} 条关联告警</span>
                </div>
                <div v-if="batchReviewDialog.evidence.length" class="evidence-list">
                  <article v-for="(row, index) in batchReviewDialog.evidence" :key="`${row.id || index}-${row.run_time}`" class="evidence-row">
                    <span class="evidence-index">{{ String(index + 1).padStart(2, '0') }}</span>
                    <div class="evidence-flow">
                      <strong>{{ row.src_ip || '-' }} <span>-></span> {{ row.dst_ip || '-' }}</strong>
                      <small>{{ row.run_time || '-' }}</small>
                    </div>
                    <div class="evidence-meta">
                      <span class="type-badge">{{ row.protocol || '-' }}</span>
                      <span class="flag-badge">{{ row.flag || '-' }}</span>
                      <span>{{ formatDuration(row.duration) }}</span>
                    </div>
                  </article>
                </div>
                <div v-else class="evidence-empty">暂无可展示的关联流量</div>
              </section>

              <section class="judgement-section">
                <h4>处置结论</h4>
                <div class="disposition-options">
                  <button
                    v-for="option in dispositionOptions"
                    :key="option.key"
                    type="button"
                    :class="['disposition-option', { active: batchReviewResult === option.key }]"
                    @click="batchReviewResult = option.key"
                  >
                    <strong>{{ option.label }}</strong>
                    <span>{{ option.description }}</span>
                  </button>
                </div>
                <label class="review-note-label" for="batch-review-note">研判备注</label>
                <textarea id="batch-review-note" v-model.trim="batchReviewNote" rows="3" maxlength="300" placeholder="记录处置依据、观察重点或后续安排（可选）"></textarea>
                <p v-if="batchReviewError" class="batch-review-error">{{ batchReviewError }}</p>
              </section>
            </div>

            <footer class="batch-review-footer">
              <button class="secondary-action" type="button" @click="closeBatchReview">取消</button>
              <button class="primary-action" type="button" :disabled="batchReviewSubmitting" @click="submitBatchReview">
                {{ batchReviewSubmitting ? '提交中...' : '确认提交研判' }}
              </button>
            </footer>
          </section>
        </div>
      </transition>
    </div>

    <div v-else class="clean-state">
      <div class="clean-card">
        <h3>告警中心</h3>
        <p>请先连接检测结果数据库，系统会在这里展示检测到的安全告警。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import TrafficChart from '../components/TrafficChart.vue'

const dbConnected = inject('dbConnected')
const backendUrl = inject('backendUrl')
const route = useRoute()

const activeFilter = ref('all')
const selectedAlert = ref(null)
const batchReviewDialog = ref(null)
const batchReviewResult = ref('watch')
const batchReviewNote = ref('')
const batchReviewSubmitting = ref(false)
const batchReviewError = ref('')
const allAlerts = ref([])
const alertsPage = ref(1)
const alertsPageSize = 50
const alertsTotal = ref(0)
const alertStats = ref({ attack: 0, false_positive: 0 })
const timeline = ref([])
const aggregationRows = ref([])
const aggregationMode = ref('src_ip')
const errorMessage = ref('')
const lastHighId = ref(0)
const hasLoadedAlerts = ref(false)
const pageNotice = ref(null)
const emailSending = ref(false)
const emailDemo = ref(null)
const adminMailSending = ref(false)
const adminMailResult = ref(null)
let ticker = null
let noticeTimer = null

const aggregationModes = [
  { key: 'src_ip', label: '来源 IP' },
  { key: 'protocol', label: '协议' },
  { key: 'service', label: '服务' },
  { key: 'time', label: '时间' },
]
const dispositionOptions = [
  { key: 'confirmed', label: '确认入侵', description: '确认存在入侵风险，纳入重点处置' },
  { key: 'watch', label: '持续观察', description: '保留告警并持续跟踪后续行为' },
  { key: 'resolved', label: '已处置', description: '已完成处置，归档本次告警' },
]
const COLORS = ['#ef4444', '#f97316', '#f59e0b', '#2563eb', '#16a34a', '#7c3aed', '#0891b2', '#65a30d']

const aggregationModeLabel = computed(() => aggregationModes.find(m => m.key === aggregationMode.value)?.label || '聚合项')

function formatNum(n) { return Number(n ?? 0).toLocaleString() }
function formatDuration(seconds) {
  const value = Number(seconds || 0)
  if (value < 1) return '<1s'
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`
}
function severityLabel(v) { return v === 'attack' ? '异常' : '正常' }
function dispositionLabel(status) {
  return ({ pending_review: '待研判', confirmed: '确认入侵', watch: '持续观察', resolved: '已处置', not_required: '无需处置' })[status] || '待研判'
}
function featureWidth(v) {
  const max = Math.max(...allAlerts.value.map(a => Number(a.src_bytes || 0) + Number(a.dst_bytes || 0)), 1)
  return `${Math.min(100, Math.max(6, Number(v || 0) / max * 100))}%`
}
function openAlert(alert) {
  selectedAlert.value = alert
  emailDemo.value = null
}
async function copyAlert() {
  if (!selectedAlert.value || !navigator.clipboard) return
  await navigator.clipboard.writeText(`#${selectedAlert.value.id} ${selectedAlert.value.type} ${selectedAlert.value.src_ip} ${selectedAlert.value.time}`)
}
function showPageNotice(alert) {
  pageNotice.value = {
    title: '新异常告警',
    message: `#${alert.id} 异常流量 / ${alert.protocol || '-'} / ${alert.service || '-'}`,
  }
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => {
    pageNotice.value = null
    noticeTimer = null
  }, 6000)
}
async function sendEmailDemo() {
  if (!selectedAlert.value) return
  emailSending.value = true
  emailDemo.value = null
  try {
    const res = await fetch(`${backendUrl.value}/api/notifications/email-demo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alert_id: selectedAlert.value.id }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '邮件通知失败')
    emailDemo.value = data
  } catch (e) {
    emailDemo.value = {
      status: 'failed',
      provider: 'demo',
      recipient_email: '-',
      subject: '发送失败',
      body: e.message || '邮件通知失败，请检查后端服务。',
    }
  } finally {
    emailSending.value = false
  }
}
async function sendAdminRiskAlert() {
  adminMailSending.value = true
  try {
    const res = await fetch(`${backendUrl.value}/api/notifications/admin-risk-alert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ threshold: 5 }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '管理员邮件告警发送失败')
    adminMailResult.value = data
  } catch (e) {
    adminMailResult.value = {
      ok: false,
      status: 'failed',
      recipient_email: '-',
      attack_count: alertCounts.value.attack,
      threshold: 5,
      message: e.message || '管理员邮件告警发送失败，请检查后端服务。',
    }
  } finally {
    adminMailSending.value = false
  }
}
function mapAlert(a) {
  return {
    id: a.id,
    type: a.predicted_label === 'attack' ? '异常流量' : '正常流量',
    severity: a.predicted_label === 'attack' ? 'attack' : 'normal',
    protocol: a.protocol,
    service: a.service,
    flag: a.flag,
    src_ip: a.src_ip || '-',
    dst_ip: a.dst_ip || '-',
    src_bytes: Number(a.src_bytes || 0),
    dst_bytes: Number(a.dst_bytes || 0),
    duration: Number(a.duration || 0),
    time: a.run_time,
    disposition: a.disposition || 'pending_review',
  }
}
function buildBarData(rows) {
  return rows.map((r, i) => ({ value: r.cnt, itemStyle: { color: COLORS[i % COLORS.length], borderRadius: [0, 6, 6, 0] } }))
}
function focusedAxis(values, minWindow = 12, minFloor = 0) {
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

const pagedAlerts = computed(() => allAlerts.value)
const alertsTotalPages = computed(() => Math.max(1, Math.ceil(alertsTotal.value / alertsPageSize)))
const alertsPageStart = computed(() => alertsTotal.value === 0 ? 0 : (alertsPage.value - 1) * alertsPageSize + 1)
const alertsPageEnd = computed(() => Math.min(alertsTotal.value, alertsPage.value * alertsPageSize))
const alertCounts = computed(() => ({
  attack: alertStats.value.attack,
  false_positive: alertStats.value.false_positive,
  total: alertStats.value.attack,
}))
const handledCount = ref(0)
const riskSourceCount = computed(() => new Set(allAlerts.value.map(item => item.src_ip).filter(Boolean)).size)
const falsePositiveRate = computed(() => {
  const attacks = alertCounts.value.attack
  return attacks ? Math.round(alertCounts.value.false_positive / attacks * 100) : 0
})
const relatedAlerts = computed(() => {
  if (!selectedAlert.value) return []
  return allAlerts.value.filter(a => a.type === selectedAlert.value.type && a.id !== selectedAlert.value.id).slice(0, 5)
})

const timelineOption = computed(() => {
  const attackValues = timeline.value.map(t => t.attack)
  const falsePositiveValues = timeline.value.map(t => t.false_positive)
  const attackAxis = focusedAxis(attackValues, 30)
  const falsePositiveAxis = focusedAxis(falsePositiveValues, 10)
  return {
    grid: [
      { left: 52, right: 22, top: 26, height: 116 },
      { left: 52, right: 22, top: 178, height: 86 },
    ],
    xAxis: [
      {
        type: 'category',
        gridIndex: 0,
        data: timeline.value.map(t => t.time),
        axisLabel: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: timeline.value.map(t => t.time),
        axisLabel: { color: '#78716c', fontSize: 11 },
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        name: '异常',
        min: attackAxis.min,
        max: attackAxis.max,
        splitNumber: 3,
        minInterval: 1,
        splitLine: { lineStyle: { color: '#f1f5f9' } },
        axisLabel: { color: '#ef4444', fontSize: 11 },
        nameTextStyle: { color: '#ef4444', fontSize: 11 },
      },
      {
        type: 'value',
        gridIndex: 1,
        name: '误报',
        min: falsePositiveAxis.min,
        max: falsePositiveAxis.max,
        splitNumber: 3,
        minInterval: 1,
        splitLine: { lineStyle: { color: '#fff7ed' } },
        axisLabel: { color: '#f59e0b', fontSize: 11 },
        nameTextStyle: { color: '#f59e0b', fontSize: 11 },
      },
    ],
    series: [
      {
        name: '异常',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        data: attackValues,
        lineStyle: { color: '#ef4444', width: 2 },
        itemStyle: { color: '#ef4444' },
        areaStyle: { color: 'rgba(239,68,68,0.06)' },
      },
      {
        name: '误报',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        data: falsePositiveValues,
        lineStyle: { color: '#f59e0b', width: 2 },
        itemStyle: { color: '#f59e0b' },
        areaStyle: { color: 'rgba(245,158,11,0.12)' },
      },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#fff',
      borderColor: '#e7e5e4',
      textStyle: { color: '#292524', fontSize: 12 },
      axisPointer: { type: 'line', link: [{ xAxisIndex: [0, 1] }] },
    },
  }
})

const attackOption = ref({
  grid: { left: 72, right: 24, top: 8, bottom: 30 },
  xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f1f5f9' } }, axisLabel: { color: '#78716c', fontSize: 10 } },
  yAxis: { type: 'category', data: [], axisLabel: { color: '#57534e', fontSize: 11 } },
  series: [{ type: 'bar', data: [], barWidth: 18, label: { show: true, position: 'right', color: '#57534e', fontSize: 11 } }],
  tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e7e5e4', textStyle: { color: '#292524', fontSize: 12 } },
})

function notifyHigh(alerts) {
  const attacks = alerts.filter(a => a.predicted_label === 'attack')
  const newest = attacks[0]
  if (!newest) return
  if (!hasLoadedAlerts.value) {
    lastHighId.value = newest.id
    hasLoadedAlerts.value = true
    return
  }
  if (newest.id <= lastHighId.value) return
  lastHighId.value = newest.id
  showPageNotice(newest)
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification('NIDS 异常告警', { body: `异常流量 / ${newest.protocol} / ${newest.service || '-'}` })
  } else if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}
async function fetchAggregation() {
  const interval = aggregationMode.value === 'time' ? 'hour' : 'hour'
  const res = await fetch(`${backendUrl.value}/api/alert-aggregation?group_by=${aggregationMode.value}&interval=${interval}&limit=12`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  aggregationRows.value = await res.json()
}
function setAggregationMode(mode) {
  aggregationMode.value = mode
  fetchAggregation().catch(() => {
    errorMessage.value = '告警聚合刷新失败，请检查后端服务。'
  })
}
async function batchReview(item) {
  batchReviewError.value = ''
  try {
    const previewRes = await fetch(`${backendUrl.value}/api/alerts?limit=1000`)
    if (!previewRes.ok) throw new Error(`HTTP ${previewRes.status}`)
    const previewPayload = await previewRes.json()
    const previewRows = Array.isArray(previewPayload) ? previewPayload : previewPayload.items || []
    const match = (row) => aggregationMode.value === 'src_ip' ? (row.src_ip || '-') === item.key : aggregationMode.value === 'protocol' ? (row.protocol || '-') === item.key : aggregationMode.value === 'service' ? (row.service || '-') === item.key : aggregationMode.value === 'time' ? String(row.run_time || '').slice(0, 13) + ':00' === item.key : true
    batchReviewDialog.value = { item, evidence: previewRows.filter(match).slice(0, 8) }
    batchReviewResult.value = 'watch'
    batchReviewNote.value = ''
  } catch (e) {
    errorMessage.value = '研判证据加载失败，请检查后端服务。'
  }
}
function closeBatchReview() {
  if (batchReviewSubmitting.value) return
  batchReviewDialog.value = null
  batchReviewError.value = ''
}
async function submitBatchReview() {
  if (!batchReviewDialog.value) return
  const labels = { confirmed: '确认入侵', watch: '持续观察', resolved: '已处置' }
  batchReviewSubmitting.value = true
  batchReviewError.value = ''
  try {
    const res = await fetch(`${backendUrl.value}/api/alert-aggregation/disposition`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        group_by: aggregationMode.value,
        group_key: batchReviewDialog.value.item.key,
        disposition: batchReviewResult.value,
        note: batchReviewNote.value,
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '批量研判失败')
    pageNotice.value = { title: '批量研判已完成', message: `${batchReviewDialog.value.item.key}：${data.handled_count} 条告警已标记为${labels[batchReviewResult.value]}` }
    batchReviewDialog.value = null
    await Promise.all([fetchAggregation(), fetchAlerts()])
  } catch (e) {
    batchReviewError.value = e.message || '批量研判失败，请检查后端服务。'
  } finally {
    batchReviewSubmitting.value = false
  }
}
function setAlertFilter(key) {
  if (activeFilter.value === key) return
  activeFilter.value = key
  alertsPage.value = 1
  fetchAlerts()
}
function setAlertPage(page) {
  const nextPage = Math.min(Math.max(1, Number(page) || 1), alertsTotalPages.value)
  if (alertsPage.value === nextPage) return
  alertsPage.value = nextPage
  fetchAlerts()
}
async function fetchAlerts() {
  try {
    errorMessage.value = ''
    const [alertsRes, statsRes, atkRes, dispositionRes] = await Promise.all([
      fetch(`${backendUrl.value}/api/alerts?page=${alertsPage.value}&page_size=${alertsPageSize}&filter=${activeFilter.value}`),
      fetch(`${backendUrl.value}/api/stats`),
      fetch(`${backendUrl.value}/api/attack-types`),
      fetch(`${backendUrl.value}/api/alert-disposition-summary`),
      fetchAggregation(),
    ])
    const alertsPayload = await alertsRes.json()
    const stats = await statsRes.json()
    const attackTypes = await atkRes.json()
    const dispositionSummary = await dispositionRes.json()
    const alerts = Array.isArray(alertsPayload) ? alertsPayload : alertsPayload.items || []
    handledCount.value = Number(dispositionSummary.handled || 0)
    alertsTotal.value = Math.max(0, (Array.isArray(alertsPayload) ? alerts.length : Number(alertsPayload.total || 0)) - handledCount.value)
    const maxPage = Math.max(1, Math.ceil(alertsTotal.value / alertsPageSize))
    if (alertsPage.value > maxPage) {
      alertsPage.value = maxPage
      return fetchAlerts()
    }
    alertStats.value = {
      attack: Number(stats.attack_count || 0),
      false_positive: Number(stats.false_positive_count || 0),
    }
    notifyHigh(alerts)
    allAlerts.value = alerts.map(mapAlert)
    const now = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    timeline.value = [...timeline.value, { time: now, ...alertCounts.value }].slice(-12)
    const attackTypeRows = [...attackTypes].reverse()
    attackOption.value.yAxis.data = attackTypeRows.map(r => r.name)
    attackOption.value.series[0].data = buildBarData(attackTypeRows)
    if (route.query.id) {
      const target = allAlerts.value.find(a => String(a.id) === String(route.query.id))
      if (target) selectedAlert.value = target
    }
  } catch (e) {
    errorMessage.value = '告警数据刷新失败，请检查后端服务。'
  }
}

watch(dbConnected, (conn) => {
  if (ticker) { clearInterval(ticker); ticker = null }
  if (conn) {
    hasLoadedAlerts.value = false
    fetchAlerts()
    ticker = setInterval(fetchAlerts, 2000)
  }
}, { immediate: true })

onBeforeUnmount(() => {
  if (ticker) clearInterval(ticker)
  if (noticeTimer) clearTimeout(noticeTimer)
})
</script>

<style scoped>
.review-batch-btn { height:28px; padding:0 9px; border:1px solid #2563eb; border-radius:5px; background:#eff6ff; color:#1d4ed8; font-size:12px; font-weight:700; cursor:pointer; white-space:nowrap; }
.review-batch-btn:hover { background:#dbeafe; }
.batch-review-overlay { position:fixed; inset:0; z-index:700; display:flex; align-items:center; justify-content:center; padding:24px; background:rgba(15,23,42,0.42); backdrop-filter:blur(2px); }
.batch-review-dialog { width:min(820px, 100%); max-height:min(780px, calc(100vh - 48px)); display:flex; flex-direction:column; overflow:hidden; border:1px solid #cbd5e1; border-radius:8px; background:#fff; box-shadow:0 24px 60px rgba(15,23,42,0.24); }
.batch-review-header { display:flex; justify-content:space-between; align-items:flex-start; gap:20px; padding:22px 24px 18px; border-bottom:1px solid #e2e8f0; background:#f8fafc; }
.batch-review-eyebrow { display:block; margin-bottom:6px; color:#2563eb; font-size:12px; font-weight:800; }
.batch-review-header h3 { margin:0; color:#172033; font-size:18px; line-height:1.35; overflow-wrap:anywhere; }
.batch-review-header p { margin:6px 0 0; color:#64748b; font-size:13px; }
.batch-review-body { overflow:auto; padding:20px 24px 22px; }
.evidence-section, .judgement-section { border:1px solid #e2e8f0; border-radius:8px; background:#fff; }
.section-heading { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:14px 16px; border-bottom:1px solid #e2e8f0; background:#f8fafc; }
.section-heading h4, .judgement-section h4 { margin:0; color:#1e293b; font-size:14px; }
.section-heading p { margin:4px 0 0; color:#64748b; font-size:12px; }
.evidence-count { flex-shrink:0; padding:4px 8px; border-radius:999px; background:#eff6ff; color:#1d4ed8; font-size:12px; font-weight:700; }
.evidence-list { padding:0 16px; }
.evidence-row { display:grid; grid-template-columns:30px minmax(0, 1fr) auto; gap:12px; align-items:center; min-height:60px; border-bottom:1px solid #f1f5f9; }
.evidence-row:last-child { border-bottom:0; }
.evidence-index { color:#94a3b8; font:700 11px 'SF Mono', 'Fira Code', monospace; }
.evidence-flow { min-width:0; }
.evidence-flow strong { display:block; overflow:hidden; color:#334155; font:600 12px 'SF Mono', 'Fira Code', monospace; text-overflow:ellipsis; white-space:nowrap; }
.evidence-flow strong span { color:#94a3b8; }
.evidence-flow small { display:block; margin-top:4px; color:#94a3b8; font-size:11px; }
.evidence-meta { display:flex; align-items:center; justify-content:flex-end; gap:7px; color:#64748b; font-size:12px; white-space:nowrap; }
.flag-badge { padding:2px 7px; border-radius:4px; background:#f8fafc; color:#475569; font:700 11px 'SF Mono', 'Fira Code', monospace; }
.evidence-empty { padding:26px 16px; color:#94a3b8; text-align:center; font-size:13px; }
.judgement-section { margin-top:16px; padding:16px; }
.disposition-options { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; margin:12px 0 16px; }
.disposition-option { min-height:72px; padding:10px; border:1px solid #dbe2ea; border-radius:6px; background:#fff; color:#64748b; text-align:left; cursor:pointer; }
.disposition-option:hover { border-color:#93c5fd; background:#f8fbff; }
.disposition-option.active { border-color:#2563eb; background:#eff6ff; box-shadow:inset 0 0 0 1px #2563eb; }
.disposition-option strong, .disposition-option span { display:block; }
.disposition-option strong { color:#334155; font-size:13px; }
.disposition-option.active strong { color:#1d4ed8; }
.disposition-option span { margin-top:5px; color:#64748b; font-size:11px; line-height:1.4; }
.review-note-label { display:block; margin-bottom:7px; color:#475569; font-size:12px; font-weight:700; }
.judgement-section textarea { box-sizing:border-box; display:block; width:100%; resize:vertical; border:1px solid #cbd5e1; border-radius:6px; padding:10px; color:#334155; font:13px inherit; line-height:1.5; outline:none; }
.judgement-section textarea:focus { border-color:#2563eb; box-shadow:0 0 0 3px rgba(37,99,235,0.1); }
.batch-review-error { margin:10px 0 0; color:#b91c1c; font-size:12px; }
.batch-review-footer { display:flex; justify-content:flex-end; gap:10px; padding:14px 24px; border-top:1px solid #e2e8f0; background:#f8fafc; }
.secondary-action, .primary-action { min-width:92px; height:34px; padding:0 14px; border-radius:6px; font-size:13px; font-weight:700; cursor:pointer; }
.secondary-action { border:1px solid #cbd5e1; background:#fff; color:#475569; }
.primary-action { border:1px solid #1d4ed8; background:#2563eb; color:#fff; }
.primary-action:disabled { opacity:0.65; cursor:wait; }
.review-modal-enter-active, .review-modal-leave-active { transition:opacity 0.18s ease; }
.review-modal-enter-active .batch-review-dialog, .review-modal-leave-active .batch-review-dialog { transition:opacity 0.18s ease, transform 0.18s ease; }
.review-modal-enter-from, .review-modal-leave-to { opacity:0; }
.review-modal-enter-from .batch-review-dialog, .review-modal-leave-to .batch-review-dialog { opacity:0; transform:translateY(10px) scale(0.985); }
.alert-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }
.summary-item { position: relative; display:flex; min-height:126px; flex-direction:column; justify-content:center; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; padding: 16px 20px; text-align: center; overflow: hidden; transition: border-color 0.2s, background 0.2s, box-shadow 0.2s; }
.summary-head { display: flex; justify-content: center; align-items: center; gap: 8px; min-height: 22px; margin-bottom: 4px; font-size: 12px; color: #78716c; font-weight: 700; }
.summary-head em { font-style: normal; color: #b91c1c; background: #fee2e2; border: 1px solid #fecaca; border-radius: 999px; padding: 2px 8px; font-size: 11px; }
.summary-count { display: block; font-size: 30px; line-height:1.15; font-weight: 800; margin-bottom: 8px; }
.summary-label { font-size: 12px; color: #78716c; }
.summary-count.danger { color: #ef4444; }
.summary-count.warning { color: #f59e0b; }
.summary-count.accent { color: #f97316; }
.summary-count.success { color: #16a34a; }
.pulse-when-hot.hot { border-color: #fca5a5; background: linear-gradient(135deg, #fff, #fef2f2); animation: hotPulse 1.35s ease-in-out infinite; }
.pulse-when-hot.hot::before { content: ""; position: absolute; inset: 0; border-radius: inherit; border: 1px solid rgba(239,68,68,0.25); pointer-events: none; }
.pulse-when-hot.hot .summary-count { text-shadow: 0 0 14px rgba(239,68,68,0.28); }
@keyframes hotPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.22), 0 2px 8px rgba(239,68,68,0.06); transform: translateY(0); }
  50% { box-shadow: 0 0 0 8px rgba(239,68,68,0.08), 0 10px 24px rgba(239,68,68,0.16); transform: translateY(-1px); }
}
.inline-alert-toast { display: flex; justify-content: space-between; align-items: center; gap: 14px; margin: -4px 0 14px; padding: 12px 14px; border: 1px solid #fecaca; border-left: 4px solid #ef4444; border-radius: 8px; background: #fef2f2; color: #991b1b; box-shadow: 0 8px 20px rgba(239,68,68,0.12); }
.inline-alert-toast strong { display: block; margin-bottom: 3px; font-size: 13px; }
.inline-alert-toast span { display: block; font-size: 12px; color: #b91c1c; }
.inline-alert-toast button { width: 24px; height: 24px; border: 0; border-radius: 6px; background: #fee2e2; color: #b91c1c; cursor: pointer; font-weight: 800; }
.notice-pop-enter-active, .notice-pop-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.notice-pop-enter-from, .notice-pop-leave-to { opacity: 0; transform: translateY(-6px); }
.mail-demo-panel { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 12px; padding: 16px 18px; border: 1px solid #fed7aa; border-radius: 8px; background: #fff7ed; }
.mail-demo-panel h3 { font-size: 14px; color: #9a3412; margin-bottom: 4px; }
.mail-demo-panel p { margin: 0; font-size: 12px; color: #9a3412; line-height: 1.5; }
.mail-demo-actions { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.mail-target { padding: 6px 10px; border-radius: 6px; background: #fff; color: #9a3412; border: 1px solid #fed7aa; font-size: 12px; font-weight: 700; }
.mail-demo-actions button { height: 34px; padding: 0 14px; border: 0; border-radius: 6px; background: #ea580c; color: #fff; font-size: 12px; font-weight: 800; cursor: pointer; }
.mail-demo-actions button:disabled { opacity: 0.65; cursor: wait; }
.mail-result { margin-bottom: 14px; padding: 12px 14px; border: 1px solid #bbf7d0; border-radius: 8px; background: #f0fdf4; color: #166534; font-size: 12px; }
.mail-result.failed { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.mail-result strong { display: block; margin-bottom: 5px; font-size: 13px; }
.mail-result span { display: block; margin-bottom: 4px; }
.mail-result p { margin: 0; line-height: 1.5; }
.mail-result pre { margin: 10px 0 0; padding: 10px; max-height: 160px; overflow: auto; border-radius: 6px; background: rgba(255,255,255,0.75); white-space: pre-wrap; font-size: 12px; line-height: 1.5; font-family: inherit; }
.error-banner { margin-bottom: 14px; padding: 10px 14px; border: 1px solid #fecaca; border-radius: 8px; color: #b91c1c; background: #fef2f2; font-size: 13px; }
.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
.table-panel, .aggregation-panel { background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; overflow: hidden; margin-bottom: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 18px; border-bottom: 1px solid #f5f5f4; }
.panel-title { font-size: 13px; font-weight: 700; color: #292524; }
.panel-subtitle { margin-top: 3px; font-size: 12px; color: #78716c; }
.filter-btns { display: flex; flex-wrap: wrap; gap: 4px; }
.filter-btn { padding: 4px 10px; border-radius: 5px; background: none; border: 1px solid transparent; color: #78716c; font-size: 12px; cursor: pointer; }
.filter-btn.active { color: #2563eb; background: #eff6ff; border-color: #dbeafe; }
.aggregation-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 14px 18px; border-bottom: 1px solid #f5f5f4; }
.aggregation-card { padding: 12px; border: 1px solid #f1f5f9; border-radius: 8px; background: #fafafa; min-width: 0; }
.aggregation-card span { display: block; font-size: 11px; color: #78716c; margin-bottom: 5px; }
.aggregation-card strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #292524; font-size: 15px; }
.aggregation-card em { display: block; margin-top: 6px; font-style: normal; color: #ef4444; font-size: 12px; font-weight: 700; }
.table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.compact-table { font-size: 12px; }
.data-table th { text-align: left; padding: 9px 14px; font-weight: 700; color: #78716c; font-size: 11px; border-bottom: 1px solid #f5f5f4; white-space: nowrap; }
.data-table td { padding: 10px 14px; color: #44403c; border-bottom: 1px solid #fafaf9; white-space: nowrap; }
.data-table tbody tr { cursor: pointer; }
.data-table tbody tr:hover, .data-table tbody tr.row-sel { background: #fafaf9; }
.pagination-bar { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 18px; border-top: 1px solid #f5f5f4; color: #78716c; font-size: 12px; }
.pagination-actions { display: flex; align-items: center; gap: 6px; }
.pagination-actions button { min-width: 52px; height: 28px; padding: 0 10px; border: 1px solid #e7e5e4; border-radius: 5px; background: #fff; color: #57534e; font-size: 12px; cursor: pointer; }
.pagination-actions button:disabled { color: #cbd5e1; background: #f8fafc; cursor: not-allowed; }
.pagination-actions strong { min-width: 54px; text-align: center; color: #292524; font-size: 12px; }
.td-mono, .type-badge { font-family: 'SF Mono', 'Fira Code', monospace; }
.type-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: #f1f5f9; color: #334155; }
.severity-tag, .status-tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; }
.sev-attack { color: #ef4444; background: rgba(239,68,68,0.08); }
.sev-normal { color: #16a34a; background: rgba(22,163,74,0.08); }
.st-blocked { color: #16a34a; background: rgba(22,163,74,0.08); }
.st-watch { color: #f59e0b; background: rgba(245,158,11,0.10); }
.disposition-tag { display:inline-block; min-width:58px; padding:2px 8px; border-radius:999px; text-align:center; font-size:12px; font-weight:700; }
.disp-pending_review { color:#b45309; background:#fffbeb; }
.disp-confirmed { color:#b91c1c; background:#fef2f2; }
.disp-watch { color:#1d4ed8; background:#eff6ff; }
.disp-resolved, .disp-not_required { color:#15803d; background:#f0fdf4; }
.fp-tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; }
.fp-yes { color: #f59e0b; background: rgba(245,158,11,0.10); }
.fp-no { color: #78716c; background: rgba(120,113,108,0.08); }
.empty-cell { text-align: center; color: #a8a29e; padding: 28px; }
.detail-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.2); z-index: 600; display: flex; justify-content: flex-end; }
.detail-panel { width: 520px; max-width: 94vw; height: 100%; background: #fff; border-left: 1px solid #e7e5e4; overflow-y: auto; }
.detail-header { display: flex; justify-content: space-between; align-items: center; padding: 18px 22px; border-bottom: 1px solid #f5f5f4; position: sticky; top: 0; background: #fff; }
.detail-header h3 { font-size: 15px; font-weight: 700; color: #292524; }
.close-btn { width: 28px; height: 28px; border: none; border-radius: 5px; background: #f5f5f4; color: #64748b; cursor: pointer; font-size: 18px; }
.detail-body { padding: 22px; }
.action-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 16px; }
.action-row button { border: 1px solid #dbeafe; border-radius: 6px; background: #eff6ff; color: #2563eb; height: 32px; font-size: 12px; font-weight: 700; cursor: pointer; }
.action-row button:disabled { opacity: 0.6; cursor: wait; }
.email-demo { margin-bottom: 16px; padding: 12px; border: 1px solid #bbf7d0; border-radius: 8px; background: #f0fdf4; color: #166534; }
.email-demo.failed { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.email-demo-head { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 8px; font-size: 13px; font-weight: 700; }
.email-demo p { margin: 4px 0; font-size: 12px; }
.email-demo pre { margin: 8px 0 0; padding: 10px; max-height: 180px; overflow: auto; border-radius: 6px; background: rgba(255,255,255,0.7); white-space: pre-wrap; font-size: 12px; line-height: 1.5; font-family: inherit; }
.detail-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #fafaf9; }
.detail-row span:first-child { font-size: 13px; color: #a8a29e; }
.feature-box, .related { margin-top: 18px; padding: 14px; border: 1px solid #e7e5e4; border-radius: 8px; background: #fafafa; }
.feature-box h4, .related h4 { font-size: 13px; color: #292524; margin-bottom: 12px; }
.feature-line { display: grid; grid-template-columns: 64px 1fr 72px; gap: 10px; align-items: center; margin: 10px 0; font-size: 12px; color: #64748b; }
.feature-line i { height: 8px; border-radius: 99px; background: #e2e8f0; overflow: hidden; }
.feature-line b { display: block; height: 100%; border-radius: inherit; background: #2563eb; }
.feature-line em { font-style: normal; text-align: right; color: #292524; }
.related-item { display: grid; grid-template-columns: 54px 1fr 132px; gap: 8px; padding: 8px 0; border-top: 1px solid #f1f5f9; font-size: 12px; color: #64748b; }
.related-item:first-of-type { border-top: 0; }
.slide-over-enter-active, .slide-over-leave-active { transition: opacity 0.18s ease; }
.slide-over-enter-from, .slide-over-leave-to { opacity: 0; }
.slide-over-enter-active .detail-panel, .slide-over-leave-active .detail-panel { transition: transform 0.2s ease; }
.slide-over-enter-from .detail-panel, .slide-over-leave-to .detail-panel { transform: translateX(100%); }
.clean-state { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 120px); }
.clean-card { text-align: center; max-width: 460px; padding: 42px 30px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.clean-card h3 { font-size: 18px; color: #292524; margin-bottom: 8px; }
.clean-card p { color: #78716c; line-height: 1.7; font-size: 14px; }
@media (max-width: 1000px) { .alert-summary, .charts-row, .aggregation-grid { grid-template-columns: 1fr 1fr; } .action-row { grid-template-columns: 1fr 1fr; } }
@media (max-width: 700px) { .alert-summary, .charts-row, .aggregation-grid, .disposition-options { grid-template-columns: 1fr; } .panel-header, .mail-demo-panel, .mail-demo-actions { align-items: flex-start; flex-direction: column; } .batch-review-overlay { align-items:flex-end; padding:0; } .batch-review-dialog { max-height:calc(100vh - 12px); border-bottom:0; border-radius:8px 8px 0 0; } .batch-review-header, .batch-review-body, .batch-review-footer { padding-left:16px; padding-right:16px; } .evidence-row { grid-template-columns:24px minmax(0, 1fr); gap:8px; padding:9px 0; } .evidence-meta { grid-column:2; justify-content:flex-start; } }
</style>
