<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

// PrimeVue
import Toolbar from 'primevue/toolbar'
import Splitter from 'primevue/splitter'
import SplitterPanel from 'primevue/splitterpanel'
import Button from 'primevue/button'
import Select from 'primevue/select'
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

import { useRouter } from 'vue-router'

// Services
import {
  generateCardsWithStream,
  analyzeTextWithClaude,
  getStoredApiKeys,
  storeApiKeys,
  validateAnthropicApiKey
} from '@/services/claude-api.js'

const toast = useToast()
const router = useRouter()

// ============================================================
// Helpers
// ============================================================
function notify(message, severity = 'info', life = 3000) {
  toast.add({ severity, summary: message, life })
}

function normalizePlainText(t) {
  return String(t || '')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

function safeId() {
  try {
    return crypto.randomUUID()
  } catch {
    return `sess_${Date.now()}_${Math.random().toString(16).slice(2)}`
  }
}

function sessionTitleFromText(text) {
  const t = String(text || '').trim()
  const firstLine = t
    .split('\n')
    .map((s) => s.trim())
    .find(Boolean)
  if (!firstLine) return 'Texto sem título'
  return firstLine.length > 60 ? firstLine.slice(0, 59) + '…' : firstLine
}

function formatSessionStamp(iso) {
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return ''
  }
}

// ============================================================
// Sessões (localStorage) — texto + marcações (Delta) + cards + contexto
// ============================================================
const LS_SESSIONS_KEY = 'spaced-rep.sessions.v1'
const LS_ACTIVE_SESSION_KEY = 'spaced-rep.sessions.active.v1'

// Para evitar estourar o localStorage sem perceber
const MAX_SESSIONS = 30
const MAX_LOCALSTORAGE_CHARS = 4_000_000 // ~4MB de margem

const sessions = ref([]) // [{id,title,createdAt,updatedAt,plainText,quillDelta,cards,documentContext}]
const activeSessionId = ref(null)
const isRestoringSession = ref(false)

const savedSessionExists = computed(() => sessions.value.length > 0)

