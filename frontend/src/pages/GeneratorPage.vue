<!-- frontend/src/pages/GeneratorPage.vue -->
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
import OllamaStatus from '@/components/OllamaStatus.vue'
import { useRouter } from 'vue-router'

// Services
import {
  generateCardsWithStream,
  analyzeText,
  getStoredApiKeys,
  storeApiKeys,
  validateAnthropicApiKey
} from '@/services/api.js'

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

function getCardType(front) {
  const q = String(front || '').trim()
  return q.includes('{{c1::') ? 'cloze' : 'basic'
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

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n))
}

// ============================================================
// Modo Leitura (Kindle full-screen + paginação real)
// Melhorias:
// - scroller = .ql-container (padding no container)
// - step correto = (contentWidth + gap)
// - snap suave após scroll
// - tema kindle claro só no campo de leitura/edição (header intacto)
// ============================================================
const LS_READER_KEY = 'spaced-rep.reader.v2'
const immersiveReader = ref(false)
const readerTwoPage = ref(true) // "spread" (2 páginas) quando a tela permitir
const readerFontScale = ref(1) // 1.0 = normal
const readerDark = ref(false) // false = Kindle (claro); true = "como está agora" (escuro)

const readerSurfaceRef = ref(null) // wrapper DOM em volta do QuillEditor
const readerScrollerEl = ref(null) // ✅ .ql-container (scroll horizontal)
const readerPage = ref(1)
const readerTotalPages = ref(1)

const readerGapPx = ref(56)
const readerPadXPx = ref(64)
const readerPadYPx = ref(48)
const readerPageWidthPx = ref(680)

// ✅ stride real entre páginas/spreads
const readerStepPx = ref(0)

const isKindleTheme = computed(() => immersiveReader.value && !readerDark.value)

const readerVars = computed(() => ({
  '--reader-scale': String(readerFontScale.value),
  '--reader-gap': `${readerGapPx.value}px`,
  '--reader-pad-x': `${readerPadXPx.value}px`,
  '--reader-pad-y': `${readerPadYPx.value}px`,
  '--reader-page-width': `${readerPageWidthPx.value}px`
}))

function toggleReader() {
  immersiveReader.value = !immersiveReader.value
  if (immersiveReader.value) {
    nextTick(() => {
      editorRef.value?.focus?.()
    })
  }
}

function toggleReaderTheme() {
  readerDark.value = !readerDark.value
  requestReaderLayout({ preserveProgress: true })
}

function readerFontMinus() {
  const progress = getReaderProgress()
  readerFontScale.value = clamp(Number(readerFontScale.value) - 0.05, 0.85, 1.6)
  nextTick(() => {
    requestReaderLayout({ preserveProgress: true, explicitProgress: progress })
  })
}
function readerFontPlus() {
  const progress = getReaderProgress()
  readerFontScale.value = clamp(Number(readerFontScale.value) + 0.05, 0.85, 1.6)
  nextTick(() => {
    requestReaderLayout({ preserveProgress: true, explicitProgress: progress })
  })
}
function toggleTwoPage() {
  const progress = getReaderProgress()
  readerTwoPage.value = !readerTwoPage.value
  nextTick(() => {
    requestReaderLayout({ preserveProgress: true, explicitProgress: progress })
  })
}

// ✅ scroller agora é o container do Quill
function resolveReaderScroller() {
  const host = readerSurfaceRef.value
  if (!host?.querySelector) return null
  return host.querySelector('.ql-container') || null
}

function attachReaderScroller() {
  const el = resolveReaderScroller()
  readerScrollerEl.value = el
  if (!el) return
  el.addEventListener('scroll', onReaderScroll, { passive: true })
  requestReaderLayout({ preserveProgress: true })
}

function detachReaderScroller() {
  const el = readerScrollerEl.value
  if (!el) return
  el.removeEventListener('scroll', onReaderScroll)
  readerScrollerEl.value = null
}

let readerScrollRaf = null
let readerSnapTimer = null

function onReaderScroll() {
  if (!immersiveReader.value) return

  if (readerScrollRaf) cancelAnimationFrame(readerScrollRaf)
  readerScrollRaf = requestAnimationFrame(() => {
    updateReaderPageStats()
  })

  // ✅ snap “macio” para a página mais próxima após o usuário parar de rolar
  if (readerSnapTimer) clearTimeout(readerSnapTimer)
  readerSnapTimer = setTimeout(() => {
    snapReaderToNearestPage()
  }, 140)
}

function computeReaderLayoutMetrics() {
  const el = readerScrollerEl.value
  if (!el) return

  const viewW = Math.max(1, el.clientWidth || 1)
  const padX = readerPadXPx.value
  const gap = readerGapPx.value

  const contentW = Math.max(320, viewW - 2 * padX)

  // ✅ decide spread baseado no contentW (e não no viewW bruto)
  const allowSpread = readerTwoPage.value && contentW >= 900
  const pageW = allowSpread ? Math.floor((contentW - gap) / 2) : Math.floor(contentW)

  readerPageWidthPx.value = clamp(pageW, 320, 1400)

  // ✅ stride real: largura do “conteúdo visível” + gap
  readerStepPx.value = Math.max(1, Math.floor(contentW + gap))
}

function updateReaderPageStats() {
  const el = readerScrollerEl.value
  if (!el) {
    readerPage.value = 1
    readerTotalPages.value = 1
    return
  }

  if (!readerStepPx.value) computeReaderLayoutMetrics()
  const step = Math.max(1, readerStepPx.value)

  const maxScroll = Math.max(0, (el.scrollWidth || el.clientWidth) - el.clientWidth)
  const total = Math.max(1, Math.ceil(maxScroll / step) + 1)

  const current = clamp(Math.round((el.scrollLeft || 0) / step) + 1, 1, total)

  readerTotalPages.value = total
  readerPage.value = current
}

function snapReaderToNearestPage() {
  const el = readerScrollerEl.value
  if (!el || !immersiveReader.value) return

  if (!readerStepPx.value) computeReaderLayoutMetrics()
  const step = Math.max(1, readerStepPx.value)

  const maxScroll = Math.max(0, (el.scrollWidth || el.clientWidth) - el.clientWidth)
  const maxIdx = Math.max(0, Math.ceil(maxScroll / step))
  const idx = clamp(Math.round((el.scrollLeft || 0) / step), 0, maxIdx)
  const target = Math.min(idx * step, maxScroll)

  el.scrollTo({ left: target, top: 0, behavior: 'smooth' })
}

function getReaderProgress() {
  const el = readerScrollerEl.value
  if (!el) return 0
  const maxScroll = Math.max(1, (el.scrollWidth || el.clientWidth) - el.clientWidth)
  return clamp((el.scrollLeft || 0) / maxScroll, 0, 1)
}

function setReaderProgress(progress01) {
  const el = readerScrollerEl.value
  if (!el) return
  const maxScroll = Math.max(0, (el.scrollWidth || el.clientWidth) - el.clientWidth)
  const target = clamp(progress01, 0, 1) * maxScroll
  el.scrollTo({ left: target, top: 0, behavior: 'auto' })
  updateReaderPageStats()
}

function readerScrollToPage(pageNumber, behavior = 'smooth') {
  const el = readerScrollerEl.value
  if (!el) return

  if (!readerStepPx.value) computeReaderLayoutMetrics()
  const step = Math.max(1, readerStepPx.value)

  const maxScroll = Math.max(0, (el.scrollWidth || el.clientWidth) - el.clientWidth)
  const total = Math.max(1, Math.ceil(maxScroll / step) + 1)

  const p = clamp(pageNumber, 1, total)
  const target = Math.min((p - 1) * step, maxScroll)

  el.scrollTo({ left: target, top: 0, behavior })
  readerPage.value = p
  readerTotalPages.value = total
}

