/**
 * useModelSelectionDialog — estado e handlers do ModelSelectionDialog para
 * qualquer página. A seleção persiste no localStorage (mesmas chaves que o
 * Gerador lê ao montar), então escolher o modelo aqui vale para as próximas
 * gerações sem depender da página do Gerador.
 */
import { ref } from 'vue'
import { getStoredApiKeys } from '@/services/api.js'

const LS_MODEL = 'green-deck.selected-model'
const LS_VALIDATION = 'green-deck.selected-validation-model'
const LS_ANALYSIS = 'green-deck.selected-analysis-model'

export function useModelSelectionDialog(options = {}) {
  const { notify = () => {} } = options

  const visible = ref(false)
  const availableModels = ref([])
  const isLoadingModels = ref(false)
  const selectedModel = ref(null)
  const selectedValidationModel = ref(null)
  const selectedAnalysisModel = ref(null)

  async function fetchModels() {
    try {
      isLoadingModels.value = true
      const keys = getStoredApiKeys()
      const headers = {}
      if (keys.openaiApiKey) headers['X-OpenAI-Key'] = keys.openaiApiKey
      if (keys.perplexityApiKey) headers['X-Perplexity-Key'] = keys.perplexityApiKey

      const resp = await fetch('/api/all-models', { headers })
      if (resp.ok) {
        const data = await resp.json()
        availableModels.value = data.models || []
      }
    } catch {
      notify('Erro ao carregar modelos disponíveis', 'error', 4000)
    } finally {
      isLoadingModels.value = false
    }
  }

  function open() {
    // Relê o localStorage — a seleção pode ter sido alterada em outra página
    selectedModel.value = localStorage.getItem(LS_MODEL) || null
    selectedValidationModel.value = localStorage.getItem(LS_VALIDATION) || null
    selectedAnalysisModel.value = localStorage.getItem(LS_ANALYSIS) || null
    visible.value = true
    fetchModels()
  }

  function save() {
    try {
      // Salva apenas se houver valor (evita gravar 'null' como string)
      if (selectedModel.value) localStorage.setItem(LS_MODEL, selectedModel.value)
      if (selectedValidationModel.value) localStorage.setItem(LS_VALIDATION, selectedValidationModel.value)
      if (selectedAnalysisModel.value) localStorage.setItem(LS_ANALYSIS, selectedAnalysisModel.value)
      visible.value = false
      notify('Modelos salvos com sucesso', 'success', 3000)
    } catch {
      notify('Erro ao salvar modelos', 'error', 3000)
    }
  }

  return {
    visible,
    availableModels,
    isLoadingModels,
    selectedModel,
    selectedValidationModel,
    selectedAnalysisModel,
    open,
    save,
    fetchModels
  }
}
