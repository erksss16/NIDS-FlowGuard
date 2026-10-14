<template>
  <div class="dashboard">
    <div v-if="dbConnected">
      <div class="toolbar">
        <div>
          <h3>系统运行概览</h3>
          <span>聚焦当前网络风险、告警与处置进展</span>
        </div>
        <div class="toolbar-actions"><button class="report-btn" @click="downloadReport">生成入侵报告</button><div class="sync-status"><i></i> 实时更新</div></div>
      </div>
      <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>
      <div class="stats-row">
        <StatCard
          label="今日流量"
          :value="formatNum(stats.totalFlows)"
          unit=" 条"
          :trend="trend.totalFlows"
          desc="当前累计检测"
          ><template #icon
            ><svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M3 12h18M15 6l6 6-6 6M9 18l-6-6 6-6" /></svg></template
        ></StatCard>
        <StatCard
          label="异常告警"
          :value="formatNum(stats.attackCount)"
          unit=" 条"
          :trend="trend.attackCount"
          desc="需要关注的事件"
          ><template #icon
            ><svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M12 2 2 21h20L12 2Z" />
              <path d="M12 9v4M12 17h.01" /></svg></template
        ></StatCard>
        <StatCard
          label="高危告警"
          :value="formatNum(highRiskCount)"
          unit=" 条"
          :trend="trend.highRisk"
          desc="建议优先处理"
          ><template #icon
            ><svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M12 3v18M5.6 6.7l12.8 10.6M18.4 6.7 5.6 17.3"
              /></svg></template
        ></StatCard>
        <StatCard
          label="当前风险指数"
          :value="riskIndex"
          unit=" / 100"
          :trend="trend.riskIndex"
          desc="综合告警强度"
          ><template #icon
            ><svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M12 2a10 10 0 1 0 10 10" />
              <path d="m12 12 6-5" />
              <circle cx="12" cy="12" r="2" /></svg></template
        ></StatCard>
      </div>
      <div class="overview-grid">
        <TrafficChart
          title="实时流量趋势"
          description="按最新检测批次汇总的正常流量与异常告警数量。"
          live
          :option="trafficTrendOption"
        />
        <section class="threat-profile">
          <div class="panel-header compact">
            <div>
              <h3 class="panel-title">疑似威胁画像</h3>
              <p>基于近期异常流量的来源、协议与服务特征</p>
            </div>
            <span class="risk-level" :class="riskLevel.className">{{
              riskLevel.label
            }}</span>
          </div>
          <div class="profile-score">
            <div
              class="score-ring"
              :style="{
                '--score': riskIndex,
                '--score-color': riskLevel.color,
              }"
            >
              <strong>{{ riskIndex }}</strong
              ><span>风险指数</span>
            </div>
            <div class="profile-copy">
              <strong>{{ profileHeadline }}</strong
              ><span>{{ profileDescription }}</span>
            </div>
          </div>
          <div class="profile-list">
            <div>
              <span>主要来源</span
              ><strong class="mono">{{ topRiskIps[0]?.ip || "-" }}</strong>
            </div>
            <div>
              <span>常见协议</span><strong>{{ dominantProtocol }}</strong>
            </div>
            <div>
              <span>关联服务</span><strong>{{ dominantService }}</strong>
            </div>
          </div>
        </section>
      </div>
      <div class="sankey-row">
        <TrafficChart title="网络流量路径" description="展示近期检测流量从入口协议到关联服务的实际路径。" :option="sankeyOption" />
      </div>
      <div class="operations-grid">
        <section class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">Top 风险源 IP</h3>
              <p>按近期异常告警次数排序</p>
            </div>
          </div>
          <div class="ip-list">
            <div
              v-for="(item, index) in topRiskIps"
              :key="item.ip"
              class="ip-row"
            >
              <span class="rank">{{ index + 1 }}</span>
              <div class="ip-main">
                <strong class="mono">{{ item.ip }}</strong
                ><span>{{ item.protocol }} · {{ item.service }}</span>
              </div>
              <div class="ip-risk">
                <b :style="{ width: `${item.score}%` }"></b>
              </div>
              <em>{{ item.count }} 次</em>
            </div>
            <div v-if="topRiskIps.length === 0" class="empty-cell">
              暂无风险来源 IP
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">最近告警处置</h3>
              <p>优先展示需要处理的最新事件</p>
            </div>
          </div>
          <div class="disposition-list">
            <div
              v-for="alert in recentAlerts"
              :key="alert.id"
              class="disposition-row"
            >
              <span class="severity-dot" :class="alert.level"></span>
              <div class="alert-main">
                <strong>{{ alert.reason }}</strong
                ><span>{{ alert.source }} · {{ alert.time }}</span>
              </div>
              <button class="disposition" :class="alert.statusClass" @click="resolveAlert(alert)">{{ alert.status }}</button>
            </div>
            <div v-if="recentAlerts.length === 0" class="empty-cell">
              当前没有待处置告警
            </div>
          </div>
        </section>
      </div>
    </div>
    <div v-else class="clean-state">
      <div class="clean-card">
        <h3>欢迎使用安全运营中心</h3>
        <p>连接检测服务后，即可查看网络风险、实时告警和处置进度。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onBeforeUnmount, inject, watch } from "vue";
