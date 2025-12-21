<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

// PrimeVue
import Toolbar from 'primevue/toolbar'
import Splitter from 'primevue/splitter'
import SplitterPanel from 'primevue/splitterpanel'
import Button from 'primevue/button'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Checkbox from 'primevue/checkbox'
import Textarea from 'primevue/textarea'
import Card from 'primevue/card'
import DataView from 'primevue/dataview'
import ProgressBar from 'primevue/progressbar'
import Menu from 'primevue/menu'
import ContextMenu from 'primevue/contextmenu'
import Toast from 'primevue/toast'
import Tag from 'primevue/tag'
import Divider from 'primevue/divider'
import { useToast } from 'primevue/usetoast'

// App components
import QuillEditor from '@/components/QuillEditor.vue'
import AnkiStatus from '@/components/AnkiStatus.vue'

// Services
import {
  generateCardsWithStream,
  analyzeTextWithClaude,
  getStoredApiKeys,
  storeApiKeys,
  validateAnthropicApiKey
} from '@/services/claude-api.js'

const toast = useToast()

// -------------------------
// Estado
// -------------------------
const cards = ref([])
const selectedText = ref('')
const documentContext = ref('')
const isAnalyzing = ref(false)

const decks = ref({})
const currentDeck = ref(null)
const ankiModelsData = ref(null)

const storedKeys = ref(getStoredApiKeys())
function refreshStoredKeys() {
  storedKeys.value = getStoredApiKeys()
}

const lastFullText = ref('')
const hasDocumentContext = computed(() => !!documentContext.value)

// Card type
const cardType = ref('basic')
const cardTypeOptions = [
  { label: 'Gerar Cartões Básicos', value: 'basic' },
  { label: 'Gerar Cartões Cloze', value: 'cloze' },
  { label: 'Gerar Cartões Básicos e Cloze', value: 'both' }
]

// UI: busca e layout dos cards
const cardSearch = ref('')
const cardsLayout = ref('list')
const cardsLayoutOptions = [
  { label: 'Lista', value: 'list' },
  { label: 'Grade', value: 'grid' }
]

const filteredCards = computed(() => {
  const q = (cardSearch.value || '').trim().toLowerCase()
  if (!q) return cards.value

  return cards.value.filter((c) => {
    const front = String(c.front || '').toLowerCase()
    const back = String(c.back || '').toLowerCase()
    const deck = String(c.deck || '').toLowerCase()
    return front.includes(q) || back.includes(q) || deck.includes(q)
  })
})

// -------------------------
// Timer (header)
// -------------------------
const processingTimerVisible = ref(false)
const timerText = ref('Processing...')
const timerSeconds = ref(0)
let timerInterval = null

function startTimer(text) {
  timerSeconds.value = 0
  timerText.value = text
  processingTimerVisible.value = true
  if (timerInterval) clearInterval(timerInterval)
  timerInterval = setInterval(() => {
    timerSeconds.value++
  }, 1000)
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
  processingTimerVisible.value = false
}

// -------------------------
// Logs (dialog)
// -------------------------
const logsVisible = ref(false)
const logs = ref([])

function addLog(message, type = 'info') {
  const timestamp = new Date().toLocaleTimeString()
  logs.value.push({ timestamp, message, type })
}

function clearLogs() {
  logs.value = []
  addLog('Logs cleared', 'info')
}

// -------------------------
// Progress Dialog
// -------------------------
const progressVisible = ref(false)
const progressTitle = ref('Processing...')
const progressValue = ref(0)

function showProgress(title = 'Processing...') {
  progressTitle.value = title
  progressValue.value = 0
  progressVisible.value = true
}

function setProgress(v) {
  progressValue.value = Math.max(0, Math.min(100, Math.floor(v)))
}

function completeProgress() {
  setProgress(100)
  setTimeout(() => (progressVisible.value = false), 650)
}

// -------------------------
// Context Summary Dialog (novo)
// -------------------------
const contextVisible = ref(false)
const contextCopying = ref(false)

async function copyContextToClipboard() {
  try {
    contextCopying.value = true
    await navigator.clipboard.writeText(documentContext.value || '')
    notify('Contexto copiado para a área de transferência', 'success', 2500)
  } catch {
    notify('Falha ao copiar contexto', 'error', 4000)
  } finally {
    contextCopying.value = false
  }
}

// -------------------------
// API Keys Dialog
// -------------------------
const apiKeyVisible = ref(false)
const anthropicApiKey = ref('')
const mochiApiKey = ref('')
const storeLocally = ref(true)
const anthropicApiKeyError = ref('')

function loadStoredKeysToForm() {
  refreshStoredKeys()
  anthropicApiKey.value = storedKeys.value.anthropicApiKey || ''
  mochiApiKey.value = storedKeys.value.mochiApiKey || ''
}

function openApiKeys() {
  anthropicApiKeyError.value = ''
  loadStoredKeysToForm()
  apiKeyVisible.value = true
}

