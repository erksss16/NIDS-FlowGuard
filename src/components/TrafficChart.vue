<template>
  <div class="chart-panel">
    <div class="panel-header">
      <div class="title-wrap">
        <h3 class="panel-title">{{ title }}</h3>
        <button
          v-if="description"
          class="info-btn"
          type="button"
          aria-label="查看图表说明"
          @click="showDescription = !showDescription"
        >
          i
        </button>
      </div>
      <span class="panel-badge" v-if="live"><span class="live-dot"></span> 实时</span>
    </div>
    <div v-if="description && showDescription" class="chart-description">
      {{ description }}
    </div>
    <div ref="chartRef" class="chart-body"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  title: String,
  description: { type: String, default: '' },
  live: { type: Boolean, default: false },
  option: { type: Object, required: true },
})

const chartRef = ref(null)
const showDescription = ref(false)
let chart = null
let resizeObserver = null

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  chart.setOption({
    backgroundColor: 'transparent',
    textStyle: { color: '#6b6662' },
    ...props.option,
  })
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartRef.value)
}

onMounted(() => nextTick(initChart))

watch(() => props.option, (opt) => {
  if (chart) chart.setOption(opt, true)
}, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<style scoped>
.chart-panel {
  background: linear-gradient(135deg, #fff 0%, #fafaf9 100%);
  border: 1px solid #e6e4df;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.3s ease;
}
.chart-panel:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 16px 20px 0;
}
.title-wrap {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 7px;
}
.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #1a1816;
  letter-spacing: 0.3px;
}
.info-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  border: 1px solid #d6d3d1;
  border-radius: 50%;
  background: #fff;
  color: #78716c;
  font-size: 12px;
  line-height: 1;
  font-weight: 800;
  cursor: pointer;
  transition: all 0.15s ease;
}
.info-btn:hover {
  border-color: #f6821f;
  color: #f6821f;
  background: #fff4e6;
}
.chart-description {
  margin: 10px 20px 0;
  padding: 9px 11px;
  border: 1px solid #e7e5e4;
  border-radius: 6px;
  background: #fff;
  color: #57534e;
  font-size: 12px;
  line-height: 1.6;
}
.panel-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #059669;
  background: linear-gradient(135deg, rgba(5,150,105,0.1) 0%, rgba(5,150,105,0.05) 100%);
  padding: 3px 10px;
  border-radius: 12px;
  font-weight: 600;
  border: 1px solid rgba(5,150,105,0.2);
}
.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #059669;
  box-shadow: 0 0 8px rgba(5,150,105,0.6);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.4;
    transform: scale(0.8);
  }
}
.chart-body {
  width: 100%;
  height: 320px;
}
</style>