function loadSessions() {
  try {
    const raw = localStorage.getItem(LS_SESSIONS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []

    return parsed
      .map((s) => ({
        id: typeof s.id === 'string' ? s.id : safeId(),
        title: typeof s.title === 'string' ? s.title : 'Sessão',
        createdAt: typeof s.createdAt === 'string' ? s.createdAt : new Date().toISOString(),
        updatedAt: typeof s.updatedAt === 'string' ? s.updatedAt : new Date().toISOString(),
        plainText: typeof s.plainText === 'string' ? s.plainText : '',
        quillDelta: s.quillDelta ?? null,
        cards: Array.isArray(s.cards) ? s.cards : [],
        documentContext: typeof s.documentContext === 'string' ? s.documentContext : ''
      }))
      .slice(0, MAX_SESSIONS)
  } catch {
    return []
  }
}

function persistSessions(list) {
  try {
    const capped = list.slice(0, MAX_SESSIONS)
    const raw = JSON.stringify(capped)
    if (raw.length > MAX_LOCALSTORAGE_CHARS) {
      // Não trava o app, só alerta e não salva
      notify('Conteúdo muito grande — não foi possível salvar a sessão no localStorage.', 'warn', 6000)
      return
    }
    localStorage.setItem(LS_SESSIONS_KEY, raw)
  } catch {
    // storage negado/cheio
    notify('Falha ao salvar sessão (storage indisponível).', 'warn', 5000)
  }
}

function loadActiveSessionId() {
  try {
    const id = localStorage.getItem(LS_ACTIVE_SESSION_KEY)
    return id || null
  } catch {
    return null
  }
}

function persistActiveSessionId(id) {
  try {
    if (!id) localStorage.removeItem(LS_ACTIVE_SESSION_KEY)
    else localStorage.setItem(LS_ACTIVE_SESSION_KEY, id)
  } catch {}
}

function getSessionById(id) {
  return sessions.value.find((s) => s.id === id) || null
}

function upsertSession(session) {
  const now = new Date().toISOString()
  const next = { ...session, updatedAt: now }

  const idx = sessions.value.findIndex((s) => s.id === next.id)
  if (idx >= 0) sessions.value.splice(idx, 1, next)
  else sessions.value.unshift(next)

  // mantém ordenado por "updatedAt" desc
  sessions.value.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
  sessions.value = sessions.value.slice(0, MAX_SESSIONS)

  persistSessions(sessions.value)
}

function deleteSessionById(id) {
  sessions.value = sessions.value.filter((s) => s.id !== id)
  persistSessions(sessions.value)

  if (activeSessionId.value === id) {
    activeSessionId.value = sessions.value[0]?.id || null
    persistActiveSessionId(activeSessionId.value)
  }
}

function clearAllSessions() {
  sessions.value = []
  activeSessionId.value = null
  persistActiveSessionId(null)
  try {
    localStorage.removeItem(LS_SESSIONS_KEY)
  } catch {}
}

function ensureActiveSession() {
  if (activeSessionId.value) return activeSessionId.value

  const id = safeId()
  activeSessionId.value = id
  persistActiveSessionId(id)

  upsertSession({
    id,
    title: 'Nova sessão',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    plainText: '',
    quillDelta: null,
    cards: [],
    documentContext: ''
  })
  return id
}

function buildActiveSessionSnapshot() {
  const id = ensureActiveSession()
  const base = getSessionById(id)

  const plainText = String(lastFullText.value || '')
  const title = sessionTitleFromText(plainText)

  // pega delta preferencialmente do último evento; se faltar, consulta o editor
  const delta = lastEditorDelta.value ?? editorRef.value?.getDelta?.() ?? null

  return {
    id,
    title,
    createdAt: base?.createdAt || new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    plainText,
    quillDelta: delta,
    cards: cards.value,
    documentContext: documentContext.value
  }
}

let persistSessionTimer = null
function schedulePersistActiveSession() {
  if (isRestoringSession.value) return
  if (persistSessionTimer) clearTimeout(persistSessionTimer)
  persistSessionTimer = setTimeout(() => {
    const snap = buildActiveSessionSnapshot()

    // não salva sessão totalmente vazia
    const hasAny =
      normalizePlainText(snap.plainText).length > 0 ||
      (Array.isArray(snap.cards) && snap.cards.length > 0) ||
      normalizePlainText(snap.documentContext).length > 0

    if (!hasAny) return
    upsertSession(snap)
  }, 350)
}

async function restoreSessionById(id) {
  const s = getSessionById(id)
  if (!s) {
    notify('Sessão não encontrada.', 'warn', 4000)
    return
  }

  isRestoringSession.value = true
  try {
    activeSessionId.value = s.id
    persistActiveSessionId(s.id)

    // restaura editor (texto + marcações)
    editorRef.value?.setDelta?.(s.quillDelta)

    // restaura cards + contexto
    cards.value = Array.isArray(s.cards) ? s.cards : []
    documentContext.value = s.documentContext || ''

    // sincroniza “last*”
    lastFullText.value = s.plainText || ''
    lastEditorDelta.value = s.quillDelta ?? null
    lastEditorHtml.value = '' // não é essencial persistir html
    lastTextForAnalysis.value = normalizePlainText(s.plainText || '')

    await nextTick()
    notify(`Sessão restaurada: ${s.title}`, 'success', 3200)
  } finally {
    // solta o lock após o Quill emitir seus eventos de setContents
    setTimeout(() => {
      isRestoringSession.value = false
    }, 0)
  }
}

function clearCurrentSession() {
  const id = activeSessionId.value

  // limpa UI
  cards.value = []
  documentContext.value = ''
  lastFullText.value = ''
  lastEditorDelta.value = null
  lastEditorHtml.value = ''
  lastTextForAnalysis.value = ''

  // limpa editor (texto + marcações)
  editorRef.value?.setDelta?.(null)

  // remove sessão atual do storage (se existir)
  if (id) {
    deleteSessionById(id)
  }

  // cria uma nova sessão vazia como “ativa”
  activeSessionId.value = null
  persistActiveSessionId(null)
  ensureActiveSession()

  notify('Sessão atual limpa.', 'info', 3000)
}

function newSession() {
  // garante que a sessão atual foi persistida antes de trocar
  schedulePersistActiveSession()

  // limpa UI/editor e cria nova sessão
  cards.value = []
  documentContext.value = ''
  lastFullText.value = ''
  lastEditorDelta.value = null
  lastEditorHtml.value = ''
  lastTextForAnalysis.value = ''

  editorRef.value?.setDelta?.(null)

  activeSessionId.value = safeId()
  persistActiveSessionId(activeSessionId.value)

  upsertSession({
    id: activeSessionId.value,
    title: 'Nova sessão',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    plainText: '',
    quillDelta: null,
    cards: [],
    documentContext: ''
  })

  notify('Nova sessão criada.', 'success', 2200)
}

// ============================================================
// Estado do App
// ============================================================
const cards = ref([])
const selectedText = ref('')
const documentContext = ref('')
const isAnalyzing = ref(false)

const decks = ref({})
const currentDeck = ref(null)
const ankiModelsData = ref(null)

// Editor tracking
const lastFullText = ref('')
const lastEditorDelta = ref(null)
const lastEditorHtml = ref('')
const lastTextForAnalysis = ref('') // texto analisado por último (normalizado)
const lastNormalizedTextOnChange = ref('') // para detectar mudanças reais sem depender do isTextMutation
const hasDocumentContext = computed(() => !!documentContext.value)

// Chaves
const storedKeys = ref(getStoredApiKeys())
function refreshStoredKeys() {
  storedKeys.value = getStoredApiKeys()
}

// Card type
const cardType = ref('basic')
const cardTypeOptions = [
  { label: 'Gerar Cartões Básicos', value: 'basic' },
  { label: 'Gerar Cartões Cloze', value: 'cloze' },
  { label: 'Gerar Cartões Básicos e Cloze', value: 'both' }
]

// Busca
const cardSearch = ref('')
const filteredCards = computed(() => {
  const q = (cardSearch.value || '').trim().toLowerCase()
  if (!q) return cards.value
  return cards.value.filter((c) => {
    const f = String(c.front || '').toLowerCase()
    const b = String(c.back || '').toLowerCase()
    const d = String(c.deck || '').toLowerCase()
    return f.includes(q) || b.includes(q) || d.includes(q)
  })
})

// ============================================================
// Timer (processingTimer)
// ============================================================
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

// ============================================================
// Logs
// ============================================================
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

// ============================================================
// Progress Dialog
// ============================================================
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

// ============================================================
// API Keys Dialog
// ============================================================
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

// ============================================================
// Decks Mochi
// ============================================================
async function fetchDecks() {
  refreshStoredKeys()
  const userMochiKey = storedKeys.value.mochiApiKey

  if (!userMochiKey) {
    decks.value = { General: 'general' }
    currentDeck.value = 'General'
    return
  }

  // backend
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
  } catch {}

  // client-side
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

  decks.value = { General: 'general' }
  currentDeck.value = 'General'
}