async function saveApiKeys() {
  const aKey = anthropicApiKey.value.trim()
  const mKey = mochiApiKey.value.trim()

  if (aKey && !validateAnthropicApiKey(aKey)) {
    anthropicApiKeyError.value = 'Required: Enter a valid Claude API key (starts with sk-ant-)'
    return
  }

  const ok = storeApiKeys(aKey, mKey, storeLocally.value)
  if (!ok) {
    notify('Failed to save API keys', 'error')
    return
  }

  refreshStoredKeys()
  apiKeyVisible.value = false
  notify('API keys saved successfully', 'success')

  if (mKey) {
    try {
      await fetchDecks()
    } catch {
      notify('Failed to connect to Mochi API', 'error')
    }
  }
}

// -------------------------
// Toast
// -------------------------
function notify(message, severity = 'info', life = 3000) {
  toast.add({ severity, summary: message, life })
}

// -------------------------
// Decks Mochi
// -------------------------
async function fetchDecks() {
  refreshStoredKeys()
  const userMochiKey = storedKeys.value.mochiApiKey

  // Sem chave: fallback
  if (!userMochiKey) {
    decks.value = { General: 'general' }
    currentDeck.value = 'General'
    return
  }

  // 1) tenta via backend
  try {
    const resp = await fetch(`/api/mochi-decks?userMochiKey=${encodeURIComponent(userMochiKey)}`)
    if (resp.ok) {
      const data = await resp.json()
      if (data?.success && data?.decks) {
        decks.value = data.decks
        currentDeck.value = Object.keys(data.decks)[0] || 'General'
        return
      }
    }
  } catch {
    // ignora e tenta client-side
  }

  // 2) tenta client-side Mochi API
  try {
    const authHeader = `Basic ${btoa(`${userMochiKey}:`)}`
    const resp = await fetch('https://app.mochi.cards/api/decks/', {
      method: 'GET',
      headers: { Authorization: authHeader }
    })
    if (!resp.ok) throw new Error(await resp.text())

    const decksData = await resp.json()
    const formatted = {}
    decksData.docs.forEach((deck) => {
      if (deck['trashed?'] || deck['archived?']) return
      const cleanId = String(deck.id).replace(/\[\[|\]\]/g, '')
      formatted[deck.name] = cleanId
    })

    decks.value = formatted
    currentDeck.value = Object.keys(formatted)[0] || 'General'
    return
  } catch (e) {
    console.error('Error using client-side Mochi API:', e)
  }

  // 3) fallback final
  decks.value = { General: 'general' }
  currentDeck.value = 'General'
}

// -------------------------
// Analyze debounce
// -------------------------
let analyzeDebounce = null
function scheduleAnalyze(fullText) {
  if (analyzeDebounce) clearTimeout(analyzeDebounce)
  analyzeDebounce = setTimeout(() => {
    if (fullText.trim().length > 100 && !isAnalyzing.value) {
      analyzeDocumentContext(fullText)
    }
  }, 1200)
}

async function analyzeDocumentContext(text) {
  if (!text || text.trim().length < 100 || isAnalyzing.value) return

  try {
    isAnalyzing.value = true
    startTimer('Analisando...')
    addLog('Starting text analysis...', 'info')
    showProgress('Analisando texto...')
    setProgress(25)

    const contextSummary = await analyzeTextWithClaude(text)
    setProgress(92)

    addLog('Text analysis completed', 'success')
    if (contextSummary) documentContext.value = contextSummary

    stopTimer()
    completeProgress()
    notify('Análise concluída. A qualidade dos cards tende a melhorar.', 'success', 3800)
  } catch (error) {
    console.error('Error analyzing document:', error)
    addLog('Analysis error: ' + (error?.message || String(error)), 'error')
    stopTimer()
    progressVisible.value = false
    notify('Falha ao analisar: ' + (error?.message || String(error)), 'error', 8000)
  } finally {
    isAnalyzing.value = false
  }
}

// -------------------------
// Gerar cards
// -------------------------
const generating = ref(false)

async function generateCardsFromSelection() {
  const text = (selectedText.value || '').trim()
  if (!text) {
    notify('Selecione um trecho para gerar cards.', 'warn', 4500)
    return
  }

  try {
    generating.value = true
    startTimer('Gerando...')
    addLog(`Starting card generation (${cardType.value})...`, 'info')
    showProgress('Gerando cards...')
    setProgress(10)

    const deckNames = Object.keys(decks.value || {}).join(', ')
    const newCards = await generateCardsWithStream(
      text,
      deckNames,
      documentContext.value,
      cardType.value,
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
          console.error('Progress error:', e)
          addLog('Progress error: ' + (e?.message || String(e)), 'error')
        }

        if (progressValue.value < 92) setProgress(progressValue.value + 4)
      }
    )

    addLog(`Generated ${newCards.length} cards successfully`, 'success')
    cards.value = [...cards.value, ...newCards]
    notify(`${newCards.length} cards criados`, 'success')

    setProgress(100)
    completeProgress()
  } catch (error) {
    console.error('Error generating cards:', error)
    addLog('Generation error: ' + (error?.message || String(error)), 'error')

    const msg = error?.message || String(error)
    if (msg.includes('FUNCTION_INVOCATION_TIMEOUT') || msg.includes('timed out')) {
      notify('Timeout: selecione um trecho menor e tente novamente.', 'error', 8000)
    } else {
      notify('Erro ao gerar: ' + msg, 'error', 8000)
    }
  } finally {
    stopTimer()
    generating.value = false
    progressVisible.value = false
  }
}

