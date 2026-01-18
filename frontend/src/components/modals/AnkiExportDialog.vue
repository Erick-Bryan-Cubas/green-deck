<!-- frontend/src/components/modals/AnkiExportDialog.vue -->
<script setup>
import { ref, computed, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Select from 'primevue/select'
import AutoComplete from 'primevue/autocomplete'

const props = defineProps({
  visible: Boolean,
  ankiModelsData: Object,
  exporting: Boolean,
  allTags: {
    type: Array,
    default: () => []
  },
  // Initial values (from saved preferences)
  initialModel: String,
  initialDeck: String,
  initialTags: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits([
  'update:visible',
  'export'
])

// Local state
const ankiModel = ref('')
const ankiFrontField = ref('')
const ankiBackField = ref('')
const ankiDeckField = ref('')
const ankiTags = ref([])
const ankiTagSuggestions = ref([])

// Initialize local state when props change
watch(() => props.visible, (visible) => {
  if (visible) {
    ankiModel.value = props.initialModel || ''
    ankiDeckField.value = props.initialDeck || ''
    ankiTags.value = [...(props.initialTags || [])]
  }
}, { immediate: true })

// Update fields when model changes
watch(ankiModel, () => {
  const fields = ankiFieldOptions.value
  ankiFrontField.value = fields[0]?.value || ''
  ankiBackField.value = fields[1]?.value || fields[0]?.value || ''
})

// Computed options
const ankiModelOptions = computed(() => {
  const d = props.ankiModelsData
  if (!d?.models) return []
  return Object.keys(d.models).map((m) => ({ label: m, value: m }))
})

const ankiDeckOptions = computed(() => {
  const d = props.ankiModelsData
  const base = [{ label: "Use card's deck", value: '' }]
  if (!d?.decks) return base
  return base.concat(d.decks.map((x) => ({ label: x, value: x })))
})

const ankiFieldOptions = computed(() => {
  const d = props.ankiModelsData
  if (!d?.models || !ankiModel.value) return []
  return (d.models[ankiModel.value] || []).map((f) => ({ label: f, value: f }))
})

// Tag autocomplete
function searchAnkiTags(event) {
  const query = (event.query || '').toLowerCase().trim()
  if (!query) {
    ankiTagSuggestions.value = [...props.allTags]
  } else {
    ankiTagSuggestions.value = props.allTags.filter(
      tag => tag.toLowerCase().includes(query)
    )
  }
}

// Actions
function close() {
  emit('update:visible', false)
}

function exportCards() {
  emit('export', {
    model: ankiModel.value,
    frontField: ankiFrontField.value,
    backField: ankiBackField.value,
    deck: ankiDeckField.value,
    tags: ankiTags.value
  })
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    header="Exportar para Anki"
    modal
    class="modern-dialog"
    style="width: min(760px, 96vw);"
  >
    <div class="anki-export-content">
      <div class="anki-export-section">
        <label class="anki-export-label">
          <i class="pi pi-file"></i>
          Tipo de Nota (Modelo)
        </label>
        <Select
          v-model="ankiModel"
          :options="ankiModelOptions"
          optionLabel="label"
          optionValue="value"
          class="w-full"
          filter
          placeholder="Selecione um modelo"
        />
      </div>

      <div class="anki-export-row">
        <div class="anki-export-section">
          <label class="anki-export-label">
            <i class="pi pi-arrow-right"></i>
            Campo Frente
          </label>
          <Select
            v-model="ankiFrontField"
            :options="ankiFieldOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
            placeholder="Selecione o campo"
          />
        </div>

        <div class="anki-export-section">
          <label class="anki-export-label">
            <i class="pi pi-arrow-left"></i>
            Campo Verso
          </label>
          <Select
            v-model="ankiBackField"
            :options="ankiFieldOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
            placeholder="Selecione o campo"
          />
        </div>
      </div>

      <div class="anki-export-section">
        <label class="anki-export-label">
          <i class="pi pi-folder"></i>
          Baralho
          <span class="anki-export-optional">(opcional)</span>
        </label>
        <Select
          v-model="ankiDeckField"
          :options="ankiDeckOptions"
          optionLabel="label"
          optionValue="value"
          class="w-full"
          filter
          placeholder="Selecione um baralho"
        />
      </div>

      <div class="anki-export-section">
        <label class="anki-export-label">
          <i class="pi pi-tags"></i>
          Tags
        </label>
        <AutoComplete
          v-model="ankiTags"
          :suggestions="ankiTagSuggestions"
          @complete="searchAnkiTags"
          multiple
          :completeOnFocus="true"
          class="w-full"
          placeholder="Selecione ou digite novas tags"
        />
        <small class="anki-export-hint">Selecione tags existentes ou digite para criar novas</small>
      </div>
    </div>

    <template #footer>
      <Button label="Cancelar" severity="secondary" outlined @click="close" />
      <Button label="Exportar para Anki" icon="pi pi-send" :loading="exporting" @click="exportCards" />
    </template>
  </Dialog>
</template>

<style scoped>
.anki-export-content {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.anki-export-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.anki-export-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.85);
}

.anki-export-label i {
  color: var(--p-primary-color);
  font-size: 0.85rem;
}

.anki-export-optional {
  font-weight: 400;
  font-size: 0.8rem;
  color: rgba(148, 163, 184, 0.7);
}

.anki-export-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 600px) {
  .anki-export-row {
    grid-template-columns: 1fr;
  }
}

.anki-export-hint {
  color: rgba(148, 163, 184, 0.7);
  font-size: 0.8rem;
}
</style>