// ============================================================
// Analyze (debounce) — NÃO reanalisa quando é só highlight
// ============================================================
let analyzeDebounce = null
function scheduleAnalyze(fullText) {
  if (analyzeDebounce) clearTimeout(analyzeDebounce)
  analyzeDebounce = setTimeout(() => {
    const normalized = normalizePlainText(fullText)
    if (normalized.length > 100 && !isAnalyzing.value) {
      // evita análise redundante do mesmo texto
      if (normalized === lastTextForAnalysis.value) return
      analyzeDocumentContext(fullText)
    }
  }, 1200)
}

async function analyzeDocumentContext(text) {
  const normalized = normalizePlainText(text)
  if (!normalized || normalized.length < 100 || isAnalyzing.value) return

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

    // marca o texto analisado
    lastTextForAnalysis.value = normalized

    stopTimer()
    completeProgress()
    notify('Análise concluída. A qualidade dos cards tende a melhorar.', 'success', 3800)

    // persistir sessão (contexto mudou)
    schedulePersistActiveSession()
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

// ============================================================
// Gerar cards
// ============================================================
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

// ============================================================
// CRUD cards
// ============================================================
function deleteCard(index) {
  cards.value.splice(index, 1)
}

function clearAllCards() {
  cards.value = []
  notify('Cards limpos (apenas UI).', 'info', 2500)
}

// ============================================================
// Preview bonito + edição ao clicar (Dialog)
// ============================================================
const editVisible = ref(false)
const editIndex = ref(-1)
const editDraft = ref({ front: '', back: '', deck: 'General' })

const availableDeckNames = computed(() => {
  const names = Object.keys(decks.value || {})
  return names.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

function openEditCard(index) {
  const c = cards.value[index]
  if (!c) return
  editIndex.value = index
  editDraft.value = {
    front: String(c.front ?? ''),
    back: String(c.back ?? ''),
    deck: String(c.deck ?? 'General')
  }
  editVisible.value = true
}

function saveEditCard() {
  const idx = editIndex.value
  if (idx < 0) return
  cards.value[idx] = {
    ...cards.value[idx],
    front: editDraft.value.front,
    back: editDraft.value.back,
    deck: editDraft.value.deck || 'General'
  }
  editVisible.value = false
  notify('Card atualizado', 'success', 2000)
}

function duplicateEditCard() {
  const idx = editIndex.value
  if (idx < 0) return
  const c = cards.value[idx]
  cards.value.splice(idx + 1, 0, { ...c })
  notify('Card duplicado', 'success', 2000)
}

function deleteEditCard() {
  const idx = editIndex.value
  if (idx < 0) return
  cards.value.splice(idx, 1)
  editVisible.value = false
  notify('Card removido', 'info', 2000)
}

// Markdown “safe”
function escapeHtml(s) {
  return String(s || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function renderMarkdownSafe(text) {
  let t = escapeHtml(text)

  // inline code
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>')

  // bold / italic
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/\*([^*]+)\*/g, '<em>$1</em>')

  // cloze highlight {{c1::...}}
  t = t.replace(/\{\{c\d+::([^}]+)\}\}/g, '<span class="cloze">$1</span>')

  // normalize newlines
  t = t.replace(/\r\n/g, '\n')

  // listas simples (- item)
  const lines = t.split('\n')
  let inList = false
  const out = []

  for (const line of lines) {
    const m = line.match(/^\s*-\s+(.*)$/)
    if (m) {
      if (!inList) {
        out.push('<ul>')
        inList = true
      }
      out.push(`<li>${m[1]}</li>`)
    } else {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push(line.length ? `<p>${line}</p>` : '<br/>')
    }
  }
  if (inList) out.push('</ul>')

  return out.join('')
}

function previewText(text, max = 260) {
  const s = String(text || '').trim().replace(/\s+/g, ' ')
  if (s.length <= max) return s
  return s.slice(0, max - 1) + '…'
}

// ============================================================
// Export Mochi / Markdown
// ============================================================
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
    notify('Erro no Mochi. Exportando em markdown.', 'error')
    exportAsMarkdown()
  } finally {
    progressVisible.value = false
  }
}

// ============================================================
// Anki
// ============================================================
const ankiVisible = ref(false)
const ankiModel = ref('')
const ankiFrontField = ref('')
const ankiBackField = ref('')
const ankiDeckField = ref('')
const ankiTags = ref('')
const ankiExporting = ref(false)

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
  return (d.models[ankiModel.value] || []).map((f) => ({ label: f, value: f }))
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
    showProgress('Carregando modelos do Anki...')
    setProgress(30)

    const resp = await fetch('/api/anki-models')
    if (!resp.ok) throw new Error('Não foi possível conectar no Anki. Verifique Anki + AnkiConnect.')

    const data = await resp.json()
    ankiModelsData.value = data
    ankiModel.value = Object.keys(data.models || {})[0] || ''

    setProgress(100)
    completeProgress()
    ankiVisible.value = true
  } catch (e) {
    notify(e?.message || String(e), 'error', 8000)
  } finally {
    progressVisible.value = false
  }
}