// -------------------------
// Cards CRUD / Deck edit
// -------------------------
function deleteCard(index) {
  cards.value.splice(index, 1)
}

const deckDialogVisible = ref(false)
const deckDialogIndex = ref(-1)
const deckDialogValue = ref('')

const availableDeckNames = computed(() => {
  const names = Object.keys(decks.value || {})
  return names.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

function openDeckDialog(index) {
  if (!availableDeckNames.value.length) {
    notify('Sem decks disponíveis. Verifique a conexão com Mochi.', 'error', 6000)
    return
  }
  deckDialogIndex.value = index
  deckDialogValue.value = cards.value[index]?.deck || availableDeckNames.value[0]
  deckDialogVisible.value = true
}

async function refreshDecksFromDialog() {
  try {
    await fetchDecks()
    notify(`${availableDeckNames.value.length} decks carregados`, 'success')
  } catch {
    notify('Falha ao atualizar decks', 'error')
  }
}

function saveDeckDialog() {
  const idx = deckDialogIndex.value
  if (idx < 0) return
  const old = cards.value[idx].deck
  cards.value[idx].deck = deckDialogValue.value
  deckDialogVisible.value = false
  if (old !== deckDialogValue.value) {
    notify(`Card movido para "${deckDialogValue.value}"`, 'success')
  }
}

function clearAllCards() {
  cards.value = []
  notify('Cards limpos', 'info')
}

// -------------------------
// Export Mochi / Markdown
// -------------------------
const exportLabel = computed(() => (storedKeys.value.mochiApiKey ? 'Export to Mochi' : 'Export as Markdown'))

function formatCardsForMochi() {
  const deckMap = {}

  cards.value.forEach((card) => {
    const deckName = card.deck || 'General'
    const deckId = decks.value[deckName]
    if (!deckId) return

    if (!deckMap[deckId]) deckMap[deckId] = []
    deckMap[deckId].push({ content: `${card.front}\n---\n${card.back}` })
  })

  const data = { version: 2, cards: [] }
  for (const [deckId, arr] of Object.entries(deckMap)) {
    arr.forEach((c) => data.cards.push({ ...c, 'deck-id': deckId }))
  }
  return data
}

function exportAsMarkdown() {
  if (!cards.value.length) {
    notify('No cards to export', 'info')
    return
  }

  let markdown = `# Flashcards - ${new Date().toLocaleDateString()}\n\n`
  const deckGroups = {}

  cards.value.forEach((card) => {
    const d = card.deck || 'General'
    if (!deckGroups[d]) deckGroups[d] = []
    deckGroups[d].push(card)
  })

  for (const [deckName, arr] of Object.entries(deckGroups)) {
    markdown += `## ${deckName}\n\n`
    arr.forEach((card, idx) => {
      markdown += `### Card ${idx + 1}\n\n`
      markdown += `**Question:** ${card.front}\n\n`
      markdown += `---\n\n`
      markdown += `**Answer:** ${card.back}\n\n`
    })
  }

  try {
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `flashcards-${new Date().toISOString().slice(0, 10)}.md`
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()

    setTimeout(() => {
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }, 100)

    notify(`${cards.value.length} cards exportados em markdown`, 'success')
  } catch (error) {
    console.error('Error exporting markdown:', error)
    notify('Falha ao exportar. Veja o console para o markdown.', 'error', 8000)
    console.log(markdown)
  }
}

async function exportToMochi() {
  if (!cards.value.length) {
    notify('No cards to export', 'info')
    return
  }

  refreshStoredKeys()
  const userMochiKey = storedKeys.value.mochiApiKey
  if (!userMochiKey) {
    exportAsMarkdown()
    return
  }

  try {
    addLog('Uploading to Mochi...', 'info')
    showProgress('Enviando para Mochi...')
    setProgress(20)

    const payload = formatCardsForMochi()
    const response = await fetch('/api/upload-to-mochi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cards: payload.cards, userMochiKey })
    })

    if (!response.ok) throw new Error('Failed to upload to Mochi')
    const result = await response.json()

    setProgress(100)
    completeProgress()
    notify(`${result.totalSuccess} de ${result.totalCards} enviados ao Mochi!`, 'success')
    addLog(`Mochi upload completed: ${result.totalSuccess}/${result.totalCards}`, 'success')
  } catch (error) {
    console.error('Error uploading to Mochi API:', error)
    notify('Erro no Mochi. Exportando em markdown.', 'error')
    exportAsMarkdown()
  } finally {
    progressVisible.value = false
  }
}

// -------------------------
// Export Anki (modal config)
// -------------------------
const ankiVisible = ref(false)
const ankiModel = ref('')
const ankiFrontField = ref('')
const ankiBackField = ref('')
const ankiDeckField = ref('')
const ankiTags = ref('')

const ankiModelOptions = computed(() => {
  const d = ankiModelsData.value
  if (!d?.models) return []
  return Object.keys(d.models).map((m) => ({ label: m, value: m }))
})

const ankiDeckOptions = computed(() => {
  const d = ankiModelsData.value
  const base = [{ label: "Use card's deck", value: '' }]
  if (!d?.decks) return base
  return base.concat(d.decks.map((x) => ({ label: x, value: x })))
})

const ankiFieldOptions = computed(() => {
  const d = ankiModelsData.value
  if (!d?.models || !ankiModel.value) return []
  const fields = d.models[ankiModel.value] || []
  return fields.map((f) => ({ label: f, value: f }))
})

watch(ankiModel, () => {
  const fields = ankiFieldOptions.value
  ankiFrontField.value = fields[0]?.value || ''
  ankiBackField.value = fields[1]?.value || fields[0]?.value || ''
})

async function exportToAnkiOpenConfig() {
  try {
    if (!cards.value.length) {
      notify('No cards to export', 'info')
      return
    }

    addLog('Fetching Anki models...', 'info')
    showProgress('Carregando modelos do Anki...')
    setProgress(30)

    const resp = await fetch('/api/anki-models')
    if (!resp.ok) {
      throw new Error('Não foi possível conectar no Anki. Verifique Anki + AnkiConnect.')
    }

    const data = await resp.json()
    ankiModelsData.value = data

    const first = Object.keys(data.models || {})[0] || ''
    ankiModel.value = first

    setProgress(100)
    completeProgress()

    ankiVisible.value = true
    addLog('Anki configuration ready', 'success')
  } catch (error) {
    console.error('Error fetching Anki config:', error)
    addLog('Anki config error: ' + (error?.message || String(error)), 'error')
    notify(error?.message || String(error), 'error', 8000)
  } finally {
    progressVisible.value = false
  }
}

const ankiExporting = ref(false)
async function exportToAnkiConfirm() {
  try {
    ankiExporting.value = true
    addLog('Starting Anki export...', 'info')
    showProgress('Enviando para Anki...')
    setProgress(20)

    const resp = await fetch('/api/upload-to-anki', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cards: cards.value,
        modelName: ankiModel.value,
        frontField: ankiFrontField.value,
        backField: ankiBackField.value,
        deckName: ankiDeckField.value,
        tags: ankiTags.value
      })
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.error || 'Failed to upload to Anki')
    }

    const result = await resp.json()
    setProgress(100)
    completeProgress()

    addLog(`Anki export completed: ${result.totalSuccess}/${result.totalCards}`, 'success')
    notify(`${result.totalSuccess} de ${result.totalCards} enviados ao Anki!`, 'success')
    ankiVisible.value = false
  } catch (error) {
    console.error('Error uploading to Anki:', error)
    addLog('Anki export error: ' + (error?.message || String(error)), 'error')
    notify('Erro ao enviar ao Anki: ' + (error?.message || String(error)), 'error', 8000)
  } finally {
    ankiExporting.value = false
    progressVisible.value = false
  }
}

