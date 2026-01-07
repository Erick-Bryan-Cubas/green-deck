<script setup>
import { computed } from 'vue'
import Button from 'primevue/button'
import Badge from 'primevue/badge'
import ScrollPanel from 'primevue/scrollpanel'
import Skeleton from 'primevue/skeleton'
import ProgressBar from 'primevue/progressbar'

const props = defineProps({
  topics: { type: Array, default: () => [] },
  segments: { type: Array, default: () => [] },
  isLoading: { type: Boolean, default: false },
  visible: { type: Boolean, default: false },
  progress: { type: Number, default: 0 },
  progressStage: { type: String, default: '' }
})

const emit = defineEmits(['navigate', 'clear', 'close'])

// Group segments by topic and sort by count
const groupedByTopic = computed(() => {
  return props.topics
    .map(t => ({
      ...t,
      segments: props.segments.filter(s => s.topic_id === t.id)
    }))
    .filter(t => t.segments.length > 0)
    .sort((a, b) => b.segments.length - a.segments.length)
})

const totalSegments = computed(() => props.segments.length)

function truncateText(text, maxLen = 45) {
  if (!text) return ''
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= maxLen) return clean
  return clean.substring(0, maxLen) + '...'
}
</script>

<template>
  <div v-if="visible" class="topic-legend">
    <div class="legend-header">
      <div class="legend-title">
        <i class="pi pi-palette"></i>
        <span>Tópicos</span>
        <Badge v-if="totalSegments > 0" :value="totalSegments" severity="secondary" />
      </div>
      <div class="legend-actions">
        <Button
          v-if="totalSegments > 0"
          icon="pi pi-eraser"
          text
          rounded
          size="small"
          @click="emit('clear')"
          v-tooltip.left="'Limpar marcações'"
        />
        <Button
          icon="pi pi-times"
          text
          rounded
          size="small"
          @click="emit('close')"
        />
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="isLoading" class="legend-loading">
      <ProgressBar :value="progress" :showValue="false" style="height: 4px" />
      <span class="loading-text">{{ progressStage || 'Analisando tópicos...' }}</span>
      <Skeleton height="40px" class="mt-2" />
      <Skeleton height="40px" class="mt-2" />
      <Skeleton height="40px" class="mt-2" />
    </div>

    <!-- Content -->
    <ScrollPanel v-else class="legend-body">
      <div v-for="topic in groupedByTopic" :key="topic.id" class="topic-group">
        <div class="topic-header">
          <span class="topic-dot" :style="{ backgroundColor: topic.color }"></span>
          <span class="topic-name">{{ topic.name }}</span>
          <Badge :value="topic.segments.length" severity="secondary" />
        </div>
        <div class="topic-segments">
          <button
            v-for="(seg, i) in topic.segments"
            :key="i"
            class="segment-btn"
            @click="emit('navigate', seg)"
          >
            <span class="segment-indicator" :style="{ backgroundColor: topic.color }"></span>
            {{ truncateText(seg.text) }}
          </button>
        </div>
      </div>

      <div v-if="!groupedByTopic.length && !isLoading" class="empty-state">
        <i class="pi pi-info-circle"></i>
        <span>Nenhum tópico identificado</span>
      </div>
    </ScrollPanel>
  </div>
</template>

<style scoped>
.topic-legend {
  background: var(--p-surface-0);
  border: 1px solid var(--p-surface-200);
  border-radius: 8px;
  margin-top: 0.75rem;
  overflow: hidden;
  max-height: 350px;
  display: flex;
  flex-direction: column;
}

.legend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--p-surface-200);
  background: var(--p-surface-50);
}

.legend-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--p-surface-700);
}

.legend-title i {
  color: var(--p-primary-500);
}

.legend-actions {
  display: flex;
  gap: 0.25rem;
}

.legend-loading {
  padding: 0.75rem;
}

.loading-text {
  display: block;
  font-size: 0.75rem;
  color: var(--p-surface-500);
  margin-top: 0.5rem;
  text-align: center;
}

.legend-body {
  flex: 1;
  overflow: auto;
  max-height: 280px;
}

.topic-group {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--p-surface-100);
}

.topic-group:last-child {
  border-bottom: none;
}

.topic-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.375rem;
}

.topic-dot {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex-shrink: 0;
}

.topic-name {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--p-surface-700);
  flex: 1;
}

.topic-segments {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-left: 1.25rem;
}

.segment-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: var(--p-surface-50);
  border: 1px solid var(--p-surface-200);
  border-radius: 4px;
  padding: 0.375rem 0.5rem;
  font-size: 0.75rem;
  color: var(--p-surface-600);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
  width: 100%;
}

.segment-btn:hover {
  background: var(--p-surface-100);
  border-color: var(--p-primary-300);
  color: var(--p-surface-800);
}

.segment-indicator {
  width: 4px;
  height: 16px;
  border-radius: 2px;
  flex-shrink: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  color: var(--p-surface-400);
  font-size: 0.875rem;
  gap: 0.5rem;
}

.empty-state i {
  font-size: 1.25rem;
}
</style>