function readerPrevPage() {
  readerScrollToPage(readerPage.value - 1)
}
function readerNextPage() {
  readerScrollToPage(readerPage.value + 1)
}
function readerFirstPage() {
  readerScrollToPage(1)
}
function readerLastPage() {
  readerScrollToPage(readerTotalPages.value)
}

let readerResizeObserver = null
let winResizeHandler = null

function requestReaderLayout({ preserveProgress = false, explicitProgress = null } = {}) {
  if (!immersiveReader.value) return

  const beforeProgress = preserveProgress ? (explicitProgress ?? getReaderProgress()) : 0

  computeReaderLayoutMetrics()

  requestAnimationFrame(() => {
    if (preserveProgress) setReaderProgress(beforeProgress)
    updateReaderPageStats()
    // ✅ garante alinhamento após mudanças de fonte/1p/2p
    snapReaderToNearestPage()
  })
}

watch([immersiveReader, readerTwoPage, readerFontScale, readerDark], () => {
  try {
    localStorage.setItem(
      LS_READER_KEY,
      JSON.stringify({
        immersiveReader: immersiveReader.value,
        readerTwoPage: readerTwoPage.value,
        readerFontScale: readerFontScale.value,
        readerDark: readerDark.value
      })
    )
  } catch {}
})

// Quando entra/sai do modo leitura, prepara scroller + observer
watch(
  immersiveReader,
  async (on) => {
    if (on) {
      await nextTick()
      attachReaderScroller()

      // ResizeObserver no scroller (melhor que window.resize)
      try {
        if (readerResizeObserver) readerResizeObserver.disconnect()
        const el = readerScrollerEl.value
        if (el && 'ResizeObserver' in window) {
          readerResizeObserver = new ResizeObserver(() => {
            requestReaderLayout({ preserveProgress: true })
          })
          readerResizeObserver.observe(el)
        }
      } catch {}

      // fallback
      winResizeHandler = () => requestReaderLayout({ preserveProgress: true })
      window.addEventListener('resize', winResizeHandler)

      requestReaderLayout({ preserveProgress: true })
    } else {
      detachReaderScroller()
      if (readerResizeObserver) {
        try {
          readerResizeObserver.disconnect()
        } catch {}
        readerResizeObserver = null
      }
      if (winResizeHandler) {
        window.removeEventListener('resize', winResizeHandler)
        winResizeHandler = null
      }
      readerPage.value = 1
      readerTotalPages.value = 1
    }
  },
  { flush: 'post' }
)

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
      notify('Conteúdo muito grande — não foi possível salvar a sessão no localStorage.', 'warn', 6000)
      return
    }
    localStorage.setItem(LS_SESSIONS_KEY, raw)
  } catch {
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

    editorRef.value?.setDelta?.(s.quillDelta)

    cards.value = Array.isArray(s.cards) ? s.cards : []
    documentContext.value = s.documentContext || ''

    lastFullText.value = s.plainText || ''
    lastEditorDelta.value = s.quillDelta ?? null
    lastEditorHtml.value = ''
    lastTextForAnalysis.value = normalizePlainText(s.plainText || '')

    await nextTick()
    notify(`Sessão restaurada: ${s.title}`, 'success', 3200)

    // se estiver no leitor, recalcula páginas
    if (immersiveReader.value) requestReaderLayout({ preserveProgress: true })
  } finally {
    setTimeout(() => {
      isRestoringSession.value = false
    }, 0)
  }
}

function clearCurrentSession() {
  const id = activeSessionId.value

  cards.value = []
  documentContext.value = ''
  lastFullText.value = ''
  lastEditorDelta.value = null
  lastEditorHtml.value = ''
  lastTextForAnalysis.value = ''

  editorRef.value?.setDelta?.(null)

  if (id) {
    deleteSessionById(id)
  }

  activeSessionId.value = null
  persistActiveSessionId(null)
  ensureActiveSession()

  notify('Sessão atual limpa.', 'info', 3000)

  if (immersiveReader.value) requestReaderLayout({ preserveProgress: false })
}

function newSession() {
  schedulePersistActiveSession()

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

  if (immersiveReader.value) {
    nextTick(() => {
      requestReaderLayout({ preserveProgress: false })
      readerFirstPage()
    })
  }
}

// ============================================================
// Estado do App
// ============================================================
const cards = ref([])
const selectedText = ref('')
const documentContext = ref('')
const currentAnalysisId = ref(null)
const isAnalyzing = ref(false)

const decks = ref({})
const currentDeck = ref(null)
const ankiModelsData = ref(null)

// Editor tracking
const lastFullText = ref('')
const lastEditorDelta = ref(null)
const lastEditorHtml = ref('')
const lastTextForAnalysis = ref('')
const lastNormalizedTextOnChange = ref('')
const hasDocumentContext = computed(() => !!documentContext.value)

// Chaves
const storedKeys = ref(getStoredApiKeys())
function refreshStoredKeys() {
  storedKeys.value = getStoredApiKeys()
}

// Card type
const cardType = ref('basic')
const cardTypeOptions = ref([
  { label: 'Básicos', value: 'basic', description: 'Gerar cartões do tipo básico' },
  { label: 'Cloze', value: 'cloze', description: 'Gerar cartões Cloze (preenchimento)' },
  { label: 'Básicos + Cloze', value: 'both', description: 'Gerar ambos os tipos' }
])

// Model selection
const selectedModel = ref('qwen-flashcard')
const availableModels = ref([])
const isLoadingModels = ref(false)