// -------------------------
// Menu (header)
// -------------------------
const menuRef = ref(null)
const menuItems = computed(() => [
  {
    label: exportLabel.value,
    icon: 'pi pi-upload',
    command: exportToMochi,
    disabled: !cards.value.length
  },
  {
    label: 'Export to Anki',
    icon: 'pi pi-send',
    command: exportToAnkiOpenConfig,
    disabled: !cards.value.length
  },
  {
    label: 'Clear Cards',
    icon: 'pi pi-trash',
    command: clearAllCards,
    disabled: !cards.value.length
  },
  { separator: true },
  {
    label: 'API Keys',
    icon: 'pi pi-key',
    command: openApiKeys
  }
])

function toggleMenu(event) {
  menuRef.value?.toggle(event)
}

// -------------------------
// Context Menu (editor)
// -------------------------
const editorRef = ref(null)
const contextMenuRef = ref(null)
const contextHasSelection = ref(false)
const contextHasHighlight = ref(false)
const contextSelectedText = ref('')

function onEditorContextMenu(payload) {
  contextHasSelection.value = !!payload.hasSelection
  contextHasHighlight.value = !!payload.hasHighlight
  contextSelectedText.value = payload.selectedText || ''

  payload.originalEvent?.preventDefault?.()
  contextMenuRef.value?.show(payload.originalEvent)
}

async function contextAnalyze() {
  const fullText = editorRef.value?.getFullText?.() || lastFullText.value || ''
  if (fullText.trim().length > 100) await analyzeDocumentContext(fullText)
  else notify('Texto muito curto para análise', 'warn', 4500)
}

async function contextGenerate(type) {
  if (!contextHasSelection.value) {
    notify('Selecione um trecho primeiro.', 'warn', 3500)
    return
  }
  cardType.value = type
  selectedText.value = contextSelectedText.value
  await generateCardsFromSelection()
}

function contextRemoveHighlight() {
  editorRef.value?.clearHighlight?.()
}

function contextMark(color) {
  editorRef.value?.formatBackground?.(color)
}

const contextMenuModel = computed(() => [
  {
    label: 'Marcar texto',
    disabled: !contextHasSelection.value,
    items: [
      { label: 'Amarelo', command: () => contextMark('#fef08a') },
      { label: 'Verde', command: () => contextMark('#bbf7d0') },
      { label: 'Azul', command: () => contextMark('#bfdbfe') },
      { label: 'Rosa', command: () => contextMark('#fbcfe8') },
      { label: 'Roxo', command: () => contextMark('#ddd6fe') },
      { label: 'Laranja', command: () => contextMark('#fed7aa') }
    ]
  },
  {
    label: 'Remover marcação',
    disabled: !contextHasHighlight.value,
    command: contextRemoveHighlight
  },
  { separator: true },
  { label: 'Analisar texto novamente', command: contextAnalyze },
  { separator: true },
  {
    label: 'Gerar cartão básico',
    disabled: !contextHasSelection.value,
    command: () => contextGenerate('basic')
  },
  {
    label: 'Gerar cartão cloze',
    disabled: !contextHasSelection.value,
    command: () => contextGenerate('cloze')
  }
])

