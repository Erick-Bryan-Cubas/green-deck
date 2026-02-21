/**
 * Composable for managing content selection and highlight extraction
 * Implements the fallback hierarchy:
 * 1. Mouse selection → 2. Highlighted content → 3. Full text (with warning)
 */
import { ref, computed } from 'vue'

/**
 * Resolve content for card generation based on priority:
 * 1. If there's mouse-selected text, use it
 * 2. If there's highlighted content, extract and concatenate it
 * 3. If nothing is selected/highlighted, use full text and return a warning flag
 */
export function useContentSelection() {
  // State
  const selectedText = ref('')
  const highlightPositions = ref([]) // [{index, length, color, text}]
  const currentHighlightIndex = ref(-1)
  const lastContentSource = ref(null) // 'selection' | 'highlight' | 'full' | null

  // Computed
  const hasSelection = computed(() => (selectedText.value || '').trim().length > 0)
  const hasHighlights = computed(() => highlightPositions.value.length > 0)
  const highlightCount = computed(() => highlightPositions.value.length)
  
  const currentHighlightLabel = computed(() => {
    if (!hasHighlights.value) return '0/0'
    const current = currentHighlightIndex.value + 1
    return `${current > 0 ? current : '-'}/${highlightCount.value}`
  })

  /**
   * Scan the editor delta for highlighted content
   * @param {object} editorRef - Reference to the QuillEditor component
   * @returns {Array} Array of highlight positions with text
   */
  function scanHighlights(editorRef) {
    if (!editorRef?.value) {
      highlightPositions.value = []
      return []
    }

    const delta = editorRef.value.getDelta?.()
    if (!delta || !delta.ops) {
      highlightPositions.value = []
      return []
    }

    const positions = []
    let idx = 0

    delta.ops.forEach((op) => {
      const ins = op.insert
      const len = typeof ins === 'string' ? ins.length : 1
      const bg = op.attributes?.highlight

      if (bg && typeof bg === 'string' && bg.startsWith('#')) {
        const text = typeof ins === 'string' ? ins : ''
        positions.push({ index: idx, length: len, color: bg, text })
      }
      idx += len
    })

    highlightPositions.value = positions
    return positions
  }

  /**
   * Get all highlighted content concatenated
   * @param {object} editorRef - Reference to the QuillEditor component
   * @returns {string} Concatenated highlighted text
   */
  function getHighlightedContent(editorRef) {
    const positions = scanHighlights(editorRef)
    if (positions.length === 0) return ''

    // Concatenate all highlighted text with double line breaks
    return positions
      .map(p => p.text.trim())
      .filter(Boolean)
      .join('\n\n')
  }

  /**
   * Get content from the Quill delta by extracting highlighted text directly
   * This is more reliable than using stored positions
   * @param {object} editorRef - Reference to the QuillEditor component
   * @returns {string} Concatenated highlighted text
   */
  function extractHighlightedTextFromDelta(editorRef) {
    if (!editorRef?.value) return ''
    
    const delta = editorRef.value.getDelta?.()
    if (!delta || !delta.ops) return ''

    const highlightedParts = []

    delta.ops.forEach((op) => {
      const ins = op.insert
      const bg = op.attributes?.highlight

      if (bg && typeof bg === 'string' && bg.startsWith('#') && typeof ins === 'string') {
        highlightedParts.push(ins)
      }
    })

    return highlightedParts
      .map(t => t.trim())
      .filter(Boolean)
      .join('\n\n')
  }

  /**
   * Resolve which content to use for card generation
   * Implements the fallback hierarchy
   * @param {object} editorRef - Reference to the QuillEditor component
   * @returns {object} { source: 'selection'|'highlight'|'full', content: string, shouldWarn: boolean }
   */
  function resolveGenerationContent(editorRef) {
    // 1. Check for mouse selection first
    const selection = (selectedText.value || '').trim()
    if (selection) {
      lastContentSource.value = 'selection'
      return {
        source: 'selection',
        content: selection,
        shouldWarn: false,
        message: null
      }
    }

    // 2. Check for highlighted content
    const highlightedContent = extractHighlightedTextFromDelta(editorRef)
    if (highlightedContent) {
      lastContentSource.value = 'highlight'
      const count = highlightPositions.value.length
      return {
        source: 'highlight',
        content: highlightedContent,
        shouldWarn: false,
        message: `Gerando a partir de ${count} trecho${count > 1 ? 's' : ''} marcado${count > 1 ? 's' : ''}`
      }
    }

    // 3. Fall back to full text with warning
    const fullText = editorRef?.value?.getFullText?.() || editorRef?.value?.getText?.() || ''
    const normalizedFullText = fullText.trim()
    
    if (!normalizedFullText) {
      lastContentSource.value = null
      return {
        source: 'empty',
        content: '',
        shouldWarn: true,
        message: 'Nenhum texto disponível para gerar cards'
      }
    }

    lastContentSource.value = 'full'
    return {
      source: 'full',
      content: normalizedFullText,
      shouldWarn: true,
      message: 'Nenhum texto selecionado ou marcado. Usando todo o texto para geração.'
    }
  }

  /**
   * Navigate to a specific highlight in the editor
   * @param {object} editorRef - Reference to the QuillEditor component
   * @param {number} index - Index of the highlight to navigate to
   */
  function goToHighlight(editorRef, index) {
    if (!editorRef?.value || highlightPositions.value.length === 0) return

    const pos = highlightPositions.value[index]
    if (!pos) return

    currentHighlightIndex.value = index

    // Access internal Quill instance
    const quill = editorRef.value.$el?.querySelector('.ql-editor')?.parentElement?.__quill
    if (quill) {
      quill.setSelection(pos.index, pos.length)
      // Scroll to the highlight
      const bounds = quill.getBounds(pos.index, pos.length)
      if (bounds) {
        const container = editorRef.value.$el?.querySelector('.ql-container')
        if (container) {
          container.scrollTop = bounds.top - container.clientHeight / 3
        }
      }
    }
  }

  /**
   * Navigate to previous highlight
   * @param {object} editorRef - Reference to the QuillEditor component
   */
  function goToPrevHighlight(editorRef) {
    if (!hasHighlights.value) return
    let newIndex = currentHighlightIndex.value - 1
    if (newIndex < 0) newIndex = highlightPositions.value.length - 1
    goToHighlight(editorRef, newIndex)
  }

  /**
   * Navigate to next highlight
   * @param {object} editorRef - Reference to the QuillEditor component
   */
  function goToNextHighlight(editorRef) {
    if (!hasHighlights.value) return
    let newIndex = currentHighlightIndex.value + 1
    if (newIndex >= highlightPositions.value.length) newIndex = 0
    goToHighlight(editorRef, newIndex)
  }

  /**
   * Update the selected text from editor event
   * @param {string} text - Selected text
   */
  function updateSelection(text) {
    selectedText.value = text || ''
  }

  /**
   * Clear the current selection
   */
  function clearSelection() {
    selectedText.value = ''
  }

  /**
   * Get a human-readable label for the content source
   * @returns {string} Label describing the source
   */
  function getSourceLabel() {
    switch (lastContentSource.value) {
      case 'selection':
        return 'Texto selecionado'
      case 'highlight':
        const count = highlightPositions.value.length
        return `${count} marcação${count > 1 ? 'ões' : ''}`
      case 'full':
        return 'Texto completo'
      default:
        return ''
    }
  }

  return {
    // State
    selectedText,
    highlightPositions,
    currentHighlightIndex,
    lastContentSource,
    
    // Computed
    hasSelection,
    hasHighlights,
    highlightCount,
    currentHighlightLabel,
    
    // Methods
    scanHighlights,
    getHighlightedContent,
    extractHighlightedTextFromDelta,
    resolveGenerationContent,
    goToHighlight,
    goToPrevHighlight,
    goToNextHighlight,
    updateSelection,
    clearSelection,
    getSourceLabel
  }
}