async function exportToAnkiConfirm() {
  try {
    ankiExporting.value = true
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
    notify(`${result.totalSuccess} de ${result.totalCards} enviados ao Anki!`, 'success')
    ankiVisible.value = false
  } catch (e) {
    notify('Erro ao enviar ao Anki: ' + (e?.message || String(e)), 'error', 8000)
  } finally {
    ankiExporting.value = false
    progressVisible.value = false
  }
}

// ============================================================
// Header menus
// ============================================================

// Menu principal (ellipsis)
const menuRef = ref(null)
const menuItems = computed(() => [
  {
    label: exportLabel.value,
    icon: 'pi pi-upload',
    disabled: !cards.value.length,
    command: exportToMochi
  },
  {
    label: 'Export to Anki',
    icon: 'pi pi-send',
    disabled: !cards.value.length,
    command: exportToAnkiOpenConfig
  },
  {
    label: 'Clear Cards (apenas UI)',
    icon: 'pi pi-times',
    disabled: !cards.value.length,
    command: clearAllCards
  },
  { separator: true },
  { label: 'API Keys', icon: 'pi pi-key', command: openApiKeys }
])

function toggleMenu(event) {
  menuRef.value?.toggle(event)
}

// Menu de sessões (selecionar/restaurar)
const sessionsMenuRef = ref(null)
function toggleSessionsMenu(event) {
  sessionsMenuRef.value?.toggle(event)
}