// -------------------------
// Editor events
// -------------------------
function onSelectionChanged(payload) {
  selectedText.value = payload.selectedText || ''
}

function onContentChanged({ fullText }) {
  lastFullText.value = fullText || ''
  scheduleAnalyze(fullText || '')
}

// -------------------------
// Computeds úteis
// -------------------------
const hasSelection = computed(() => (selectedText.value || '').trim().length > 0)
const hasCards = computed(() => cards.value.length > 0)

const headerHint = computed(() => {
  if (generating.value) return 'Gerando cards…'
  if (isAnalyzing.value) return 'Analisando texto…'
  if (!hasSelection.value) return 'Selecione um trecho no editor para habilitar "Create Cards".'
  return 'Seleção pronta — gere cards quando quiser.'
})

// -------------------------
// Lifecycle
// -------------------------
let globalKeyHandler = null

onMounted(async () => {
  loadStoredKeysToForm()
  try {
    await fetchDecks()
  } catch {
    // ok fallback
  }

  // Atalho moderno: Ctrl+Enter gera cards (se houver seleção)
  globalKeyHandler = (e) => {
    const isCtrlEnter = (e.ctrlKey || e.metaKey) && e.key === 'Enter'
    if (!isCtrlEnter) return
    if (hasSelection.value && !generating.value && !isAnalyzing.value) {
      e.preventDefault()
      generateCardsFromSelection()
    }
  }
  window.addEventListener('keydown', globalKeyHandler)
})

onBeforeUnmount(() => {
  if (timerInterval) clearInterval(timerInterval)
  if (analyzeDebounce) clearTimeout(analyzeDebounce)
  if (globalKeyHandler) window.removeEventListener('keydown', globalKeyHandler)
})
</script>

