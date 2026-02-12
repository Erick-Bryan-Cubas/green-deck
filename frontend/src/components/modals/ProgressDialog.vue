<!-- frontend/src/components/modals/ProgressDialog.vue -->
<script setup>
import Dialog from 'primevue/dialog'
import ProgressBar from 'primevue/progressbar'
import Button from 'primevue/button'

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
  },
  cancellable: {
    type: Boolean,
    default: false
  },
  canceling: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'cancel'])
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
      <div class="extraction-progress-main">
        <ProgressBar
          :value="value"
          :showValue="false"
          class="extraction-bar"
        />

        <div class="extraction-stats">
          <span class="extraction-pages">{{ stage || title }}</span>
          <span class="extraction-percent">{{ value }}%</span>
        </div>
      </div>

      <div class="progress-info mt-3">
        <Button
          v-if="cancellable"
          :label="canceling ? 'Cancelando...' : 'Cancelar'"
          icon="pi pi-times"
          class="cancel-extraction-btn"
          :disabled="canceling"
          @click="emit('cancel')"
        />
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

.extraction-progress-main {
  width: 100%;
}

.extraction-bar {
  height: 14px;
  border-radius: 7px;
  overflow: hidden;
}

.extraction-bar :deep(.p-progressbar) {
  background: var(--surface-200);
  height: 14px;
  border-radius: 7px;
}

.extraction-bar :deep(.p-progressbar-value) {
  background: linear-gradient(
    90deg,
    #16a34a 0%,
    #22c55e 50%,
    #16a34a 100%
  );
  background-size: 200% 100%;
  animation: extraction-shimmer 1.5s ease-in-out infinite;
  border-radius: 7px;
}

@keyframes extraction-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

.extraction-stats {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.4rem;
  font-size: 0.8rem;
}

.extraction-pages {
  color: var(--text-color-secondary);
}

.extraction-percent {
  font-weight: 600;
  color: var(--green-600);
}

.progress-info {
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.cancel-extraction-btn {
  background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 50%, #c084fc 100%) !important;
  border: none !important;
  color: white !important;
  font-weight: 600;
  transition: all 0.2s ease;
}

.cancel-extraction-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #7c3aed 0%, #9333ea 50%, #a855f7 100%) !important;
  transform: translateY(-1px);
}

.cancel-extraction-btn:active:not(:disabled) {
  transform: translateY(0);
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