const sessionsMenuItems = computed(() => {
  const sorted = [...sessions.value].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))

  const restoreItems = sorted.length
    ? sorted.map((s) => ({
        label: `${s.title} — ${formatSessionStamp(s.updatedAt)}`,
        icon: s.id === activeSessionId.value ? 'pi pi-check' : 'pi pi-file',
        command: () => restoreSessionById(s.id)
      }))
    : [{ label: 'Nenhuma sessão salva', icon: 'pi pi-inbox', disabled: true }]

  return [
    { label: 'Nova sessão', icon: 'pi pi-plus', command: newSession },
    { separator: true },
    { label: 'Restaurar sessão', icon: 'pi pi-history', disabled: true },
    ...restoreItems,
    { separator: true },
    {
      label: 'Limpar sessão atual (UI + storage)',
      icon: 'pi pi-times',
      command: clearCurrentSession
    },
    {
      label: 'Limpar todas as sessões',
      icon: 'pi pi-ban',
      command: () => {
        clearAllSessions()
        clearCurrentSession()
      }
    }
  ]
})

// ============================================================
// Context menu do editor
// ============================================================
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
  const normalized = normalizePlainText(fullText)
  if (normalized.length > 100) await analyzeDocumentContext(fullText)
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
  { label: 'Remover marcação', disabled: !contextHasHighlight.value, command: contextRemoveHighlight },
  { separator: true },
  { label: 'Analisar texto novamente', command: contextAnalyze },
  { separator: true },
  { label: 'Gerar cartão básico', disabled: !contextHasSelection.value, command: () => contextGenerate('basic') },
  { label: 'Gerar cartão cloze', disabled: !contextHasSelection.value, command: () => contextGenerate('cloze') }
])

// ============================================================
// Eventos do editor
// ============================================================
function onSelectionChanged(payload) {
  selectedText.value = payload.selectedText || ''
}

