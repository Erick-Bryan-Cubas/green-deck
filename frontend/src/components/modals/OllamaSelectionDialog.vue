<!-- frontend/src/components/modals/OllamaSelectionDialog.vue -->
<script setup>
import Dialog from 'primevue/dialog'

const props = defineProps({
  visible: Boolean,
  models: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits([
  'update:visible',
  'select'
])

// Format model size from bytes to human-readable
function formatModelSize(bytes) {
  if (!bytes) return ''
  const gb = bytes / (1024 * 1024 * 1024)
  if (gb >= 1) return `${gb.toFixed(1)} GB`
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(0)} MB`
}

function selectModel(modelName) {
  emit('select', modelName)
  emit('update:visible', false)
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    modal
    :closable="false"
    class="ollama-selection-dialog"
    :style="{ width: 'min(500px, 96vw)' }"
  >
    <template #header>
      <div class="flex align-items-center gap-3 w-full">
        <div
          class="flex align-items-center justify-content-center border-round-lg flex-shrink-0"
          style="width: 2.5rem; height: 2.5rem; background: linear-gradient(135deg, #10b981, #059669)"
        >
          <i class="pi pi-server text-white" style="font-size: 1.2rem" />
        </div>
        <span class="font-semibold" style="color: #f1f5f9">Selecione um Modelo</span>
      </div>
    </template>

    <div class="flex flex-column gap-3">
      <p class="m-0 mb-2" style="color: rgba(148, 163, 184, 0.9)">
        Detectamos multiplos modelos no Ollama.<br />
        Selecione qual deseja usar para geracao de flashcards:
      </p>

      <div
        v-for="model in models"
        :key="model.name"
        class="ollama-model-item flex align-items-center justify-content-between p-3 border-round-lg cursor-pointer transition-all transition-duration-200"
        style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(148, 163, 184, 0.1)"
        @click="selectModel(model.name)"
      >
        <div>
          <span class="font-semibold" style="color: #f1f5f9">{{ model.name }}</span>
          <div class="text-sm mt-1" style="color: rgba(148, 163, 184, 0.7)">
            <span v-if="model.size">{{ formatModelSize(model.size) }}</span>
            <span v-if="model.parameter_size"> · {{ model.parameter_size }}</span>
            <span v-if="model.family"> · {{ model.family }}</span>
          </div>
        </div>
        <i class="pi pi-chevron-right" style="color: rgba(148, 163, 184, 0.5)" />
      </div>

      <div v-if="models.length === 0" class="text-center p-4" style="color: rgba(148, 163, 184, 0.7)">
        <i class="pi pi-exclamation-circle text-xl mb-2" />
        <p class="m-0">Nenhum modelo LLM encontrado no Ollama.</p>
      </div>
    </div>
  </Dialog>
</template>

<style scoped>
.ollama-model-item:hover {
  background: rgba(15, 23, 42, 0.8) !important;
  border-color: rgba(16, 185, 129, 0.3) !important;
}

:deep(.ollama-selection-dialog) {
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.98) 0%, rgba(10, 10, 14, 0.99) 100%);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 20px;
  box-shadow:
    0 25px 50px -12px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(255, 255, 255, 0.05) inset;
}

:deep(.ollama-selection-dialog .p-dialog-header) {
  background: transparent;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
  padding: 1.25rem 1.5rem;
}

:deep(.ollama-selection-dialog .p-dialog-content) {
  background: transparent;
  padding: 1.5rem;
}
</style>
