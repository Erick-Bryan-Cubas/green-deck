/**
 * useApiKeysDialog — estado e handlers do ApiKeysDialog para qualquer página.
 * As chaves vivem no localStorage (services/api), então o diálogo pode ser
 * hospedado fora do Gerador sem duplicar lógica.
 */
import { computed, ref } from 'vue'
import { getStoredApiKeys, storeApiKeys } from '@/services/api.js'

export function useApiKeysDialog(options = {}) {
  const { notify = () => {}, onSaved = () => {} } = options

  const visible = ref(false)
  const storedKeys = ref({})

  const hasStoredKeys = computed(() =>
    !!(storedKeys.value.anthropicApiKey || storedKeys.value.openaiApiKey || storedKeys.value.perplexityApiKey)
  )

  function open() {
    storedKeys.value = getStoredApiKeys() || {}
    visible.value = true
  }

  function onSave({ anthropicApiKey, openaiApiKey, perplexityApiKey, storeLocally }) {
    const ok = storeApiKeys(anthropicApiKey, openaiApiKey, perplexityApiKey, storeLocally)
    if (ok) {
      notify('Chaves de API salvas com sucesso!', 'success')
      onSaved()
    } else {
      notify('Erro ao salvar as chaves', 'error')
    }
    storedKeys.value = getStoredApiKeys() || {}
    visible.value = false
  }

  function onClear() {
    storeApiKeys('', '', '', false)
    notify('Chaves removidas', 'info')
    storedKeys.value = {}
    onSaved()
  }

  return { visible, storedKeys, hasStoredKeys, open, onSave, onClear }
}