function onContentChanged(payload) {
  if (isRestoringSession.value) return

  const fullText = payload?.fullText ?? ''
  const html = payload?.html ?? ''
  const delta = payload?.delta ?? null
  const isTextMutationFromEditor = payload?.isTextMutation // pode vir undefined se seu QuillEditor ainda não emite

  lastFullText.value = fullText
  lastEditorHtml.value = html
  if (delta) lastEditorDelta.value = delta

  // persiste sempre (inclusive highlights)
  schedulePersistActiveSession()

  // NÃO reanalisa ao marcar highlight:
  // 1) se o editor informou que não houve mutação de texto, sai
  if (isTextMutationFromEditor === false) return

  // 2) fallback seguro: se o texto normalizado não mudou, foi formatação
  const normalized = normalizePlainText(fullText)
  if (normalized === lastNormalizedTextOnChange.value) return
  lastNormalizedTextOnChange.value = normalized

  // análise só se há texto suficiente
  if (normalized.length > 100) scheduleAnalyze(fullText)
}

// ============================================================
// Computeds úteis
// ============================================================
const hasSelection = computed(() => (selectedText.value || '').trim().length > 0)
const hasCards = computed(() => cards.value.length > 0)

// ============================================================
// Autosave (cards/contexto)
// ============================================================
watch(
  cards,
  () => {
    if (isRestoringSession.value) return
    schedulePersistActiveSession()
  },
  { deep: true }
)

watch(documentContext, () => {
  if (isRestoringSession.value) return
  schedulePersistActiveSession()
})

// ============================================================
// Lifecycle
// ============================================================
let globalKeyHandler = null

onMounted(async () => {
  // carrega storage (sessões + ativa)
  sessions.value = loadSessions()
  activeSessionId.value = loadActiveSessionId()

  // se não tem ativa, cria uma
  ensureActiveSession()

  loadStoredKeysToForm()
  try {
    await fetchDecks()
  } catch {}

  if (sessions.value.length && !cards.value.length && !normalizePlainText(lastFullText.value)) {
    notify('Sessões encontradas. Use “Sessões” para restaurar.', 'info', 4500)
  }

  // Ctrl+Enter gera
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
  if (persistSessionTimer) clearTimeout(persistSessionTimer)
  if (globalKeyHandler) window.removeEventListener('keydown', globalKeyHandler)
})
</script>