<template>
  <Toast />
  <ContextMenu ref="contextMenuRef" :model="contextMenuModel" appendTo="body" />

  <div class="app-shell" :class="{ 'has-context': hasDocumentContext }">
    <!-- HEADER -->
    <Toolbar class="app-header">
      <template #start>
        <div class="header-left">
          <div class="brand">
            <div class="brand-icon">🧠</div>
            <div class="brand-text">
              <div class="brand-title">Flash Card Generator</div>
              <div class="brand-subtitle">
                {{ headerHint }}
              </div>
            </div>
          </div>

          <div class="header-badges">
            <Tag v-if="hasDocumentContext" severity="success" class="pill">
              <i class="pi pi-sparkles mr-2" /> Contexto pronto
            </Tag>
            <Tag v-else severity="secondary" class="pill">
              <i class="pi pi-file mr-2" /> Cole um texto para análise
            </Tag>
          </div>
        </div>
      </template>

      <template #end>
        <div class="header-right">
          <div class="status-wrap">
            <AnkiStatus />
          </div>

          <Divider layout="vertical" class="hdr-divider" />

          <div class="controls">
            <Select
              v-model="cardType"
              :options="cardTypeOptions"
              optionLabel="label"
              optionValue="value"
              class="cardtype"
              :disabled="generating || isAnalyzing"
            />

            <Button
              icon="pi pi-bolt"
              label="Create Cards"
              class="cta"
              :disabled="!hasSelection || generating || isAnalyzing"
              :loading="generating"
              :title="hasSelection ? 'Ctrl+Enter também funciona' : 'Selecione um trecho no editor'"
              @click="generateCardsFromSelection"
            />

            <Button
              icon="pi pi-sparkles"
              label="Contexto"
              severity="secondary"
              outlined
              :disabled="!hasDocumentContext"
              @click="contextVisible = true"
            />

            <Button
              icon="pi pi-list"
              label="Logs"
              severity="secondary"
              outlined
              @click="logsVisible = true"
            />

            <Button icon="pi pi-ellipsis-v" severity="secondary" outlined @click="toggleMenu" />
            <Menu ref="menuRef" :model="menuItems" popup />
          </div>

          <div v-if="processingTimerVisible" class="timer-chip">
            <span class="timer-ico">⏱️</span>
            <span class="timer-text">{{ timerText }}</span>
            <span class="timer-val">{{ timerSeconds }}s</span>
          </div>
        </div>
      </template>
    </Toolbar>

    <!-- MAIN -->
    <div class="main">
      <!-- Layout vertical (top/bottom) — estilo moderno "flow" -->
      <Splitter class="main-splitter" layout="vertical">
        <!-- Editor -->
        <SplitterPanel :size="58" :minSize="25">
          <div class="panel panel-editor">
            <div class="panel-head">
              <div class="panel-title">
                <i class="pi pi-pencil mr-2" />
                Editor
              </div>
              <div class="panel-actions">
                <Tag severity="secondary" class="pill subtle">
                  <i class="pi pi-mouse mr-2" /> Clique direito para opções
                </Tag>
              </div>
            </div>

            <div class="panel-body">
              <QuillEditor
                ref="editorRef"
                @selection-changed="onSelectionChanged"
                @content-changed="onContentChanged"
                @context-menu="onEditorContextMenu"
              />
            </div>
          </div>
        </SplitterPanel>

        <!-- Output -->
        <SplitterPanel :size="42" :minSize="20">
          <div class="panel panel-output">
            <div class="panel-head">
              <div class="panel-title">
                <i class="pi pi-clone mr-2" />
                Cards
                <Tag :severity="hasCards ? 'success' : 'secondary'" class="pill ml-2">
                  {{ hasCards ? `${cards.length} total` : 'Sem cards' }}
                </Tag>
              </div>

              <div class="panel-actions">
                <div class="search-wrap">
                  <i class="pi pi-search search-ico" />
                  <InputText v-model="cardSearch" class="search" placeholder="Buscar em front/back/deck..." />
                </div>

                <SelectButton
                  v-model="cardsLayout"
                  :options="cardsLayoutOptions"
                  optionLabel="label"
                  optionValue="value"
                  class="layout-toggle"
                />

                <Button
                  :disabled="!hasCards"
                  :label="exportLabel"
                  icon="pi pi-upload"
                  outlined
                  @click="exportToMochi"
                />
                <Button
                  :disabled="!hasCards"
                  label="Anki"
                  icon="pi pi-send"
                  outlined
                  @click="exportToAnkiOpenConfig"
                />
                <Button
                  :disabled="!hasCards"
                  label="Limpar"
                  icon="pi pi-trash"
                  severity="danger"
                  outlined
                  @click="clearAllCards"
                />
              </div>
            </div>

            <div class="panel-body output-body">
              <div v-if="!hasCards" class="empty-state">
                <div class="empty-icon">✨</div>
                <div class="empty-title">Nenhum card ainda</div>
                <div class="empty-subtitle">
                  Cole um texto, selecione um trecho e gere cards. Você pode marcar (highlight) trechos com o clique direito.
                </div>
              </div>

              <DataView v-else :value="filteredCards" :layout="cardsLayout" class="cards-view">
                <!-- LIST -->
                <template #list="{ items }">
                  <div class="cards-list">
                    <Card v-for="(c, i) in items" :key="i" class="card-item">
                      <template #title>
                        <div class="card-head">
                          <div class="card-left">
                            <span class="card-index">Card {{ i + 1 }}</span>
                            <Button
                              text
                              size="small"
                              :label="c.deck || 'General'"
                              icon="pi pi-tag"
                              class="deck-btn"
                              @click="openDeckDialog(i)"
                              title="Clique para mudar o deck"
                            />
                          </div>
                          <Button icon="pi pi-times" severity="danger" text @click="deleteCard(i)" title="Excluir" />
                        </div>
                      </template>

                      <template #content>
                        <div class="grid">
                          <div class="col-12 md:col-6">
                            <div class="field-title">Front</div>
                            <Textarea v-model="c.front" autoResize class="w-full field-area" />
                          </div>
                          <div class="col-12 md:col-6">
                            <div class="field-title">Back</div>
                            <Textarea v-model="c.back" autoResize class="w-full field-area" />
                          </div>
                        </div>
                      </template>
                    </Card>
                  </div>
                </template>

                <!-- GRID -->
                <template #grid="{ items }">
                  <div class="cards-grid">
                    <Card v-for="(c, i) in items" :key="i" class="card-item">
                      <template #title>
                        <div class="card-head">
                          <div class="card-left">
                            <span class="card-index">#{{ i + 1 }}</span>
                            <Button
                              text
                              size="small"
                              :label="c.deck || 'General'"
                              icon="pi pi-tag"
                              class="deck-btn"
                              @click="openDeckDialog(i)"
                              title="Clique para mudar o deck"
                            />
                          </div>
                          <Button icon="pi pi-times" severity="danger" text @click="deleteCard(i)" title="Excluir" />
                        </div>
                      </template>

                      <template #content>
                        <div class="field-title">Front</div>
                        <Textarea v-model="c.front" autoResize class="w-full field-area mb-3" />
                        <div class="field-title">Back</div>
                        <Textarea v-model="c.back" autoResize class="w-full field-area" />
                      </template>
                    </Card>
                  </div>
                </template>
              </DataView>
            </div>
          </div>
        </SplitterPanel>
      </Splitter>
    </div>

    <!-- LOGS -->
    <Dialog v-model:visible="logsVisible" header="🔍 Logs" modal class="modern-dialog" style="width: min(980px, 96vw);">
      <div class="logs-wrap">
        <div v-if="!logs.length" class="logs-empty">Sem logs ainda.</div>
        <div v-else>
          <div v-for="(l, idx) in logs" :key="idx" class="log-row" :class="`t-${l.type}`">
            <span class="log-ts">[{{ l.timestamp }}]</span>
            <span class="log-msg">{{ l.message }}</span>
          </div>
        </div>
      </div>

      <template #footer>
        <Button label="Clear Logs" icon="pi pi-trash" severity="secondary" outlined @click="clearLogs" />
        <Button label="Close" icon="pi pi-times" @click="logsVisible = false" />
      </template>
    </Dialog>

    <!-- PROGRESS -->
    <Dialog v-model:visible="progressVisible" :header="progressTitle" modal class="modern-dialog" style="width: min(520px, 95vw);">
      <ProgressBar :value="progressValue" />
      <div class="mt-2 text-right">{{ progressValue }}%</div>
    </Dialog>

    <!-- CONTEXT SUMMARY -->
    <Dialog v-model:visible="contextVisible" header="📌 Contexto do Documento" modal class="modern-dialog" style="width: min(980px, 96vw);">
      <div class="context-box">
        <Textarea :modelValue="documentContext" readonly autoResize class="w-full context-area" />
      </div>

      <template #footer>
        <Button label="Copiar" icon="pi pi-copy" :loading="contextCopying" outlined @click="copyContextToClipboard" />
        <Button label="Fechar" icon="pi pi-times" @click="contextVisible = false" />
      </template>
    </Dialog>

    <!-- API KEYS -->
    <Dialog v-model:visible="apiKeyVisible" header="API Key Setup" modal class="modern-dialog" style="width: min(760px, 96vw);">
      <div class="disclaimer">
        ⚠️ I vibe coded this whole thing. I know nothing about security. Please don't use API keys with large balances or auto-refills.
      </div>

      <div class="grid">
        <div class="col-12">
          <label class="font-semibold">Claude API Key <span class="req">(Required se você usar Claude)</span></label>
          <InputText v-model="anthropicApiKey" class="w-full" placeholder="sk-ant-api03-..." autocomplete="off" />
          <small class="text-color-secondary">Get your API key from console.anthropic.com/keys</small>
          <div v-if="anthropicApiKeyError" class="err">{{ anthropicApiKeyError }}</div>
        </div>

        <div class="col-12 mt-3">
          <label class="font-semibold">Mochi API Key <span class="opt">(Optional)</span></label>
          <InputText v-model="mochiApiKey" class="w-full" placeholder="Your Mochi API key (optional)" autocomplete="off" />
          <small class="text-color-secondary">
            Opcional — permite exportar direto pro Mochi. Sem ela, exporta em markdown.
          </small>
        </div>

        <div class="col-12 mt-3 flex align-items-center gap-2">
          <Checkbox v-model="storeLocally" :binary="true" />
          <label>Remember API keys on this device</label>
        </div>
      </div>

      <template #footer>
        <Button label="Cancel" severity="secondary" outlined @click="apiKeyVisible = false" />
        <Button label="Save API Keys" icon="pi pi-save" @click="saveApiKeys" />
      </template>
    </Dialog>

    <!-- DECK EDIT -->
    <Dialog v-model:visible="deckDialogVisible" header="Select Deck" modal class="modern-dialog" style="width: min(520px, 95vw);">
      <div class="mb-2 text-color-secondary">Escolha um deck para este card:</div>

      <div class="flex align-items-center gap-2">
        <Select
          v-model="deckDialogValue"
          :options="availableDeckNames.map(x => ({ label: x, value: x }))"
          optionLabel="label"
          optionValue="value"
          class="flex-1"
          filter
          placeholder="Selecione..."
        />
        <Button icon="pi pi-refresh" severity="secondary" outlined @click="refreshDecksFromDialog" title="Atualizar decks" />
      </div>

      <template #footer>
        <Button label="Cancel" severity="secondary" outlined @click="deckDialogVisible = false" />
        <Button label="Update Deck" icon="pi pi-check" @click="saveDeckDialog" />
      </template>
    </Dialog>

    <!-- ANKI CONFIG -->
    <Dialog v-model:visible="ankiVisible" header="Anki Export Configuration" modal class="modern-dialog" style="width: min(760px, 96vw);">
      <div class="grid">
        <div class="col-12">
          <label class="font-semibold">Note Type (Model)</label>
          <Select v-model="ankiModel" :options="ankiModelOptions" optionLabel="label" optionValue="value" class="w-full" filter />
        </div>

        <div class="col-12 md:col-6 mt-3">
          <label class="font-semibold">Front Field</label>
          <Select v-model="ankiFrontField" :options="ankiFieldOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>

        <div class="col-12 md:col-6 mt-3">
          <label class="font-semibold">Back Field</label>
          <Select v-model="ankiBackField" :options="ankiFieldOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>

        <div class="col-12 mt-3">
          <label class="font-semibold">Deck (optional)</label>
          <Select v-model="ankiDeckField" :options="ankiDeckOptions" optionLabel="label" optionValue="value" class="w-full" filter />
        </div>

        <div class="col-12 mt-3">
          <label class="font-semibold">Tags (comma-separated, optional)</label>
          <InputText v-model="ankiTags" class="w-full" placeholder="tag1, tag2" autocomplete="off" />
        </div>
      </div>

      <template #footer>
        <Button label="Cancel" severity="secondary" outlined @click="ankiVisible = false" />
        <Button label="Export to Anki" icon="pi pi-send" :loading="ankiExporting" @click="exportToAnkiConfirm" />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
