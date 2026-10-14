<template>
  <div class="table-panel">
    <div class="panel-header">
      <h3 class="panel-title">{{ title }}</h3>
    </div>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="col in columns" :key="col.key" :style="col.width ? { width: col.width } : {}">{{ col.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in data" :key="i">
            <td v-for="col in columns" :key="col.key">
              <span v-if="col.key === 'severity'" class="severity-tag" :class="'sev-' + row.severity">
                {{ row.severity === 'high' ? '高危' : row.severity === 'false_positive' ? '误报' : '低危' }}
              </span>
              <span v-else-if="col.key === 'type'" class="type-badge">{{ row.type }}</span>
              <span v-else>{{ row[col.key] }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
defineProps({ title: String, columns: Array, data: Array })
</script>

<style scoped>
.table-panel {
  background: #fff;
  border: 1px solid #e7e5e4;
  border-radius: 8px;
  overflow: hidden;
}
.panel-header {
  padding: 14px 18px;
  border-bottom: 1px solid #f5f5f4;
}
.panel-title { font-size: 13px; font-weight: 600; color: #292524; }
.table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th {
  text-align: left; padding: 9px 18px;
  font-weight: 500; color: #a8a29e;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em;
  border-bottom: 1px solid #f5f5f4;
}
.data-table td {
  padding: 10px 18px;
  color: #44403c;
  border-bottom: 1px solid #fafaf9;
}
.data-table tbody tr:hover { background: #fafaf9; }

.severity-tag {
  display: inline-block; padding: 1px 8px; border-radius: 10px;
  font-size: 12px; font-weight: 500;
}
.sev-high { color: #ef4444; background: rgba(239,68,68,0.08); }
.sev-false_positive { color: #f59e0b; background: rgba(245,158,11,0.08); }
.sev-low { color: #f97316; background: rgba(249,115,22,0.08); }

.type-badge {
  display: inline-block; padding: 1px 8px; border-radius: 4px;
  font-size: 12px; font-weight: 500;
  background: #f5f5f4; color: #44403c;
  font-family: 'SF Mono', 'Fira Code', monospace;
}
</style>