<template>
  <Toast />
  <ContextMenu ref="contextMenuRef" :model="contextMenuModel" appendTo="body" />

  <!-- Menu popup de sessões -->
  <Menu ref="sessionsMenuRef" :model="sessionsMenuItems" popup />

  <div class="app-shell" :class="{ 'has-context': hasDocumentContext }">
    <!-- HEADER -->
    <Toolbar class="app-header">
      <template #start>
        <div class="header-left">
          <div class="brand">
            <div class="brand-icon">
              <img class="brand-icon-img" src="/green.svg" alt="Green Deck" />
            </div>

            <div class="brand-text">
              <img class="brand-header-logo" src="/green-header.svg" alt="Green Deck" />
              <div class="brand-subtitle">
                Selecione um trecho no editor para habilitar “Create Cards”. (Ctrl+Enter)
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

            <Tag v-if="savedSessionExists" severity="info" class="pill">
              <i class="pi pi-history mr-2" /> Sessões: {{ sessions.length }}
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
              icon="pi pi-database"
              label="Browser"
              severity="secondary"
              outlined
              @click="router.push('/browser')"
            />

            <Button
              icon="pi pi-history"
              label="Sessões"
              severity="secondary"
              outlined
              :disabled="!savedSessionExists"
              @click="toggleSessionsMenu"
            />

            <Button
              icon="pi pi-times"
              label="Limpar sessão"
              severity="danger"
              outlined
              @click="clearCurrentSession"
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

        <!-- Cards -->
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

                <Button :disabled="!hasCards" :label="exportLabel" icon="pi pi-upload" outlined @click="exportToMochi" />
                <Button :disabled="!hasCards" label="Anki" icon="pi pi-send" outlined @click="exportToAnkiOpenConfig" />
              </div>
            </div>

            <div class="panel-body output-body">
              <div v-if="!hasCards" class="empty-state">
                <div class="empty-icon">✨</div>
                <div class="empty-title">Nenhum card ainda</div>
                <div class="empty-subtitle">
                  Cole um texto, selecione um trecho e gere cards. Você pode marcar trechos com clique direito.
                </div>

                <div class="empty-actions">
                  <Button
                    icon="pi pi-history"
                    label="Sessões"
                    outlined
                    :disabled="!savedSessionExists"
                    @click="toggleSessionsMenu"
                  />
                  <Button icon="pi pi-times" label="Limpar sessão" severity="danger" outlined @click="clearCurrentSession" />
                </div>
              </div>

              <DataView v-else :value="filteredCards" layout="list" class="cards-view">
                <template #list="{ items }">
                  <div class="cards-list">
                    <Card
                      v-for="(c, i) in items"
                      :key="i"
                      class="card-item clickable"
                      @click="openEditCard(cards.indexOf(c))"
                    >
                      <template #title>
                        <div class="card-head">
                          <div class="card-left">
                            <span class="card-index">Card {{ cards.indexOf(c) + 1 }}</span>
                            <span class="deck-pill">
                              <i class="pi pi-tag mr-2" /> {{ c.deck || 'General' }}
                            </span>
                          </div>

                          <Button
                            icon="pi pi-times"
                            severity="danger"
                            text
                            class="icon-only"
                            title="Excluir"
                            @click.stop="deleteCard(cards.indexOf(c))"
                          />
                        </div>
                      </template>

                      <template #content>
                        <div class="preview-grid">
                          <div class="preview-block">
                            <div class="preview-label">Front</div>
                            <div class="preview-text" v-html="renderMarkdownSafe(previewText(c.front, 300))"></div>
                          </div>

                          <div class="preview-block">
                            <div class="preview-label">Back</div>
                            <div class="preview-text" v-html="renderMarkdownSafe(previewText(c.back, 300))"></div>
                          </div>
                        </div>

                        <div class="preview-hint">
                          <i class="pi pi-pen-to-square mr-2" />
                          Clique no card para editar
                        </div>
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

    <!-- EDIT DIALOG -->
    <Dialog v-model:visible="editVisible" header="Editar Card" modal class="modern-dialog" style="width: min(980px, 96vw);">
      <div class="edit-meta">
        <Tag severity="info" class="pill">
          <i class="pi pi-hashtag mr-2" /> {{ editIndex + 1 }}
        </Tag>

        <Tag severity="secondary" class="pill">
          <i class="pi pi-tag mr-2" /> Deck
        </Tag>

        <Select
          v-model="editDraft.deck"
          :options="availableDeckNames.map(x => ({ label: x, value: x }))"
          optionLabel="label"
          optionValue="value"
          class="deck-select"
          filter
          placeholder="General"
        />

        <Button icon="pi pi-refresh" severity="secondary" outlined @click="fetchDecks" title="Atualizar decks" />
      </div>

      <div class="grid mt-2">
        <div class="col-12 md:col-6">
          <div class="field-title">Front</div>
          <Textarea v-model="editDraft.front" autoResize class="w-full field-area" />
        </div>
        <div class="col-12 md:col-6">
          <div class="field-title">Back</div>
          <Textarea v-model="editDraft.back" autoResize class="w-full field-area" />
        </div>
      </div>

      <Divider />

      <div class="grid">
        <div class="col-12 md:col-6">
          <div class="field-title">Preview Front</div>
          <div class="md-preview" v-html="renderMarkdownSafe(editDraft.front)"></div>
        </div>
        <div class="col-12 md:col-6">
          <div class="field-title">Preview Back</div>
          <div class="md-preview" v-html="renderMarkdownSafe(editDraft.back)"></div>
        </div>
      </div>

      <template #footer>
        <Button label="Duplicar" icon="pi pi-copy" severity="secondary" outlined @click="duplicateEditCard" />
        <Button label="Excluir" icon="pi pi-trash" severity="danger" outlined @click="deleteEditCard" />
        <Button label="Cancelar" icon="pi pi-times" severity="secondary" outlined @click="editVisible = false" />
        <Button label="Salvar" icon="pi pi-check" @click="saveEditCard" />
      </template>
    </Dialog>

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