import StatCard from "../components/StatCard.vue";
import TrafficChart from "../components/TrafficChart.vue";
const dbConnected = inject("dbConnected");
const backendUrl = inject("backendUrl");
const stats = ref({ totalFlows: 0, attackCount: 0, attackPct: 0 });
const previousStats = ref(null);
const recentAlerts = ref([]);
const topRiskIps = ref([]);
const protocolData = ref([]);
const flowRows = ref([]);
const trafficTrend = ref([]);
const errorMessage = ref("");
const handledAlerts = ref(JSON.parse(sessionStorage.getItem("nids_handled_alerts") || "{}"));
let ticker = null;
function formatNum(n) {
  return Number(n || 0).toLocaleString();
}
function diffPercent(current, previous) {
  if (!previous) return 0;
  return Number((((current - previous) / previous) * 100).toFixed(1));
}
function isHighRisk(row) {
  return (
    row.has_drift ||
    Number(row.src_bytes || 0) + Number(row.dst_bytes || 0) > 10000
  );
}
const highRiskCount = computed(
  () => recentAlerts.value.filter((a) => a.level === "high").length,
);
const highRiskRate = computed(() => recentAlerts.value.length ? highRiskCount.value / recentAlerts.value.length * 100 : 0);
const sourceConcentration = computed(() => recentAlerts.value.length ? (topRiskIps.value[0]?.count || 0) / recentAlerts.value.length * 100 : 0);
const riskIndex = computed(() =>
  Math.round(Math.min(100, stats.value.attackPct * 0.55 + highRiskRate.value * 0.30 + sourceConcentration.value * 0.15)),
);
function resolveAlert(alert) { handledAlerts.value = { ...handledAlerts.value, [alert.id]: true }; sessionStorage.setItem("nids_handled_alerts", JSON.stringify(handledAlerts.value)); alert.status = "已处理"; alert.statusClass = "resolved"; }
function downloadReport() { window.open(`${backendUrl.value}/api/reports/intrusion`, "_blank", "noopener"); }
const trend = computed(() => {
  const previous = previousStats.value;
  return {
    totalFlows: diffPercent(stats.value.totalFlows, previous?.totalFlows),
    attackCount: diffPercent(stats.value.attackCount, previous?.attackCount),
    highRisk: previous ? highRiskCount.value - previous.highRisk : 0,
    riskIndex: previous ? riskIndex.value - previous.riskIndex : 0,
  };
});
const riskLevel = computed(() =>
  riskIndex.value >= 70
    ? { label: "高风险", className: "high", color: "#dc2626" }
    : riskIndex.value >= 35
      ? { label: "中风险", className: "medium", color: "#d97706" }
      : { label: "低风险", className: "low", color: "#059669" },
);
const dominantProtocol = computed(() => protocolData.value[0]?.protocol || "-");
const dominantService = computed(() => topRiskIps.value[0]?.service || "-");
const profileHeadline = computed(() =>
  riskIndex.value >= 70
    ? "检测到持续高风险活动"
    : riskIndex.value >= 35
      ? "存在需要关注的异常活动"
      : "当前网络风险保持可控",
);
const profileDescription = computed(() =>
  highRiskCount.value
    ? `${highRiskCount.value} 条高危告警等待优先处置。`
    : "暂无高危告警，系统持续监测中。",
);
const trafficTrendOption = computed(() => ({
  color: ["#059669", "#dc2626"],
  legend: {
    top: 2,
    right: 18,
    itemWidth: 10,
    itemHeight: 10,
    textStyle: { color: "#57534e", fontSize: 11 },
  },
  grid: { left: 48, right: 18, top: 42, bottom: 30 },
  xAxis: {
    type: "category",
    data: trafficTrend.value.map((item) => item.time),
    boundaryGap: false,
    axisLabel: { color: "#78716c", fontSize: 11 },
    axisTick: { show: false },
  },
  yAxis: {
    type: "value",
    minInterval: 1,
    splitLine: { lineStyle: { color: "#f1f5f9" } },
    axisLabel: { color: "#78716c", fontSize: 11 },
  },
  series: [
    {
      name: "正常流量",
      type: "line",
      smooth: true,
      symbol: "none",
      data: trafficTrend.value.map((item) => item.normal),
      lineStyle: { width: 2, color: "#059669" },
      areaStyle: { color: "rgba(5,150,105,0.08)" },
    },
    {
      name: "异常告警",
      type: "line",
      smooth: true,
      symbol: "none",
      data: trafficTrend.value.map((item) => item.attack),
      lineStyle: { width: 2.5, color: "#dc2626" },
      areaStyle: { color: "rgba(220,38,38,0.08)" },
    },
  ],
  tooltip: {
    trigger: "axis",
    backgroundColor: "#fff",
    borderColor: "#e7e5e4",
    textStyle: { color: "#292524", fontSize: 12 },
  },
}));
const sankeyOption = computed(() => {
  const pairs = new Map()
  flowRows.value.forEach(row => {
    const protocol = row.protocol || '未知协议'
    const service = row.service || '未知服务'
    const key = `${protocol}|${service}`
    pairs.set(key, (pairs.get(key) || 0) + 1)
  })
  const pairRows = [...pairs.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12)
  const protocols = [...new Set(pairRows.map(([key]) => key.split('|')[0]))]
  const services = [...new Set(pairRows.map(([key]) => key.split('|')[1]))]
  return { tooltip: { trigger: 'item', backgroundColor: '#fff', borderColor: '#e7e5e4', textStyle: { color: '#292524', fontSize: 12 } }, series: [{ type: 'sankey', left: '8%', right: '10%', top: '8%', bottom: '8%', nodeWidth: 14, nodeGap: 12, data: [{ name: '近期流量' }, ...protocols.map(name => ({ name })), ...services.map(name => ({ name }))], links: [...protocols.map(protocol => ({ source: '近期流量', target: protocol, value: pairRows.filter(([key]) => key.startsWith(`${protocol}|`)).reduce((sum, [, value]) => sum + value, 0) })), ...pairRows.map(([key, value]) => { const [source, target] = key.split('|'); return { source, target, value } })], lineStyle: { color: 'gradient', opacity: .22, curveness: .45 }, emphasis: { focus: 'adjacency', lineStyle: { opacity: .9 } }, blur: { lineStyle: { opacity: .06 } }, itemStyle: { borderColor: '#fff', borderWidth: 1 }, label: { color: '#44403c', fontSize: 11, fontWeight: 600 } }] }
});
function buildTopIps(alerts) {
  const groups = new Map();
  alerts.forEach((row) => {
    const ip = row.src_ip || "-";
    const current = groups.get(ip) || {
      ip,
      count: 0,
      protocol: row.protocol || "-",
      service: row.service || "-",
    };
    current.count += 1;
    groups.set(ip, current);
  });
  const rows = [...groups.values()]
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
  const max = rows[0]?.count || 1;
  return rows.map((row) => ({
    ...row,
    score: Math.max(12, Math.round((row.count / max) * 100)),
  }));
}
async function fetchDashboard() {
  errorMessage.value = "";
  try {
    const [statsRes, alertsRes, protocolRes, flowsRes] = await Promise.all([
      fetch(`${backendUrl.value}/api/stats`),
      fetch(`${backendUrl.value}/api/alerts?limit=100`),
      fetch(`${backendUrl.value}/api/protocol-distribution`),
      fetch(`${backendUrl.value}/api/flows?limit=1000`),
    ]);
    if (![statsRes, alertsRes, protocolRes, flowsRes].every((res) => res.ok))
      throw new Error("request failed");
    const [s, alerts, protocols, flows] = await Promise.all([
      statsRes.json(),
      alertsRes.json(),
      protocolRes.json(),
      flowsRes.json(),
    ]);
    previousStats.value = {
      ...stats.value,
      highRisk: highRiskCount.value,
      riskIndex: riskIndex.value,
    };
    stats.value = {
      totalFlows: Number(s.total_flows || 0),
      attackCount: Number(s.attack_count || 0),
      attackPct: Number(s.attack_pct || 0),
    };
    protocolData.value = protocols;
    flowRows.value = flows;
    topRiskIps.value = buildTopIps(alerts);
    recentAlerts.value = alerts.slice(0, 6).map((row) => {
      const high = isHighRisk(row);
      return {
        id: row.id,
        reason: high ? "高风险异常流量" : "疑似异常流量",
        source: `${row.src_ip || "-"} -> ${row.dst_ip || "-"}`,
        time: row.run_time || "-",
        level: high ? "high" : "medium",
        status: handledAlerts.value[row.id] ? "已处理" : (high ? "待优先处理" : "待研判"),
        statusClass: handledAlerts.value[row.id] ? "resolved" : (high ? "pending" : "review"),
      };
    });
    const now = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const normal = Math.max(
      0,
      Number(s.total_flows || 0) - Number(s.attack_count || 0),
    );
    const savedTrend = trafficTrend.value.length ? trafficTrend.value : JSON.parse(sessionStorage.getItem("nids_traffic_trend") || "[]");
    trafficTrend.value = [
      ...savedTrend,
      { time: now, normal, attack: Number(s.attack_count || 0) },
    ].slice(-18); sessionStorage.setItem("nids_traffic_trend", JSON.stringify(trafficTrend.value));
  } catch {
    errorMessage.value = "数据刷新失败，请确认后端服务正在运行。";
  }
}
watch(
  dbConnected,
  (connected) => {
    if (ticker) {
      clearInterval(ticker);
      ticker = null;
    }
    if (connected) {
      fetchDashboard();
      ticker = setInterval(fetchDashboard, 5000);
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  if (ticker) clearInterval(ticker);
});
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  padding: 14px 18px;
  background: #fff;
  border: 1px solid #e7e5e4;
  border-radius: 8px;
}
.toolbar h3 {
  margin-bottom: 3px;
  font-size: 16px;
  color: #292524;
}
.toolbar span,
.panel-header p {
  font-size: 12px;
  color: #78716c;
}
.sync-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #059669;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.toolbar-actions { display:flex; align-items:center; gap:12px; }
.report-btn { height:30px; padding:0 12px; border:0; border-radius:6px; background:#f97316; color:#fff; font-size:12px; font-weight:700; cursor:pointer; }
.report-btn:hover { background:#ea580c; }
.sync-status i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 4px rgba(5, 150, 105, 0.1);
}
.error-banner {
  margin-bottom: 14px;
  padding: 10px 14px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #b91c1c;
  background: #fef2f2;
  font-size: 13px;
}
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.overview-grid {
  display: grid;
  grid-template-columns: minmax(520px, 1.45fr) minmax(330px, 0.8fr);
  gap: 14px;
  margin-bottom: 16px;
}
.sankey-row { margin-bottom: 16px; }
.threat-profile,
.panel {
  overflow: hidden;
  background: #fff;
  border: 1px solid #e7e5e4;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.035);
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid #f5f5f4;
}
.panel-header.compact {
  align-items: flex-start;
}
.panel-title {
  font-size: 14px;
  color: #292524;
  font-weight: 700;
}
.panel-header p {
  margin-top: 3px;
}
.risk-level,
.disposition {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}
.risk-level.high,
.disposition.pending {
  color: #b91c1c;
  background: #fef2f2;
}
.risk-level.medium,
.disposition.review {
  color: #b45309;
  background: #fffbeb;
}
.risk-level.low {
  color: #047857;
  background: #f0fdf4;
}
.disposition { border:0; cursor:pointer; font-family:inherit; }
.disposition.resolved { color:#047857; background:#f0fdf4; }
.profile-score {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 18px;
}
.score-ring {
  --score: 0;
  --score-color: #059669;
  display: flex;
  flex: 0 0 94px;
  width: 94px;
  aspect-ratio: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background:
    radial-gradient(#fff 57%, transparent 58%),
    conic-gradient(var(--score-color) calc(var(--score) * 1%), #f1f5f9 0);
}
.score-ring strong {
  font-size: 25px;
  color: #292524;
  line-height: 1;
}
.score-ring span {
  margin-top: 4px;
  font-size: 10px;
  color: #78716c;
}
.profile-copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.profile-copy strong {
  font-size: 14px;
  color: #292524;
}
.profile-copy span {
  font-size: 12px;
  line-height: 1.55;
  color: #78716c;
}
.profile-list {
  padding: 0 18px 16px;
}
.profile-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-top: 1px solid #f5f5f4;
  font-size: 12px;
}
.profile-list span {
  color: #78716c;
}
.profile-list strong {
  color: #292524;
  text-align: right;
}
.mono {
  font-family: "SF Mono", "Fira Code", monospace;
}
.operations-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.ip-list,
.disposition-list {
  padding: 4px 18px 10px;
}
.ip-row,
.disposition-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 56px;
  border-bottom: 1px solid #f5f5f4;
}
.ip-row:last-child,
.disposition-row:last-child {
  border-bottom: 0;
}
.rank {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border-radius: 4px;
  background: #f5f5f4;
  color: #78716c;
  font-size: 11px;
  font-weight: 700;
}
.ip-main,
.alert-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}
.ip-main strong,
.alert-main strong {
  overflow: hidden;
  color: #292524;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ip-main span,
.alert-main span {
  overflow: hidden;
  color: #78716c;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ip-risk {
  width: 78px;
  height: 5px;
  overflow: hidden;
  border-radius: 5px;
  background: #f1f5f9;
}
.ip-risk b {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #dc2626;
}
.ip-row em {
  width: 36px;
  color: #78716c;
  font-size: 11px;
  font-style: normal;
  text-align: right;
  white-space: nowrap;
}
.severity-dot {
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d97706;
}
.severity-dot.high {
  background: #dc2626;
  box-shadow: 0 0 0 4px rgba(220, 38, 38, 0.09);
}
.empty-cell {
  padding: 28px 0;
  color: #a8a29e;
  font-size: 13px;
  text-align: center;
}
.clean-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 120px);
}
.clean-card {
  max-width: 460px;
  padding: 42px 30px;
  border: 1px solid #e7e5e4;
  border-radius: 8px;
  background: #fff;
  text-align: center;
}
.clean-card h3 {
  margin-bottom: 8px;
  font-size: 18px;
  color: #292524;
}
.clean-card p {
  color: #78716c;
  font-size: 14px;
  line-height: 1.7;
}
@media (max-width: 1200px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .overview-grid,
  .operations-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .stats-row {
    grid-template-columns: 1fr;
  }
  .toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
  .profile-score {
    align-items: flex-start;
  }
  .ip-risk {
    display: none;
  }
}
</style>
