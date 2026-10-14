<template>
  <div class="stat-card">
    <div class="stat-header">
      <span class="stat-icon"><slot name="icon"></slot></span>
      <span class="stat-label">{{ label }}</span>
    </div>
    <div class="stat-value">
      <span class="stat-number">{{ value }}</span>
      <span class="stat-unit">{{ unit }}</span>
    </div>
    <div class="stat-footer">
      <span class="stat-change" :class="trendClass">
        <svg v-if="trend > 0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="18 15 12 9 6 15"/></svg>
        <svg v-else-if="trend < 0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="6" y1="12" x2="18" y2="12"/></svg>
        {{ Math.abs(trend) }}%
      </span>
      <span class="stat-desc">{{ desc }}</span>
    </div>
    <slot name="extra"></slot>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: String, value: [String, Number], unit: { type: String, default: '' },
  trend: { type: Number, default: 0 }, desc: String,
})

const trendClass = computed(() => {
  if (props.trend > 0) return 'up'
  if (props.trend < 0) return 'down'
  return 'flat'
})
</script>

<style scoped>
.stat-card {
  background: #fff;
  border: 1px solid #e7e5e4;
  border-radius: 8px;
  padding: 18px 20px;
  transition: box-shadow 0.15s;
}
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.04); }

.stat-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.stat-icon {
  width: 32px; height: 32px;
  border-radius: 6px;
  background: rgba(249,115,22,0.08);
  color: #f97316;
  display: flex;
  align-items: center;
  justify-content: center;
}
.stat-icon :deep(svg) { width: 16px; height: 16px; }
.stat-label { font-size: 13px; color: #78716c; font-weight: 500; }

.stat-value { display: flex; align-items: baseline; gap: 4px; margin-bottom: 6px; }
.stat-number { font-size: 26px; font-weight: 700; color: #292524; letter-spacing: -0.02em; }
.stat-unit { font-size: 12px; color: #a8a29e; }

.stat-footer { display: flex; align-items: center; gap: 4px; }
.stat-change {
  display: inline-flex; align-items: center; gap: 2px;
  font-size: 12px; font-weight: 600;
  padding: 1px 6px; border-radius: 4px;
}
.stat-change svg { width: 12px; height: 12px; }
.stat-change.up { color: #16a34a; background: rgba(22,163,74,0.08); }
.stat-change.down { color: #ef4444; background: rgba(239,68,68,0.08); }
.stat-change.flat { color: #64748b; background: rgba(100,116,139,0.08); }
.stat-desc { font-size: 12px; color: #a8a29e; margin-left: 2px; }
</style>