/* ---------- Shell ---------- */
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background:
    radial-gradient(1200px 700px at 12% -10%, rgba(99, 102, 241, 0.25), transparent 55%),
    radial-gradient(900px 600px at 95% 10%, rgba(16, 185, 129, 0.18), transparent 60%),
    radial-gradient(900px 600px at 60% 110%, rgba(236, 72, 153, 0.14), transparent 55%),
    linear-gradient(180deg, rgba(10, 10, 12, 0.0), rgba(10, 10, 12, 0.35));
}

.main {
  flex: 1;
  min-height: 0;
  padding: 14px;
}

.main-splitter {
  height: 100%;
}

/* ---------- Header ---------- */
.app-header {
  position: sticky;
  top: 0;
  z-index: 50;
  border: 0;
  padding: 14px 14px;
  backdrop-filter: blur(10px);
}

:deep(.p-toolbar) {
  background: rgba(17, 24, 39, 0.60);
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 8px 24px rgba(0,0,0,0.28);
}

.brand-title {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.3px;
}

.brand-subtitle {
  font-size: 12.5px;
  opacity: 0.78;
  margin-top: 2px;
}

.header-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.cardtype {
  width: 20rem;
}

.hdr-divider {
  height: 26px;
  opacity: 0.6;
}

.timer-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.timer-text {
  opacity: 0.85;
  font-size: 12.5px;
}

