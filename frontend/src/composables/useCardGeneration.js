/**
 * Composable for card generation logic
 * Handles the generation flow with content resolution fallback
 */
import { ref, computed } from 'vue'
import { generateCardsWithStream } from '@/services/api.js'
import { useContentSelection } from './useContentSelection.js'

/**
 * Card generation composable with smart content selection
 */
export function useCardGeneration(options = {}) {
  const {
    notify = () => {},
    addLog = () => {},
    startTimer = () => {},
    stopTimer = () => {},
    showProgress = () => {},
    setProgress = () => {},
    completeProgress = () => {},
    schedulePersistActiveSession = () => {}
  } = options

  // State
  const generating = ref(false)
  const cardType = ref('basic') // 'basic' | 'cloze' | 'both'
  const lastGenerationSource = ref(null) // Track where content came from

  // Content selection composable
  const contentSelection = useContentSelection()

  /**
   * Generate cards with smart content resolution
   * Uses the fallback hierarchy: selection → highlights → full text
   * @param {object} params - Generation parameters
   * @returns {Promise<Array>} Generated cards
   */
  async function generateCards({
    editorRef,
    cards,
    decks,
    documentContext,
    selectedModel,
    currentAnalysisId,
    progressValue
  }) {
    // Resolve which content to use
    const resolved = contentSelection.resolveGenerationContent(editorRef)

    // Handle empty content
    if (resolved.source === 'empty') {
      notify(resolved.message || 'Nenhum texto disponível', 'warn', 4500)
      return []
    }

    // Show warning if using full text (nothing selected/highlighted)
    if (resolved.shouldWarn && resolved.message) {
      notify(resolved.message, 'warn', 5000)
    }

    // Show info about source if using highlights
    if (resolved.source === 'highlight' && resolved.message) {
      notify(resolved.message, 'info', 3000)
    }

    lastGenerationSource.value = resolved.source
    const text = resolved.content

    try {
      generating.value = true
      startTimer('Gerando...')
      
      const sourceLabel = contentSelection.getSourceLabel()
      addLog(`Starting card generation (${cardType.value}) from: ${sourceLabel}`, 'info')
      console.log('Card type being sent:', cardType.value, '| Source:', resolved.source)
      
      showProgress('Gerando cards...')
      setProgress(10)

      const deckNames = Object.keys(decks?.value || decks || {}).join(', ')
      const context = documentContext?.value ?? documentContext ?? ''
      const model = selectedModel?.value ?? selectedModel ?? null
      const analysisId = currentAnalysisId?.value ?? currentAnalysisId ?? null

      const newCards = await generateCardsWithStream(
        text,
        deckNames,
        context,
        cardType.value,
        model,
        ({ stage, data }) => {
          try {
            if (stage === 'stage' && data?.stage) {
              const s = data.stage
              if (s === 'analysis_started') addLog('Stage: Analysis started', 'info')
              else if (s === 'analysis_completed') addLog('Stage: Analysis completed', 'success')
              else if (s === 'generation_started') addLog('Stage: Generation started', 'info')
              else if (s === 'generation_completed') addLog('Stage: Generation completed', 'success')
              else if (s === 'parsing_started') addLog('Stage: Parsing started', 'info')
              else if (s === 'parsing_completed') addLog('Stage: Parsing completed', 'success')
            }
          } catch (e) {
            addLog('Progress error: ' + (e?.message || String(e)), 'error')
          }

          const currentProgress = progressValue?.value ?? progressValue ?? 10
          if (currentProgress < 92) setProgress(currentProgress + 4)
        },
        analysisId
      )

      addLog(`Generated ${newCards.length} cards successfully`, 'success')

      // Add cards to the list
      if (cards?.value) {
        cards.value = [...cards.value, ...newCards]
      }

      notify(`${newCards.length} cards criados`, 'success')

      setProgress(100)
      completeProgress()
      schedulePersistActiveSession()

      return newCards
    } catch (error) {
      console.error('Error generating cards:', error)
      addLog('Generation error: ' + (error?.message || String(error)), 'error')

      const msg = error?.message || String(error)
      if (msg.includes('FUNCTION_INVOCATION_TIMEOUT') || msg.includes('timed out')) {
        notify('Timeout: selecione um trecho menor e tente novamente.', 'error', 8000)
      } else {
        notify('Erro ao gerar: ' + msg, 'error', 8000)
      }

      return []
    } finally {
      stopTimer()
      generating.value = false
    }
  }

  /**
   * Generate cards from explicit text (for context menu, edit dialog, etc.)
   * @param {string} text - Text to generate cards from
   * @param {object} params - Additional parameters
   */
  async function generateCardsFromText(text, params = {}) {
    const {
      type = cardType.value,
      decks = {},
      documentContext = '',
      selectedModel = null,
      currentAnalysisId = null,
      progressValue = { value: 10 },
      cards = null,
      sourceCardId = null
    } = params

    if (!text?.trim()) {
      notify('Texto vazio para gerar cards.', 'warn', 4500)
      return []
    }

    try {
      generating.value = true
      startTimer('Gerando...')
      addLog(`Starting card generation (${type}) from explicit text`, 'info')
      showProgress('Gerando cards...')
      setProgress(10)

      const deckNames = Object.keys(decks?.value || decks || {}).join(', ')
      const context = documentContext?.value ?? documentContext ?? ''
      const model = selectedModel?.value ?? selectedModel ?? null
      const analysisId = currentAnalysisId?.value ?? currentAnalysisId ?? null

      const newCards = await generateCardsWithStream(
        text,
        deckNames,
        context,
        type,
        model,
        ({ stage, data }) => {
          const currentProgress = progressValue?.value ?? progressValue ?? 10
          if (currentProgress < 92) setProgress(currentProgress + 4)
        },
        analysisId
      )

      // If this is a sub-card (generated from another card), mark the source
      if (sourceCardId !== null && newCards.length > 0) {
        newCards.forEach(card => {
          card.src = `Card #${sourceCardId + 1}`
        })
      }

      // Add cards to the list
      if (cards?.value) {
        cards.value = [...cards.value, ...newCards]
      }

      addLog(`Generated ${newCards.length} cards successfully`, 'success')
      notify(`${newCards.length} cards criados`, 'success')

      setProgress(100)
      completeProgress()

      return newCards
    } catch (error) {
      console.error('Error generating cards:', error)
      addLog('Generation error: ' + (error?.message || String(error)), 'error')
      notify('Erro ao gerar: ' + (error?.message || String(error)), 'error', 8000)
      return []
    } finally {
      stopTimer()
      generating.value = false
    }
  }

  /**
   * Set the card type for generation
   * @param {string} type - 'basic' | 'cloze' | 'both'
   */
  function setCardType(type) {
    cardType.value = type
  }

  /**
   * Get information about the last generation source
   * @returns {object} Source information
   */
  function getLastGenerationInfo() {
    return {
      source: lastGenerationSource.value,
      label: contentSelection.getSourceLabel()
    }
  }

  return {
    // State
    generating,
    cardType,
    lastGenerationSource,

    // Content selection (re-export for convenience)
    ...contentSelection,

    // Methods
    generateCards,
    generateCardsFromText,
    setCardType,
    getLastGenerationInfo
  }
}
