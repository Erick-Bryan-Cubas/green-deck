/**
 * usePromptSettingsDialog — estado e handlers do PromptSettingsDialog para
 * qualquer página. Os prompts personalizados persistem no localStorage
 * (mesma chave que o Gerador usa), então editar aqui vale para as próximas
 * gerações. O PromptEditor interno busca os prompts padrão do servidor.
 */
import { computed, ref } from 'vue'

const LS_CUSTOM_PROMPTS_KEY = 'green-deck.custom-prompts.v1'

export function usePromptSettingsDialog(options = {}) {
  const { notify = () => {} } = options

  const visible = ref(false)
  const savedPrompts = ref(null)

  const hasCustomPrompts = computed(() => {
    const saved = savedPrompts.value
    if (!saved) return false
    return !!(saved.userProfile || saved.systemPrompt || saved.guidelines || saved.generationPrompt)
  })

  function open() {
    try {
      const raw = localStorage.getItem(LS_CUSTOM_PROMPTS_KEY)
      savedPrompts.value = raw ? JSON.parse(raw) : null
    } catch {
      savedPrompts.value = null
    }
    visible.value = true
  }

  function onSave(prompts) {
    try {
      if (!prompts || Object.keys(prompts).length === 0) {
        localStorage.removeItem(LS_CUSTOM_PROMPTS_KEY)
        savedPrompts.value = null
      } else {
        localStorage.setItem(LS_CUSTOM_PROMPTS_KEY, JSON.stringify(prompts))
        savedPrompts.value = prompts
      }
      notify('Prompts salvos com sucesso', 'success', 3000)
      visible.value = false
    } catch {
      notify('Erro ao salvar prompts', 'error', 4000)
    }
  }

  function onReset() {
    localStorage.removeItem(LS_CUSTOM_PROMPTS_KEY)
    savedPrompts.value = null
    notify('Prompts restaurados aos padrões', 'success', 3000)
    visible.value = false
  }

  return { visible, savedPrompts, hasCustomPrompts, open, onSave, onReset }
}
