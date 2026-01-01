<!-- frontend/src/components/LazyChart.vue -->
<!-- Lazy-loaded wrapper for PrimeVue Chart to improve initial page load -->
<script setup>
import { defineAsyncComponent, computed } from 'vue'
import Skeleton from 'primevue/skeleton'

const props = defineProps({
  type: {
    type: String,
    required: true
  },
  data: {
    type: Object,
    default: () => ({})
  },
  options: {
    type: Object,
    default: () => ({})
  },
  width: {
    type: String,
    default: undefined
  },
  height: {
    type: String,
    default: undefined
  },
  class: {
    type: String,
    default: ''
  }
})

// Lazy load PrimeVue Chart component
const Chart = defineAsyncComponent({
  loader: () => import('primevue/chart'),
  loadingComponent: {
    components: { Skeleton },
    props: ['height'],
    template: `
      <div class="chart-loading" :style="{ height: height || '200px' }">
        <Skeleton width="100%" height="100%" borderRadius="14px" />
      </div>
    `
  },
  delay: 50,
  timeout: 30000
})

const chartStyle = computed(() => {
  const style = {}
  if (props.width) style.width = props.width
  if (props.height) style.height = props.height
  return style
})
</script>

<template>
  <Chart
    :type="type"
    :data="data"
    :options="options"
    :style="chartStyle"
    :class="props.class"
  />
</template>

<style scoped>
.chart-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 14px;
}
</style>
