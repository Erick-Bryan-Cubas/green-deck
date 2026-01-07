<!-- frontend/src/components/LazyChart.vue -->
<!-- Lazy-loaded wrapper for PrimeVue Chart with IntersectionObserver optimization -->
<script setup>
import { defineAsyncComponent, computed, ref, onMounted, onUnmounted } from 'vue'
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

// Track visibility
const containerRef = ref(null)
const isVisible = ref(false)
const hasBeenVisible = ref(false)
let observer = null

// Lazy load PrimeVue Chart component
const Chart = defineAsyncComponent({
  loader: () => import('primevue/chart'),
  delay: 50,
  timeout: 30000
})

const chartStyle = computed(() => {
  const style = {}
  if (props.width) style.width = props.width
  if (props.height) style.height = props.height
  return style
})

onMounted(() => {
  // Use IntersectionObserver to detect when chart enters viewport
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && !hasBeenVisible.value) {
          isVisible.value = true
          hasBeenVisible.value = true
          // Once visible, disconnect observer - chart stays loaded
          observer?.disconnect()
        }
      })
    },
    {
      root: null,
      rootMargin: '50px', // Start loading slightly before it's visible
      threshold: 0.1
    }
  )

  if (containerRef.value) {
    observer.observe(containerRef.value)
  }
})

onUnmounted(() => {
  observer?.disconnect()
})
</script>

<template>
  <div ref="containerRef" class="lazy-chart-container" :style="chartStyle">
    <!-- Show skeleton until visible -->
    <div v-if="!isVisible" class="chart-loading">
      <Skeleton width="100%" height="100%" borderRadius="14px" />
    </div>

    <!-- Load chart only when visible -->
    <Suspense v-else>
      <template #default>
        <Chart
          :type="type"
          :data="data"
          :options="options"
          :style="chartStyle"
          :class="props.class"
        />
      </template>
      <template #fallback>
        <div class="chart-loading">
          <Skeleton width="100%" height="100%" borderRadius="14px" />
        </div>
      </template>
    </Suspense>
  </div>
</template>

<style scoped>
.lazy-chart-container {
  position: relative;
  min-height: 200px;
}

.chart-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 14px;
}
</style>
