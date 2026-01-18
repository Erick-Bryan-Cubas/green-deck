<!-- frontend/src/components/modals/ModelSelectionDialog.vue -->
<script setup>
import { ref, computed, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Divider from 'primevue/divider'

const props = defineProps({
  visible: Boolean,
  availableModels: {
    type: Array,
    default: () => []
  },
  selectedModel: String,
  selectedValidationModel: String,
  selectedAnalysisModel: String,
  isLoadingModels: Boolean
})

const emit = defineEmits([
  'update:visible',
  'update:selectedModel',
  'update:selectedValidationModel',
  'update:selectedAnalysisModel',
  'save',
  'refresh'
])

// Local state for editing
const localSelectedModel = ref(props.selectedModel)
const localValidationModel = ref(props.selectedValidationModel)
const localAnalysisModel = ref(props.selectedAnalysisModel)

// Sync local state with props
watch(() => props.selectedModel, (val) => { localSelectedModel.value = val })
watch(() => props.selectedValidationModel, (val) => { localValidationModel.value = val })
watch(() => props.selectedAnalysisModel, (val) => { localAnalysisModel.value = val })

// Reset local state when modal opens
watch(() => props.visible, (visible) => {
  if (visible) {
    localSelectedModel.value = props.selectedModel
    localValidationModel.value = props.selectedValidationModel
    localAnalysisModel.value = props.selectedAnalysisModel
  }
})

// Computed: filtered model lists
const llmModels = computed(() => props.availableModels.filter(m => m.type !== 'embedding'))

// Helper functions
function getProviderSeverity(provider) {
  if (provider === 'ollama') return 'success'
  if (provider === 'openai') return 'info'
  return 'warning'
}

function getProviderLabel(provider) {
  if (provider === 'ollama') return 'Ollama'
  if (provider === 'openai') return 'OpenAI'
  return 'Perplexity'
}

function getTypeSeverity(type) {
  return type === 'embedding' ? 'secondary' : 'contrast'
}

function getTypeLabel(type) {
  return type === 'embedding' ? 'Embedding' : 'LLM'
}

function getModelInfo(modelName) {
  return props.availableModels.find(m => m.name === modelName)
}

// Actions
function close() {
  emit('update:visible', false)
}

function save() {
  emit('update:selectedModel', localSelectedModel.value)
  emit('update:selectedValidationModel', localValidationModel.value)
  emit('update:selectedAnalysisModel', localAnalysisModel.value)
  emit('save')
  close()
}

function refresh() {
  emit('refresh')
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    header="Configurar Modelos"
    modal
    class="modern-dialog"
    style="width: min(860px, 96vw);"
  >
    <div class="model-info">
      <i class="pi pi-info-circle mr-2" />
      Configure os modelos para cada etapa do pipeline. Modelos Ollama são locais (privacidade total). Modelos de API requerem chaves configuradas.
    </div>

    <div class="grid mt-3">
      <!-- Modelo de Geração -->
      <div class="col-12 md:col-6">
        <label class="font-semibold"><i class="pi pi-sparkles mr-2" />Modelo de Geração</label>
        <Select
          v-model="localSelectedModel"
          :options="llmModels"
          optionLabel="name"
          optionValue="name"
          class="w-full mt-2"
          filter
          :loading="isLoadingModels"
          placeholder="Selecione um modelo"
        >
          <template #option="{ option }">
            <div class="model-option">
              <span class="model-name">{{ option.name }}</span>
              <div class="model-tags">
                <Tag :severity="getProviderSeverity(option.provider)" class="pill model-tag">
                  {{ getProviderLabel(option.provider) }}
                </Tag>
                <Tag :severity="getTypeSeverity(option.type)" class="pill model-tag">
                  {{ getTypeLabel(option.type) }}
                </Tag>
              </div>
            </div>
          </template>
          <template #value="{ value }">
            <div v-if="value" class="model-selected">
              <span class="model-name">{{ value }}</span>
              <div v-if="getModelInfo(value)" class="model-tags">
                <Tag :severity="getProviderSeverity(getModelInfo(value).provider)" class="pill model-tag">
                  {{ getProviderLabel(getModelInfo(value).provider) }}
                </Tag>
              </div>
            </div>
          </template>
        </Select>
        <small class="text-color-secondary mt-1 block">
          Cria os flashcards a partir do texto
        </small>
      </div>

      <!-- Modelo de Análise -->
      <div class="col-12 md:col-6">
        <label class="font-semibold"><i class="pi pi-search mr-2" />Modelo de Análise</label>
        <Select
          v-model="localAnalysisModel"
          :options="availableModels"
          optionLabel="name"
          optionValue="name"
          class="w-full mt-2"
          filter
          :loading="isLoadingModels"
          placeholder="Selecione um modelo"
        >
          <template #option="{ option }">
            <div class="model-option">
              <span class="model-name">{{ option.name }}</span>
              <div class="model-tags">
                <Tag :severity="getProviderSeverity(option.provider)" class="pill model-tag">
                  {{ getProviderLabel(option.provider) }}
                </Tag>
                <Tag :severity="getTypeSeverity(option.type)" class="pill model-tag">
                  {{ getTypeLabel(option.type) }}
                </Tag>
              </div>
            </div>
          </template>
          <template #value="{ value }">
            <div v-if="value" class="model-selected">
              <span class="model-name">{{ value }}</span>
              <div v-if="getModelInfo(value)" class="model-tags">
                <Tag :severity="getProviderSeverity(getModelInfo(value).provider)" class="pill model-tag">
                  {{ getProviderLabel(getModelInfo(value).provider) }}
                </Tag>
                <Tag :severity="getTypeSeverity(getModelInfo(value).type)" class="pill model-tag">
                  {{ getTypeLabel(getModelInfo(value).type) }}
                </Tag>
              </div>
            </div>
          </template>
        </Select>
        <small class="text-color-secondary mt-1 block">
          Extrai conceitos-chave do texto (Embedding: rápido | LLM: preciso)
        </small>
      </div>

      <!-- Modelo de Validação -->
      <div class="col-12 mt-3">
        <label class="font-semibold"><i class="pi pi-check-circle mr-2" />Modelo de Validação</label>
        <Select
          v-model="localValidationModel"
          :options="llmModels"
          optionLabel="name"
          optionValue="name"
          class="w-full mt-2"
          filter
          :loading="isLoadingModels"
          placeholder="Selecione um modelo"
        >
          <template #option="{ option }">
            <div class="model-option">
              <span class="model-name">{{ option.name }}</span>
              <div class="model-tags">
                <Tag :severity="getProviderSeverity(option.provider)" class="pill model-tag">
                  {{ getProviderLabel(option.provider) }}
                </Tag>
                <Tag :severity="getTypeSeverity(option.type)" class="pill model-tag">
                  {{ getTypeLabel(option.type) }}
                </Tag>
              </div>
            </div>
          </template>
          <template #value="{ value }">
            <div v-if="value" class="model-selected">
              <span class="model-name">{{ value }}</span>
              <div v-if="getModelInfo(value)" class="model-tags">
                <Tag :severity="getProviderSeverity(getModelInfo(value).provider)" class="pill model-tag">
                  {{ getProviderLabel(getModelInfo(value).provider) }}
                </Tag>
              </div>
            </div>
          </template>
        </Select>
        <small class="text-color-secondary mt-1 block">
          Verifica se os cards gerados estão ancorados no texto selecionado usando LLM
        </small>
      </div>
    </div>

    <Divider />

    <div class="model-tips">
      <p><strong>💡 Dica:</strong> Use modelos menores/mais rápidos para validação (ex: llama3.2:3b, gemma2:2b) para economizar tokens.</p>
    </div>

    <template #footer>
      <Button label="Atualizar Lista" icon="pi pi-refresh" severity="secondary" outlined @click="refresh" :loading="isLoadingModels" />
      <Button label="Cancelar" severity="secondary" outlined @click="close" />
      <Button label="Salvar" icon="pi pi-check" @click="save" />
    </template>
  </Dialog>
</template>

<style scoped>
.model-info {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(99, 102, 241, 0.08);
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-option {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.model-name {
  font-weight: 500;
}

.model-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.model-tag {
  font-size: 10px;
  padding: 2px 6px;
}

.model-selected {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-tips {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.15);
}

.model-tips p {
  margin: 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.pill {
  border-radius: 20px;
}
</style>
