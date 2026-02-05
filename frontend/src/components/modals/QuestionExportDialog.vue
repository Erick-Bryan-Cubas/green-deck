<!-- frontend/src/components/modals/QuestionExportDialog.vue -->
<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Select from 'primevue/select'
import AutoComplete from 'primevue/autocomplete'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import ProgressBar from 'primevue/progressbar'

const props = defineProps({
  visible: Boolean,
  questions: {
    type: Array,
    default: () => []
  },
  ankiDecks: {
    type: Array,
    default: () => []
  },
  allTags: {
    type: Array,
    default: () => []
  },
  exporting: Boolean,
  allInOneStatus: {
    type: Object,
    default: () => ({ hasModel: false, checking: true })
  }
})

const emit = defineEmits([
  'update:visible',
  'export',
  'checkModel'
])

// Local state
const selectedDeck = ref('')
const selectedTags = ref([])
const tagSuggestions = ref([])

// Computed
const deckOptions = computed(() => {
  const base = [{ label: "Usar deck da questão", value: '' }]
  if (!props.ankiDecks?.length) return base
  return base.concat(props.ankiDecks.map(d => ({ label: d, value: d })))
})

const questionsCount = computed(() => props.questions.length)

const typeCounts = computed(() => {
  const counts = { kprim: 0, mc: 0, sc: 0 }
  for (const q of props.questions) {
    if (q.qtype === 0) counts.kprim++
    else if (q.qtype === 1) counts.mc++
    else counts.sc++
  }
  return counts
})

const canExport = computed(() => {
  return props.allInOneStatus?.hasModel && questionsCount.value > 0 && !props.exporting
})

// Methods
function searchTags(event) {
  const query = (event.query || '').toLowerCase().trim()
  if (!query) {
    tagSuggestions.value = [...props.allTags]
  } else {
    tagSuggestions.value = props.allTags.filter(
      tag => tag.toLowerCase().includes(query)
    )
  }
}

function close() {
  emit('update:visible', false)
}

function exportQuestions() {
  emit('export', {
    questions: props.questions,
    deckName: selectedDeck.value || null,
    tags: selectedTags.value.join(',')
  })
}