:deep(.cta.p-button) {
  border-radius: 999px;
  box-shadow: 0 10px 24px rgba(0,0,0,0.22);
}

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

/* Splitter */
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

/* Search */
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

/* Empty */
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
.empty-actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}

/* Cards preview */
.cards-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.card-item :deep(.p-card) {
  border-radius: 16px;
}
.card-item :deep(.p-card-body) {
  padding: 14px;
}
.clickable {
  cursor: pointer;
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
  font-weight: 900;
  opacity: 0.92;
}
.deck-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(148,163,184,0.18);
  font-weight: 800;
  font-size: 12px;
  opacity: 0.95;
}
.preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 920px) {
  .preview-grid {
    grid-template-columns: 1fr;
  }
  .cardtype { width: 100%; }
  .search-wrap { width: 100%; }
}
.preview-block {
  border-radius: 14px;
  padding: 10px 12px;
  border: 1px solid rgba(148,163,184,0.14);
  background: rgba(255,255,255,0.03);
}
.preview-label {
  font-weight: 900;
  font-size: 12px;
  opacity: 0.75;
  margin-bottom: 8px;
}
.preview-text {
  font-size: 13.5px;
  line-height: 1.35;
  opacity: 0.92;
}
.preview-hint {
  margin-top: 10px;
  font-size: 12px;
  opacity: 0.7;
  display: flex;
  align-items: center;
}

/* markdown-ish */
.preview-text :deep(code),
.md-preview :deep(code) {
  padding: 2px 6px;
  border-radius: 8px;
  background: rgba(0,0,0,0.35);
  border: 1px solid rgba(148,163,184,0.18);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
}
.preview-text :deep(ul),
.md-preview :deep(ul) {
  margin: 8px 0 0 18px;
}
.preview-text :deep(p),
.md-preview :deep(p) {
  margin: 0 0 6px 0;
}
.preview-text :deep(.cloze),
.md-preview :deep(.cloze) {
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(251, 191, 36, 0.18);
  border: 1px solid rgba(251, 191, 36, 0.35);
  font-weight: 900;
}

/* Edit dialog */
.edit-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.deck-select {
  width: min(320px, 100%);
}
.field-title {
  font-weight: 900;
  opacity: 0.85;
  margin-bottom: 6px;
}
.field-area :deep(textarea) {
  border-radius: 14px;
}
.md-preview {
  border-radius: 14px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.14);
  background: rgba(255,255,255,0.03);
  min-height: 120px;
  font-size: 13.5px;
  line-height: 1.35;
  opacity: 0.92;
}

/* Dialogs */
.disclaimer {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.05);
  margin-bottom: 14px;
}
.req { color: #ef4444; font-weight: 900; margin-left: 6px; }
.opt { opacity: 0.7; margin-left: 6px; }
.err { color: #ef4444; margin-top: 8px; font-weight: 800; }

/* Logs */
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
.log-ts { opacity: 0.7; white-space: nowrap; }
.log-msg { opacity: 0.92; }
.log-row.t-success { border-color: rgba(16, 185, 129, 0.25); }
.log-row.t-error { border-color: rgba(239, 68, 68, 0.25); }

/* Pills */
.pill {
  border-radius: 999px;
  font-weight: 900;
}
.pill.subtle { opacity: 0.9; }

.brand-icon-img {
  width: 30px;
  height: 30px;
  display: block;
}

.brand-header-logo {
  height: 34px;   /* ajuste fino aqui (32–42 costuma ficar ótimo) */
  width: auto;
  display: block;
  user-select: none;
  -webkit-user-drag: none;
}

@media (max-width: 520px) {
  .brand-header-logo {
    height: 28px;
  }
}

</style>
