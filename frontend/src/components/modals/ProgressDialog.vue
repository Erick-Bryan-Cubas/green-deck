<!-- frontend/src/components/modals/ProgressDialog.vue -->
<script setup>
import Dialog from 'primevue/dialog'
import ProgressBar from 'primevue/progressbar'

defineProps({
  visible: Boolean,
  title: {
    type: String,
    default: 'Processing...'
  },
  value: {
    type: Number,
    default: 0
  },
  stage: {
    type: String,
    default: ''
  },
  icon: {
    type: String,
    default: ''
  },
  details: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:visible'])
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    :header="title"
    modal
    :closable="false"
    class="modern-dialog progress-dialog"
    style="width: min(560px, 95vw);"
  >
    <div class="progress-content">
      <ProgressBar :value="value" :showValue="false" style="height: 8px;" />

      <div class="progress-info mt-3">
        <div class="progress-stage" v-if="stage">
          <i v-if="icon" :class="icon" class="progress-stage-icon"></i>
          {{ stage }}
        </div>
        <div class="progress-percent">{{ value }}%</div>
      </div>

      <!-- Pipeline summary -->
      <div class="progress-pipeline mt-3" v-if="Object.keys(details).length > 0">
        <div class="pipeline-stats">
          <div v-if="details.parsed" class="stat-item">
            <span class="stat-label">Parseados:</span>
            <span class="stat-value">{{ details.parsed }} cards</span>
          </div>
          <div v-if="details.srcKept !== undefined" class="stat-item">
            <span class="stat-label">Validação SRC:</span>
            <span class="stat-value success"><i class="pi pi-check"></i> {{ details.srcKept }}</span>
            <span class="stat-value danger" v-if="details.srcDropped"><i class="pi pi-times"></i> {{ details.srcDropped }}</span>
          </div>
          <div v-if="details.relevanceKept !== undefined" class="stat-item">
            <span class="stat-label">Relevância:</span>
            <span class="stat-value success"><i class="pi pi-check"></i> {{ details.relevanceKept }}</span>
            <span class="stat-value danger" v-if="details.relevanceDropped"><i class="pi pi-times"></i> {{ details.relevanceDropped }}</span>
          </div>
          <div v-if="details.totalCards" class="stat-item total">
            <span class="stat-label">Total Final:</span>
            <span class="stat-value">{{ details.totalCards }} cards</span>
          </div>
        </div>
      </div>
    </div>
  </Dialog>
</template>

<style scoped>
.progress-content {
  padding: 0.5rem 0;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.progress-stage {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.9rem;
}

.progress-stage-icon {
  color: var(--p-primary-color);
}

.progress-percent {
  font-weight: 600;
  color: var(--p-primary-color);
}

.progress-pipeline {
  padding: 12px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.pipeline-stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
}

.stat-item.total {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
  font-weight: 600;
}

.stat-label {
  color: rgba(148, 163, 184, 0.8);
  min-width: 100px;
}

.stat-value {
  color: rgba(255, 255, 255, 0.9);
}

.stat-value.success {
  color: #10b981;
}

.stat-value.danger {
  color: #ef4444;
}

.stat-value i {
  font-size: 0.75rem;
  margin-right: 2px;
}
</style>