// Watch for modal open
watch(() => props.visible, (visible) => {
  if (visible) {
    selectedDeck.value = ''
    selectedTags.value = []
    // Check if AllInOne model is available
    emit('checkModel')
  }
})
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    header="Exportar Questões para Anki"
    modal
    class="modern-dialog"
    style="width: min(680px, 96vw);"
  >
    <div class="export-content">
      <!-- AllInOne Model Status -->
      <div class="model-status-section">
        <div v-if="allInOneStatus.checking" class="checking-status">
          <i class="pi pi-spin pi-spinner mr-2" />
          <span>Verificando modelo AllInOne...</span>
        </div>

        <Message v-else-if="!allInOneStatus.hasModel" severity="warn" :closable="false">
          <div class="flex flex-column gap-2">
            <div class="flex align-items-center gap-2">
              <i class="pi pi-exclamation-triangle" />
              <strong>Modelo "AllInOne (kprim, mc, sc)" não encontrado</strong>
            </div>
            <p class="m-0 text-sm">
              Instale a extensão Multiple Choice for Anki para usar este tipo de nota.
            </p>
            <a
              href="https://ankiweb.net/shared/info/1566095810"
              target="_blank"
              class="text-primary text-sm"
            >
              <i class="pi pi-external-link mr-1" />
              Baixar extensão
            </a>
          </div>
        </Message>

        <Message v-else severity="success" :closable="false">
          <div class="flex align-items-center gap-2">
            <i class="pi pi-check-circle" />
            <span>Modelo AllInOne disponível</span>
          </div>
        </Message>
      </div>

      <!-- Summary -->
      <div class="summary-section">
        <div class="summary-header">
          <span class="summary-count">{{ questionsCount }} questões</span>
          <span class="summary-label">serão exportadas</span>
        </div>
        <div class="type-breakdown">
          <Tag v-if="typeCounts.kprim > 0" severity="info" class="pill">
            {{ typeCounts.kprim }} Kprim
          </Tag>
          <Tag v-if="typeCounts.mc > 0" severity="success" class="pill">
            {{ typeCounts.mc }} MC
          </Tag>
          <Tag v-if="typeCounts.sc > 0" severity="warning" class="pill">
            {{ typeCounts.sc }} SC
          </Tag>
        </div>
      </div>

      <!-- Field Mapping Info -->
      <div class="mapping-section">
        <div class="mapping-header">
          <i class="pi pi-arrows-h" />
          <span>Mapeamento de Campos</span>
        </div>
        <div class="mapping-grid">
          <div class="mapping-row">
            <span class="field-from">question</span>
            <i class="pi pi-arrow-right" />
            <span class="field-to">Question</span>
          </div>
          <div class="mapping-row">
            <span class="field-from">qtype</span>
            <i class="pi pi-arrow-right" />
            <span class="field-to">QType</span>
          </div>
          <div class="mapping-row">
            <span class="field-from">options</span>
            <i class="pi pi-arrow-right" />
            <span class="field-to">Q_1 - Q_5</span>
          </div>
          <div class="mapping-row">
            <span class="field-from">answers</span>
            <i class="pi pi-arrow-right" />
            <span class="field-to">Answers</span>
          </div>
          <div class="mapping-row">
            <span class="field-from">comment</span>
            <i class="pi pi-arrow-right" />
            <span class="field-to">Comment</span>
          </div>
        </div>
      </div>

      <!-- Deck Selection -->
      <div class="field-section">
        <label class="field-label">
          <i class="pi pi-folder" />
          Baralho
          <span class="optional">(opcional)</span>
        </label>
        <Select
          v-model="selectedDeck"
          :options="deckOptions"
          optionLabel="label"
          optionValue="value"
          class="w-full"
          filter
          placeholder="Selecione um baralho"
          :disabled="!allInOneStatus.hasModel"
        />
      </div>

      <!-- Tags -->
      <div class="field-section">
        <label class="field-label">
          <i class="pi pi-tags" />
          Tags
        </label>
        <AutoComplete
          v-model="selectedTags"
          :suggestions="tagSuggestions"
          @complete="searchTags"
          multiple
          :completeOnFocus="true"
          class="w-full"
          placeholder="Selecione ou digite tags"
          :disabled="!allInOneStatus.hasModel"
        />
        <small class="field-hint">
          Selecione tags existentes ou digite para criar novas
        </small>
      </div>
    </div>

    <template #footer>
      <Button label="Cancelar" severity="secondary" outlined @click="close" />
      <Button
        label="Exportar para Anki"
        icon="pi pi-send"
        :loading="exporting"
        :disabled="!canExport"
        @click="exportQuestions"
      />
    </template>
  </Dialog>
</template>

<style scoped>
.export-content {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.model-status-section {
  margin-bottom: 0.5rem;
}

.checking-status {
  display: flex;
  align-items: center;
  padding: 12px;
  background: rgba(99, 102, 241, 0.08);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.7);
}

.summary-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: rgba(99, 102, 241, 0.08);
  border-radius: 10px;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.summary-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.summary-count {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--p-primary-color);
}

.summary-label {
  font-size: 0.9rem;
  color: rgba(148, 163, 184, 0.8);
}

.type-breakdown {
  display: flex;
  gap: 6px;
}

.mapping-section {
  padding: 14px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.mapping-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.8);
}

.mapping-header i {
  color: var(--p-primary-color);
}

.mapping-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mapping-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.8rem;
}

.field-from {
  min-width: 80px;
  color: rgba(148, 163, 184, 0.7);
  font-family: monospace;
}

.mapping-row i {
  color: rgba(99, 102, 241, 0.6);
  font-size: 0.7rem;
}

.field-to {
  color: rgba(255, 255, 255, 0.8);
  font-family: monospace;
}

.field-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.85);
}

.field-label i {
  color: var(--p-primary-color);
  font-size: 0.85rem;
}

.optional {
  font-weight: 400;
  font-size: 0.8rem;
  color: rgba(148, 163, 184, 0.7);
}

.field-hint {
  color: rgba(148, 163, 184, 0.7);
  font-size: 0.8rem;
}
</style>