.timer-val {
  font-weight: 800;
  font-size: 12.5px;
}

/* CTA visual mais “moderna” */
:deep(.cta.p-button) {
  border-radius: 999px;
  box-shadow: 0 10px 24px rgba(0,0,0,0.22);
}

/* ---------- Panels ---------- */
.panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;

  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(17, 24, 39, 0.58);
  backdrop-filter: blur(10px);
  box-shadow: 0 14px 30px rgba(0,0,0,0.26);
  overflow: hidden;
}

.panel-head {
  padding: 12px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.panel-title {
  font-weight: 800;
  letter-spacing: -0.2px;
  display: flex;
  align-items: center;
}

.panel-body {
  padding: 12px;
  flex: 1;
  min-height: 0;
}

.output-body {
  overflow: auto;
}

/* Splitter handle mais “clean” */
:deep(.p-splitter) {
  border: 0;
  background: transparent;
}

:deep(.p-splitter-gutter) {
  background: transparent;
}

:deep(.p-splitter-gutter-handle) {
  background: rgba(148, 163, 184, 0.28);
  border-radius: 999px;
}

/* ---------- Cards ---------- */
.cards-view {
  height: 100%;
}

.cards-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 920px) {
  .cards-grid {
    grid-template-columns: 1fr;
  }
  .cardtype {
    width: 100%;
  }
}

.card-item :deep(.p-card) {
  border-radius: 16px;
}

.card-item :deep(.p-card-body) {
  padding: 14px 14px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.card-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-index {
  font-weight: 800;
  opacity: 0.9;
}

.deck-btn {
  padding: 0 !important;
  font-weight: 700;
}

.field-title {
  font-weight: 800;
  opacity: 0.85;
  margin-bottom: 6px;
}

.field-area :deep(textarea) {
  border-radius: 14px;
}

/* ---------- Search / toggle ---------- */
.search-wrap {
  position: relative;
  width: 18rem;
}

.search {
  width: 100%;
  padding-left: 34px;
  border-radius: 999px;
}

.search-ico {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  opacity: 0.75;
}

.layout-toggle :deep(.p-button) {
  border-radius: 999px;
}

/* ---------- Empty state ---------- */
.empty-state {
  height: 100%;
  display: grid;
  place-items: center;
  text-align: center;
  padding: 28px;
  opacity: 0.92;
}

.empty-icon {
  font-size: 44px;
  margin-bottom: 6px;
}

.empty-title {
  font-size: 18px;
  font-weight: 900;
  letter-spacing: -0.3px;
}

.empty-subtitle {
  margin-top: 8px;
  max-width: 62ch;
  opacity: 0.82;
  line-height: 1.35;
}

/* ---------- Dialogs ---------- */
.modern-dialog :deep(.p-dialog-header) {
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.disclaimer {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.05);
  margin-bottom: 14px;
}

.req {
  color: #ef4444;
  font-weight: 800;
  margin-left: 6px;
}

.opt {
  opacity: 0.7;
  margin-left: 6px;
}

.err {
  color: #ef4444;
  margin-top: 8px;
  font-weight: 700;
}

/* ---------- Logs ---------- */
.logs-wrap {
  max-height: 60vh;
  overflow: auto;
  padding: 6px 2px;
}

.logs-empty {
  opacity: 0.75;
  padding: 10px;
}

.log-row {
  display: flex;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 10px;
  margin-bottom: 6px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(148, 163, 184, 0.10);
}

.log-ts {
  opacity: 0.7;
  white-space: nowrap;
}

.log-msg {
  opacity: 0.92;
}

.log-row.t-success {
  border-color: rgba(16, 185, 129, 0.25);
}

.log-row.t-error {
  border-color: rgba(239, 68, 68, 0.25);
}

/* ---------- Pills ---------- */
.pill {
  border-radius: 999px;
  font-weight: 800;
}

.pill.subtle {
  opacity: 0.9;
}

/* ---------- Context ---------- */
.context-area :deep(textarea) {
  border-radius: 14px;
}
</style>