// Busca
const cardSearch = ref('')
const filteredCards = computed(() => {
  const q = (cardSearch.value || '').trim().toLowerCase()
  if (!q) return cards.value
  return cards.value.filter((c) => {
    const f = String(c.front || '').toLowerCase()
    const b = String(c.back || '').toLowerCase()
    const d = String(c.deck || '').toLowerCase()
    const s = String(c.src || '').toLowerCase()
    return f.includes(q) || b.includes(q) || d.includes(q) || s.includes(q)
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
// Model Selection Dialog
// ============================================================
const modelSelectionVisible = ref(false)

async function fetchAvailableModels() {
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
  } catch (e) {
    notify('Erro ao carregar modelos disponíveis', 'error', 4000)
  } finally {
    isLoadingModels.value = false
  }
}

function openModelSelection() {
  modelSelectionVisible.value = true
  fetchAvailableModels()
}

function saveModelSelection() {
  try {
    localStorage.setItem('spaced-rep.selected-model', selectedModel.value)
    modelSelectionVisible.value = false
    notify('Modelo selecionado: ' + selectedModel.value, 'success', 3000)
  } catch (e) {
    notify('Erro ao salvar modelo', 'error', 3000)
  }
}

// ============================================================
// API Keys Dialog
// ============================================================
const apiKeyVisible = ref(false)
const anthropicApiKey = ref('')
const openaiApiKey = ref('')
const perplexityApiKey = ref('')
const storeLocally = ref(true)
const anthropicApiKeyError = ref('')

function loadStoredKeysToForm() {
  refreshStoredKeys()
  anthropicApiKey.value = storedKeys.value.anthropicApiKey || ''
  openaiApiKey.value = storedKeys.value.openaiApiKey || ''
  perplexityApiKey.value = storedKeys.value.perplexityApiKey || ''
}

function openApiKeys() {
  anthropicApiKeyError.value = ''
  loadStoredKeysToForm()
  apiKeyVisible.value = true
}

async function saveApiKeys() {
  const aKey = anthropicApiKey.value.trim()
  const oKey = openaiApiKey.value.trim()
  const pKey = perplexityApiKey.value.trim()

  if (aKey && !validateAnthropicApiKey(aKey)) {
    anthropicApiKeyError.value = 'Required: Enter a valid Claude API key (starts with sk-ant-)'
    return
  }

  const ok = storeApiKeys(aKey, oKey, pKey, storeLocally.value)
  if (!ok) {
    notify('Failed to save API keys', 'error')
    return
  }

  refreshStoredKeys()
  apiKeyVisible.value = false
  notify('API keys saved successfully', 'success')
}

// ============================================================
// Decks
// ============================================================
async function fetchDecks() {
  refreshStoredKeys()
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

    const result = await analyzeText(text)
    setProgress(92)

    addLog('Text analysis completed', 'success')
    if (result) {
      if (typeof result === 'string') {
        documentContext.value = result
      } else {
        documentContext.value = result.summary || ''
        currentAnalysisId.value = result.analysisId || null
      }
    }

    lastTextForAnalysis.value = normalized

    stopTimer()
    completeProgress()
    notify('Análise concluída. A qualidade dos cards tende a melhorar.', 'success', 3800)

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
    console.log('Card type being sent:', cardType.value)
    showProgress('Gerando cards...')
    setProgress(10)

    const deckNames = Object.keys(decks.value || {}).join(', ')
    const newCards = await generateCardsWithStream(
      text,
      deckNames,
      documentContext.value,
      cardType.value,
      selectedModel.value,
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
      },
      currentAnalysisId.value
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
const editContextMenuRef = ref(null)
const editSelectedText = ref('')
const editCustomInstructionVisible = ref(false)
const editCustomInstruction = ref('')
const editPendingCardType = ref('')
const expandedCards = ref(new Set())

const availableDeckNames = computed(() => {
  const names = Object.keys(decks.value || {})
  return names.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

const hierarchicalCards = computed(() => {
  const result = []
  const childrenMap = new Map()
  
  filteredCards.value.forEach((card, idx) => {
    const actualIdx = cards.value.indexOf(card)
    if (card.src && card.src.startsWith('Card #')) {
      const parentNum = parseInt(card.src.replace('Card #', ''))
      if (!childrenMap.has(parentNum)) childrenMap.set(parentNum, [])
      childrenMap.get(parentNum).push({ card, actualIdx })
    } else {
      result.push({ card, actualIdx, children: [] })
    }
  })
  
  result.forEach((item, idx) => {
    const cardNum = cards.value.indexOf(item.card) + 1
    item.children = childrenMap.get(cardNum) || []
  })
  
  return result
})

function toggleCardExpand(idx) {
  if (expandedCards.value.has(idx)) {
    expandedCards.value.delete(idx)
  } else {
    expandedCards.value.add(idx)
  }
}

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

function onEditTextSelect(event) {
  const selection = window.getSelection()
  const text = selection?.toString().trim() || ''
  editSelectedText.value = text
  if (text && event.button === 2) {
    event.preventDefault()
    editContextMenuRef.value?.show(event)
  }
}

function editGenerateCard(type) {
  if (!editSelectedText.value) return
  editPendingCardType.value = type
  editCustomInstructionVisible.value = true
}

async function editGenerateCardConfirm() {
  const text = editSelectedText.value
  const instruction = editCustomInstruction.value.trim()
  const type = editPendingCardType.value
  const sourceCardId = editIndex.value
  
  editCustomInstructionVisible.value = false
  editCustomInstruction.value = ''
  
  if (!text) return
  
  try {
    generating.value = true
    startTimer('Gerando...')
    showProgress('Gerando card...')
    setProgress(10)
    
    const context = instruction || documentContext.value
    const newCards = await generateCardsWithStream(
      text,
      editDraft.value.deck,
      context,
      type,
      selectedModel.value,
      ({ stage }) => {
        if (progressValue.value < 92) setProgress(progressValue.value + 4)
      },
      currentAnalysisId.value
    )
    
    newCards.forEach(card => {
      card.src = `Card #${sourceCardId + 1}`
    })
    
    cards.value = [...cards.value, ...newCards]
    notify(`${newCards.length} card(s) criado(s)`, 'success')
    completeProgress()
  } catch (error) {
    notify('Erro ao gerar: ' + (error?.message || String(error)), 'error', 8000)
  } finally {
    stopTimer()
    generating.value = false
    progressVisible.value = false
  }
}

const editContextMenuModel = computed(() => [
  {
    label: 'Gerar card Basic',
    icon: 'pi pi-plus',
    disabled: !editSelectedText.value,
    command: () => editGenerateCard('basic')
  },
  {
    label: 'Gerar card Cloze',
    icon: 'pi pi-plus',
    disabled: !editSelectedText.value,
    command: () => editGenerateCard('cloze')
  }
])

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

  t = t.replace(/`([^`]+)`/g, '<code>$1</code>')
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  t = t.replace(/\{\{c\d+::([^}]+)\}\}/g, '<span class="cloze">$1</span>')
  t = t.replace(/\r\n/g, '\n')

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
// Export Markdown
// ============================================================
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
// Sidebar Menu
// ============================================================
const sidebarOpen = ref(true)
const sidebarExpanded = ref(false)
const expandedMenus = ref(new Set())

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function toggleSidebarExpand() {
  sidebarExpanded.value = !sidebarExpanded.value
  if (!sidebarExpanded.value) {
    expandedMenus.value.clear()
  }
}

function toggleSubmenu(key) {
  if (!sidebarExpanded.value) return
  if (expandedMenus.value.has(key)) {
    expandedMenus.value.delete(key)
  } else {
    expandedMenus.value.add(key)
  }
}

function closeSidebar() {
  sidebarOpen.value = false
}

const sidebarMenuItems = computed(() => [
  {
    key: 'sessions',
    label: 'Sessões',
    icon: 'pi pi-history',
    badge: sessions.value.length,
    submenu: [
      { label: 'Nova sessão', icon: 'pi pi-plus', command: () => { newSession(); closeSidebar() } },
      { separator: true },
      ...sessions.value
        .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
        .map((s) => ({
          label: `${s.title}`,
          sublabel: formatSessionStamp(s.updatedAt),
          icon: s.id === activeSessionId.value ? 'pi pi-check' : 'pi pi-file',
          command: () => { restoreSessionById(s.id); closeSidebar() }
        })),
      { separator: true },
      { label: 'Limpar sessão atual', icon: 'pi pi-times', command: () => { clearCurrentSession(); closeSidebar() } },
      { label: 'Limpar todas', icon: 'pi pi-ban', command: () => { clearAllSessions(); clearCurrentSession(); closeSidebar() } }
    ]
  },
  {
    key: 'cards',
    label: 'Cards',
    icon: 'pi pi-clone',
    badge: cards.value.length,
    submenu: [
      { label: 'Export to Anki', icon: 'pi pi-send', disabled: !cards.value.length, command: () => { exportToAnkiOpenConfig(); closeSidebar() } },
      { label: 'Export Markdown', icon: 'pi pi-download', disabled: !cards.value.length, command: () => { exportAsMarkdown(); closeSidebar() } },
      { label: 'Clear Cards', icon: 'pi pi-times', disabled: !cards.value.length, command: () => { clearAllCards(); closeSidebar() } }
    ]
  },
  {
    key: 'config',
    label: 'Configurações',
    icon: 'pi pi-cog',
    submenu: [
      { label: 'Escolher Modelo', icon: 'pi pi-microchip', command: () => { openModelSelection(); closeSidebar() } },
      { label: 'API Keys', icon: 'pi pi-key', command: () => { openApiKeys(); closeSidebar() } }
    ]
  },
  { separator: true },
  { label: 'Browser', icon: 'pi pi-database', command: () => { router.push('/browser'); closeSidebar() } },
  { label: 'Dashboard', icon: 'pi pi-chart-bar', command: () => { router.push('/dashboard'); closeSidebar() } },
  { label: 'Logs', icon: 'pi pi-wave-pulse', command: () => { logsVisible.value = true; closeSidebar() } }
])

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
  { label: 'Gerar cartão cloze', disabled: !contextHasSelection.value, command: () => contextGenerate('cloze') },
  { label: 'Gerar ambos', disabled: !contextHasSelection.value, command: () => contextGenerate('both') }
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
  const isTextMutationFromEditor = payload?.isTextMutation

  lastFullText.value = fullText
  lastEditorHtml.value = html
  if (delta) lastEditorDelta.value = delta

  schedulePersistActiveSession()

  if (isTextMutationFromEditor === false) return

  const normalized = normalizePlainText(fullText)
  if (normalized === lastNormalizedTextOnChange.value) return
  lastNormalizedTextOnChange.value = normalized

  if (normalized.length > 100) scheduleAnalyze(fullText)

  // se estiver lendo, recalcula o layout/páginas (mantendo progresso)
  if (immersiveReader.value) {
    requestReaderLayout({ preserveProgress: true })
  }
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

  // carrega preferências do modo leitura
  try {
    const saved = JSON.parse(localStorage.getItem(LS_READER_KEY) || '{}')
    immersiveReader.value = !!saved.immersiveReader
    readerTwoPage.value = saved.readerTwoPage ?? true
    readerFontScale.value = saved.readerFontScale ?? 1
    readerDark.value = saved.readerDark ?? false
  } catch {}

  // carrega modelo selecionado
  try {
    const savedModel = localStorage.getItem('spaced-rep.selected-model')
    if (savedModel) selectedModel.value = savedModel
  } catch {}

  ensureActiveSession()

  loadStoredKeysToForm()
  try {
    await fetchDecks()
  } catch {}

  if (sessions.value.length && !cards.value.length && !normalizePlainText(lastFullText.value)) {
    notify('Sessões encontradas. Use “Sessões” para restaurar.', 'info', 4500)
  }

  // atalhos
  globalKeyHandler = (e) => {
    // ESC sai do modo leitura
    if (e.key === 'Escape' && immersiveReader.value) {
      e.preventDefault()
      immersiveReader.value = false
      return
    }

    // Paginação (modo leitura)
    if (immersiveReader.value) {
      const key = e.key

      // prev/next
      if (key === 'ArrowLeft' || key === 'PageUp') {
        e.preventDefault()
        readerPrevPage()
        return
      }
      if (key === 'ArrowRight' || key === 'PageDown' || key === ' ') {
        e.preventDefault()
        readerNextPage()
        return
      }
      if (key === 'Home') {
        e.preventDefault()
        readerFirstPage()
        return
      }
      if (key === 'End') {
        e.preventDefault()
        readerLastPage()
        return
      }

      // Ctrl +/- para fonte
      const isCtrl = e.ctrlKey || e.metaKey
      if (isCtrl && (key === '=' || key === '+')) {
        e.preventDefault()
        readerFontPlus()
        return
      }
      if (isCtrl && key === '-') {
        e.preventDefault()
        readerFontMinus()
        return
      }
    }

    // Ctrl+Enter gera cards (modo normal)
    const isCtrlEnter = (e.ctrlKey || e.metaKey) && e.key === 'Enter'
    if (!isCtrlEnter) return
    if (hasSelection.value && !generating.value && !isAnalyzing.value) {
      e.preventDefault()
      generateCardsFromSelection()
    }
  }
  window.addEventListener('keydown', globalKeyHandler)

  // Se iniciar já no modo leitura, garante layout depois de montar
  if (immersiveReader.value) {
    await nextTick()
    attachReaderScroller()
    requestReaderLayout({ preserveProgress: true })
  }
})

onBeforeUnmount(() => {
  if (timerInterval) clearInterval(timerInterval)
  if (analyzeDebounce) clearTimeout(analyzeDebounce)
  if (persistSessionTimer) clearTimeout(persistSessionTimer)
  if (globalKeyHandler) window.removeEventListener('keydown', globalKeyHandler)

  if (readerScrollRaf) cancelAnimationFrame(readerScrollRaf)
  if (readerSnapTimer) clearTimeout(readerSnapTimer)

  detachReaderScroller()
  if (readerResizeObserver) {
    try {
      readerResizeObserver.disconnect()
    } catch {}
  }
  if (winResizeHandler) {
    window.removeEventListener('resize', winResizeHandler)
  }
})
</script>

<template>
  <Toast />
  <ContextMenu ref="contextMenuRef" :model="contextMenuModel" appendTo="body" />

  <!-- Sidebar -->
  <aside v-if="sidebarOpen" class="sidebar" :class="{ 'expanded': sidebarExpanded }">
    <div class="sidebar-header">
      <img src="/green.svg" alt="Logo" class="sidebar-logo" />
      <Button 
        :icon="sidebarExpanded ? 'pi pi-chevron-left' : 'pi pi-chevron-right'" 
        text 
        rounded 
        severity="secondary"
        @click="toggleSidebarExpand" 
        class="sidebar-toggle"
        :title="sidebarExpanded ? 'Recolher' : 'Expandir'"
      />
    </div>

    <nav class="sidebar-nav">
      <template v-for="(item, idx) in sidebarMenuItems" :key="idx">
        <div v-if="item.separator" class="sidebar-separator"></div>
        
        <div v-else-if="item.submenu" class="sidebar-item has-submenu">
          <button 
            class="sidebar-link" 
            :class="{ 'expanded': expandedMenus.has(item.key) }"
            @click="toggleSubmenu(item.key)"
            :title="!sidebarExpanded ? item.label : ''"
          >
            <i :class="item.icon" class="sidebar-icon"></i>
            <span v-if="sidebarExpanded" class="sidebar-label">{{ item.label }}</span>
            <Tag v-if="sidebarExpanded && item.badge" severity="secondary" class="sidebar-badge">{{ item.badge }}</Tag>
            <i v-if="sidebarExpanded" class="pi pi-chevron-down sidebar-chevron"></i>
          </button>
          
          <Transition name="submenu">
            <div v-if="sidebarExpanded && expandedMenus.has(item.key)" class="sidebar-submenu">
              <template v-for="(sub, subIdx) in item.submenu" :key="subIdx">
                <div v-if="sub.separator" class="submenu-separator"></div>
                <button 
                  v-else
                  class="submenu-link" 
                  :class="{ 'disabled': sub.disabled }"
                  :disabled="sub.disabled"
                  @click="sub.command?.()"
                >
                  <i :class="sub.icon" class="submenu-icon"></i>
                  <div class="submenu-text">
                    <span class="submenu-label">{{ sub.label }}</span>
                    <span v-if="sub.sublabel" class="submenu-sublabel">{{ sub.sublabel }}</span>
                  </div>
                </button>
              </template>
            </div>
          </Transition>
        </div>

        <button 
          v-else 
          class="sidebar-link" 
          @click="item.command?.()"
          :title="!sidebarExpanded ? item.label : ''"
        >
          <i :class="item.icon" class="sidebar-icon"></i>
          <span v-if="sidebarExpanded" class="sidebar-label">{{ item.label }}</span>
        </button>
      </template>
    </nav>
  </aside>

  <div
    class="app-shell"
    :class="{
      'has-context': hasDocumentContext,
      'reader-mode': immersiveReader,
      'reader-kindle': immersiveReader && !readerDark,
      'reader-dark': immersiveReader && readerDark
    }"
  >
    <!-- HEADER -->
    <Toolbar class="app-header">
      <template #start>
        <div class="header-left">
          <Button icon="pi pi-bars" text rounded @click="toggleSidebar" class="menu-toggle" title="Menu" v-if="!sidebarOpen" />
          
          <div class="brand">
            <div class="brand-text">
              <img class="brand-header-logo" src="/green-header.svg" alt="Green Deck" />
              <div v-if="!immersiveReader" class="brand-subtitle">Flashcard generator powered by AI 🎈</div>
            </div>
          </div>

          <div v-if="!immersiveReader" class="header-badges">
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

          <div v-else class="header-badges">
            <Tag class="pill subtle">
              <i class="pi pi-book mr-2" /> Leitura
            </Tag>
            <Tag class="pill subtle">
              <i class="pi pi-file mr-2" /> Página {{ readerPage }} / {{ readerTotalPages }}
            </Tag>
          </div>
        </div>
      </template>

      <template #end>
        <div class="header-right">
          <div v-if="!immersiveReader" class="status-wrap">
            <div class="status-pills">
              <div class="status-item">
                <AnkiStatus />
                <span class="status-label">Anki</span>
              </div>

              <span class="status-sep" aria-hidden="true"></span>

              <div class="status-item">
                <OllamaStatus />
                <span class="status-label">Ollama</span>
              </div>
            </div>
          </div>

          <Divider v-if="!immersiveReader" layout="vertical" class="hdr-divider" />

          <div class="controls">
            <!-- Controles do modo leitura -->
            <template v-if="immersiveReader">
              <Button
                icon="pi pi-angle-double-left"
                severity="secondary"
                text
                @click="readerFirstPage"
                :disabled="readerPage <= 1"
                title="Primeira (Home)"
              />
              <Button
                icon="pi pi-angle-left"
                severity="secondary"
                text
                @click="readerPrevPage"
                :disabled="readerPage <= 1"
                title="Anterior (← / PageUp)"
              />

              <Tag class="pill subtle page-chip">
                <i class="pi pi-file mr-2" /> {{ readerPage }} / {{ readerTotalPages }}
              </Tag>

              <Button
                icon="pi pi-angle-right"
                severity="secondary"
                text
                @click="readerNextPage"
                :disabled="readerPage >= readerTotalPages"
                title="Próxima (→ / Space / PageDown)"
              />
              <Button
                icon="pi pi-angle-double-right"
                severity="secondary"
                text
                @click="readerLastPage"
                :disabled="readerPage >= readerTotalPages"
                title="Última (End)"
              />

              <Divider layout="vertical" class="hdr-divider" />

              <Button icon="pi pi-minus" severity="secondary" text @click="readerFontMinus" title="Diminuir fonte (Ctrl -)" />
              <Tag class="pill subtle">{{ Math.round(readerFontScale * 100) }}%</Tag>
              <Button icon="pi pi-plus" severity="secondary" text @click="readerFontPlus" title="Aumentar fonte (Ctrl +)" />

              <Button
                icon="pi pi-columns"
                severity="secondary"
                :outlined="!readerTwoPage"
                :text="readerTwoPage"
                @click="toggleTwoPage"
                title="Alternar 1p / 2p (spread)"
              />

              <Button
                :icon="readerDark ? 'pi pi-sun' : 'pi pi-moon'"
                severity="secondary"
                text
                @click="toggleReaderTheme"
                :title="readerDark ? 'Modo claro (Kindle)' : 'Modo escuro'"
              />

              <Button icon="pi pi-times" severity="secondary" outlined @click="toggleReader" title="Sair (Esc)" />
            </template>

            <!-- Controles normais -->
            <template v-else>
              <Button
                icon="pi pi-book"
                :label="immersiveReader ? 'Sair leitura' : 'Leitura'"
                severity="secondary"
                outlined
                @click="toggleReader"
                title="Ativar modo leitura"
              />

              <Select
                v-model="cardType"
                :options="cardTypeOptions"
                optionLabel="label"
                optionValue="value"
                class="cardtype"
                :disabled="generating || isAnalyzing"
              >
                <template #option="{ option }">
                  <div class="card-type-item">
                    <i class="pi pi-fw pi-book cardtype-icon" aria-hidden="true" />
                    <div class="ct-body">
                      <div class="ct-label">{{ option.label }}</div>
                      <div class="ct-desc">{{ option.description }}</div>
                    </div>
                  </div>
                </template>

                <template #value="{ value }">
                  <div class="card-type-selected">
                    <i class="pi pi-fw pi-book cardtype-icon" aria-hidden="true" />
                    <span class="ct-label">{{ (cardTypeOptions.find(o => o.value === value) || {}).label }}</span>
                  </div>
                </template>
              </Select>

              <Button
                icon="pi pi-bolt"
                label="Create Cards"
                class="cta"
                :disabled="!hasSelection || generating || isAnalyzing"
                :loading="generating"
                :title="hasSelection ? 'Ctrl+Enter também funciona' : 'Selecione um trecho no editor'"
                @click="generateCardsFromSelection"
              />


            </template>
          </div>

          <div v-if="processingTimerVisible && !immersiveReader" class="timer-chip">
            <span class="timer-ico">⏱️</span>
            <span class="timer-text">{{ timerText }}</span>
            <span class="timer-val">{{ timerSeconds }}s</span>
          </div>
        </div>
      </template>
    </Toolbar>

    <!-- MAIN -->
    <div class="main">
      <Splitter class="main-splitter" layout="horizontal">
        <!-- Editor -->
        <SplitterPanel :size="immersiveReader ? 100 : 70" :minSize="25">
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

            <div class="panel-body" :class="{ 'reader-body': immersiveReader }">
              <div
                ref="readerSurfaceRef"
                class="editor-surface"
                :class="{ 'reader-surface': immersiveReader }"
                :style="immersiveReader ? readerVars : null"
              >
                <QuillEditor
                  ref="editorRef"
                  @selection-changed="onSelectionChanged"
                  @content-changed="onContentChanged"
                  @context-menu="onEditorContextMenu"
                />
              </div>
            </div>
          </div>
        </SplitterPanel>

        <!-- Cards -->
        <SplitterPanel class="cards-splitter" :size="immersiveReader ? 0 : 42" :minSize="immersiveReader ? 0 : 20">
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

                <div class="export-group">
                  <Button
                    class="export-btn"
                    :disabled="!hasCards"
                    label="Export to Anki"
                    icon="pi pi-send"
                    outlined
                    @click="exportToAnkiOpenConfig"
                  />
                </div>
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
                  <Button icon="pi pi-eraser" label="Limpar sessão" severity="danger" outlined @click="clearCurrentSession" />
                </div>
              </div>

              <DataView v-else :value="hierarchicalCards" layout="list" class="cards-view">
                <template #list="{ items }">
                  <div class="cards-list">
                    <template v-for="(item, i) in items" :key="i">
                      <Card
                        class="card-item clickable"
                        @click="openEditCard(item.actualIdx)"
                      >
                        <template #title>
                          <div class="card-head">
                            <div class="card-left">
                              <Button
                                v-if="item.children.length > 0"
                                :icon="expandedCards.has(i) ? 'pi pi-chevron-down' : 'pi pi-chevron-right'"
                                text
                                rounded
                                size="small"
                                class="expand-btn"
                                @click.stop="toggleCardExpand(i)"
                              />
                              <span class="card-index">Card {{ item.actualIdx + 1 }}</span>
                              <Tag 
                                :severity="getCardType(item.card.front) === 'cloze' ? 'warning' : 'info'" 
                                class="pill card-type-tag"
                              >
                                {{ getCardType(item.card.front) === 'cloze' ? 'CLOZE' : 'BASIC' }}
                              </Tag>
                              <span class="deck-pill">
                                <i class="pi pi-tag mr-2" /> {{ item.card.deck || 'General' }}
                              </span>
                              <Tag v-if="item.children.length > 0" severity="secondary" class="pill">
                                <i class="pi pi-sitemap mr-2" /> {{ item.children.length }}
                              </Tag>
                            </div>

                            <Button
                              icon="pi pi-trash"
                              severity="danger"
                              text
                              class="icon-only"
                              title="Excluir Cartão"
                              @click.stop="deleteCard(item.actualIdx)"
                            />
                          </div>
                        </template>

                        <template #content>
                          <div class="preview-grid">
                            <div class="preview-block">
                              <div class="preview-label">Front</div>
                              <div class="preview-text" v-html="renderMarkdownSafe(previewText(item.card.front, 300))"></div>
                            </div>

                            <div class="preview-block">
                              <div class="preview-label">Back</div>
                              <div class="preview-text" v-html="renderMarkdownSafe(previewText(item.card.back, 300))"></div>
                            </div>
                          </div>

                          <div v-if="item.card.src" class="text-xs opacity-70 mt-2">
                            <strong>Fonte:</strong> {{ previewText(item.card.src, 160) }}
                          </div>

                          <div class="preview-hint">
                            <i class="pi pi-pen-to-square mr-2" />
                            Clique no card para editar
                          </div>
                        </template>
                      </Card>

                      <!-- Children cards -->
                      <Transition name="children">
                        <div v-if="expandedCards.has(i) && item.children.length > 0" class="children-container">
                          <Card
                            v-for="(child, ci) in item.children"
                            :key="ci"
                            class="card-item card-child clickable"
                            @click="openEditCard(child.actualIdx)"
                          >
                            <template #title>
                              <div class="card-head">
                                <div class="card-left">
                                  <span class="card-index">Card {{ child.actualIdx + 1 }}</span>
                                  <Tag 
                                    :severity="getCardType(child.card.front) === 'cloze' ? 'warning' : 'info'" 
                                    class="pill card-type-tag"
                                  >
                                    {{ getCardType(child.card.front) === 'cloze' ? 'CLOZE' : 'BASIC' }}
                                  </Tag>
                                  <span class="deck-pill">
                                    <i class="pi pi-tag mr-2" /> {{ child.card.deck || 'General' }}
                                  </span>
                                </div>

                                <Button
                                  icon="pi pi-trash"
                                  severity="danger"
                                  text
                                  class="icon-only"
                                  title="Excluir Cartão"
                                  @click.stop="deleteCard(child.actualIdx)"
                                />
                              </div>
                            </template>

                            <template #content>
                              <div class="preview-grid">
                                <div class="preview-block">
                                  <div class="preview-label">Front</div>
                                  <div class="preview-text" v-html="renderMarkdownSafe(previewText(child.card.front, 300))"></div>
                                </div>

                                <div class="preview-block">
                                  <div class="preview-label">Back</div>
                                  <div class="preview-text" v-html="renderMarkdownSafe(previewText(child.card.back, 300))"></div>
                                </div>
                              </div>

                              <div v-if="child.card.src" class="text-xs opacity-70 mt-2">
                                <strong>Fonte:</strong> {{ previewText(child.card.src, 160) }}
                              </div>

                              <div class="preview-hint">
                                <i class="pi pi-pen-to-square mr-2" />
                                Clique no card para editar
                              </div>
                            </template>
                          </Card>
                        </div>
                      </Transition>
                    </template>
                  </div>
                </template>
              </DataView>
            </div>
          </div>
        </SplitterPanel>
      </Splitter>
    </div>

    <!-- EDIT DIALOG -->
    <Dialog
      v-model:visible="editVisible"
      header="Editar Card"
      modal
      appendTo="body"
      :draggable="false"
      :dismissableMask="true"
      class="modern-dialog"
      style="width: min(980px, 96vw);"
    >
      <ContextMenu ref="editContextMenuRef" :model="editContextMenuModel" appendTo="body" />

      <div class="edit-meta">
        <Tag severity="info" class="pill">
          <i class="pi pi-hashtag mr-2" /> {{ editIndex + 1 }}
        </Tag>

        <Tag 
          :severity="getCardType(editDraft.front) === 'cloze' ? 'warning' : 'info'" 
          class="pill card-type-tag"
        >
          {{ getCardType(editDraft.front) === 'cloze' ? 'CLOZE' : 'BASIC' }}
        </Tag>

        <Tag severity="secondary" class="pill">
          <i class="pi pi-tag mr-2" /> Deck
        </Tag>

        <Select
          v-model="editDraft.deck"
          :options="availableDeckNames.map((x) => ({ label: x, value: x }))"
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
          <Textarea 
            v-model="editDraft.front" 
            autoResize 
            class="w-full field-area" 
            @contextmenu="onEditTextSelect"
          />
        </div>
        <div class="col-12 md:col-6">
          <div class="field-title">Back</div>
          <Textarea 
            v-model="editDraft.back" 
            autoResize 
            class="w-full field-area"
            @contextmenu="onEditTextSelect"
          />
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

    <!-- CUSTOM INSTRUCTION DIALOG -->
    <Dialog
      v-model:visible="editCustomInstructionVisible"
      header="Instrução Customizada"
      modal
      appendTo="body"
      class="modern-dialog"
      style="width: min(640px, 96vw);"
    >
      <div class="mb-3">
        <label class="font-semibold">Instrução para o LLM (opcional)</label>
        <Textarea 
          v-model="editCustomInstruction" 
          autoResize 
          class="w-full mt-2" 
          rows="4"
          placeholder="Ex: Foque em conceitos técnicos, use linguagem formal..."
        />
        <small class="text-color-secondary mt-2 block">
          Deixe em branco para usar o contexto padrão do documento.
        </small>
      </div>

      <template #footer>
        <Button label="Cancelar" severity="secondary" outlined @click="editCustomInstructionVisible = false" />
        <Button label="Gerar" icon="pi pi-bolt" @click="editGenerateCardConfirm" />
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
    <Dialog
      v-model:visible="progressVisible"
      :header="progressTitle"
      modal
      class="modern-dialog"
      style="width: min(520px, 95vw);"
    >
      <ProgressBar :value="progressValue" />
      <div class="mt-2 text-right">{{ progressValue }}%</div>
    </Dialog>

    <!-- API KEYS -->
    <Dialog v-model:visible="apiKeyVisible" header="API Key Setup" modal class="modern-dialog" style="width: min(760px, 96vw);">
      <div class="disclaimer">
        ⚠️ I vibe coded this whole thing. I know nothing about security. Please don't use API keys with large balances or
        auto-refills.
      </div>

      <div class="grid">
        <div class="col-12">
          <label class="font-semibold">Claude API Key <span class="opt">(Optional)</span></label>
          <InputText v-model="anthropicApiKey" class="w-full" placeholder="sk-ant-api03-..." autocomplete="off" />
          <small class="text-color-secondary">Get your API key from console.anthropic.com/keys</small>
          <div v-if="anthropicApiKeyError" class="err">{{ anthropicApiKeyError }}</div>
        </div>

        <div class="col-12 mt-3">
          <label class="font-semibold">OpenAI API Key <span class="opt">(Optional)</span></label>
          <InputText v-model="openaiApiKey" class="w-full" placeholder="sk-..." autocomplete="off" />
          <small class="text-color-secondary">Get your API key from platform.openai.com/api-keys</small>
        </div>

        <div class="col-12 mt-3">
          <label class="font-semibold">Perplexity API Key <span class="opt">(Optional)</span></label>
          <InputText v-model="perplexityApiKey" class="w-full" placeholder="pplx-..." autocomplete="off" />
          <small class="text-color-secondary">Get your API key from perplexity.ai/settings/api</small>
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

    <!-- MODEL SELECTION -->
    <Dialog v-model:visible="modelSelectionVisible" header="Escolher Modelo" modal class="modern-dialog" style="width: min(760px, 96vw);">
      <div class="model-info">
        <i class="pi pi-info-circle mr-2" />
        Escolha o modelo para geração de cartões. Modelos Ollama são locais (privacidade total). Modelos de API requerem chaves configuradas.
      </div>

      <div class="grid mt-3">
        <div class="col-12">
          <label class="font-semibold">Modelo Selecionado</label>
          <Select 
            v-model="selectedModel" 
            :options="availableModels" 
            optionLabel="name" 
            optionValue="name" 
            class="w-full" 
            filter
            :loading="isLoadingModels"
            placeholder="Selecione um modelo"
          >
            <template #option="{ option }">
              <div class="model-option">
                <span class="model-name">{{ option.name }}</span>
                <Tag 
                  :severity="option.provider === 'ollama' ? 'success' : option.provider === 'openai' ? 'info' : 'warning'" 
                  class="pill model-tag"
                >
                  {{ option.provider === 'ollama' ? 'Ollama' : option.provider === 'openai' ? 'OpenAI' : 'Perplexity' }}
                </Tag>
              </div>
            </template>
            <template #value="{ value }">
              <div v-if="value" class="model-selected">
                <span class="model-name">{{ value }}</span>
                <Tag 
                  v-if="availableModels.find(m => m.name === value)"
                  :severity="availableModels.find(m => m.name === value).provider === 'ollama' ? 'success' : availableModels.find(m => m.name === value).provider === 'openai' ? 'info' : 'warning'" 
                  class="pill model-tag"
                >
                  {{ availableModels.find(m => m.name === value).provider === 'ollama' ? 'Ollama' : availableModels.find(m => m.name === value).provider === 'openai' ? 'OpenAI' : 'Perplexity' }}
                </Tag>
              </div>
            </template>
          </Select>
          <small class="text-color-secondary mt-2 block">
            Modelo atual: <strong>{{ selectedModel }}</strong>
          </small>
        </div>
      </div>

      <template #footer>
        <Button label="Atualizar Lista" icon="pi pi-refresh" severity="secondary" outlined @click="fetchAvailableModels" :loading="isLoadingModels" />
        <Button label="Cancelar" severity="secondary" outlined @click="modelSelectionVisible = false" />
        <Button label="Salvar" icon="pi pi-check" @click="saveModelSelection" />
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
/* =========================
   Sidebar Menu
========================= */
.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: 70px;
  background: rgba(17, 24, 39, 0.98);
  backdrop-filter: blur(20px);
  border-right: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 4px 0 20px rgba(0, 0, 0, 0.3);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: visible;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar.expanded {
  width: 280px;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255, 255, 255, 0.03);
  min-height: 70px;
  overflow: visible;
  gap: 12px;
}

.sidebar-logo {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
}

.sidebar-toggle {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  transition: all 0.2s ease;
  background: rgba(16, 185, 129, 0.12) !important;
  border: 1px solid rgba(16, 185, 129, 0.25);
  margin-left: auto;
  border-radius: 8px !important;
}

.sidebar-toggle:hover {
  background: rgba(16, 185, 129, 0.22) !important;
  transform: scale(1.08);
  border-color: rgba(16, 185, 129, 0.4);
}

.sidebar-toggle :deep(.p-button-icon) {
  font-size: 12px;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: visible;
  padding: 12px 8px;
}

.sidebar-separator {
  height: 1px;
  background: rgba(148, 163, 184, 0.12);
  margin: 8px 12px;
}

.sidebar-item {
  margin-bottom: 4px;
}

.sidebar-link {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.9);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  position: relative;
}

.sidebar-link:hover {
  background: rgba(99, 102, 241, 0.12);
  color: #fff;
}

.sidebar-link.expanded {
  background: rgba(99, 102, 241, 0.15);
  color: #fff;
}

.sidebar-icon {
  font-size: 18px;
  width: 20px;
  text-align: center;
  opacity: 0.9;
  flex-shrink: 0;
}

.sidebar-label {
  flex: 1;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.sidebar.expanded .sidebar-label {
  opacity: 1;
}

.sidebar-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 800;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.sidebar.expanded .sidebar-badge {
  opacity: 1;
}

.sidebar-chevron {
  font-size: 12px;
  transition: transform 0.3s ease, opacity 0.2s ease 0.1s;
  opacity: 0;
  flex-shrink: 0;
}

.sidebar.expanded .sidebar-chevron {
  opacity: 0.7;
}

.sidebar-link.expanded .sidebar-chevron {
  transform: rotate(180deg);
}

.sidebar-submenu {
  padding-left: 12px;
  margin-top: 4px;
  overflow: hidden;
}

.submenu-separator {
  height: 1px;
  background: rgba(148, 163, 184, 0.08);
  margin: 6px 12px;
}

.submenu-link {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.8);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  text-align: left;
  margin-bottom: 2px;
}

.submenu-link:hover:not(.disabled) {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.submenu-link.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.submenu-icon {
  font-size: 14px;
  width: 18px;
  text-align: center;
  opacity: 0.8;
  flex-shrink: 0;
}

.submenu-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.submenu-label {
  font-weight: 600;
}

.submenu-sublabel {
  font-size: 11px;
  opacity: 0.6;
  font-weight: 500;
}

.submenu-enter-active {
  animation: submenu-expand 0.3s ease;
}

.submenu-leave-active {
  animation: submenu-collapse 0.2s ease;
}

@keyframes submenu-expand {
  from {
    opacity: 0;
    max-height: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    max-height: 1000px;
    transform: translateY(0);
  }
}

@keyframes submenu-collapse {
  from {
    opacity: 1;
    max-height: 1000px;
  }
  to {
    opacity: 0;
    max-height: 0;
  }
}

.menu-toggle {
  width: 40px;
  height: 40px;
}

/* =========================
   Base
========================= */
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin-left: 70px;
  transition: margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background:
    radial-gradient(1200px 700px at 12% -10%, rgba(99, 102, 241, 0.25), transparent 55%),
    radial-gradient(900px 600px at 95% 10%, rgba(16, 185, 129, 0.18), transparent 60%),
    radial-gradient(900px 600px at 60% 110%, rgba(236, 72, 153, 0.14), transparent 55%),
    linear-gradient(180deg, rgba(10, 10, 12, 0.0), rgba(10, 10, 12, 0.35));
}

.sidebar.expanded ~ .app-shell {
  margin-left: 280px;
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
  align-items: center;
  gap: 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-header-logo {
  height: 28px;
  width: auto;
}

.brand-subtitle {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.6;
  letter-spacing: 0.3px;
}

.header-badges {
  display: flex;
  gap: 8px;
  align-items: center;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cardtype {
  width: 11rem;
  min-width: 10rem;
}

.hdr-divider {
  height: 24px;
  opacity: 0.5;
}

:deep(.cta.p-button) {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
  font-weight: 700;
  transition: all 0.2s ease;
}

:deep(.cta.p-button:hover) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
}

@media (max-width: 768px) {
  .header-left {
    gap: 12px;
  }
  .brand-subtitle {
    display: none;
  }
  .header-badges {
    display: none;
  }
  .status-wrap {
    display: none;
  }
  .hdr-divider {
    display: none;
  }
}

/* =========================
   Panels
========================= */
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
.expand-btn {
  width: 32px;
  height: 32px;
  margin-right: 4px;
}
.children-container {
  margin-left: 48px;
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-left: 16px;
  border-left: 3px solid rgba(99, 102, 241, 0.3);
}
.card-item.card-child :deep(.p-card) {
  background: rgba(99, 102, 241, 0.04);
  border: 1px solid rgba(99, 102, 241, 0.2);
}
.children-enter-active,
.children-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}
.children-enter-from,
.children-leave-to {
  opacity: 0;
  max-height: 0;
  transform: translateY(-10px);
}
.children-enter-to,
.children-leave-from {
  opacity: 1;
  max-height: 2000px;
  transform: translateY(0);
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
.card-type-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 800;
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
  height: 34px;
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

/* =========================
   Status pills (Header)
========================= */
.status-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-pills {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(148, 163, 184, 0.15);
}

.status-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.status-label {
  font-weight: 700;
  font-size: 11px;
  opacity: 0.8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.status-sep {
  width: 1px;
  height: 16px;
  background: rgba(148, 163, 184, 0.2);
}

/* =========================
   Modern Dialog (PrimeVue)
========================= */
:deep(.p-dialog.modern-dialog) {
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(17, 24, 39, 0.92);
  backdrop-filter: blur(14px);
  box-shadow: 0 28px 70px rgba(0, 0, 0, 0.55);
}

:deep(.p-dialog.modern-dialog .p-dialog-header) {
  padding: 14px 16px;
  background: rgba(255, 255, 255, 0.04);
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

:deep(.p-dialog.modern-dialog .p-dialog-title) {
  font-weight: 900;
  letter-spacing: -0.2px;
}

:deep(.p-dialog.modern-dialog .p-dialog-content) {
  padding: 16px;
  background: transparent;
}

:deep(.p-dialog.modern-dialog .p-dialog-footer) {
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.03);
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

:deep(.p-dialog.modern-dialog .p-dialog-header-icon) {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

:deep(.p-dialog.modern-dialog .p-dialog-header-icon:hover) {
  background: rgba(255, 255, 255, 0.10);
}

:deep(.p-dialog-mask) {
  backdrop-filter: blur(8px);
  background: rgba(0, 0, 0, 0.55);
}

:deep(.modern-dialog .p-inputtext),
:deep(.modern-dialog .p-textarea),
:deep(.modern-dialog .p-dropdown),
:deep(.modern-dialog .p-select) {
  border-radius: 14px;
}

:deep(.modern-dialog .p-inputtext:focus),
:deep(.modern-dialog .p-textarea:focus),
:deep(.modern-dialog .p-dropdown:not(.p-disabled).p-focus),
:deep(.modern-dialog .p-select:not(.p-disabled).p-focus) {
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.55);
}

/* =========================
   Espaços dos botões (Cards header)
========================= */
.panel-actions{
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.export-group{
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.export-btn{
  white-space: nowrap;
}

/* =========================
   MODO LEITURA (full screen + paginação) — Melhorado
========================= */
.reader-mode .cards-splitter{
  display: none;
}

/* remove gutters no modo leitura */
.reader-mode :deep(.p-splitter-gutter){
  display: none !important;
}

/* ocupa a tela, sem "margem" */
.reader-mode .main{
  padding: 0 !important;
}

/* painel do editor vira uma “tela” */
.reader-mode .panel{
  border-radius: 0;
  border: 0;
  box-shadow: none;
}

/* remove cabeçalho interno do editor (o topo fica no Toolbar) */
.reader-mode .panel-editor .panel-head{
  display: none;
}

/* sem padding interno; o editor toma tudo */
.reader-mode .panel-editor .panel-body{
  padding: 0 !important;
}

/* superfície do editor */
.editor-surface{
  height: 100%;
  min-height: 0;
}

/* wrapper do leitor */
.reader-surface{
  height: 100%;
  width: 100%;
}

/* ✅ Scroller no .ql-container (padding aqui vira “margem” fixa) */
.reader-mode .reader-surface :deep(.ql-container){
  height: 100% !important;
  overflow-x: auto !important;
  overflow-y: hidden !important;
  scroll-behavior: smooth;

  padding: var(--reader-pad-y) var(--reader-pad-x);
  box-sizing: border-box;

  /* esconde scrollbar */
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.reader-mode .reader-surface :deep(.ql-container::-webkit-scrollbar){
  width: 0;
  height: 0;
}

/* ✅ Conteúdo em colunas no .ql-editor (sem padding horizontal) */
.reader-mode .reader-surface :deep(.ql-editor){
  height: 100%;
  min-height: 100%;
  width: max-content !important;

  padding: 0 !important;
  margin: 0 !important;

  overflow: visible !important;

  font-family: ui-serif, Georgia, Cambria, "Times New Roman", Times, serif;
  font-size: calc(20px * var(--reader-scale));
  line-height: 1.65;
  letter-spacing: 0.15px;

  column-width: var(--reader-page-width);
  column-gap: var(--reader-gap);
  column-fill: auto;
}

/* =========================
   Tema Kindle (claro) — SOMENTE no campo de Leitura/Edição
   (Header permanece no tema principal)
========================= */
.reader-mode.reader-kindle .panel-editor{
  background: #ffffff !important;
}

.reader-mode.reader-kindle .reader-surface :deep(.ql-container),
.reader-mode.reader-kindle .reader-surface :deep(.ql-editor){
  background: #ffffff !important;
  color: #111827 !important;
}

/* toolbar do Quill dentro do editor (se existir) */
.reader-mode.reader-kindle .reader-surface :deep(.ql-toolbar){
  background: rgba(255,255,255,0.92) !important;
  border: 0 !important;
  border-bottom: 1px solid rgba(0,0,0,0.10) !important;
  color: #111827 !important;
}

/* =========================
   Tema escuro (mantém look atual)
========================= */
.reader-mode.reader-dark .panel-editor{
  background: rgba(17, 24, 39, 0.58);
}

/* =========================
   Responsivo
========================= */
@media (max-width: 520px){
  .reader-mode .reader-surface :deep(.ql-container){
    padding: 28px 22px;
  }
  .reader-mode .reader-surface :deep(.ql-editor){
    font-size: calc(18px * var(--reader-scale));
  }
}

/* Card type select styling */
.cardtype {
  --cardtype-bg: rgba(255,255,255,0.04);
}
.cardtype :deep(.p-dropdown){
  min-width: auto;
  height: 36px;
}
.cardtype :deep(.p-dropdown .p-dropdown-label){
  line-height: 36px;
  height: 36px;
  display: inline-block;
  padding-left: 8px;
}
.cardtype :deep(.p-dropdown-trigger){
  height: 36px;
}
.cardtype :deep(.p-dropdown-panel){
  background: rgba(17,24,39,0.98);
  border: 1px solid rgba(148,163,184,0.12);
  border-radius: 12px;
  padding: 6px 6px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.45);
  min-width: 12rem;
}
.cardtype :deep(.p-dropdown-items .p-dropdown-item){
  padding: 6px 8px;
  border-radius: 8px;
}
.cardtype :deep(.p-dropdown-items .p-dropdown-item:hover){
  background: rgba(99,102,241,0.10);
}
.cardtype :deep(.p-dropdown-items .p-dropdown-item.p-highlight){
  background: rgba(99,102,241,0.14);
}
.card-type-item{
  display:flex;
  gap:0.5rem;
  align-items:center;
  padding:6px 8px;
}
.cardtype-icon{
  font-size:0.92rem;
  color:var(--primary-color, #90caf9);
  margin-top:0;
}
.ct-body{ }
.ct-label{
  font-size:0.82rem;
  font-weight:700;
  line-height:1;
}
.ct-desc{
  font-size:0.70rem;
  color:rgba(255,255,255,0.58);
  margin-top:2px;
}
.card-type-selected{
  display:flex;
  gap:0.5rem;
  align-items:center;
}
.cardtype :deep(.p-dropdown-label), .cardtype .card-type-selected .ct-label{
  font-size:0.9rem;
}

/* Model selection styling */
.model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
}

.model-selected {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-name {
  flex: 1;
  font-weight: 600;
}

.model-tag {
  font-size: 11px;
  padding: 2px 8px;
}
</style>
