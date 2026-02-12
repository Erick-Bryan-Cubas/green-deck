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
import InputSwitch from 'primevue/inputswitch'
import Checkbox from 'primevue/checkbox'
import Card from 'primevue/card'
import DataView from 'primevue/dataview'
import ProgressBar from 'primevue/progressbar'
import ProgressSpinner from 'primevue/progressspinner'
import Paginator from 'primevue/paginator'
import Menu from 'primevue/menu'
import ContextMenu from 'primevue/contextmenu'
import Toast from 'primevue/toast'
import Tag from 'primevue/tag'
import Divider from 'primevue/divider'
import { useToast } from 'primevue/usetoast'

// App components - with lazy loading for performance
import LazyQuillEditor from '@/components/LazyQuillEditor.vue'
import AnkiStatus from '@/components/AnkiStatus.vue'
import OllamaStatus from '@/components/OllamaStatus.vue'
import SidebarMenu from '@/components/SidebarMenu.vue'
import DocumentUpload from '@/components/DocumentUpload.vue'
import TopicLegend from '@/components/TopicLegend.vue'
import { colorTokens, sidebarIconColors } from '@/config/theme'

// Modal components
import GenerateModal from '@/components/modals/GenerateModal.vue'
import EditCardDialog from '@/components/modals/EditCardDialog.vue'
import ModelSelectionDialog from '@/components/modals/ModelSelectionDialog.vue'
import IntroModal from '@/components/modals/IntroModal.vue'
import AnkiExportDialog from '@/components/modals/AnkiExportDialog.vue'
import ApiKeysDialog from '@/components/modals/ApiKeysDialog.vue'
import PromptSettingsDialog from '@/components/modals/PromptSettingsDialog.vue'
import ProgressDialog from '@/components/modals/ProgressDialog.vue'
import OllamaSelectionDialog from '@/components/modals/OllamaSelectionDialog.vue'
import TopicConfirmDialog from '@/components/modals/TopicConfirmDialog.vue'
import CustomInstructionDialog from '@/components/modals/CustomInstructionDialog.vue'
import QuestionGenerateModal from '@/components/modals/QuestionGenerateModal.vue'
import QuestionExportDialog from '@/components/modals/QuestionExportDialog.vue'

// Question components
import QuestionCardItem from '@/components/QuestionCardItem.vue'
import QuizInteractive from '@/components/QuizInteractive.vue'
import { useRouter } from 'vue-router'
import { useOllamaStatus } from '@/composables/useStatusWebSocket'
import { useTheme } from '@/composables/useTheme'

// Services
import {
  generateCardsWithStream,
  cancelCardsGeneration,
  analyzeText,
  segmentTopics,
  getStoredApiKeys,
  storeApiKeys,
  hasAnyApiKey,
  fetchOllamaInfo
} from '@/services/api.js'
import { downloadTextFile, exportCardsAsMarkdown } from '@/services/export'
import {
  generateQuestionsStream,
  parseQuestionsStream,
  uploadQuestionsToAnki,
  checkAllInOneModel
} from '@/services/questionApi.js'

// Security utilities
import { sanitizeHtml } from '@/utils/sanitize.js'

const toast = useToast()
const router = useRouter()
const { isDark, toggleTheme } = useTheme()
// WebSocket status do Ollama (para detectar quando fica disponível)
const { status: ollamaWsStatus } = useOllamaStatus()
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

function buildSessionInfo(session) {
  const created = formatSessionStamp(session?.createdAt)
  const updated = formatSessionStamp(session?.updatedAt)
  const cardsCount = sessionCardCount(session)
  const cardsLabel = cardsCount === 1 ? '1 cartão' : `${cardsCount} cartões`

  return [
    created ? `Criada em: ${created}` : null,
    updated ? `Atualizada em: ${updated}` : null,
    `Total de cartões: ${cardsLabel}`
  ]
    .filter(Boolean)
    .join('\n')
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n))
}

function formatCount(value) {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return '0'
  try {
    return num.toLocaleString(undefined)
  } catch {
    return String(num)
  }
}

function countWords(text) {
  const cleaned = String(text || '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return 0
  return cleaned.split(' ').length
}

// ============================================================
// localStorage Keys
// ============================================================
const INTRO_SHOWN_KEY = 'green-deck.intro-shown'
const LS_READER_KEY = 'green-deck.reader.v2'
const LS_ANKI_PREFS_KEY = 'green-deck.anki-export-prefs'

// ============================================================
// Modo Leitura (Kindle full-screen + paginação real)
// Melhorias:
// - scroller = .ql-container (padding no container)
// - step correto = (contentWidth + gap)
// - snap suave após scroll
// - tema kindle claro só no campo de leitura/edição (header intacto)
// ============================================================
const immersiveReader = ref(false)
const readerTwoPage = ref(true) // "spread" (2 páginas) quando a tela permitir
const readerFontScale = ref(1) // 1.0 = normal
const readerTheme = ref('kindle') // 'kindle' | 'dark' | 'sepia'
const readerDark = ref(false) // mantido para compatibilidade

const readerSurfaceRef = ref(null) // wrapper DOM em volta do QuillEditor
const readerScrollerEl = ref(null) // ✅ .ql-container (scroll horizontal)
const readerPage = ref(1)
const readerTotalPages = ref(1)
const readerProgress = ref(0) // 0-100 para barra de progresso
const readerShowProgress = ref(true) // mostrar barra de progresso
const readerAutoHideControls = ref(false) // auto-hide após inatividade
const readerControlsVisible = ref(true)
const showLineNumbers = ref(true) // mostrar números de linha no editor

// Flag para ignorar onContentChanged durante navegação de página PDF
let isNavigatingPdfPage = false

// Touch/swipe support
let touchStartX = 0
let touchStartY = 0
let isSwiping = false
const SWIPE_THRESHOLD = 50 // px mínimos para considerar swipe

const readerGapPx = ref(56)
const readerPadXPx = ref(64)
const readerPadYPx = ref(48)
const readerPageWidthPx = ref(680)

// ✅ stride real entre páginas/spreads
const readerStepPx = ref(0)

const readerThemeOptions = [
  { value: 'kindle', label: 'Claro', icon: 'pi-sun' },
  { value: 'sepia', label: 'Sépia', icon: 'pi-palette' },
  { value: 'dark', label: 'Escuro', icon: 'pi-moon' }
]

const readerVars = computed(() => ({
  '--reader-scale': String(readerFontScale.value),
  '--reader-gap': `${readerGapPx.value}px`,
  '--reader-pad-x': `${readerPadXPx.value}px`,
  '--reader-pad-y': `${readerPadYPx.value}px`,
  '--reader-page-width': `${readerPageWidthPx.value}px`
}))

function toggleReader() {
  immersiveReader.value = !immersiveReader.value
  console.log('[toggleReader] immersiveReader:', immersiveReader.value, 
    'usePdfPagination:', usePdfPagination.value, 
    'pdfPagesContent.length:', pdfPagesContent.value.length)
    
  if (immersiveReader.value) {
    // Se temos paginação do PDF, inicializa com as páginas do PDF
    if (usePdfPagination.value && pdfPagesContent.value.length > 0) {
      console.log('[toggleReader] initializing PDF pagination')
      readerTotalPages.value = pdfPagesContent.value.length
      // Vai para a primeira página do PDF
      readerGoToPdfPage(1)
    }
    nextTick(() => {
      editorRef.value?.focus?.()
    })
  } else {
    // Ao sair do modo leitura, restaura o texto completo
    if (usePdfPagination.value && pdfPagesContent.value.length > 0) {
      const PAGE_BREAK_MARKER = "\n\n<!-- PAGE_BREAK -->\n\n"
      const fullText = pdfPagesContent.value.map(p => p.text).join(PAGE_BREAK_MARKER)
      if (editorRef.value?.setContent) {
        editorRef.value.setContent(fullText)
      }
    }
  }
}

function setReaderEnabled(nextValue) {
  if (nextValue === immersiveReader.value) return
  toggleReader()
}

function setReaderTheme(theme) {
  readerTheme.value = theme
  readerDark.value = theme === 'dark'
  requestReaderLayout({ preserveProgress: true })
}

// Touch/Swipe handlers para navegação móvel
function onTouchStart(e) {
  if (!immersiveReader.value) return
  const touch = e.touches[0]
  touchStartX = touch.clientX
  touchStartY = touch.clientY
  isSwiping = false
}

function onTouchMove(e) {
  if (!immersiveReader.value || !touchStartX) return
  const touch = e.touches[0]
  const deltaX = touch.clientX - touchStartX
  const deltaY = touch.clientY - touchStartY
  
  // Se movimento horizontal é maior que vertical, é swipe
  if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 10) {
    isSwiping = true
    e.preventDefault()
  }
}

function onTouchEnd(e) {
  if (!immersiveReader.value || !touchStartX) return
  const touch = e.changedTouches[0]
  const deltaX = touch.clientX - touchStartX
  
  if (isSwiping && Math.abs(deltaX) >= SWIPE_THRESHOLD) {
    if (deltaX > 0) {
      readerPrevPage()
    } else {
      readerNextPage()
    }
  }
  
  touchStartX = 0
  touchStartY = 0
  isSwiping = false
}

// Auto-hide controls
let controlsHideTimer = null
function resetControlsTimer() {
  readerControlsVisible.value = true
  if (controlsHideTimer) clearTimeout(controlsHideTimer)
  if (readerAutoHideControls.value && immersiveReader.value) {
    controlsHideTimer = setTimeout(() => {
      readerControlsVisible.value = false
    }, 3000)
  }
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
  
  // Touch events para swipe navigation
  el.addEventListener('touchstart', onTouchStart, { passive: true })
  el.addEventListener('touchmove', onTouchMove, { passive: false })
  el.addEventListener('touchend', onTouchEnd, { passive: true })
  
  // Mouse move para auto-hide
  el.addEventListener('mousemove', resetControlsTimer, { passive: true })
  
  requestReaderLayout({ preserveProgress: true })
}

function detachReaderScroller() {
  const el = readerScrollerEl.value
  if (!el) return
  el.removeEventListener('scroll', onReaderScroll)
  el.removeEventListener('touchstart', onTouchStart)
  el.removeEventListener('touchmove', onTouchMove)
  el.removeEventListener('touchend', onTouchEnd)
  el.removeEventListener('mousemove', resetControlsTimer)
  readerScrollerEl.value = null
}

let readerScrollRaf = null
let readerSnapTimer = null

function onReaderScroll() {
  if (!immersiveReader.value) return
  
  // Quando usa paginação do PDF, não recalcula baseado em scroll
  if (usePdfPagination.value) return

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

  // ✅ Quando usa paginação do PDF, sempre usa página única (sem spread)
  // pois cada página do PDF é uma unidade que deve ser exibida inteira
  const allowSpread = !usePdfPagination.value && readerTwoPage.value && contentW >= 900
  const pageW = allowSpread ? Math.floor((contentW - gap) / 2) : Math.floor(contentW)

  readerPageWidthPx.value = clamp(pageW, 320, 1400)

  // ✅ stride real: largura do “conteúdo visível” + gap
  readerStepPx.value = Math.max(1, Math.floor(contentW + gap))
}

function updateReaderPageStats() {
  // Se temos paginação baseada no PDF, use essa
  if (usePdfPagination.value && pdfPagesContent.value.length > 0) {
    readerTotalPages.value = pdfPagesContent.value.length
    // readerPage.value já é controlado pelas funções de navegação
    readerProgress.value = readerTotalPages.value > 1 
      ? Math.round(((readerPage.value - 1) / (readerTotalPages.value - 1)) * 100)
      : 100
    return
  }
  
  // Caso contrário, usa a paginação por scroll (comportamento original)
  const el = readerScrollerEl.value
  if (!el) {
    readerPage.value = 1
    readerTotalPages.value = 1
    readerProgress.value = 0
    return
  }

  if (!readerStepPx.value) computeReaderLayoutMetrics()
  const step = Math.max(1, readerStepPx.value)

  const maxScroll = Math.max(0, (el.scrollWidth || el.clientWidth) - el.clientWidth)
  const total = Math.max(1, Math.ceil(maxScroll / step) + 1)

  const current = clamp(Math.round((el.scrollLeft || 0) / step) + 1, 1, total)

  readerTotalPages.value = total
  readerPage.value = current
  
  // Atualiza barra de progresso (0-100)
  readerProgress.value = maxScroll > 0 
    ? Math.round((el.scrollLeft / maxScroll) * 100) 
    : (total === 1 ? 100 : 0)
}

function snapReaderToNearestPage() {
  // Não faz snap quando usando paginação do PDF (cada página é uma unidade)
  if (usePdfPagination.value) return
  
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
  // Se temos paginação PDF, navega para a página correspondente
  if (usePdfPagination.value && pdfPagesContent.value.length > 0) {
    const pageIndex = Math.round(progress01 * (pdfPagesContent.value.length - 1))
    readerGoToPdfPage(pageIndex + 1)
    return
  }
  
  const el = readerScrollerEl.value
  if (!el) return
  const maxScroll = Math.max(0, (el.scrollWidth || el.clientWidth) - el.clientWidth)
  const target = clamp(progress01, 0, 1) * maxScroll
  el.scrollTo({ left: target, top: 0, behavior: 'auto' })
  updateReaderPageStats()
}

// Navega para uma página específica do PDF
function readerGoToPdfPage(pageNumber) {
  console.log('[readerGoToPdfPage] pageNumber:', pageNumber, 
    'usePdfPagination:', usePdfPagination.value, 
    'pdfPagesContent.length:', pdfPagesContent.value.length)
    
  if (!usePdfPagination.value || pdfPagesContent.value.length === 0) return
  
  const total = pdfPagesContent.value.length
  const p = clamp(pageNumber, 1, total)
  
  // Evita navegação para a mesma página
  if (p === readerPage.value) return
  
  console.log('[readerGoToPdfPage] navigating to page:', p, 'of', total)
  
  // Ativa flag para ignorar onContentChanged
  isNavigatingPdfPage = true
  
  // Atualiza o conteúdo do editor para mostrar apenas esta página
  const pageContent = pdfPagesContent.value[p - 1]
  if (pageContent && editorRef.value?.setContent) {
    editorRef.value.setContent(pageContent.text)
    console.log('[readerGoToPdfPage] content set, words:', pageContent.word_count)
  }
  
  readerPage.value = p
  readerTotalPages.value = total
  readerProgress.value = total > 1 ? Math.round(((p - 1) / (total - 1)) * 100) : 100
  
  // Scroll para o topo da página
  const el = readerScrollerEl.value
  if (el) {
    el.scrollTo({ left: 0, top: 0, behavior: 'auto' })
  }
  
  // Desativa flag após um pequeno delay para garantir que onContentChanged foi processado
  nextTick(() => {
    isNavigatingPdfPage = false
  })
}

function readerScrollToPage(pageNumber, behavior = 'smooth') {
  // DEBUG: log para verificar estado da paginação
  console.log('[readerScrollToPage] pageNumber:', pageNumber, 
    'usePdfPagination:', usePdfPagination.value, 
    'pdfPagesContent.length:', pdfPagesContent.value.length,
    'readerPage:', readerPage.value)
  
  // Se temos paginação PDF, usa a navegação por página
  if (usePdfPagination.value && pdfPagesContent.value.length > 0) {
    readerGoToPdfPage(pageNumber)
    return
  }
  
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

// Handler para o Paginator do PrimeVue
function onPaginatorPageChange(event) {
  // event.page é 0-indexed, convertemos para 1-indexed
  const newPage = event.page + 1
  // Evita loop: só navega se a página for diferente da atual
  if (newPage !== readerPage.value) {
    readerGoToPdfPage(newPage)
  }
}

// Computed para o índice 0-based usado pelo Paginator
const paginatorFirst = computed(() => readerPage.value - 1)

let readerResizeObserver = null
let winResizeHandler = null

function requestReaderLayout({ preserveProgress = false, explicitProgress = null } = {}) {
  if (!immersiveReader.value) return
  
  // Se estamos usando paginação do PDF, não precisa recalcular layout de scroll
  if (usePdfPagination.value) {
    // Apenas atualiza as estatísticas de página
    updateReaderPageStats()
    return
  }

  const beforeProgress = preserveProgress ? (explicitProgress ?? getReaderProgress()) : 0

  computeReaderLayoutMetrics()

  requestAnimationFrame(() => {
    if (preserveProgress) setReaderProgress(beforeProgress)
    updateReaderPageStats()
    // ✅ garante alinhamento após mudanças de fonte/1p/2p
    snapReaderToNearestPage()
  })
}

watch([immersiveReader, readerTwoPage, readerFontScale, readerTheme, readerShowProgress, readerAutoHideControls, showLineNumbers], () => {
  try {
    localStorage.setItem(
      LS_READER_KEY,
      JSON.stringify({
        immersiveReader: immersiveReader.value,
        readerTwoPage: readerTwoPage.value,
        readerFontScale: readerFontScale.value,
        readerTheme: readerTheme.value,
        readerDark: readerTheme.value === 'dark',
        readerShowProgress: readerShowProgress.value,
        readerAutoHideControls: readerAutoHideControls.value,
        showLineNumbers: showLineNumbers.value
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
const LS_SESSIONS_KEY = 'green-deck.sessions.v1'
const LS_ACTIVE_SESSION_KEY = 'green-deck.sessions.active.v1'

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
  return id
}

function sessionCardCount(session) {
  return Array.isArray(session?.cards) ? session.cards.length : 0
}

function resetWorkspaceState() {
  cards.value = []
  documentContext.value = ''
  lastFullText.value = ''
  lastEditorDelta.value = null
  lastEditorHtml.value = ''
  lastTextForAnalysis.value = ''

  pdfPagesContent.value = []
  usePdfPagination.value = false

  topicSegments.value = []
  topicDefinitions.value = []
  showTopicLegend.value = false

  questionCards.value = []

  editorRef.value?.setDelta?.(null)

  if (immersiveReader.value) {
    requestReaderLayout({ preserveProgress: false })
  }
}

function deleteSessionWithConfirmation(id) {
  const target = getSessionById(id)
  if (!target) {
    notify('Sessão não encontrada.', 'warn', 3000)
    return
  }

  const cardsCount = sessionCardCount(target)
  const cardLabel = cardsCount === 1 ? '1 cartão' : `${cardsCount} cartões`
  const confirmed = window.confirm(
    `Apagar a sessão "${target.title}"?\n\nSerão removidos ${cardLabel} dessa sessão.`
  )
  if (!confirmed) return

  const wasActive = activeSessionId.value === id
  const remaining = sessions.value.filter((s) => s.id !== id)

  if (persistSessionTimer) {
    clearTimeout(persistSessionTimer)
    persistSessionTimer = null
  }
  if (saveStatusTimer) {
    clearTimeout(saveStatusTimer)
    saveStatusTimer = null
  }
  saveStatus.value = 'idle'

  sessions.value = remaining
  persistSessions(sessions.value)

  if (!wasActive) {
    notify('Sessão apagada.', 'success', 2600)
    return
  }

  const nextId = remaining[0]?.id || null
  if (!nextId) {
    activeSessionId.value = null
    persistActiveSessionId(null)

    isRestoringSession.value = true
    try {
      resetWorkspaceState()
    } finally {
      setTimeout(() => {
        isRestoringSession.value = false
      }, 0)
    }
    notify('Sessão apagada. Nenhuma sessão restante.', 'success', 3200)
    return
  }

  restoreSessionById(nextId)
  notify('Sessão apagada.', 'success', 2600)
}

function clearAllSessionsWithConfirmation() {
  const totalSessions = sessions.value.length
  if (!totalSessions) {
    notify('Não há sessões para apagar.', 'info', 2600)
    return
  }

  const totalCards = sessions.value.reduce((acc, session) => acc + sessionCardCount(session), 0)
  const sessionLabel = totalSessions === 1 ? '1 sessão' : `${totalSessions} sessões`
  const cardLabel = totalCards === 1 ? '1 cartão' : `${totalCards} cartões`

  const confirmed = window.confirm(
    `Apagar todas as sessões (${sessionLabel})?\n\nSerão removidos ${cardLabel} no total.`
  )
  if (!confirmed) return

  if (persistSessionTimer) {
    clearTimeout(persistSessionTimer)
    persistSessionTimer = null
  }
  if (saveStatusTimer) {
    clearTimeout(saveStatusTimer)
    saveStatusTimer = null
  }
  saveStatus.value = 'idle'

  isRestoringSession.value = true
  try {
    clearAllSessions()
    resetWorkspaceState()
  } finally {
    setTimeout(() => {
      isRestoringSession.value = false
    }, 0)
  }

  notify('Todas as sessões foram apagadas.', 'success', 3200)
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
    documentContext: documentContext.value,
    // Topic segmentation data
    topicSegments: topicSegments.value,
    topicDefinitions: topicDefinitions.value,
    // AllInOne questions
    questionCards: questionCards.value
  }
}

let persistSessionTimer = null
let saveStatusTimer = null

function schedulePersistActiveSession() {
  if (isRestoringSession.value) return
  if (persistSessionTimer) clearTimeout(persistSessionTimer)
  if (saveStatusTimer) clearTimeout(saveStatusTimer)
  
  // Mostra "Salvando..." imediatamente
  saveStatus.value = 'saving'
  
  persistSessionTimer = setTimeout(() => {
    const snap = buildActiveSessionSnapshot()

    const hasAny =
      normalizePlainText(snap.plainText).length > 0 ||
      (Array.isArray(snap.cards) && snap.cards.length > 0) ||
      (Array.isArray(snap.questionCards) && snap.questionCards.length > 0) ||
      normalizePlainText(snap.documentContext).length > 0

    if (!hasAny) {
      saveStatus.value = 'idle'
      return
    }
    upsertSession(snap)
    
    // Mostra "Salvo ✓" por 2 segundos, depois esconde
    saveStatus.value = 'saved'
    saveStatusTimer = setTimeout(() => {
      saveStatus.value = 'idle'
    }, 2500)
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

    // Restaura topic segmentation
    topicSegments.value = s.topicSegments || []
    topicDefinitions.value = s.topicDefinitions || []
    showTopicLegend.value = topicSegments.value.length > 0

    // Restaura AllInOne questions
    questionCards.value = Array.isArray(s.questionCards) ? s.questionCards : []

    await nextTick()

    // Reaplicar highlights dos tópicos se existirem
    if (topicSegments.value.length > 0 && topicDefinitions.value.length > 0) {
      const highlightData = topicSegments.value.map(seg => ({
        start: seg.start,
        end: seg.end,
        color: topicDefinitions.value.find(t => t.id === seg.topic_id)?.color || 'var(--app-text)'
      }))
      editorRef.value?.applyTopicHighlights(highlightData)
    }

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
  if (!activeSessionId.value) {
    notify('Nenhuma sessão ativa para apagar.', 'info', 2600)
    return
  }
  deleteSessionWithConfirmation(activeSessionId.value)
}

function newSession() {
  schedulePersistActiveSession()

  isRestoringSession.value = true
  resetWorkspaceState()
  isRestoringSession.value = false

  activeSessionId.value = safeId()
  persistActiveSessionId(activeSessionId.value)

  notify('Nova sessão pronta. Ela será salva quando houver conteúdo.', 'success', 2400)

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

// ============================================================
// Questions (AllInOne kprim, mc, sc)
// ============================================================
const questionCards = ref([])
const showQuestionGenerateModal = ref(false)
const showQuestionExportDialog = ref(false)
const isGeneratingQuestions = ref(false)
const isExportingQuestions = ref(false)
const allInOneStatus = ref({ hasModel: false, checking: true })
const questionPreviewVisible = ref(false)
const questionPreviewData = ref(null)

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

// Topic segmentation state
const isSegmentingTopics = ref(false)
const topicSegments = ref([])
const topicDefinitions = ref([])
const showTopicLegend = ref(false)
const topicSegmentProgress = ref(0)
const topicSegmentStage = ref('')
let topicSegmentTimer = null

// Modal de confirmação para marcação de tópicos
const showTopicConfirmModal = ref(false)
const pendingTextForSegmentation = ref('')

// Flag para evitar duplicação de triggers ao carregar PDF
const isLoadingPdf = ref(false)

// Watch para debug de mudanças no stage
watch(topicSegmentStage, (newVal, oldVal) => {
  console.log('[TopicSegmentation] Stage changed:', { from: oldVal, to: newVal })
})

watch(topicSegmentProgress, (newVal, oldVal) => {
  console.log('[TopicSegmentation] Progress changed:', { from: oldVal, to: newVal })
})

// ============================================================
// Indicador de salvamento
// ============================================================
const saveStatus = ref('saved') // 'saving' | 'saved' | 'idle'
const saveStatusText = computed(() => {
  if (saveStatus.value === 'saving') return 'Salvando...'
  if (saveStatus.value === 'saved') return 'Salvo ✓'
  return ''
})
const saveStatusIcon = computed(() => {
  if (saveStatus.value === 'saving') return 'pi pi-spin pi-spinner'
  if (saveStatus.value === 'saved') return 'pi pi-check-circle'
  return ''
})
const saveStatusSeverity = computed(() => {
  if (saveStatus.value === 'saving') return 'warning'
  return 'success'
})

// ============================================================
// Estatísticas de texto
// ============================================================
const textStats = computed(() => {
  const text = lastFullText.value || ''
  const words = text.trim() ? text.trim().split(/\s+/).length : 0
  const chars = text.length
  const charsNoSpaces = text.replace(/\s/g, '').length
  // Tempo de leitura médio: 200 palavras por minuto
  const readingTimeMin = Math.ceil(words / 200)
  return {
    words,
    chars,
    charsNoSpaces,
    readingTimeMin,
    readingTimeLabel: readingTimeMin <= 1 ? '< 1 min' : `${readingTimeMin} min`
  }
})

// ============================================================
// Navegação entre highlights
// ============================================================
const highlightPositions = ref([]) // [{index, length, color}]
const currentHighlightIndex = ref(-1)

function scanHighlights() {
  if (!editorRef.value) {
    highlightPositions.value = []
    return
  }

  const delta = editorRef.value.getDelta?.()
  if (!delta || !delta.ops) {
    highlightPositions.value = []
    return
  }

  const positions = []
  let idx = 0
  let lastHighlight = null

  delta.ops.forEach((op) => {
    const ins = op.insert
    const len = typeof ins === 'string' ? ins.length : 1
    const bg = op.attributes?.background

    if (bg && typeof bg === 'string' && bg.startsWith('#')) {
      // Check if we should merge with previous highlight (same color)
      if (lastHighlight && lastHighlight.color === bg) {
        // Extend to include current segment
        lastHighlight.length = (idx + len) - lastHighlight.index
      } else {
        // New highlight group
        lastHighlight = { index: idx, length: len, color: bg }
        positions.push(lastHighlight)
      }
    } else {
      // Check if this is just whitespace/newlines between highlights
      const isWhitespaceOnly = typeof ins === 'string' && /^[\s\n]+$/.test(ins)
      if (!isWhitespaceOnly || !lastHighlight) {
        // Non-whitespace content breaks the highlight chain
        lastHighlight = null
      }
      // If whitespace, keep lastHighlight active for potential merge
    }
    idx += len
  })

  highlightPositions.value = positions
}

const hasHighlights = computed(() => highlightPositions.value.length > 0)
const highlightCount = computed(() => highlightPositions.value.length)
const currentHighlightLabel = computed(() => {
  if (!hasHighlights.value) return '0/0'
  const current = currentHighlightIndex.value + 1
  return `${current > 0 ? current : '-'}/${highlightCount.value}`
})

function goToHighlight(index) {
  if (!editorRef.value || highlightPositions.value.length === 0) return
  
  const pos = highlightPositions.value[index]
  if (!pos) return
  
  currentHighlightIndex.value = index
  
  // Acessa o Quill interno via exposed method ou diretamente
  const quill = editorRef.value.$el?.querySelector('.ql-editor')?.parentElement?.__quill
  if (quill) {
    quill.setSelection(pos.index, pos.length)
    // Scroll para o highlight
    const bounds = quill.getBounds(pos.index, pos.length)
    if (bounds) {
      const container = editorRef.value.$el?.querySelector('.ql-container')
      if (container) {
        container.scrollTop = bounds.top - container.clientHeight / 3
      }
    }
  }
}

function goToPrevHighlight() {
  if (!hasHighlights.value) return
  let newIndex = currentHighlightIndex.value - 1
  if (newIndex < 0) newIndex = highlightPositions.value.length - 1
  goToHighlight(newIndex)
}

function goToNextHighlight() {
  if (!hasHighlights.value) return
  let newIndex = currentHighlightIndex.value + 1
  if (newIndex >= highlightPositions.value.length) newIndex = 0
  goToHighlight(newIndex)
}

// ============================================================
// Busca no texto do editor (Find in Text)
// ============================================================
const editorSearchVisible = ref(false)
const editorSearchQuery = ref('')
const editorSearchResults = ref([]) // [{index, length}]
const editorSearchCurrentIndex = ref(-1)
const editorSearchInputRef = ref(null)

const hasEditorSearchResults = computed(() => editorSearchResults.value.length > 0)
const editorSearchLabel = computed(() => {
  if (!editorSearchQuery.value.trim()) return ''
  if (!hasEditorSearchResults.value) return '0 resultados'
  const current = editorSearchCurrentIndex.value + 1
  return `${current}/${editorSearchResults.value.length}`
})

function toggleEditorSearch() {
  editorSearchVisible.value = !editorSearchVisible.value
  if (editorSearchVisible.value) {
    nextTick(() => {
      editorSearchInputRef.value?.focus()
    })
  } else {
    clearEditorSearch()
  }
}

function clearEditorSearch() {
  editorSearchQuery.value = ''
  editorSearchResults.value = []
  editorSearchCurrentIndex.value = -1
  removeEditorSearchHighlights()
}

function closeEditorSearch() {
  editorSearchVisible.value = false
  clearEditorSearch()
}

function performEditorSearch() {
  const query = editorSearchQuery.value.trim().toLowerCase()
  if (!query) {
    editorSearchResults.value = []
    editorSearchCurrentIndex.value = -1
    removeEditorSearchHighlights()
    return
  }
  
  const text = (lastFullText.value || '').toLowerCase()
  const results = []
  let pos = 0
  
  while (pos < text.length) {
    const idx = text.indexOf(query, pos)
    if (idx === -1) break
    results.push({ index: idx, length: query.length })
    pos = idx + 1
  }
  
  editorSearchResults.value = results
  editorSearchCurrentIndex.value = results.length > 0 ? 0 : -1
  
  if (results.length > 0) {
    goToEditorSearchResult(0)
  }
}

function goToEditorSearchResult(index) {
  if (!editorRef.value || editorSearchResults.value.length === 0) return
  
  const result = editorSearchResults.value[index]
  if (!result) return
  
  editorSearchCurrentIndex.value = index
  
  const quill = editorRef.value.$el?.querySelector('.ql-editor')?.parentElement?.__quill
  if (quill) {
    quill.setSelection(result.index, result.length)
    const bounds = quill.getBounds(result.index, result.length)
    if (bounds) {
      const container = editorRef.value.$el?.querySelector('.ql-container')
      if (container) {
        container.scrollTop = bounds.top - container.clientHeight / 3
      }
    }
  }
}

function goToPrevEditorSearchResult() {
  if (!hasEditorSearchResults.value) return
  let newIndex = editorSearchCurrentIndex.value - 1
  if (newIndex < 0) newIndex = editorSearchResults.value.length - 1
  goToEditorSearchResult(newIndex)
}

function goToNextEditorSearchResult() {
  if (!hasEditorSearchResults.value) return
  let newIndex = editorSearchCurrentIndex.value + 1
  if (newIndex >= editorSearchResults.value.length) newIndex = 0
  goToEditorSearchResult(newIndex)
}

function removeEditorSearchHighlights() {
  // Remove visual highlights (se implementado via CSS/overlay)
}

function onEditorSearchKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault()
    if (e.shiftKey) {
      goToPrevEditorSearchResult()
    } else {
      goToNextEditorSearchResult()
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    closeEditorSearch()
  }
}

watch(editorSearchQuery, () => {
  performEditorSearch()
})

// ============================================================
// Undo/Redo do Editor (Quill)
// ============================================================
function editorUndo() {
  const quill = editorRef.value?.$el?.querySelector('.ql-editor')?.parentElement?.__quill
  if (quill?.history) {
    quill.history.undo()
  }
}

function editorRedo() {
  const quill = editorRef.value?.$el?.querySelector('.ql-editor')?.parentElement?.__quill
  if (quill?.history) {
    quill.history.redo()
  }
}

// Chaves
const storedKeys = ref(getStoredApiKeys())
function refreshStoredKeys() {
  storedKeys.value = getStoredApiKeys()
}

// Card type
const cardType = ref('basic')
const cardTypeOptions = ref([
  { label: 'Basicos', value: 'basic', description: 'Gerar cartoes do tipo basico' },
  { label: 'Cloze', value: 'cloze', description: 'Gerar cartoes Cloze (preenchimento)' },
  { label: 'Basicos + Cloze', value: 'both', description: 'Gerar ambos os tipos' }
])

// Card quantity slider
const numCardsEnabled = ref(false)
const numCardsSlider = ref(10)

// Generate Modal (unified modal for generation settings)
const generateModalVisible = ref(false)
const generateStep = ref('1') // '1': Quantidade, '2': Prompts (string for PrimeVue Stepper)
const customPrompts = ref(null)

// Prompts salvos persistentes (localStorage)
const LS_CUSTOM_PROMPTS_KEY = 'green-deck.custom-prompts.v1'
const savedCustomPrompts = ref(null) // { systemPrompt, guidelines, generationPrompt }
const promptSettingsVisible = ref(false)
const defaultPromptsData = ref(null) // Cache dos prompts padrão do servidor

// Computed: verifica se há prompts personalizados salvos
const hasCustomPromptsSaved = computed(() => {
  const saved = savedCustomPrompts.value
  if (!saved) return false
  return !!(saved.userProfile || saved.systemPrompt || saved.guidelines || saved.generationPrompt)
})

const quantityMode = ref('auto')

function onCustomPromptsUpdate(prompts) {
  customPrompts.value = prompts
}

// ============================================================
// Gerenciamento de Prompts Persistentes
// ============================================================
function loadSavedPrompts() {
  try {
    const raw = localStorage.getItem(LS_CUSTOM_PROMPTS_KEY)
    if (raw) {
      savedCustomPrompts.value = JSON.parse(raw)
    }
  } catch (e) {
    console.error('Erro ao carregar prompts salvos:', e)
  }
}

function savePromptSettings(prompts) {
  try {
    if (!prompts || Object.keys(prompts).length === 0) {
      // Se não há prompts customizados, remove do localStorage
      localStorage.removeItem(LS_CUSTOM_PROMPTS_KEY)
      savedCustomPrompts.value = null
    } else {
      localStorage.setItem(LS_CUSTOM_PROMPTS_KEY, JSON.stringify(prompts))
      savedCustomPrompts.value = prompts
    }
    notify('Prompts salvos com sucesso', 'success', 3000)
    promptSettingsVisible.value = false
  } catch (e) {
    console.error('Erro ao salvar prompts:', e)
    notify('Erro ao salvar prompts', 'error', 4000)
  }
}

function resetPromptsToDefaults() {
  try {
    localStorage.removeItem(LS_CUSTOM_PROMPTS_KEY)
    savedCustomPrompts.value = null
    notify('Prompts restaurados aos padrões', 'success', 3000)
    promptSettingsVisible.value = false
  } catch (e) {
    console.error('Erro ao restaurar prompts:', e)
    notify('Erro ao restaurar prompts', 'error', 4000)
  }
}

async function openPromptSettings() {
  // Carrega prompts padrão do servidor se ainda não tem
  if (!defaultPromptsData.value) {
    try {
      const { getDefaultPrompts } = await import('@/services/api.js')
      defaultPromptsData.value = await getDefaultPrompts()
    } catch (e) {
      console.error('Erro ao carregar prompts padrão:', e)
      notify('Erro ao carregar prompts padrão', 'error', 4000)
      return
    }
  }
  promptSettingsVisible.value = true
}

// Obtém os prompts efetivos para geração (prioridade: temporários > salvos > padrões)
function getEffectivePrompts() {
  // Se há prompts temporários da sessão (do modal de geração), usa eles
  if (customPrompts.value) {
    return customPrompts.value
  }
  // Se há prompts salvos no localStorage, usa eles
  if (savedCustomPrompts.value && hasCustomPromptsSaved.value) {
    return savedCustomPrompts.value
  }
  // Caso contrário, retorna null (usa padrões do servidor)
  return null
}

async function openGenerateModal() {
  // Atualizar info do Ollama antes de abrir (para GPU/VRAM)
  if (getModelInfo(selectedModel.value)?.provider === 'ollama') {
    try {
      ollamaInfo.value = await fetchOllamaInfo()
    } catch (e) {
      console.error('Erro ao buscar info do Ollama:', e)
    }
  }
  generateStep.value = '1'
  quantityMode.value = numCardsEnabled.value ? 'manual' : 'auto'
  generateModalVisible.value = true
}

// Atualiza info do Ollama periodicamente durante a geração
let ollamaInfoInterval = null

function startOllamaInfoPolling() {
  if (getModelInfo(selectedModel.value)?.provider !== 'ollama') return
  
  // Atualiza a cada 2 segundos durante a geração
  ollamaInfoInterval = setInterval(async () => {
    try {
      ollamaInfo.value = await fetchOllamaInfo()
    } catch (e) {
      console.error('Erro ao atualizar info do Ollama:', e)
    }
  }, 2000)
}

function stopOllamaInfoPolling() {
  if (ollamaInfoInterval) {
    clearInterval(ollamaInfoInterval)
    ollamaInfoInterval = null
  }
}

// Handler para o novo componente GenerateModal
function onGenerateModalConfirm({ quantityMode: qMode, numCards, cardType: cType, customPrompts: prompts }) {
  numCardsEnabled.value = (qMode === 'manual')
  numCardsSlider.value = numCards
  if (cType) cardType.value = cType
  if (prompts) customPrompts.value = prompts
  generateModalVisible.value = false
  generateCardsFromSelection()
}

// Model selection
const selectedModel = ref(null)           // Modelo para geração de cards (dinâmico)
const selectedValidationModel = ref(null) // Modelo para validação de qualidade
const selectedAnalysisModel = ref(null)   // Modelo para análise de texto
const availableModels = ref([])
const isLoadingModels = ref(false)

// Ollama info state (para fallback e info GPU/VRAM)
const ollamaInfo = ref(null)
const isLoadingOllamaInfo = ref(false)
const ollamaModelSelectionVisible = ref(false) // Modal para seleção quando múltiplos modelos

// Lista de modelos de embedding
const embeddingModels = computed(() => availableModels.value.filter(m => m.type === 'embedding'))

// Helper functions para tags de modelo
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

function getModelInfo(modelName) {
  return availableModels.value.find(m => m.name === modelName)
}

// Helper para detectar modelos de embedding
function isEmbeddingModel(name) {
  if (!name) return false
  const patterns = ['embed', 'nomic', 'mxbai', 'bge-', 'gte-', 'e5-', 'sentence-', 'all-minilm']
  return patterns.some(p => name.toLowerCase().includes(p))
}

// Computed: modelos LLM do Ollama (excluindo embeddings)
const ollamaLlmModels = computed(() => {
  if (!ollamaInfo.value?.models) return []
  return ollamaInfo.value.models.filter(m => !isEmbeddingModel(m.name))
})

// Computed: info do modelo em execução (para GPU/VRAM)
const runningModelInfo = computed(() => {
  if (!ollamaInfo.value?.running_models || !selectedModel.value) return null
  return ollamaInfo.value.running_models.find(m =>
    m.name === selectedModel.value ||
    m.name.startsWith(selectedModel.value.split(':')[0])
  )
})

// Computed: info atual do modelo (running ou inferido)
const currentModelInfo = computed(() => {
  if (runningModelInfo.value) return runningModelInfo.value
  // Se modelo Ollama não está rodando, assume CPU (conservador)
  if (ollamaInfo.value?.connected && getModelInfo(selectedModel.value)?.provider === 'ollama') {
    return { using_gpu: false, size_vram_mb: 0, name: selectedModel.value }
  }
  return null
})

// Seleciona um modelo Ollama do modal de seleção
function selectOllamaModel(modelName) {
  selectedModel.value = modelName
  selectedValidationModel.value = modelName
  selectedAnalysisModel.value = modelName
  ollamaModelSelectionVisible.value = false
  saveModelSelection()
  notify(`Modelo selecionado: ${modelName}`, 'success', 3000)

  // Se estiver no fluxo de onboarding, mostra modal de API keys em seguida (se necessário)
  if (isOnboardingFlow.value) {
    setTimeout(() => showApiKeysIfNeeded(), 300)
  }
}

// Inicializa seleção de modelo com fallback para Ollama
async function initializeModelSelection() {
  // 0. Atualizar estado das API keys
  refreshStoredKeys()

  // 1. Buscar info do Ollama
  try {
    isLoadingOllamaInfo.value = true
    ollamaInfo.value = await fetchOllamaInfo()
  } catch (e) {
    console.error('Erro ao buscar info do Ollama:', e)
  } finally {
    isLoadingOllamaInfo.value = false
  }

  // 2. Verificar modelo salvo no localStorage
  const savedModel = localStorage.getItem('green-deck.selected-model')
  const savedValidationModel = localStorage.getItem('green-deck.selected-validation-model')
  const savedAnalysisModel = localStorage.getItem('green-deck.selected-analysis-model')

  // Helper: verifica se modelo requer API key que não está mais disponível
  const isModelAvailable = (modelName) => {
    if (!modelName) return false
    const lower = modelName.toLowerCase()

    // Modelos que requerem API keys
    if (lower.includes('sonar') && !storedKeys.value.perplexityApiKey) return false
    if ((lower.includes('gpt') || lower.startsWith('o1-')) && !storedKeys.value.openaiApiKey) return false
    if (lower.includes('claude') && !storedKeys.value.anthropicApiKey) return false

    // Se é um modelo de API (não-Ollama) e passou nas verificações acima, está disponível
    const isApiModel = lower.includes('sonar') || lower.includes('gpt') ||
                       lower.startsWith('o1-') || lower.includes('claude')
    if (isApiModel) return true

    // Para modelos Ollama: verificar se existe na lista (correspondência parcial)
    // Extrai nome base sem tag de versão (ex: "llama3.2:latest" -> "llama3.2")
    const baseName = modelName.split(':')[0].toLowerCase()
    const isOllamaModel = ollamaInfo.value?.models?.some(m => {
      const modelBaseName = m.name.split(':')[0].toLowerCase()
      return modelBaseName === baseName || m.name === modelName
    })

    return isOllamaModel
  }

  if (savedModel && isModelAvailable(savedModel)) {
    // Usuário já tem modelo salvo E ele está disponível - usar
    selectedModel.value = savedModel
    selectedValidationModel.value = (savedValidationModel && isModelAvailable(savedValidationModel)) ? savedValidationModel : savedModel
    selectedAnalysisModel.value = (savedAnalysisModel && isModelAvailable(savedAnalysisModel)) ? savedAnalysisModel : savedModel
    return
  }

  // Se modelo salvo não está mais disponível, limpar do localStorage
  if (savedModel && !isModelAvailable(savedModel)) {
    localStorage.removeItem('green-deck.selected-model')
    localStorage.removeItem('green-deck.selected-validation-model')
    localStorage.removeItem('green-deck.selected-analysis-model')
    console.log(`Modelo salvo "${savedModel}" não está mais disponível, resetando...`)
  }

  // 3. Lógica de fallback: Ollama disponível (independente de API keys)
  // NOTA: Se estamos no fluxo de intro (primeira execução), NÃO abre modal Ollama aqui
  // O fluxo de intro vai disparar os modais na ordem correta ao finalizar
  const introShown = localStorage.getItem(INTRO_SHOWN_KEY)
  const isFirstRun = !introShown

  // Se já temos um modelo selecionado em memória, não precisa fazer nada
  if (selectedModel.value) {
    return
  }

  if (ollamaInfo.value?.connected) {
    const llmModels = ollamaLlmModels.value

    if (llmModels.length === 1) {
      // Apenas 1 modelo LLM disponível - usar automaticamente
      selectedModel.value = llmModels[0].name
      selectedValidationModel.value = llmModels[0].name
      selectedAnalysisModel.value = llmModels[0].name
      if (!isFirstRun) {
        notify(`Usando modelo Ollama: ${llmModels[0].name}`, 'info', 3000)
      }
    } else if (llmModels.length > 1 && !isFirstRun) {
      // Mais de 1 modelo - mostrar modal de seleção (apenas se não é primeira execução)
      ollamaModelSelectionVisible.value = true
    } else if (!hasAnyApiKey() && !isFirstRun) {
      // Nenhum modelo LLM disponível e sem API keys
      notify('Nenhum modelo LLM disponível no Ollama. Instale um modelo ou configure uma API key.', 'warn', 6000)
    }
  } else if (!hasAnyApiKey() && !isFirstRun) {
    // Ollama não conectado e sem API keys
    notify('Ollama não conectado. Inicie o Ollama ou configure uma API key.', 'warn', 6000)
  }
}

// Watcher: detecta quando Ollama fica disponível (via WebSocket)
// Se não há modelo selecionado e não há API keys, mostra modal de seleção
watch(
  () => ollamaWsStatus.value.connected,
  async (isConnected, wasConnected) => {
    // Só reage quando Ollama FICA disponível (transição de false para true)
    // E não estamos no fluxo de intro (primeira execução)
    const introShown = localStorage.getItem(INTRO_SHOWN_KEY)
    if (isConnected && !wasConnected && !selectedModel.value && !hasAnyApiKey() && introShown) {
      console.log('[Ollama] Ficou disponível, buscando modelos...')

      // Buscar info atualizada do Ollama
      try {
        ollamaInfo.value = await fetchOllamaInfo()
      } catch (e) {
        console.error('Erro ao buscar info do Ollama:', e)
        return
      }

      const llmModels = ollamaLlmModels.value

      if (llmModels.length === 1) {
        // Apenas 1 modelo - usar automaticamente
        selectedModel.value = llmModels[0].name
        selectedValidationModel.value = llmModels[0].name
        selectedAnalysisModel.value = llmModels[0].name
        notify(`Ollama conectado! Usando modelo: ${llmModels[0].name}`, 'success', 4000)
      } else if (llmModels.length > 1) {
        // Múltiplos modelos - mostrar modal de seleção
        notify('Ollama conectado! Selecione um modelo.', 'info', 3000)
        ollamaModelSelectionVisible.value = true
      }
    }
  }
)

// Busca
const cardSearch = ref('')
const searchExpanded = ref(false)
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
// Seleção múltipla de cards
// ============================================================
const selectedCards = ref(new Set())
const isSelectionMode = ref(false)

const hasSelectedCards = computed(() => selectedCards.value.size > 0)
const selectedCount = computed(() => selectedCards.value.size)
const allCardsSelected = computed(() => 
  cards.value.length > 0 && selectedCards.value.size === cards.value.length
)

function toggleCardSelection(index, event) {
  if (event) event.stopPropagation()
  if (selectedCards.value.has(index)) {
    selectedCards.value.delete(index)
  } else {
    selectedCards.value.add(index)
  }
  // Force reactivity
  selectedCards.value = new Set(selectedCards.value)
}

function toggleSelectAll() {
  if (allCardsSelected.value) {
    selectedCards.value = new Set()
  } else {
    selectedCards.value = new Set(cards.value.map((_, i) => i))
  }
}

function clearSelection() {
  selectedCards.value = new Set()
  isSelectionMode.value = false
}

function bulkDeleteSelected() {
  if (selectedCards.value.size === 0) return
  // Sort descending to delete from end first (preserve indices)
  const indices = Array.from(selectedCards.value).sort((a, b) => b - a)
  // Push to undo history
  const deletedCards = indices.map(i => ({ index: i, card: { ...cards.value[i] } }))
  pushToUndoHistory({ type: 'bulk-delete', cards: deletedCards })
  // Delete
  indices.forEach(i => cards.value.splice(i, 1))
  notify(`${indices.length} cartões removidos`, 'success', 2500)
  clearSelection()
  schedulePersistActiveSession()
}

function bulkExportSelected() {
  if (selectedCards.value.size === 0) return
  // Trigger Anki export with only selected cards
  exportToAnkiOpenConfig(Array.from(selectedCards.value))
}

function toggleSelectionMode() {
  isSelectionMode.value = !isSelectionMode.value
  if (!isSelectionMode.value) {
    selectedCards.value = new Set()
  }
}

// ============================================================
// Undo/Redo History
// ============================================================
const undoHistory = ref([])
const redoHistory = ref([])
const MAX_UNDO_HISTORY = 50

const canUndo = computed(() => undoHistory.value.length > 0)
const canRedo = computed(() => redoHistory.value.length > 0)

function pushToUndoHistory(action) {
  undoHistory.value.push(action)
  if (undoHistory.value.length > MAX_UNDO_HISTORY) {
    undoHistory.value.shift()
  }
  // Clear redo when new action is performed
  redoHistory.value = []
}

function undo() {
  if (undoHistory.value.length === 0) return
  const action = undoHistory.value.pop()
  
  if (action.type === 'delete') {
    // Restore single card
    cards.value.splice(action.index, 0, action.card)
    redoHistory.value.push(action)
    notify('Cartão restaurado', 'success', 2000)
  } else if (action.type === 'bulk-delete') {
    // Restore multiple cards (in order)
    action.cards.sort((a, b) => a.index - b.index).forEach(item => {
      cards.value.splice(item.index, 0, item.card)
    })
    redoHistory.value.push(action)
    notify(`${action.cards.length} cartões restaurados`, 'success', 2000)
  } else if (action.type === 'clear-all') {
    cards.value = action.cards
    redoHistory.value.push(action)
    notify('Todos os cartões restaurados', 'success', 2000)
  }
  
  schedulePersistActiveSession()
}

function redo() {
  if (redoHistory.value.length === 0) return
  const action = redoHistory.value.pop()
  
  if (action.type === 'delete') {
    cards.value.splice(action.index, 1)
    undoHistory.value.push(action)
    notify('Redo: cartão removido', 'info', 2000)
  } else if (action.type === 'bulk-delete') {
    const indices = action.cards.map(c => c.index).sort((a, b) => b - a)
    indices.forEach(i => cards.value.splice(i, 1))
    undoHistory.value.push(action)
    notify(`Redo: ${action.cards.length} cartões removidos`, 'info', 2000)
  } else if (action.type === 'clear-all') {
    cards.value = []
    undoHistory.value.push(action)
    notify('Redo: todos os cartões removidos', 'info', 2000)
  }
  
  schedulePersistActiveSession()
}

// ============================================================
// Highlight de busca (with XSS sanitization)
// ============================================================
function highlightSearchTerm(text) {
  const q = (cardSearch.value || '').trim()
  if (!q) return sanitizeHtml(text)
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  const highlighted = String(text || '').replace(regex, '<mark class="search-highlight">$1</mark>')
  return sanitizeHtml(highlighted)
}

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

const logsHasError = computed(() => logs.value.some((l) => l?.type === 'error' || l?.type === 'danger'))

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
const progressStage = ref('')
const progressIcon = ref('')
const progressDetails = ref({})
const generationAbortController = ref(null)
const generationRequestId = ref(null)
const generationCanceling = ref(false)
const generationWasCancelled = ref(false)
let generationForceAbortTimer = null
const generationProgressCancellable = computed(() =>
  progressVisible.value && generating.value && !!generationAbortController.value
)

function setupGenerationCancellation() {
  const controller = new AbortController()
  generationAbortController.value = controller
  generationRequestId.value = safeId()
  generationCanceling.value = false
  generationWasCancelled.value = false
  if (generationForceAbortTimer) {
    clearTimeout(generationForceAbortTimer)
    generationForceAbortTimer = null
  }
  return {
    signal: controller.signal,
    requestId: generationRequestId.value
  }
}

function clearGenerationCancellation() {
  generationAbortController.value = null
  generationRequestId.value = null
  generationCanceling.value = false
  generationWasCancelled.value = false
  if (generationForceAbortTimer) {
    clearTimeout(generationForceAbortTimer)
    generationForceAbortTimer = null
  }
}

async function cancelCurrentGeneration() {
  const controller = generationAbortController.value
  if (!controller || generationCanceling.value) return

  generationCanceling.value = true
  const requestId = generationRequestId.value

  try {
    if (requestId) {
      await cancelCardsGeneration(requestId)
    }
  } catch {
    addLog('Erro ao sinalizar cancelamento no backend (seguindo com abort local)', 'warn')
  } finally {
    generationWasCancelled.value = true
    setProgress(progressValue.value, 'Cancelando... aguardando retorno parcial', null, 'pi pi-times')

    // Fallback: se o backend não responder, aborta localmente (evita travar UI)
    generationForceAbortTimer = setTimeout(() => {
      try {
        controller.abort()
      } catch {}
    }, 20000)
  }
}

function showProgress(title = 'Processing...') {
  progressTitle.value = title
  progressValue.value = 0
  progressStage.value = ''
  progressIcon.value = ''
  progressDetails.value = {}
  progressVisible.value = true
}

function setProgress(v, stage = null, details = null, icon = null) {
  progressValue.value = Math.max(0, Math.min(100, Math.floor(v)))
  if (stage) progressStage.value = stage
  if (icon) progressIcon.value = icon
  if (details) progressDetails.value = { ...progressDetails.value, ...details }
}

function completeProgress() {
  setProgress(100, 'Concluído!', null, 'pi pi-check-circle')
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
    // Salva apenas se houver valor (evita salvar 'null' como string)
    if (selectedModel.value) {
      localStorage.setItem('green-deck.selected-model', selectedModel.value)
    }
    if (selectedValidationModel.value) {
      localStorage.setItem('green-deck.selected-validation-model', selectedValidationModel.value)
    }
    if (selectedAnalysisModel.value) {
      localStorage.setItem('green-deck.selected-analysis-model', selectedAnalysisModel.value)
    }
    modelSelectionVisible.value = false
    notify('Modelos salvos com sucesso', 'success', 3000)
  } catch (e) {
    notify('Erro ao salvar modelos', 'error', 3000)
  }
}

// ============================================================
// Intro Modal (Onboarding)
// ============================================================
const introModalVisible = ref(false)
const introStep = ref(1)
const dontShowIntroAgain = ref(false)
const isOnboardingFlow = ref(false) // Flag para controlar fluxo de onboarding
const TOTAL_INTRO_STEPS = 3

function finishIntro() {
  if (dontShowIntroAgain.value) {
    localStorage.setItem(INTRO_SHOWN_KEY, 'true')
  }
  introModalVisible.value = false
  // Mantém flag de onboarding ativa para controlar fluxo pós-intro
  isOnboardingFlow.value = true
  // Dispara fluxo pós-intro (Ollama selection -> API keys)
  triggerPostIntroFlow()
}

// Handler para o componente IntroModal
function onIntroComplete({ dontShowAgain }) {
  if (dontShowAgain) {
    localStorage.setItem(INTRO_SHOWN_KEY, 'true')
  }
  isOnboardingFlow.value = true
  triggerPostIntroFlow()
}

function triggerPostIntroFlow() {
  // 1. Se Ollama tem múltiplos modelos, mostra seleção
  if (ollamaLlmModels.value.length > 1) {
    ollamaModelSelectionVisible.value = true
  } else {
    // 2. Senão, verifica se precisa configurar API keys
    showApiKeysIfNeeded()
  }
}

function showApiKeysIfNeeded() {
  const keys = getStoredApiKeys()
  if (!keys.anthropicApiKey && !keys.openaiApiKey && !keys.perplexityApiKey) {
    // Nenhuma chave configurada, mostra modal de API keys
    apiKeyVisible.value = true
  }
  // Finaliza fluxo de onboarding
  isOnboardingFlow.value = false
}

// ============================================================
// API Keys Dialog
// ============================================================
const apiKeyVisible = ref(false)

function openApiKeys() {
  refreshStoredKeys()
  apiKeyVisible.value = true
}

// Verifica se há alguma chave API salva
const hasStoredApiKeys = computed(() => {
  return !!(storedKeys.value.anthropicApiKey || storedKeys.value.openaiApiKey || storedKeys.value.perplexityApiKey)
})

// ============================================================
// Decks
// ============================================================
async function fetchDecks() {
  refreshStoredKeys()
  decks.value = { General: 'general' }
  currentDeck.value = 'General'
}

// ============================================================
// Analyze
// ============================================================
async function analyzeDocumentContext(text) {
  const normalized = normalizePlainText(text)
  if (!normalized || normalized.length < 100 || isAnalyzing.value) return

  try {
    isAnalyzing.value = true
    startTimer('Analisando...')
    addLog(`Starting text analysis with model: ${selectedAnalysisModel.value}...`, 'info')
    showProgress('Analisando texto...')
    setProgress(25)

    const result = await analyzeText(text, selectedAnalysisModel.value)
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
    notify('Análise concluída. A qualidade dos cartões tende a melhorar.', 'success', 3800)

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
// Topic Segmentation - Marcação automática por tópico
// ============================================================

function scheduleTopicSegmentation(text) {
  if (topicSegmentTimer) clearTimeout(topicSegmentTimer)
  // Mostra modal de confirmação ao invés de executar diretamente
  topicSegmentTimer = setTimeout(() => {
    if (text.length >= 200) {
      pendingTextForSegmentation.value = text
      showTopicConfirmModal.value = true
    }
  }, 400)
}

function confirmTopicSegmentation() {
  showTopicConfirmModal.value = false
  // Tenta obter o texto do editor em ordem de preferência
  let currentText = editorRef.value?.getRawText?.()
  if (!currentText || currentText.length === 0) {
    currentText = editorRef.value?.getFullText?.()
  }
  if (!currentText || currentText.length === 0) {
    currentText = pendingTextForSegmentation.value
  }
  
  console.log('[TopicSegmentation] Using text from editor, length:', currentText?.length)
  console.log('[TopicSegmentation] Text preview:', currentText?.substring(0, 100))
  
  if (currentText && currentText.length >= 200) {
    performTopicSegmentation(currentText)
  } else {
    addLog('[Segmentação] ⚠ Texto insuficiente para análise (mínimo 200 caracteres)', 'warn')
    notify('Texto insuficiente para análise. Mínimo 200 caracteres.', 'warn', 3000)
  }
  pendingTextForSegmentation.value = ''
}

function cancelTopicSegmentation() {
  showTopicConfirmModal.value = false
  pendingTextForSegmentation.value = ''
}

async function performTopicSegmentation(text) {
  if (isSegmentingTopics.value || text.length < 200) {
    console.log('[TopicSegmentation] Skipped - already running or text too short')
    return
  }

  addLog('[Segmentação] Iniciando análise de segmentação por tópicos', 'info')
  console.log('[TopicSegmentation] Starting with text length:', text.length)
  console.log('[TopicSegmentation] Text preview (first 200 chars):', text.substring(0, 200))
  console.log('[TopicSegmentation] Using model:', selectedAnalysisModel.value)

  // Usar o texto passado como parâmetro (que já foi validado e é confiável)
  const textLength = text.length
  console.log('[TopicSegmentation] Text length from parameter:', textLength)
  addLog(`[Segmentação] Tamanho do texto: ${textLength} caracteres`, 'info')
  addLog(`[Segmentação] Modelo: ${selectedAnalysisModel.value}`, 'info')

  isSegmentingTopics.value = true
  showTopicLegend.value = true
  topicSegmentProgress.value = 0
  topicSegmentStage.value = 'Iniciando...'

  try {
    const result = await segmentTopics(text, selectedAnalysisModel.value, (event) => {
      console.log('[TopicSegmentation] Progress event received:', JSON.stringify(event))
      const stage = event.stage || event.data?.stage || 'processing'
      const percent = event.data?.percent || 0
      console.log('[TopicSegmentation] Extracted - Stage:', stage, 'Percent:', percent)
      console.log('[TopicSegmentation] Formatted stage:', formatSegmentStage(stage))
      
      // Atualiza o state de forma mais segura
      topicSegmentProgress.value = percent
      const formattedStage = formatSegmentStage(stage)
      console.log('[TopicSegmentation] Setting topicSegmentStage to:', formattedStage)
      topicSegmentStage.value = formattedStage
      
      addLog(`[Segmentação] ${formattedStage} (${percent}%)`, 'info')
    })

    console.log('[TopicSegmentation] Result:', result)
    console.log('[TopicSegmentation] Backend text_length:', result.text_length)
    addLog(`[Segmentação] ✓ Análise concluída com sucesso`, 'success')

    // Validar comprimento do texto usando o texto original passado como parâmetro
    const backendTextLength = result.text_length || 0
    console.log('[TopicSegmentation] Length comparison:', { parameterTextLength: text.length, backendTextLength, diff: Math.abs(text.length - backendTextLength) })

    // Aviso se houver diferença significativa (mais de 50 caracteres)
    if (backendTextLength > 0 && Math.abs(text.length - backendTextLength) > 50) {
      console.warn('[TopicSegmentation] Text length mismatch - positions may be incorrect')
      addLog('[Segmentação] ⚠ Diferença detectada no comprimento do texto', 'warn')
    }

    topicSegments.value = result.segments
    topicDefinitions.value = result.topics

    console.log('[TopicSegmentation] Segments received:', result.segments.length)
    console.log('[TopicSegmentation] Topics received:', result.topics)
    console.log('[TopicSegmentation] First segment:', result.segments[0])
    addLog(`[Segmentação] ${result.segments.length} trechos identificados em ${result.topics.length} tópico(s)`, 'info')
    result.topics.forEach(topic => {
      addLog(`  • ${topic.name}: ${result.segments.filter(s => s.topic_id === topic.id).length} trechos`, 'info')
    })

    // Aplica highlights no editor
    if (result.segments.length > 0) {
      addLog(`[Segmentação] Aplicando ${result.segments.length} highlights no editor...`, 'info')
      const highlightData = result.segments.map(s => {
        const topic = result.topics.find(t => t.id === s.topic_id)
        console.log('[TopicSegmentation] Segment topic_id:', s.topic_id, '-> topic:', topic?.id, '-> color:', topic?.color)
        return {
          start: s.start,
          end: s.end,
          color: topic?.color || 'var(--app-text)'
        }
      })
      console.log('[TopicSegmentation] Applying', highlightData.length, 'highlights')
      console.log('[TopicSegmentation] First highlight:', highlightData[0])

      // Aguarda próximo tick para garantir que o editor está pronto
      await nextTick()

      const applied = editorRef.value?.applyTopicHighlights(highlightData)
      console.log('[TopicSegmentation] Applied result:', applied)
      addLog(`[Segmentação] ✓ Highlights aplicados com sucesso`, 'success')

      notify(`${result.segments.length} trechos marcados por tópico`, 'success', 3000)
    } else {
      addLog('[Segmentação] ⚠ Nenhum tópico foi identificado no texto', 'warn')
      notify('Nenhum tópico identificado no texto', 'info', 3000)
      showTopicLegend.value = false
    }

    schedulePersistActiveSession()
  } catch (err) {
    console.error('[TopicSegmentation] Error:', err)
    const errorMsg = err?.message || String(err)
    addLog(`[Segmentação] ✗ Erro ao segmentar tópicos: ${errorMsg}`, 'error')
    notify('Erro ao segmentar tópicos: ' + errorMsg, 'error', 5000)
    showTopicLegend.value = false
  } finally {
    isSegmentingTopics.value = false
    topicSegmentProgress.value = 100
  }
}

function formatSegmentStage(stage) {
  if (!stage) return 'Processando...'
  
  const stages = {
    'preparing': '📋 Preparando texto...',
    'building_prompt': '✍️ Construindo prompt de análise...',
    'calling_llm': '🤖 Enviando para análise de IA...',
    'parsing_response': '📖 Processando resposta da IA...',
    'building_topics': '🏷️ Identificando e agrupando tópicos...',
    'mapping_segments': '🗺️ Mapeando trechos para tópicos...',
    'validating': '✓ Validando resultados...',
    'done': '✅ Concluído'
  }
  
  const formatted = stages[stage]
  if (formatted) {
    console.log('[formatSegmentStage] Found mapping for stage:', stage, '->', formatted)
    return formatted
  }
  
  // Se não encontrar um mapeamento, capitalize o stage
  console.log('[formatSegmentStage] No mapping for stage:', stage, '- using as-is')
  return String(stage)
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ') + '...'
}

function onNavigateToSegment(segment) {
  editorRef.value?.scrollToPosition(segment.start, segment.end - segment.start)
}

function clearTopicHighlights() {
  editorRef.value?.clearTopicHighlights()
  topicSegments.value = []
  topicDefinitions.value = []
  showTopicLegend.value = false
  schedulePersistActiveSession()
}

// ============================================================
// Gerar cards - com fallback: seleção → highlights → texto completo
// ============================================================
const generating = ref(false)
const lastGenerationSource = ref(null) // 'selection' | 'highlight' | 'full'
const lastGenerationWordCount = ref(0)

/**
 * Resolve which content to use for card generation
 * Priority: 1. Mouse selection → 2. Highlighted content → 3. Full text (with warning)
 * @returns {object} { source, content, shouldWarn, message }
 */
function resolveGenerationContent() {
  // 1. Check for mouse selection first
  const selection = (selectedText.value || '').trim()
  if (selection) {
    console.log('[resolveGenerationContent] Using mouse selection:', selection.substring(0, 50) + '...')
    return {
      source: 'selection',
      content: selection,
      shouldWarn: false,
      message: null
    }
  }

  // 2. Check for highlighted content
  const highlightData = editorRef.value?.getHighlightedContent?.()
  console.log('[resolveGenerationContent] Highlight data:', highlightData)
  
  if (highlightData && highlightData.count > 0 && highlightData.combined) {
    const count = highlightData.count
    console.log('[resolveGenerationContent] Using highlights:', count, 'parts')
    return {
      source: 'highlight',
      content: highlightData.combined,
      shouldWarn: false,
      message: `Gerando a partir de ${count} trecho${count > 1 ? 's' : ''} marcado${count > 1 ? 's' : ''}`
    }
  }

  // 3. Fall back to full text with warning
  const fullText = (editorRef.value?.getFullText?.() || lastFullText.value || '').trim()
  console.log('[resolveGenerationContent] Falling back to full text, length:', fullText.length)
  
  if (!fullText) {
    return {
      source: 'empty',
      content: '',
      shouldWarn: true,
      message: 'Nenhum texto disponível para gerar cartões'
    }
  }

  return {
    source: 'full',
    content: fullText,
    shouldWarn: true,
    message: 'Nenhum texto selecionado ou marcado. Usando todo o texto para geração.'
  }
}

/**
 * Get a human-readable label for the content source
 */
function getSourceLabel() {
  switch (lastGenerationSource.value) {
    case 'selection':
      return 'Texto selecionado'
    case 'highlight':
      const hl = editorRef.value?.getHighlightedContent?.()
      const count = hl?.count || highlightPositions.value.length
      return `${count} marcação${count > 1 ? 'ões' : ''}`
    case 'full':
      return 'Texto completo'
    default:
      return ''
  }
}

async function generateCardsFromSelection() {
  // Resolve which content to use (fallback hierarchy)
  const resolved = resolveGenerationContent()

  // Handle empty content
  if (resolved.source === 'empty') {
    notify(resolved.message || 'Nenhum texto disponível', 'warn', 4500)
    return
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
  lastGenerationWordCount.value = countWords(resolved.content)
  const text = resolved.content

  try {
    generating.value = true
    const { signal, requestId } = setupGenerationCancellation()
    startTimer('Gerando...')
    startOllamaInfoPolling() // Inicia polling de info do Ollama
    const sourceLabel = getSourceLabel()
    addLog(`Iniciando geração de cartões (${cardType.value}) a partir de: ${sourceLabel}`, 'info')
    console.log('Card type being sent:', cardType.value, '| Source:', resolved.source)
    showProgress('Gerando cartões...')
    setProgress(10, 'Preparando prompt...', null, 'pi pi-spinner pi-spin')

    const deckNames = Object.keys(decks.value || {}).join(', ')
    const newCards = await generateCardsWithStream(
      text,
      deckNames,
      documentContext.value,
      cardType.value,
      selectedModel.value,
      ({ stage, data }) => {
        try {
          // Tratamento de erro de escassez de conteudo
          if (stage === 'error' && data?.type === 'content_scarcity') {
            const msg = `${data.error} (Recomendado: ${data.recommended_max} cartões)`
            notify(msg, 'warn', 8000)
            addLog(msg, 'error')
            generating.value = false
            progressVisible.value = false
            stopTimer()
            throw new Error(msg)
          }

          // Tratamento de warning
          if (stage === 'warning' && data?.message) {
            notify(data.message, 'warn', 5000)
            addLog(data.message, 'warn')
          }

          if (stage === 'cancelled') {
            generationWasCancelled.value = true
            addLog(`Geração cancelada pelo usuário (parcial: ${data?.partial_cards ?? 0} cartões)`, 'warn')
            return
          }

          if (stage === 'stage' && data?.stage) {
            const s = data.stage

            // Mapeamento de estagios para UI amigavel (usando icones PrimeVue)
            const stageMap = {
              'generation_started': { progress: 15, label: 'Enviando prompt ao LLM...', icon: 'pi pi-send' },
              'parsed': { 
                progress: 45, 
                label: `Parseados ${data.count || 0} cartões`, 
                icon: 'pi pi-file-edit',
                details: { parsed: data.count, mode: data.mode, beforeFilter: data.before_type_filter }
              },
              'src_filtered': { 
                progress: 55, 
                label: `Validação SRC: ${data.kept || 0} aprovados, ${data.dropped || 0} removidos`, 
                icon: 'pi pi-search',
                details: { srcKept: data.kept, srcDropped: data.dropped }
              },
              'llm_relevance_filtered': { 
                progress: 62, 
                label: `Filtro relevância: ${data.kept || 0} mantidos, ${data.dropped || 0} removidos`, 
                icon: 'pi pi-bullseye',
                details: { relevanceKept: data.kept, relevanceDropped: data.dropped }
              },
              'src_bypassed': { 
                progress: 58, 
                label: `SRC bypass: ${data.count || 0} cartões mantidos`, 
                icon: 'pi pi-bolt' 
              },
              'src_relaxed': { 
                progress: 65, 
                label: `SRC relaxado: ${data.total_after_relax || 0} cartões (min: ${data.target_min || 0})`, 
                icon: 'pi pi-sync' 
              },
              'lang_check': { 
                progress: 70, 
                label: `Idioma: ${data.lang || 'unknown'} (${data.cards || 0} cartões)`, 
                icon: 'pi pi-globe' 
              },
              'repair_pass': { 
                progress: 72, 
                label: `Iniciando reparo... (${data.reason || ''})`, 
                icon: 'pi pi-wrench' 
              },
              'repair_parsed': { 
                progress: 80, 
                label: `Reparo: ${data.count || 0} cartões adicionais`, 
                icon: 'pi pi-wrench' 
              },
              'repair_src_filtered': { 
                progress: 85, 
                label: `Reparo SRC: ${data.kept || 0} aprovados`, 
                icon: 'pi pi-search',
                details: { srcKept: data.kept, srcDropped: data.dropped }
              },
              'repair_llm_relevance_filtered': { 
                progress: 88, 
                label: `Reparo relevância: ${data.kept || 0} mantidos`, 
                icon: 'pi pi-bullseye' 
              },
              'repair_src_bypassed': { 
                progress: 86, 
                label: `Reparo SRC bypass: ${data.count || 0} cartões`, 
                icon: 'pi pi-bolt' 
              },
              'lang_check_after_repair': { 
                progress: 92, 
                label: `Idioma pós-reparo: ${data.lang || 'unknown'} (${data.cards || 0} cartões)`, 
                icon: 'pi pi-globe' 
              },
              'done': { 
                progress: 98, 
                label: `Concluído: ${data.total_cards || 0} cartões finais`, 
                icon: 'pi pi-check-circle',
                details: { totalCards: data.total_cards }
              }
            }
            
            const stageInfo = stageMap[s]
            if (stageInfo) {
              setProgress(stageInfo.progress, stageInfo.label, stageInfo.details, stageInfo.icon)
              addLog(`Stage: ${stageInfo.label}`, s === 'done' ? 'success' : 'info')
            } else {
              // Estágios não mapeados
              addLog(`Stage: ${s}`, 'info')
            }
          }
        } catch (e) {
          addLog('Progress error: ' + (e?.message || String(e)), 'error')
        }
      },
      currentAnalysisId.value,
      selectedValidationModel.value,
      selectedAnalysisModel.value,
      getEffectivePrompts(), // Prioridade: temporários > salvos > padrões
      numCardsEnabled.value ? numCardsSlider.value : null,
      signal,
      requestId
    )

    if (newCards.length > 0) {
      cards.value = [...cards.value, ...newCards]
      if (generationWasCancelled.value) {
        addLog(`Cancelado: preservados ${newCards.length} cartões`, 'warn')
        notify(`Cancelado — ${newCards.length} cartão(ões) preservado(s)`, 'info', 4500)
      } else {
        addLog(`Gerados ${newCards.length} cartões com sucesso`, 'success')
        notify(`${newCards.length} cartões criados`, 'success')
      }
      schedulePersistActiveSession()
    } else if (generationWasCancelled.value) {
      notify('Geração cancelada', 'info', 3000)
    }

    setProgress(100, 'Concluído!', null, 'pi pi-check-circle')
    completeProgress()
  } catch (error) {
    console.error('Error generating cards:', error)
    if (error?.name === 'AbortError') {
      addLog('Geração cancelada pelo usuário', 'warn')
      notify('Geração cancelada', 'info', 3000)
      return
    }

    addLog('Generation error: ' + (error?.message || String(error)), 'error')

    const msg = error?.message || String(error)
    if (msg.includes('FUNCTION_INVOCATION_TIMEOUT') || msg.includes('timed out')) {
      notify('Timeout: selecione um trecho menor e tente novamente.', 'error', 8000)
    } else {
      notify('Erro ao gerar: ' + msg, 'error', 8000)
    }
  } finally {
    stopTimer()
    stopOllamaInfoPolling() // Para polling de info do Ollama
    generating.value = false
    progressVisible.value = false
    clearGenerationCancellation()
  }
}

// ============================================================
// Questions Generation (AllInOne kprim, mc, sc)
// ============================================================
function openQuestionGenerateModal() {
  showQuestionGenerateModal.value = true
}

async function handleGenerateQuestions(params) {
  const { textSource, questionType, numQuestions, domain, model } = params

  try {
    isGeneratingQuestions.value = true
    showQuestionGenerateModal.value = false

    // Determine text to use
    let text = ''
    if (textSource === 'selection' && selectedText.value) {
      text = selectedText.value
    } else {
      text = lastFullText.value
    }

    if (!text || text.trim().length < 50) {
      notify('Texto insuficiente para gerar questões', 'warn')
      return
    }

    progressVisible.value = true
    progressStage.value = 'Gerando questões...'
    progressPct.value = 10

    const questions = await generateQuestionsStream({
      text: text,
      textContext: documentContext.value || '',
      questionType: questionType,
      numQuestions: numQuestions,
      model: model,
      domain: domain,
      apiKeys: getStoredApiKeys()
    }, (progress) => {
      console.log('[Questions] Progress:', progress)
      if (progress.event === 'generating') {
        progressStage.value = 'Chamando modelo...'
        progressPct.value = 30
      } else if (progress.event === 'parsing') {
        progressStage.value = 'Parseando questões...'
        progressPct.value = 70
      } else if (progress.event === 'parsed') {
        progressStage.value = `${progress.data.count} questões geradas`
        progressPct.value = 90
      }
    })

    if (questions && questions.length > 0) {
      questionCards.value = [...questionCards.value, ...questions]
      notify(`${questions.length} questões geradas!`, 'success')
      schedulePersistActiveSession()
    } else {
      notify('Nenhuma questão foi gerada', 'warn')
    }

    progressPct.value = 100
    progressStage.value = 'Concluído!'

  } catch (error) {
    console.error('Error generating questions:', error)
    notify('Erro ao gerar questões: ' + (error?.message || String(error)), 'error')
  } finally {
    isGeneratingQuestions.value = false
    progressVisible.value = false
  }
}

async function handleParseQuestions(params) {
  const { text, model } = params

  try {
    isGeneratingQuestions.value = true
    showQuestionGenerateModal.value = false

    if (!text || text.trim().length < 50) {
      notify('Texto insuficiente para interpretar', 'warn')
      return
    }

    progressVisible.value = true
    progressStage.value = 'Interpretando questões...'
    progressPct.value = 10

    const questions = await parseQuestionsStream({
      text: text,
      model: model,
      apiKeys: getStoredApiKeys()
    }, (progress) => {
      console.log('[Questions] Parse Progress:', progress)
      if (progress.event === 'parsing') {
        progressStage.value = 'Chamando modelo...'
        progressPct.value = 40
      } else if (progress.event === 'parsed') {
        progressStage.value = `${progress.data.count} questões identificadas`
        progressPct.value = 90
      }
    })

    if (questions && questions.length > 0) {
      questionCards.value = [...questionCards.value, ...questions]
      notify(`${questions.length} questões interpretadas!`, 'success')
      schedulePersistActiveSession()
    } else {
      notify('Nenhuma questão identificada no texto', 'warn')
    }

    progressPct.value = 100
    progressStage.value = 'Concluído!'

  } catch (error) {
    console.error('Error parsing questions:', error)
    notify('Erro ao interpretar questões: ' + (error?.message || String(error)), 'error')
  } finally {
    isGeneratingQuestions.value = false
    progressVisible.value = false
  }
}

function deleteQuestion(index) {
  questionCards.value.splice(index, 1)
  notify('Questão removida', 'info')
  schedulePersistActiveSession()
}

function openQuestionPreview(index) {
  questionPreviewData.value = questionCards.value[index]
  questionPreviewVisible.value = true
}

function openQuestionExportDialog() {
  showQuestionExportDialog.value = true
}

async function checkAllInOneModelStatus() {
  try {
    allInOneStatus.value = { hasModel: false, checking: true }
    const result = await checkAllInOneModel()
    allInOneStatus.value = {
      hasModel: result.hasModel,
      checking: false,
      fields: result.fields,
      installUrl: result.installUrl
    }
  } catch (error) {
    console.error('Error checking AllInOne model:', error)
    allInOneStatus.value = { hasModel: false, checking: false }
  }
}

async function handleExportQuestions(params) {
  const { questions, deckName, tags } = params

  try {
    isExportingQuestions.value = true

    const result = await uploadQuestionsToAnki({
      questions: questions,
      deckName: deckName,
      tags: tags
    })

    if (result.success) {
      notify(`${result.totalSuccess}/${result.totalQuestions} questões exportadas para Anki!`, 'success')
      showQuestionExportDialog.value = false
    } else {
      notify('Falha ao exportar questões', 'error')
    }
  } catch (error) {
    console.error('Error exporting questions:', error)
    notify('Erro ao exportar: ' + (error?.message || String(error)), 'error')
  } finally {
    isExportingQuestions.value = false
  }
}

function clearAllQuestions() {
  questionCards.value = []
  notify('Todas as questões removidas', 'info')
  schedulePersistActiveSession()
}

// ============================================================
// CRUD cards
// ============================================================
function deleteCard(index, skipUndo = false) {
  if (!skipUndo) {
    pushToUndoHistory({ type: 'delete', index, card: { ...cards.value[index] } })
  }
  cards.value.splice(index, 1)
  notify('Cartão removido (Ctrl+Z para desfazer)', 'info', 3000)
  schedulePersistActiveSession()
}

function openClearAllCards() {
  clearCardsVisible.value = true
}

function clearAllCards() {
  if (cards.value.length > 0) {
    pushToUndoHistory({ type: 'clear-all', cards: [...cards.value] })
  }
  cards.value = []
  clearCardsVisible.value = false
  notify('Todos os cartões removidos (Ctrl+Z para desfazer)', 'success', 3000)
  schedulePersistActiveSession()
}

// ============================================================
// Preview bonito + edição ao clicar (Dialog)
// ============================================================
const editVisible = ref(false)
const editIndex = ref(-1)
const editDraft = ref({ front: '', back: '', deck: 'General' })
const editSelectedText = ref('')
const editFrontRef = ref(null)
const editBackRef = ref(null)
const editFrontReady = ref(false)
const editBackReady = ref(false)
const pendingEditContent = ref(null) // { front, back } - conteúdo pendente para carregar quando editor estiver pronto
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

  // Armazena conteúdo pendente para carregar quando editores estiverem prontos
  pendingEditContent.value = {
    front: editDraft.value.front,
    back: editDraft.value.back
  }

  editVisible.value = true

  // Se editores já estão prontos (reuso do modal), carrega imediatamente
  nextTick(() => {
    if (editFrontReady.value && editFrontRef.value) {
      editFrontRef.value.setContent(editDraft.value.front)
    }
    if (editBackReady.value && editBackRef.value) {
      editBackRef.value.setContent(editDraft.value.back)
    }
  })
}

// Handlers para o componente EditCardDialog
function onEditCardSave({ index, front, back, deck }) {
  if (index < 0) return
  cards.value[index] = {
    ...cards.value[index],
    front,
    back,
    deck: deck || 'General'
  }
  notify('Cartão atualizado', 'success', 2000)
  schedulePersistActiveSession()
}

function onEditCardDelete(index) {
  if (index < 0) return
  cards.value.splice(index, 1)
  notify('Cartão removido', 'info', 2000)
  schedulePersistActiveSession()
}

function onEditCardDuplicate(index) {
  if (index < 0) return
  const c = cards.value[index]
  cards.value.splice(index + 1, 0, { ...c })
  notify('Cartão duplicado', 'success', 2000)
  schedulePersistActiveSession()
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
    const { signal, requestId } = setupGenerationCancellation()
    startTimer('Gerando...')
    showProgress('Gerando cartão...')
    setProgress(10)
    
    const context = instruction || documentContext.value
    const newCards = await generateCardsWithStream(
      text,
      editDraft.value.deck,
      context,
      type,
      selectedModel.value,
      ({ stage }) => {
        if (stage === 'cancelled') {
          generationWasCancelled.value = true
          return
        }
        if (progressValue.value < 92) setProgress(progressValue.value + 4)
      },
      currentAnalysisId.value,
      selectedValidationModel.value,
      selectedAnalysisModel.value,
      getEffectivePrompts(), // Prioridade: temporários > salvos > padrões
      null, // numCards
      signal,
      requestId
    )

    if (newCards.length > 0) {
      newCards.forEach(card => {
        card.src = `Card #${sourceCardId + 1}`
      })
      
      cards.value = [...cards.value, ...newCards]
      if (generationWasCancelled.value) {
        notify(`Cancelado — ${newCards.length} cartão(ões) preservado(s)`, 'info', 4500)
      } else {
        notify(`${newCards.length} cartão(ões) criado(s)`, 'success')
      }
      schedulePersistActiveSession()
      completeProgress()
    } else if (generationWasCancelled.value) {
      notify('Geração cancelada', 'info', 3000)
    }
  } catch (error) {
    if (error?.name === 'AbortError') {
      notify('Geração cancelada', 'info', 3000)
      return
    }
    notify('Erro ao gerar: ' + (error?.message || String(error)), 'error', 8000)
  } finally {
    stopTimer()
    generating.value = false
    progressVisible.value = false
    clearGenerationCancellation()
  }
}

// Markdown "safe"
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

  // Final sanitization to ensure XSS safety
  return sanitizeHtml(out.join(''))
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
  exportCardsAsMarkdown(cards.value, notify)
}

// ============================================================
// Export Texto do Editor
// ============================================================
function exportTextAs(format = 'txt') {
  const text = lastFullText.value?.trim()
  if (!text) {
    notify('Nenhum texto para exportar', 'info')
    return
  }
  
  const now = new Date().toISOString().slice(0, 10)
  let content = ''
  let filename = ''
  let mimeType = 'text/plain'
  
  if (format === 'md') {
    // Exporta como Markdown (tenta preservar formatação básica)
    content = `# Documento\n\n${text}`
    filename = `documento-${now}.md`
    mimeType = 'text/markdown'
  } else if (format === 'html') {
    // Exporta como HTML
    const html = lastEditorHtml.value || escapeHtml(text).replace(/\n/g, '<br>')
    content = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Documento - ${now}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; }
    .cloze { background: var(--export-markdown-cloze-bg); padding: 2px 4px; border-radius: 3px; }
    code { background: var(--export-markdown-code-bg); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
  </style>
</head>
<body>
${html}
</body>
</html>`
    filename = `documento-${now}.html`
    mimeType = 'text/html'
  } else {
    // Texto puro
    content = text
    filename = `documento-${now}.txt`
    mimeType = 'text/plain'
  }

  downloadTextFile(content, filename, mimeType)
  
  notify(`Texto exportado como ${format.toUpperCase()}`, 'success')
}

// Menu de exportação do texto
const exportTextMenuRef = ref(null)
const exportTextMenuItems = computed(() => [
  { 
    label: 'Exportar como TXT', 
    icon: 'pi pi-file', 
    command: () => exportTextAs('txt') 
  },
  { 
    label: 'Exportar como Markdown', 
    icon: 'pi pi-hashtag', 
    command: () => exportTextAs('md') 
  },
  { 
    label: 'Exportar como HTML', 
    icon: 'pi pi-code', 
    command: () => exportTextAs('html') 
  }
])

function showExportTextMenu(event) {
  exportTextMenuRef.value?.toggle(event)
}

// ============================================================
// Anki
// ============================================================
const ankiVisible = ref(false)
const ankiModel = ref('')
const ankiFrontField = ref('')
const ankiBackField = ref('')
const ankiDeckField = ref('')
const ankiTags = ref([])
const ankiExporting = ref(false)
const clearCardsVisible = ref(false)

// Tag autocomplete
const ankiAllTags = ref([])
const ankiTagSuggestions = ref([])

// Anki preferences persistence
function loadAnkiPreferences() {
  try {
    const raw = localStorage.getItem(LS_ANKI_PREFS_KEY)
    if (raw) return JSON.parse(raw)
  } catch (e) {
    console.warn('Failed to load Anki preferences:', e)
  }
  return {}
}

function saveAnkiPreferences() {
  try {
    const prefs = {
      model: ankiModel.value,
      deck: ankiDeckField.value,
      tags: ankiTags.value
    }
    localStorage.setItem(LS_ANKI_PREFS_KEY, JSON.stringify(prefs))
  } catch (e) {
    console.warn('Failed to save Anki preferences:', e)
  }
}

function searchAnkiTags(event) {
  const query = (event.query || '').toLowerCase().trim()
  if (!query) {
    ankiTagSuggestions.value = [...ankiAllTags.value]
  } else {
    ankiTagSuggestions.value = ankiAllTags.value.filter(
      tag => tag.toLowerCase().includes(query)
    )
  }
}

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

// Armazena quais cards exportar (null = todos, array = índices específicos)
const cardsToExport = ref(null)

const exportableCards = computed(() => {
  if (cardsToExport.value === null) return cards.value
  return cardsToExport.value.map(i => cards.value[i]).filter(Boolean)
})

async function exportToAnkiOpenConfig(selectedIndices = null) {
  try {
    // Se passar índices, exporta apenas esses; senão, exporta todos
    cardsToExport.value = Array.isArray(selectedIndices) ? selectedIndices : null
    const cardsCount = cardsToExport.value ? cardsToExport.value.length : cards.value.length

    if (cardsCount === 0) {
      notify('Nenhum cartão para exportar', 'info')
      return
    }
    showProgress('Carregando modelos do Anki...')
    setProgress(30)

    // Fetch models and tags in parallel
    const [modelsResp, tagsResp] = await Promise.all([
      fetch('/api/anki-models'),
      fetch('/api/anki-tags')
    ])

    if (!modelsResp.ok) throw new Error('Não foi possível conectar no Anki. Verifique Anki + AnkiConnect.')

    const data = await modelsResp.json()
    ankiModelsData.value = data

    // Handle tags response
    if (tagsResp.ok) {
      const tagsData = await tagsResp.json()
      ankiAllTags.value = tagsData.tags || []
    }

    // Load saved preferences from localStorage
    const savedPrefs = loadAnkiPreferences()
    const modelKeys = Object.keys(data.models || {})

    // Use saved model if it exists in available models, otherwise use first
    if (savedPrefs.model && modelKeys.includes(savedPrefs.model)) {
      ankiModel.value = savedPrefs.model
    } else {
      ankiModel.value = modelKeys[0] || ''
    }

    // Restore other saved preferences
    if (savedPrefs.deck !== undefined) ankiDeckField.value = savedPrefs.deck
    if (Array.isArray(savedPrefs.tags)) ankiTags.value = savedPrefs.tags

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

    const cardsData = exportableCards.value

    // Convert tags array to comma-separated string for backend
    const tagsString = Array.isArray(ankiTags.value) ? ankiTags.value.join(', ') : ankiTags.value

    const resp = await fetch('/api/upload-to-anki', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cards: cardsData,
        modelName: ankiModel.value,
        frontField: ankiFrontField.value,
        backField: ankiBackField.value,
        deckName: ankiDeckField.value,
        tags: tagsString
      })
    })

    // Traduz erros comuns do AnkiConnect
    function translateAnkiError(error) {
      if (!error) return 'Erro desconhecido'
      if (error.includes('duplicate')) return 'Cartão já existe no Anki (duplicata)'
      if (error.includes('model was not found')) return 'Tipo de nota não encontrado'
      if (error.includes('deck was not found')) return 'Deck não encontrado'
      if (error.includes('field') && error.includes('not in model')) return 'Campo não existe no tipo de nota'
      return error
    }

    // Aceita 200 (sucesso total), 207 (sucesso parcial) e 422 (falha total)
    const result = await resp.json()
    setProgress(100)
    completeProgress()

    // Erro de conexão ou outro erro HTTP
    if (!resp.ok && resp.status !== 207 && resp.status !== 422) {
      throw new Error(result.error || 'Falha ao conectar com Anki')
    }

    // Show detailed error if some cards failed
    if (result.totalSuccess === 0 && result.results?.length > 0) {
      const firstError = result.results.find(r => r.error)?.error
      const translatedError = translateAnkiError(firstError)
      notify(`Nenhum cartão exportado: ${translatedError}`, 'error', 8000)
      console.error('[Anki Export] All cards failed:', result.results)
      return
    } else if (result.totalSuccess < result.totalCards) {
      const failedCount = result.totalCards - result.totalSuccess
      const duplicateCount = result.results.filter(r => r.error?.includes('duplicate')).length

      if (duplicateCount === failedCount) {
        notify(`${result.totalSuccess} enviados, ${duplicateCount} já existiam no Anki`, 'warn', 5000)
      } else {
        const firstError = result.results.find(r => r.error)?.error
        notify(`${result.totalSuccess} de ${result.totalCards} enviados. ${failedCount} falharam: ${translateAnkiError(firstError)}`, 'warn', 8000)
      }
      console.warn('[Anki Export] Some cards failed:', result.results)
    } else {
      notify(
        result.totalSuccess === 1
          ? '1 cartão enviado ao Anki!'
          : `${result.totalSuccess} cartões enviados ao Anki!`,
        'success'
      )
    }

    // Save preferences on successful export (only if at least one succeeded)
    if (result.totalSuccess > 0) {
      saveAnkiPreferences()
      ankiVisible.value = false

      // Limpa seleção após exportar
      if (cardsToExport.value !== null) {
        clearSelection()
      }
      cardsToExport.value = null
    }
  } catch (e) {
    console.error('[Anki Export] Error:', e)
    notify('Erro ao enviar ao Anki: ' + (e?.message || String(e)), 'error', 8000)
  } finally {
    ankiExporting.value = false
    progressVisible.value = false
  }
}

// Handler para o componente AnkiExportDialog
async function onAnkiExport({ model, frontField, backField, deck, tags }) {
  // Atualiza os valores locais
  ankiModel.value = model
  ankiFrontField.value = frontField
  ankiBackField.value = backField
  ankiDeckField.value = deck
  ankiTags.value = tags
  // Chama a exportação existente
  await exportToAnkiConfirm()
}

// Handler: ApiKeysDialog
function onApiKeysSave({ anthropicApiKey: aKey, openaiApiKey: oKey, perplexityApiKey: pKey, storeLocally: store }) {
  const ok = storeApiKeys(aKey, oKey, pKey, store)
  if (ok) {
    notify('Chaves de API salvas com sucesso!', 'success')
    fetchAvailableModels()
  } else {
    notify('Erro ao salvar as chaves', 'error')
  }
  apiKeyVisible.value = false
}

function onApiKeysClear() {
  storeApiKeys('', '', '', false)
  notify('Chaves removidas', 'info')
  fetchAvailableModels()
}

// Handler: PromptSettingsDialog
function onPromptSettingsSave(prompts) {
  savePromptSettings(prompts)
}

function onPromptSettingsReset() {
  resetPromptsToDefaults()
}

// Handler: OllamaSelectionDialog
function onOllamaModelSelect(modelName) {
  selectOllamaModel(modelName)
}

// Handler: TopicConfirmDialog
function onTopicConfirm() {
  confirmTopicSegmentation()
}

function onTopicCancel() {
  cancelTopicSegmentation()
}

// Handler: CustomInstructionDialog
function onCustomInstructionConfirm(instruction) {
  editCustomInstruction.value = instruction
  editGenerateCardConfirm()
}

// ============================================================
// Sidebar Menu
// ============================================================
const sidebarRef = ref(null)

const totalCardsAcrossSessions = computed(() =>
  sessions.value.reduce((acc, session) => acc + sessionCardCount(session), 0)
)

const sidebarMenuItems = computed(() => [
  {
    key: 'sessions',
    label: 'Sessões',
    icon: 'pi pi-history',
    iconColor: colorTokens.primary,
    badge: sessions.value.length,
    tooltip: 'Gerenciar sessões de estudo',
    submenu: [
      { label: 'Nova sessão', icon: 'pi pi-plus', iconColor: colorTokens.success, command: newSession },
      { separator: true },
      ...sessions.value
        .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
        .slice(0, 8)
        .map((s) => ({
          label: `${s.title}`,
          sessionInfo: buildSessionInfo(s),
          metricCount: sessionCardCount(s),
          sublabelMetric: `${sessionCardCount(s)} ${sessionCardCount(s) === 1 ? 'cartão' : 'cartões'}`,
          icon: s.id === activeSessionId.value ? 'pi pi-check-circle' : 'pi pi-file',
          iconColor: s.id === activeSessionId.value ? colorTokens.success : colorTokens.neutral,
          active: s.id === activeSessionId.value,
          actionIcon: 'pi pi-trash',
          actionTooltip: 'Apagar sessão',
          actionCommand: () => deleteSessionWithConfirmation(s.id),
          command: () => restoreSessionById(s.id)
        })),
      ...(sessions.value.length > 8 ? [{ label: `+${sessions.value.length - 8} mais...`, icon: 'pi pi-ellipsis-h', iconColor: colorTokens.neutral, disabled: true }] : []),
      { separator: true },
      { label: 'Total de cartões', icon: 'pi pi-chart-pie', iconColor: colorTokens.success, badge: totalCardsAcrossSessions.value, disabled: true },
      { label: 'Limpar todas', icon: 'pi pi-trash', iconColor: colorTokens.danger, danger: true, command: clearAllSessionsWithConfirmation }
    ]
  },
  {
    key: 'cards',
    label: 'Cartões',
    icon: 'pi pi-clone',
    iconColor: colorTokens.success,
    badge: cards.value.length,
    tooltip: 'Gerenciar flashcards gerados',
    submenu: [
      { label: 'Exportar para Anki', icon: 'pi pi-send', iconColor: colorTokens.info, disabled: !cards.value.length, command: exportToAnkiOpenConfig },
      { label: 'Exportar Markdown', icon: 'pi pi-file-export', iconColor: colorTokens.primary, disabled: !cards.value.length, command: exportAsMarkdown },
      { separator: true },
      { label: 'Limpar Cartões', icon: 'pi pi-trash', iconColor: colorTokens.danger, danger: true, disabled: !cards.value.length, command: clearAllCards }
    ]
  },
  {
    key: 'config',
    label: 'Configurações',
    icon: 'pi pi-cog',
    iconColor: colorTokens.neutral,
    tooltip: 'Ajustes e preferências',
    submenu: [
      { label: 'Escolher Modelo IA', icon: 'pi pi-microchip-ai', iconColor: colorTokens.success, command: openModelSelection },
      {
        label: 'Prompts de Geração',
        icon: 'pi pi-file-edit',
        iconColor: colorTokens.primary,
        command: openPromptSettings,
        badge: hasCustomPromptsSaved.value ? '✓' : null,
        badgeColor: colorTokens.primary
      },
      { label: 'Chaves de API', icon: 'pi pi-key', iconColor: colorTokens.warning, command: openApiKeys }
    ]
  },
  { separator: true },
  { key: 'browser', label: 'Browser', icon: 'pi pi-database', iconColor: colorTokens.info, tooltip: 'Navegar pelos cartões salvos', command: () => router.push('/browser') },
  { key: 'dashboard', label: 'Dashboard', icon: 'pi pi-chart-bar', iconColor: colorTokens.warning, tooltip: 'Estatísticas de estudo', command: () => router.push('/dashboard') },
  {
    key: 'logs',
    label: 'Logs',
    icon: 'pi pi-wave-pulse',
    status: logsHasError.value ? 'error' : 'ok',
    iconColor: logsHasError.value ? colorTokens.danger : colorTokens.neutral,
    tooltip: 'Ver registros do sistema',
    command: () => {
      logsVisible.value = true
    }
  }
])

// Footer actions para o sidebar
const sidebarFooterActions = computed(() => [
  { icon: 'pi pi-question-circle', tooltip: 'Documentação', command: () => router.push('/docs') },
  { icon: isDark.value ? 'pi pi-sun' : 'pi pi-moon', tooltip: isDark.value ? 'Ativar modo claro' : 'Ativar modo escuro', command: toggleTheme }
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

function resolveColorToken(color) {
  if (typeof color !== 'string') return color
  if (!color.startsWith('var(')) return color
  const match = color.match(/--[^)]+/)
  const token = match ? match[0] : ''
  if (!token || typeof window === 'undefined') return color
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  return value || color
}

function contextMark(color) {
  editorRef.value?.formatBackground?.(resolveColorToken(color))
}

const contextMenuModel = computed(() => [
  {
    label: 'Marcar texto',
    disabled: !contextHasSelection.value,
    items: [
      { label: 'Amarelo', command: () => contextMark('var(--highlight-palette-yellow)') },
      { label: 'Verde', command: () => contextMark('var(--highlight-palette-green)') },
      { label: 'Azul', command: () => contextMark('var(--highlight-palette-blue)') },
      { label: 'Rosa', command: () => contextMark('var(--highlight-palette-pink)') },
      { label: 'Roxo', command: () => contextMark('var(--highlight-palette-purple)') },
      { label: 'Laranja', command: () => contextMark('var(--highlight-palette-orange)') }
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
  // Ignora mudanças de conteúdo causadas pela navegação de página do PDF
  if (isNavigatingPdfPage) {
    console.log('[onContentChanged] ignorando - navegação de página PDF em andamento')
    return
  }
  
  if (isRestoringSession.value) return

  const fullText = payload?.fullText ?? ''
  const html = payload?.html ?? ''
  const delta = payload?.delta ?? null
  const isTextMutationFromEditor = payload?.isTextMutation

  lastFullText.value = fullText
  lastEditorHtml.value = html
  if (delta) lastEditorDelta.value = delta

  schedulePersistActiveSession()
  
  // Atualiza posições dos highlights
  scanHighlights()

  if (isTextMutationFromEditor === false) return

  const normalized = normalizePlainText(fullText)
  if (normalized === lastNormalizedTextOnChange.value) return

  // Detecta paste: adição significativa de texto em uma única operação
  const prevLen = lastNormalizedTextOnChange.value?.length || 0
  const textDiff = normalized.length - prevLen
  const isPaste = textDiff > 200 // threshold para considerar como paste

  lastNormalizedTextOnChange.value = normalized

  // Segmentação automática de tópicos quando detecta paste (mas não durante carregamento de PDF)
  if (isPaste && !isSegmentingTopics.value && !isLoadingPdf.value) {
    scheduleTopicSegmentation(fullText)
  }

  // Análise automática removida - agora é feita apenas inicialmente ou sob demanda
  // O usuário pode usar o botão "Analisar" ou o menu de contexto

  // se estiver lendo, recalcula o layout/páginas (mantendo progresso)
  // Mas não se estiver usando paginação do PDF (a navegação é controlada manualmente)
  if (immersiveReader.value && !usePdfPagination.value) {
    requestReaderLayout({ preserveProgress: true })
  }
}

// ============================================================
// Document Upload Handlers
// ============================================================
// Dados das páginas do documento para paginação no modo leitura
const pdfPagesContent = ref([])  // Array com { page_number, text, word_count }
const usePdfPagination = ref(false)  // Se deve usar paginação baseada no documento

function onDocumentExtracted({ text, filename, pages, wordCount, pagesContent, metadata }) {
  console.log('[onDocumentExtracted] pagesContent:', pagesContent?.length, 'pages:', pages)

  // Seta flag para evitar que onContentChanged dispare segmentação duplicada
  isLoadingPdf.value = true

  // Armazena conteúdo das páginas para paginação
  pdfPagesContent.value = pagesContent || []
  usePdfPagination.value = pagesContent && pagesContent.length > 0

  console.log('[onDocumentExtracted] usePdfPagination set to:', usePdfPagination.value)

  // Determina o tipo de documento para o emoji
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const formatEmoji = getFormatEmoji(ext)

  // Insere o texto extraído no editor
  if (editorRef.value?.setContent) {
    editorRef.value.setContent(text)
    notify(`${formatEmoji} "${filename}" carregado: ${wordCount} palavras`, 'success', 4000)

    // Cria uma nova sessão para o documento
    const newSession = {
      id: safeId(),
      title: `${formatEmoji} ${filename}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      plainText: text || '',
      quillDelta: null,
      cards: [],
      documentContext: '',
      topicSegments: [],
      topicDefinitions: [],
      questionCards: [],
      source: 'document',
      documentFilename: filename,
      documentPages: pages,
      documentPagesContent: pagesContent || []
    }
    activeSessionId.value = newSession.id
    persistActiveSessionId(activeSessionId.value)
    upsertSession(newSession)

    // Atualiza estatísticas do modo leitura se estiver ativo
    if (immersiveReader.value && usePdfPagination.value) {
      readerTotalPages.value = pagesContent.length
      readerPage.value = 1
    }

    // Pergunta se quer marcar tópicos (após delay para não conflitar)
    setTimeout(() => {
      isLoadingPdf.value = false
      if (text.length >= 200) {
        scheduleTopicSegmentation(text)
      }
    }, 800)
  } else {
    isLoadingPdf.value = false
    notify('Erro ao inserir texto no editor', 'error', 4000)
  }
}

function getFormatEmoji(ext) {
  const emojis = {
    'pdf': '📄',
    'docx': '📝', 'doc': '📝',
    'pptx': '📊', 'ppt': '📊',
    'xlsx': '📈', 'xls': '📈',
    'html': '🌐', 'htm': '🌐',
    'md': '📑', 'markdown': '📑',
    'adoc': '📋', 'asciidoc': '📋',
    'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️', 'tiff': '🖼️', 'tif': '🖼️', 'bmp': '🖼️'
  }
  return emojis[ext] || '📄'
}

function onDocumentError(error) {
  console.error('Document extraction error:', error)
  // Toast já é exibido pelo componente DocumentUpload
}

// ============================================================
// Computeds úteis
// ============================================================
const hasSelection = computed(() => (selectedText.value || '').trim().length > 0)
const hasCards = computed(() => cards.value.length > 0)
const hasQuestions = computed(() => questionCards.value.length > 0)
const hasAnyOutput = computed(() => hasCards.value || hasQuestions.value)

// Verifica se há conteúdo disponível para geração (seleção, highlights ou texto)
const canGenerate = computed(() => {
  // Has mouse selection
  if (hasSelection.value) return true
  
  // Has highlighted content
  if (hasHighlights.value) return true
  
  // Has any text in editor
  const fullText = (lastFullText.value || '').trim()
  return fullText.length > 0
})

// Label descritivo da fonte de geração para tooltip/feedback
const generationSourceLabel = computed(() => {
  if (hasSelection.value) return 'Gerar a partir da seleção'
  if (hasHighlights.value) return `Gerar a partir de ${highlightCount.value} marcação${highlightCount.value > 1 ? 'ões' : ''}`
  const fullText = (lastFullText.value || '').trim()
  if (fullText.length > 0) return 'Gerar a partir de todo o texto'
  return 'Sem texto disponível'
})

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
    readerTheme.value = saved.readerTheme ?? 'kindle'
    readerDark.value = saved.readerDark ?? false
    readerShowProgress.value = saved.readerShowProgress ?? true
    readerAutoHideControls.value = saved.readerAutoHideControls ?? false
    showLineNumbers.value = saved.showLineNumbers ?? true
  } catch {}

  // Inicializa seleção de modelo com fallback para Ollama
  await initializeModelSelection()

  // carrega prompts personalizados salvos
  loadSavedPrompts()

  ensureActiveSession()

  try {
    await fetchDecks()
  } catch {}

  // Verifica se é primeira execução (intro não foi mostrada)
  const introShown = localStorage.getItem(INTRO_SHOWN_KEY)
  if (!introShown) {
    // Mostra modal de introdução
    introModalVisible.value = true
    // O fluxo pós-intro (Ollama selection -> API keys) será disparado ao finalizar a intro
  }

  if (sessions.value.length && !cards.value.length && !normalizePlainText(lastFullText.value)) {
    notify('Sessões encontradas. Use "Sessões" para restaurar.', 'info', 4500)
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

    // Ctrl+Enter gera cards (modo normal) - agora usa canGenerate para incluir highlights e texto completo
    const isCtrl = e.ctrlKey || e.metaKey
    const isCtrlEnter = isCtrl && e.key === 'Enter'
    if (isCtrlEnter && canGenerate.value && !generating.value && !isAnalyzing.value) {
      e.preventDefault()
      generateCardsFromSelection()
      return
    }

    // Ctrl+F abre busca no editor
    if (isCtrl && e.key === 'f') {
      e.preventDefault()
      toggleEditorSearch()
      return
    }

    // Undo: Ctrl+Z
    if (isCtrl && e.key === 'z' && !e.shiftKey) {
      // Only trigger if not in an input/textarea
      const activeEl = document.activeElement
      const isInput = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable)
      if (!isInput && canUndo.value) {
        e.preventDefault()
        undo()
        return
      }
    }

    // Redo: Ctrl+Y or Ctrl+Shift+Z
    if ((isCtrl && e.key === 'y') || (isCtrl && e.shiftKey && e.key === 'z') || (isCtrl && e.shiftKey && e.key === 'Z')) {
      const activeEl = document.activeElement
      const isInput = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable)
      if (!isInput && canRedo.value) {
        e.preventDefault()
        redo()
        return
      }
    }

    // Escape cancela modo seleção
    if (e.key === 'Escape' && isSelectionMode.value) {
      e.preventDefault()
      clearSelection()
      return
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
  if (ollamaInfoInterval) clearInterval(ollamaInfoInterval)

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

  if (generationAbortController.value) {
    try {
      generationAbortController.value.abort()
    } catch {}
  }
})
</script>

<template>
  <Toast />
  <ContextMenu ref="contextMenuRef" :model="contextMenuModel" appendTo="body" />
  <Menu ref="exportTextMenuRef" :model="exportTextMenuItems" popup appendTo="body" />

  <!-- Sidebar -->
  <SidebarMenu
    ref="sidebarRef"
    :menu-items="sidebarMenuItems"
    :footer-actions="sidebarFooterActions"
  />

  <div
    class="app-shell"
    :class="{
      'has-context': hasDocumentContext,
      'reader-mode': immersiveReader,
      'reader-kindle': immersiveReader && readerTheme === 'kindle',
      'reader-sepia': immersiveReader && readerTheme === 'sepia',
      'reader-dark': immersiveReader && readerTheme === 'dark',
      'reader-pdf-pagination': immersiveReader && usePdfPagination,
      'controls-hidden': immersiveReader && !readerControlsVisible,
      'sidebar-expanded': sidebarRef?.sidebarExpanded
    }"
    @mousemove="resetControlsTimer"
  >
    <!-- HEADER -->
    <Toolbar class="app-header">
      <template #start>
        <div class="header-left">
          <Button icon="pi pi-bars" text rounded @click="sidebarRef?.toggleSidebar()" class="menu-toggle" title="Menu" v-if="!sidebarRef?.sidebarOpen" />
          
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
            <div class="editor-switch" title="Modo Zen">
              <span class="editor-switch-label">
                <i class="pi pi-bullseye" />
                Modo Zen
              </span>
              <InputSwitch
                class="zen-switch"
                :modelValue="immersiveReader"
                @update:modelValue="setReaderEnabled"
                title="Sair do Modo Zen (Esc)"
              />
            </div>
            <Tag class="pill subtle" :title="usePdfPagination ? 'Páginas do PDF original' : 'Páginas virtuais'">
              <i :class="usePdfPagination ? 'pi pi-file-pdf mr-2' : 'pi pi-file mr-2'" /> 
              Página {{ readerPage }} / {{ readerTotalPages }}
              <span v-if="usePdfPagination" class="pdf-badge">(PDF)</span>
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

          <div class="controls" :class="{ 'reader-controls': immersiveReader }">
            <!-- Controles do modo leitura -->
            <template v-if="immersiveReader">
              <!-- Navegação de páginas -->
              <div class="reader-nav-group">
                <Button
                  icon="pi pi-angle-double-left"
                  severity="secondary"
                  text
                  rounded
                  @click="readerFirstPage"
                  :disabled="readerPage <= 1"
                  title="Primeira (Home)"
                />
                <Button
                  icon="pi pi-angle-left"
                  severity="secondary"
                  text
                  rounded
                  @click="readerPrevPage"
                  :disabled="readerPage <= 1"
                  title="Anterior (← / PageUp)"
                />

                <div class="page-indicator">
                  <span class="page-current">{{ readerPage }}</span>
                  <span class="page-sep">/</span>
                  <span class="page-total">{{ readerTotalPages }}</span>
                </div>

                <Button
                  icon="pi pi-angle-right"
                  severity="secondary"
                  text
                  rounded
                  @click="readerNextPage"
                  :disabled="readerPage >= readerTotalPages"
                  title="Próxima (→ / Space / PageDown)"
                />
                <Button
                  icon="pi pi-angle-double-right"
                  severity="secondary"
                  text
                  rounded
                  @click="readerLastPage"
                  :disabled="readerPage >= readerTotalPages"
                  title="Última (End)"
                />
              </div>

              <Divider layout="vertical" class="hdr-divider" />

              <!-- Controle de fonte -->
              <div class="reader-font-group">
                <Button icon="pi pi-minus" severity="secondary" text rounded size="small" @click="readerFontMinus" title="Diminuir fonte (Ctrl -)" />
                <span class="font-scale-label">{{ Math.round(readerFontScale * 100) }}%</span>
                <Button icon="pi pi-plus" severity="secondary" text rounded size="small" @click="readerFontPlus" title="Aumentar fonte (Ctrl +)" />
              </div>

              <Divider layout="vertical" class="hdr-divider" />

              <!-- Layout e Tema -->
              <div class="reader-layout-group">
                <Button
                  :icon="readerTwoPage ? 'pi pi-stop' : 'pi pi-columns'"
                  severity="secondary"
                  :outlined="readerTwoPage"
                  :text="!readerTwoPage"
                  rounded
                  @click="toggleTwoPage"
                  :title="readerTwoPage ? 'Modo página única' : 'Modo duas páginas'"
                />

                <!-- Seletor de tema visual -->
                <div class="theme-selector">
                  <Button
                    v-for="opt in readerThemeOptions"
                    :key="opt.value"
                    :icon="'pi ' + opt.icon"
                    :severity="readerTheme === opt.value ? 'primary' : 'secondary'"
                    :outlined="readerTheme !== opt.value"
                    :text="readerTheme !== opt.value"
                    rounded
                    size="small"
                    @click="setReaderTheme(opt.value)"
                    :title="opt.label"
                    :class="{ 'theme-active': readerTheme === opt.value }"
                  />
                </div>

                <Button
                  :icon="readerShowProgress ? 'pi pi-chart-line' : 'pi pi-minus'"
                  severity="secondary"
                  :text="!readerShowProgress"
                  :outlined="readerShowProgress"
                  rounded
                  size="small"
                  @click="readerShowProgress = !readerShowProgress"
                  :title="readerShowProgress ? 'Ocultar barra de progresso' : 'Mostrar barra de progresso'"
                />
              </div>

              <Divider layout="vertical" class="hdr-divider" />

              <Button 
                icon="pi pi-times" 
                severity="secondary" 
                outlined 
                rounded
                @click="toggleReader" 
                title="Sair (Esc)" 
              />
            </template>

            <!-- Controles normais -->
            <template v-else>

              <!-- Document Upload Button -->
              <DocumentUpload
                @extracted="onDocumentExtracted"
                @error="onDocumentError"
              />

              <!-- Analyze Button -->
              <Button
                icon="pi pi-eye"
                label="Analisar"
                class="btn-shine"
                :disabled="!canGenerate || generating || isAnalyzing"
                :loading="isAnalyzing"
                title="Analisar texto para melhorar a qualidade dos cartões gerados"
                @click="contextAnalyze"
              />

              <Button
                icon="pi pi-bolt"
                label="Criar Cartões"
                class="cta"
                :disabled="!canGenerate || generating || isAnalyzing"
                :loading="generating"
                :title="generationSourceLabel + ' (Ctrl+Enter)'"
                @click="openGenerateModal"
              />

              <Button
                icon="pi pi-question-circle"
                label="Questões"
                class="btn-shine"
                :disabled="!canGenerate || isGeneratingQuestions"
                :loading="isGeneratingQuestions"
                title="Gerar questões AllInOne (kprim, mc, sc)"
                @click="openQuestionGenerateModal"
              />

            </template>
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
                
                <!-- Indicador de salvamento -->
                <Transition name="fade">
                  <Tag 
                    v-if="saveStatus !== 'idle'" 
                    :severity="saveStatusSeverity" 
                    class="pill save-status ml-2"
                  >
                    <i :class="saveStatusIcon" class="mr-1" /> {{ saveStatusText }}
                  </Tag>
                </Transition>
              </div>

              <div class="panel-actions">
                <!-- Modo Zen + números de linha (movidos do header) -->
                <div class="editor-zen-group">
                  <div class="editor-switch" title="Ativar Modo Zen">
                    <span class="editor-switch-label">
                      <i class="pi pi-bullseye" />
                      Modo Zen
                    </span>
                    <InputSwitch
                      class="zen-switch"
                      :modelValue="immersiveReader"
                      @update:modelValue="setReaderEnabled"
                      :title="immersiveReader ? 'Sair do Modo Zen (Esc)' : 'Ativar Modo Zen'"
                    />
                  </div>
                  <div class="editor-switch" title="Mostrar/ocultar números de linha">
                    <span class="editor-switch-label">
                      <i class="pi pi-list" />
                      Nº de linhas
                    </span>
                    <InputSwitch
                      class="line-switch"
                      v-model="showLineNumbers"
                      :title="showLineNumbers ? 'Ocultar números de linha' : 'Mostrar números de linha'"
                    />
                  </div>
                </div>
                <!-- Undo/Redo do Editor -->
                <div class="editor-undo-redo">
                  <Button
                    icon="pi pi-undo"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    @click="editorUndo"
                    title="Desfazer edição (Ctrl+Z)"
                  />
                  <Button
                    icon="pi pi-redo"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    @click="editorRedo"
                    title="Refazer edição (Ctrl+Y)"
                  />
                </div>
                
                <!-- Busca no texto -->
                <Button
                  icon="pi pi-search"
                  severity="secondary"
                  :outlined="editorSearchVisible"
                  text
                  rounded
                  size="small"
                  @click="toggleEditorSearch"
                  title="Buscar no texto (Ctrl+F)"
                />
                
                <!-- Navegação de Highlights -->
                <div v-if="hasHighlights" class="highlight-nav">
                  <Button
                    icon="pi pi-chevron-left"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    @click="goToPrevHighlight"
                    title="Highlight anterior"
                  />
                  <Tag severity="warning" class="pill highlight-counter">
                    <i class="pi pi-palette mr-1" /> {{ currentHighlightLabel }}
                  </Tag>
                  <Button
                    icon="pi pi-chevron-right"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    @click="goToNextHighlight"
                    title="Próximo highlight"
                  />
                </div>
                
                <!-- Estatísticas de texto -->
                <div class="text-stats">
                  <Tag severity="secondary" class="pill stats-pill">
                    <i class="pi pi-align-left mr-1" /> {{ textStats.words }} palavras
                  </Tag>
                  <Tag severity="secondary" class="pill stats-pill">
                    <i class="pi pi-clock mr-1" /> {{ textStats.readingTimeLabel }}
                  </Tag>
                </div>
                
                <!-- Exportar texto -->
                <Button
                  icon="pi pi-download"
                  severity="secondary"
                  text
                  rounded
                  size="small"
                  :disabled="!textStats.words"
                  @click="showExportTextMenu"
                  title="Exportar texto"
                />

              </div>
            </div>

            <div class="panel-body" :class="{ 'reader-body': immersiveReader }">
              <!-- Barra de progresso flutuante -->
              <Transition name="progress-bar">
                <div v-if="immersiveReader && readerShowProgress" class="reader-progress-wrapper">
                  <div class="reader-progress-bar">
                    <div 
                      class="reader-progress-fill" 
                      :style="{ width: readerProgress + '%' }"
                    ></div>
                  </div>
                  <span class="reader-progress-label">{{ readerProgress }}%</span>
                </div>
              </Transition>

              <!-- Barra de busca no texto -->
              <Transition name="slide-down">
                <div v-if="editorSearchVisible" class="editor-search-bar">
                  <div class="search-input-wrap">
                    <i class="pi pi-search search-icon" />
                    <InputText
                      ref="editorSearchInputRef"
                      v-model="editorSearchQuery"
                      class="search-input"
                      placeholder="Buscar no texto..."
                      @keydown="onEditorSearchKeydown"
                    />
                    <span v-if="editorSearchQuery" class="search-results-label">{{ editorSearchLabel }}</span>
                  </div>
                  <div class="search-nav-btns">
                    <Button
                      icon="pi pi-chevron-up"
                      severity="secondary"
                      text
                      rounded
                      size="small"
                      :disabled="!hasEditorSearchResults"
                      @click="goToPrevEditorSearchResult"
                      title="Resultado anterior (Shift+Enter)"
                    />
                    <Button
                      icon="pi pi-chevron-down"
                      severity="secondary"
                      text
                      rounded
                      size="small"
                      :disabled="!hasEditorSearchResults"
                      @click="goToNextEditorSearchResult"
                      title="Próximo resultado (Enter)"
                    />
                    <Button
                      icon="pi pi-times"
                      severity="secondary"
                      text
                      rounded
                      size="small"
                      @click="closeEditorSearch"
                      title="Fechar (Esc)"
                    />
                  </div>
                </div>
              </Transition>

              <!-- Indicadores laterais de navegação (touch/click zones) -->
              <Transition name="fade">
                <div v-if="immersiveReader" class="reader-nav-zones">
                  <button 
                    class="nav-zone nav-zone-left" 
                    @click="readerPrevPage"
                    :disabled="readerPage <= 1"
                    title="Página anterior"
                  >
                    <i class="pi pi-chevron-left"></i>
                  </button>
                  <button 
                    class="nav-zone nav-zone-right" 
                    @click="readerNextPage"
                    :disabled="readerPage >= readerTotalPages"
                    title="Próxima página"
                  >
                    <i class="pi pi-chevron-right"></i>
                  </button>
                </div>
              </Transition>

              <div
                ref="readerSurfaceRef"
                class="editor-surface"
                :class="{ 'reader-surface': immersiveReader }"
                :style="immersiveReader ? readerVars : null"
              >
                <LazyQuillEditor
                  ref="editorRef"
                  :show-line-numbers="showLineNumbers && !immersiveReader"
                  @selection-changed="onSelectionChanged"
                  @content-changed="onContentChanged"
                  @context-menu="onEditorContextMenu"
                />

                <!-- Overlay de carregamento durante segmentação de tópicos -->
                <Transition name="fade">
                  <div v-if="isSegmentingTopics" class="segmentation-overlay">
                    <div class="segmentation-content">
                      <ProgressSpinner
                        style="width: 50px; height: 50px"
                        strokeWidth="4"
                        animationDuration=".8s"
                      />
                      <div class="segmentation-text">
                        <span class="stage">{{ topicSegmentStage || 'Analisando tópicos...' }}</span>
                        <ProgressBar :value="topicSegmentProgress" :showValue="false" style="height: 6px; width: 200px" />
                        <span class="percent">{{ topicSegmentProgress }}%</span>
                      </div>
                    </div>
                  </div>
                </Transition>

                <!-- Topic Legend - navegação por tópicos -->
                <TopicLegend
                  v-if="!immersiveReader"
                  :visible="showTopicLegend"
                  :topics="topicDefinitions"
                  :segments="topicSegments"
                  :is-loading="isSegmentingTopics"
                  :progress="topicSegmentProgress"
                  :progress-stage="topicSegmentStage"
                  @navigate="onNavigateToSegment"
                  @clear="clearTopicHighlights"
                  @close="showTopicLegend = false"
                />
              </div>

              <!-- Indicador de página flutuante / Paginator para PDF -->
              <Transition name="fade">
                <div v-if="immersiveReader" class="reader-page-float">
                  <!-- Paginator PrimeVue para PDFs (navegação precisa entre páginas) -->
                  <Paginator 
                    v-if="usePdfPagination"
                    :rows="1"
                    :totalRecords="readerTotalPages"
                    :first="paginatorFirst"
                    @page="onPaginatorPageChange"
                    template="FirstPageLink PrevPageLink CurrentPageReport NextPageLink LastPageLink"
                    currentPageReportTemplate="{currentPage} de {totalPages}"
                    class="reader-paginator"
                  />
                  <!-- Indicador simples para texto normal -->
                  <template v-else>
                    <span class="float-page">{{ readerPage }}</span>
                    <span class="float-sep">de</span>
                    <span class="float-total">{{ readerTotalPages }}</span>
                  </template>
                </div>
              </Transition>
            </div>
          </div>
        </SplitterPanel>

        <!-- Cards -->
        <SplitterPanel class="cards-splitter" :size="immersiveReader ? 0 : 42" :minSize="immersiveReader ? 0 : 20">
          <div class="panel panel-output">
            <div class="panel-head">
              <div class="panel-title">
                <i class="pi pi-clone mr-2" />
                Cartões
                <Tag :severity="hasCards ? 'success' : 'secondary'" class="pill ml-2 cards-total-pill">
                  <i class="pi pi-inbox mr-1" />
                  <span class="total-label">Total</span>
                  <span class="total-sep">•</span>
                  <span class="total-value">{{ hasCards ? formatCount(cards.length) : '0' }}</span>
                </Tag>
                <Tag v-if="hasSelectedCards" severity="warning" class="pill ml-2">
                  {{ selectedCount }} selecionados
                </Tag>
                <!-- Indicador da fonte da última geração -->
                <Transition name="fade">
                  <Tag 
                    v-if="lastGenerationSource && hasCards" 
                    :severity="lastGenerationSource === 'selection' ? 'info' : lastGenerationSource === 'highlight' ? 'warning' : 'secondary'" 
                    class="pill ml-2 generation-source-tag"
                    :title="'Última geração: ' + getSourceLabel() + (lastGenerationSource === 'full' && lastGenerationWordCount ? ` (${formatCount(lastGenerationWordCount)} palavras)` : '')"
                  >
                    <i :class="lastGenerationSource === 'selection' ? 'pi pi-mouse' : lastGenerationSource === 'highlight' ? 'pi pi-palette' : 'pi pi-file'" class="mr-1" style="font-size: 0.75rem" />
                    <span class="source-label">
                      {{ lastGenerationSource === 'selection' ? 'Seleção' : lastGenerationSource === 'highlight' ? 'Marcações' : 'Texto completo' }}
                    </span>
                    <span v-if="lastGenerationSource === 'full' && lastGenerationWordCount" class="source-count">
                      {{ formatCount(lastGenerationWordCount) }} palavras
                    </span>
                  </Tag>
                </Transition>
              </div>

              <div class="panel-actions">
                <!-- Undo/Redo buttons -->
                <div class="undo-redo-group">
                  <Button
                    icon="pi pi-undo"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    :disabled="!canUndo"
                    @click="undo"
                    title="Desfazer (Ctrl+Z)"
                  />
                  <Button
                    icon="pi pi-refresh"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    :disabled="!canRedo"
                    @click="redo"
                    title="Refazer (Ctrl+Y)"
                  />
                </div>

                <!-- Selection mode toggle -->
                <Button
                  :icon="isSelectionMode ? 'pi pi-check-square' : 'pi pi-stop'"
                  :severity="isSelectionMode ? 'primary' : 'secondary'"
                  :outlined="isSelectionMode"
                  text
                  rounded
                  size="small"
                  :disabled="!hasCards"
                  @click="toggleSelectionMode"
                  :title="isSelectionMode ? 'Sair do modo seleção' : 'Modo seleção'"
                />

                <div class="search-wrap" :class="{ 'expanded': searchExpanded }">
                  <button class="search-toggle" @click="searchExpanded = !searchExpanded" type="button">
                    <i class="pi pi-search" />
                  </button>
                  <InputText 
                    v-show="searchExpanded" 
                    v-model="cardSearch" 
                    class="search" 
                    placeholder="Buscar..."
                    @blur="!cardSearch && (searchExpanded = false)"
                  />
                </div>

                <div class="export-group">
                  <Button
                    class="clear-all-btn"
                    icon="pi pi-delete-left"
                    :disabled="!hasCards"
                    severity="danger"
                    text
                    rounded
                    @click="openClearAllCards"
                    title="Limpar todos os cartões"
                  />
                  <Button
                    class="export-btn"
                    :disabled="!hasCards"
                    icon="pi pi-send"
                    outlined
                    rounded
                    v-tooltip.top="'Exportar para o Anki'"
                    @click="exportToAnkiOpenConfig"
                  />
                </div>
              </div>
            </div>

            <!-- Floating selection bar -->
            <Transition name="slide-up">
              <div v-if="hasSelectedCards" class="selection-bar">
                <div class="selection-info">
                  <Checkbox 
                    :modelValue="allCardsSelected" 
                    @update:modelValue="toggleSelectAll"
                    binary
                  />
                  <span class="selection-count">{{ selectedCount }} de {{ cards.length }}</span>
                </div>
                <div class="selection-actions">
                  <Button
                    icon="pi pi-send"
                    label="Exportar"
                    severity="primary"
                    size="small"
                    @click="bulkExportSelected"
                  />
                  <Button
                    icon="pi pi-trash"
                    label="Excluir"
                    severity="danger"
                    size="small"
                    @click="bulkDeleteSelected"
                  />
                  <Button
                    icon="pi pi-times"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    @click="clearSelection"
                    title="Cancelar seleção"
                  />
                </div>
              </div>
            </Transition>

            <div class="panel-body output-body">
              <div v-if="!hasAnyOutput" class="empty-state">
                <div class="empty-icon">✨</div>
                <div class="empty-title">Nenhum cartão ainda</div>
                <div class="empty-subtitle">
                  Cole um texto, selecione um trecho e gere cartões. Você pode marcar trechos com clique direito.
                </div>

                <div class="empty-actions">
                  <Button
                    icon="pi pi-history"
                    label="Sessões"
                    outlined
                    :disabled="!savedSessionExists"
                    @click="toggleSessionsMenu"
                  />
                </div>
              </div>

              <!-- Questions Section -->
              <div v-if="hasQuestions" class="questions-section">
                <div class="section-header">
                  <div class="section-title">
                    <i class="pi pi-question-circle mr-2" />
                    Questões ({{ questionCards.length }})
                  </div>
                  <div class="section-actions">
                    <Button
                      icon="pi pi-send"
                      label="Exportar Questões"
                      size="small"
                      outlined
                      @click="openQuestionExportDialog"
                    />
                    <Button
                      icon="pi pi-trash"
                      severity="danger"
                      text
                      size="small"
                      @click="clearAllQuestions"
                      title="Limpar todas as questões"
                    />
                  </div>
                </div>
                <div class="questions-list">
                  <QuestionCardItem
                    v-for="(q, idx) in questionCards"
                    :key="q.id || idx"
                    :question="q"
                    :index="idx"
                    @delete="deleteQuestion"
                    @preview="openQuestionPreview"
                  />
                </div>
              </div>

              <!-- Cards Section -->
              <div v-if="hasCards" class="cards-section">
                <div v-if="hasQuestions" class="section-header">
                  <div class="section-title">
                    <i class="pi pi-clone mr-2" />
                    Cartões ({{ cards.length }})
                  </div>
                </div>
              </div>

              <DataView v-if="hasCards" :value="hierarchicalCards" layout="list" class="cards-view">
                <template #list="{ items }">
                  <div class="cards-list">
                    <template v-for="(item, i) in items" :key="i">
                      <Card
                        class="card-item clickable"
                        :class="{ 'card-selected': selectedCards.has(item.actualIdx) }"
                        @click="isSelectionMode ? toggleCardSelection(item.actualIdx, $event) : openEditCard(item.actualIdx)"
                      >
                        <template #title>
                          <div class="card-head">
                            <div class="card-left">
                              <!-- Checkbox para seleção -->
                              <Checkbox
                                v-if="isSelectionMode"
                                :modelValue="selectedCards.has(item.actualIdx)"
                                @update:modelValue="toggleCardSelection(item.actualIdx, $event)"
                                @click.stop
                                binary
                                class="card-checkbox"
                              />
                              <Button
                                v-if="item.children.length > 0"
                                :icon="expandedCards.has(i) ? 'pi pi-chevron-down' : 'pi pi-chevron-right'"
                                text
                                rounded
                                size="small"
                                class="expand-btn"
                                @click.stop="toggleCardExpand(i)"
                              />
                              <span class="card-index">Cartão {{ item.actualIdx + 1 }}</span>
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
                              v-if="!isSelectionMode"
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
                              <div class="preview-text" v-html="highlightSearchTerm(renderMarkdownSafe(previewText(item.card.front, 300)))"></div>
                            </div>

                            <div class="preview-block">
                              <div class="preview-label">Back</div>
                              <div class="preview-text" v-html="highlightSearchTerm(renderMarkdownSafe(previewText(item.card.back, 300)))"></div>
                            </div>
                          </div>

                          <div v-if="item.card.src" class="text-xs opacity-70 mt-2 card-source">
                            <strong>Fonte:</strong> <span v-html="highlightSearchTerm(previewText(item.card.src, 160))"></span>
                          </div>

                          <div class="preview-hint">
                            <i class="pi pi-pen-to-square mr-2" />
                            {{ isSelectionMode ? 'Clique para selecionar' : 'Clique no cartão para editar' }}
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
                            :class="{ 'card-selected': selectedCards.has(child.actualIdx) }"
                            @click="isSelectionMode ? toggleCardSelection(child.actualIdx, $event) : openEditCard(child.actualIdx)"
                          >
                            <template #title>
                              <div class="card-head">
                                <div class="card-left">
                                  <!-- Checkbox para seleção -->
                                  <Checkbox
                                    v-if="isSelectionMode"
                                    :modelValue="selectedCards.has(child.actualIdx)"
                                    @update:modelValue="toggleCardSelection(child.actualIdx, $event)"
                                    @click.stop
                                    binary
                                    class="card-checkbox"
                                  />
                                  <span class="card-index">Cartão {{ child.actualIdx + 1 }}</span>
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
                                  v-if="!isSelectionMode"
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
                                  <div class="preview-text" v-html="highlightSearchTerm(renderMarkdownSafe(previewText(child.card.front, 300)))"></div>
                                </div>

                                <div class="preview-block">
                                  <div class="preview-label">Back</div>
                                  <div class="preview-text" v-html="highlightSearchTerm(renderMarkdownSafe(previewText(child.card.back, 300)))"></div>
                                </div>
                              </div>

                              <div v-if="child.card.src" class="text-xs opacity-70 mt-2 card-source">
                                <strong>Fonte:</strong> <span v-html="highlightSearchTerm(previewText(child.card.src, 160))"></span>
                              </div>

                              <div class="preview-hint">
                                <i class="pi pi-pen-to-square mr-2" />
                                {{ isSelectionMode ? 'Clique para selecionar' : 'Clique no cartão para editar' }}
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

    <!-- GENERATE MODAL -->
    <GenerateModal
      v-model:visible="generateModalVisible"
      :selectedModel="selectedModel"
      :currentModelInfo="currentModelInfo"
      :generating="generating"
      :cardType="cardType"
      :numCardsEnabled="numCardsEnabled"
      :numCardsSlider="numCardsSlider"
      :getModelInfo="getModelInfo"
      :getProviderSeverity="getProviderSeverity"
      :getProviderLabel="getProviderLabel"
      @update:numCardsSlider="numCardsSlider = $event"
      @update:cardType="cardType = $event"
      @customPromptsUpdate="onCustomPromptsUpdate"
      @confirm="onGenerateModalConfirm"
    />

    <!-- EDIT DIALOG -->
    <EditCardDialog
      v-model:visible="editVisible"
      :card="editIndex >= 0 ? cards[editIndex] : null"
      :cardIndex="editIndex"
      :availableDeckNames="availableDeckNames"
      :selectedModel="selectedModel"
      @save="onEditCardSave"
      @delete="onEditCardDelete"
      @duplicate="onEditCardDuplicate"
      @fetchDecks="fetchDecks"
    />

    <!-- CUSTOM INSTRUCTION DIALOG -->
    <CustomInstructionDialog
      v-model:visible="editCustomInstructionVisible"
      :initialInstruction="editCustomInstruction"
      @confirm="onCustomInstructionConfirm"
    />

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
    <ProgressDialog
      v-model:visible="progressVisible"
      :title="progressTitle"
      :value="progressValue"
      :stage="progressStage"
      :icon="progressIcon"
      :details="progressDetails"
      :cancellable="generationProgressCancellable"
      :canceling="generationCanceling"
      @cancel="cancelCurrentGeneration"
    />

    <!-- TOPIC SEGMENTATION CONFIRM -->
    <TopicConfirmDialog
      v-model:visible="showTopicConfirmModal"
      @confirm="onTopicConfirm"
      @cancel="onTopicCancel"
    />

    <!-- API KEYS -->
    <ApiKeysDialog
      v-model:visible="apiKeyVisible"
      :storedKeys="storedKeys"
      :hasStoredKeys="hasStoredApiKeys"
      @save="onApiKeysSave"
      @clear="onApiKeysClear"
    />

    <!-- MODEL SELECTION -->
    <ModelSelectionDialog
      v-model:visible="modelSelectionVisible"
      :availableModels="availableModels"
      :selectedModel="selectedModel"
      :selectedValidationModel="selectedValidationModel"
      :selectedAnalysisModel="selectedAnalysisModel"
      :isLoadingModels="isLoadingModels"
      @update:selectedModel="selectedModel = $event"
      @update:selectedValidationModel="selectedValidationModel = $event"
      @update:selectedAnalysisModel="selectedAnalysisModel = $event"
      @save="saveModelSelection"
      @refresh="fetchAvailableModels"
    />

    <!-- PROMPT SETTINGS -->
    <PromptSettingsDialog
      v-model:visible="promptSettingsVisible"
      :cardType="cardType"
      :savedPrompts="savedCustomPrompts"
      :hasCustomPrompts="hasCustomPromptsSaved"
      @save="onPromptSettingsSave"
      @reset="onPromptSettingsReset"
    />

    <!-- INTRO MODAL (Onboarding) -->
    <IntroModal
      v-model:visible="introModalVisible"
      @complete="onIntroComplete"
    />

    <!-- OLLAMA MODEL SELECTION (fallback) -->
    <OllamaSelectionDialog
      v-model:visible="ollamaModelSelectionVisible"
      :models="ollamaLlmModels"
      @select="onOllamaModelSelect"
    />

    <!-- CLEAR ALL CARDS CONFIRMATION -->
    <Dialog
      v-model:visible="clearCardsVisible"
      header="Confirmar Exclusão"
      modal
      appendTo="body"
      class="modern-dialog"
      style="width: min(480px, 96vw);"
    >
      <div class="confirmation-content">
        <i class="pi pi-exclamation-triangle confirmation-icon"></i>
        <p class="confirmation-text">
          Tem certeza que deseja apagar todos os <strong>{{ cards.length }} cartões</strong>?
        </p>
        <p class="confirmation-warning">
          Esta ação não pode ser desfeita.
        </p>
      </div>

      <template #footer>
        <Button label="Cancelar" severity="secondary" outlined @click="clearCardsVisible = false" />
        <Button label="Sim, apagar tudo" icon="pi pi-trash" severity="danger" @click="clearAllCards" />
      </template>
    </Dialog>

    <!-- ANKI CONFIG -->
    <AnkiExportDialog
      v-model:visible="ankiVisible"
      :ankiModelsData="ankiModelsData"
      :exporting="ankiExporting"
      :allTags="ankiAllTags"
      :initialModel="ankiModel"
      :initialDeck="ankiDeckField"
      :initialTags="ankiTags"
      @export="onAnkiExport"
    />

    <!-- QUESTION GENERATE MODAL -->
    <QuestionGenerateModal
      v-model:visible="showQuestionGenerateModal"
      :selectedModel="selectedModel"
      :currentModelInfo="currentModelInfo"
      :generating="isGeneratingQuestions"
      :hasSelectedText="!!selectedText"
      :selectedTextLength="selectedText?.length || 0"
      :fullTextLength="lastFullText?.length || 0"
      :getModelInfo="getModelInfo"
      :getProviderSeverity="getProviderSeverity"
      :getProviderLabel="getProviderLabel"
      @generate="handleGenerateQuestions"
      @parse="handleParseQuestions"
    />

    <!-- QUESTION EXPORT DIALOG -->
    <QuestionExportDialog
      v-model:visible="showQuestionExportDialog"
      :questions="questionCards"
      :ankiDecks="ankiModelsData?.decks || []"
      :allTags="ankiAllTags"
      :exporting="isExportingQuestions"
      :allInOneStatus="allInOneStatus"
      @export="handleExportQuestions"
      @checkModel="checkAllInOneModelStatus"
    />

    <!-- QUESTION PREVIEW DIALOG -->
    <Dialog
      v-model:visible="questionPreviewVisible"
      header="Preview da Questão"
      modal
      class="modern-dialog"
      style="width: min(720px, 96vw);"
    >
      <QuizInteractive
        v-if="questionPreviewData"
        :question="questionPreviewData"
        :compact="false"
        :showActions="true"
      />
    </Dialog>
  </div>
</template>

<style scoped>
/* =========================
   Base
========================= */
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin-left: 104px;
  margin-right: 12px;
  margin-top: 12px;
  margin-bottom: 12px;
  border-radius: 24px;
  overflow: hidden;
  transition: margin-left 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  background: var(--shell-bg);
  border: 1px solid var(--shell-border);
  box-shadow: var(--shell-shadow);
}

.app-shell.sidebar-expanded {
  margin-left: 324px;
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
  padding: 12px 16px;
  backdrop-filter: blur(16px);
  border-radius: 24px 24px 0 0;
  background: var(--header-bg);
}

:deep(.p-toolbar) {
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--header-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: nowrap;
}

.app-header :deep(.p-toolbar-group-left),
.app-header :deep(.p-toolbar-group-right) {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-header :deep(.p-toolbar-group-right) {
  justify-content: flex-end;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
  flex-wrap: nowrap;
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
  min-width: 0;
  flex-wrap: nowrap;
}

.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: nowrap;
}

.hdr-divider {
  height: 24px;
  opacity: 0.5;
}

.menu-toggle {
  width: 40px;
  height: 40px;
}

@media (max-width: 1200px) {
  .app-header {
    padding: 10px 12px;
  }
  .header-left,
  .header-right {
    gap: 10px;
  }
  .header-badges {
    display: none;
  }
}

@media (max-width: 1024px) {
  .status-wrap {
    display: none;
  }
  .controls {
    gap: 6px;
  }
  .menu-toggle {
    width: 36px;
    height: 36px;
  }
  .app-header :deep(.p-button) {
    padding: 0.4rem 0.6rem;
  }
}

/* CTA Create Cards - verde da logo #28ca73 com efeito de reflexo */
:deep(.cta.p-button) {
  position: relative;
  background: #28ca73 !important;
  border: 1px solid #22b866 !important;
  color: #ffffff !important;
  font-weight: 700;
  overflow: hidden;
  transition: all 0.3s ease;
}

:deep(.cta.p-button)::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.35), transparent);
  transition: left 0.5s ease;
  pointer-events: none;
}

:deep(.cta.p-button:hover)::before {
  left: 100%;
}

:deep(.cta.p-button:hover) {
  background: #22b866 !important;
  border-color: #1da55a !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(40, 202, 115, 0.4);
}

/* Botão secundário premium - verde da logo #28ca73 */
:deep(.btn-shine.p-button) {
  position: relative;
  background: #28ca73 !important;
  border: 1px solid #22b866 !important;
  color: #ffffff !important;
  overflow: hidden;
  transition: all 0.3s ease;
}

:deep(.btn-shine.p-button)::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.35), transparent);
  transition: left 0.5s ease;
  pointer-events: none;
}

:deep(.btn-shine.p-button:hover)::before {
  left: 100%;
}

:deep(.btn-shine.p-button:hover) {
  background: #22b866 !important;
  border-color: #1da55a !important;
  color: #ffffff !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(40, 202, 115, 0.4);
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
  border-radius: 20px;
  border: 1px solid var(--panel-border);
  background: var(--panel-bg);
  backdrop-filter: blur(16px);
  box-shadow: var(--panel-shadow);
  overflow: hidden;
  transition: box-shadow 0.3s ease, border-color 0.3s ease;
}

.panel:hover {
  border-color: var(--panel-border-hover);
  box-shadow: var(--panel-shadow-hover);
}

.panel-head {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--panel-head-border);
  background: var(--panel-head-bg);
  min-width: 0;
}

.panel-title {
  font-weight: 800;
  letter-spacing: -0.2px;
  display: flex;
  align-items: center;
  min-width: 0;
  flex-shrink: 0;
  white-space: nowrap;
}

.panel-body {
  padding: 12px;
  flex: 1;
  min-height: 0;
}

.output-body {
  overflow: auto;
}

/* Container Queries — responsividade baseada na largura do painel */
.panel-editor {
  container-type: inline-size;
  container-name: editor-panel;
}

.panel-output {
  container-type: inline-size;
  container-name: cards-panel;
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
  background: var(--app-border);
  border-radius: 999px;
}

/* =========================
   Editor Search Bar
========================= */
.editor-search-bar {
  position: absolute;
  top: 8px;
  right: 12px;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--searchbar-bg);
  border: 1px solid var(--searchbar-border);
  border-radius: 12px;
  backdrop-filter: blur(12px);
  box-shadow: var(--searchbar-shadow);
}

.search-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
}

.search-input-wrap .search-icon {
  color: var(--searchbar-icon);
  font-size: 14px;
}

.editor-search-bar .search-input {
  width: 200px;
  height: 32px;
  padding: 0 8px;
  border-radius: 8px;
  background: var(--searchbar-input-bg);
  border: 1px solid var(--searchbar-input-border);
  font-size: 13px;
  color: inherit;
}

.editor-search-bar .search-input:focus {
  background: var(--searchbar-input-focus-bg);
  border-color: var(--searchbar-input-focus-border);
  box-shadow: var(--searchbar-input-focus-ring);
}

.search-results-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--searchbar-label);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.search-nav-btns {
  display: flex;
  align-items: center;
  gap: 2px;
}

/* Slide down animation */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-12px);
}

/* Search (cards) */
.search-wrap {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.search-toggle {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--chip-bg);
  border: 1px solid var(--chip-border);
  color: var(--chip-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.search-toggle:hover {
  background: var(--chip-hover-bg);
  border-color: var(--chip-hover-border);
  color: var(--chip-hover-text);
  transform: scale(1.05);
}

.search-wrap.expanded .search-toggle {
  background: var(--chip-active-bg);
  border-color: var(--chip-active-border);
  color: var(--chip-active-text);
}

.search {
  width: 0;
  opacity: 0;
  padding: 0;
  height: 40px;
  border-radius: 12px;
  background: var(--chip-bg);
  border: 1px solid var(--chip-border);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 14px;
}

.search-wrap.expanded .search {
  width: 200px;
  opacity: 1;
  padding: 0 12px;
}

.search:focus {
  background: var(--chip-hover-bg);
  border-color: var(--chip-active-border);
  box-shadow: var(--searchbar-input-focus-ring);
}

.search::placeholder {
  color: var(--searchbar-placeholder);
  font-weight: 500;
}

/* Empty */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 48px 28px;
  opacity: 0.92;
  min-height: 200px;
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

/* =========================
   Questions Section
========================= */
.questions-section {
  margin-bottom: 20px;
}

.questions-section .section-header,
.cards-section .section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--section-bg);
  border-radius: 10px;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  font-weight: 700;
  font-size: 0.9rem;
  color: var(--section-title);
}

.section-title i {
  color: var(--p-primary-color);
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.questions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* =========================
   Editor Actions (Undo/Redo, Stats, Highlights)
========================= */
.editor-undo-redo {
  display: flex;
  gap: 2px;
  align-items: center;
}

.highlight-nav {
  display: flex;
  gap: 4px;
  align-items: center;
}

.highlight-counter {
  font-variant-numeric: tabular-nums;
  min-width: 60px;
  justify-content: center;
}

.text-stats {
  display: flex;
  gap: 6px;
  align-items: center;
}

.stats-pill {
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  opacity: 0.85;
}

.save-status {
  font-size: 11px;
  animation: fadeInStatus 0.3s ease;
}

@keyframes fadeInStatus {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

/* =========================
   Seleção múltipla e Undo/Redo (Cards)
========================= */
.undo-redo-group {
  display: flex;
  gap: 2px;
  align-items: center;
}

.selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--selection-bg);
  border: 1px solid var(--selection-border);
  border-radius: 12px;
  margin: 0 12px 12px 12px;
  backdrop-filter: blur(8px);
}

.selection-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.selection-count {
  font-weight: 700;
  font-size: 14px;
  color: var(--selection-text);
}

.selection-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.card-checkbox {
  margin-right: 8px;
}

/* Flashcards (PrimeVue Card) */
.card-item {
  border-radius: 16px;
  border: 1px solid var(--app-border);
  background: var(--app-card);
  box-shadow: var(--app-shadow);
  backdrop-filter: blur(10px);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, transform 0.2s ease;
}

.card-item:hover {
  border-color: var(--panel-border-hover);
  box-shadow: var(--panel-shadow-hover);
  transform: translateY(-2px);
}

.card-item.card-selected {
  border: 2px solid var(--selection-card-border);
  background: var(--selection-card-bg);
  box-shadow: var(--selection-card-ring), var(--app-shadow);
}

/* Slide up animation para selection bar */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

/* =========================
   Highlight de busca
========================= */
:deep(.search-highlight) {
  background: var(--highlight-bg);
  padding: 1px 4px;
  border-radius: 4px;
  font-weight: 700;
  color: inherit;
}

/* Cards preview */
.cards-view {
  /* PrimeVue DataView (Aura) pinta o fundo do conteúdo via token --p-dataview-content-background */
  --p-dataview-content-background: transparent;
  --p-dataview-content-border-color: transparent;
  --p-dataview-content-border-width: 0px;
}

.cards-view :deep(.p-dataview-content) {
  background: transparent;
  border: 0;
}

.cards-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
  border-left: 3px solid var(--selection-border);
}
.card-item.card-child {
  background: var(--card-child-bg);
  border: 1px solid var(--card-child-border);
  box-shadow: none;
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
  background: var(--deck-pill-bg);
  border: 1px solid var(--deck-pill-border);
  font-weight: 800;
  font-size: 12px;
  opacity: 0.95;
}
.preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  border-radius: 14px;
  border: 1px solid var(--preview-border);
  background: var(--preview-bg);
  overflow: hidden;
}
@media (max-width: 920px) {
  .preview-grid {
    grid-template-columns: 1fr;
  }
  .search-wrap { width: 100%; }
}
.preview-block {
  padding: 12px 16px;
  min-width: 0;
}

/* Divisão sutil entre Front/Back */
.preview-block + .preview-block {
  border-left: 1px solid var(--preview-border);
}

@media (max-width: 920px) {
  .preview-block + .preview-block {
    border-left: none;
    border-top: 1px solid var(--preview-border);
  }
}

.preview-label {
  font-weight: 800;
  font-size: 12px;
  color: var(--app-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}
.preview-text {
  font-size: 14px;
  line-height: 1.5;
  color: var(--app-text);
}

.card-source {
  font-size: 12px;
  line-height: 1.45;
  color: var(--app-text-muted);
}

.preview-hint {
  margin-top: 10px;
  font-size: 12px;
  opacity: 0.4;
  display: flex;
  align-items: center;
  transition: opacity 0.2s ease;
}
.card-item:hover .preview-hint {
  opacity: 0.9;
}

/* Delete button: visible only on hover */
.card-head .icon-only {
  opacity: 0;
  transition: opacity 0.2s ease;
}
.card-item:hover .card-head .icon-only {
  opacity: 1;
}

/* markdown-ish */
.preview-text :deep(code),
.md-preview :deep(code) {
  padding: 2px 6px;
  border-radius: 8px;
  background: var(--highlight-help-bg);
  border: 1px solid var(--highlight-help-border);
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
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--cloze-bg);
  border: 1px solid var(--cloze-border);
  border-bottom: 2px solid var(--cloze-border);
  font-weight: 700;
  display: inline;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
  line-height: 1.7;
}

/* Edit dialog */
.field-area :deep(textarea) {
  border-radius: 14px;
}

/* Edit Card Dialog - Enhanced */
:deep(.edit-card-dialog) {
  --edit-accent: var(--edit-accent);
}

.edit-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 16px;
  flex-wrap: wrap;
}

.edit-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.edit-card-number {
  font-size: 1.25rem;
  font-weight: 900;
  color: var(--edit-accent);
}

.edit-type-tag {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  font-weight: 700;
}

.edit-header-right {
  display: flex;
  align-items: center;
}

.deck-select-compact {
  width: 180px;
}

.edit-card-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 768px) {
  .edit-card-content {
    grid-template-columns: 1fr;
  }
  .edit-dialog-header {
    flex-direction: column;
    align-items: flex-start;
  }
}

.edit-field {
  display: flex;
  flex-direction: column;
}

.edit-field-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 800;
  font-size: 14px;
  margin-bottom: 10px;
  color: var(--edit-field-label);
}

.edit-field-header i {
  color: var(--edit-accent);
  font-size: 15px;
}

/* Edit Card QuillEditor */
.edit-card-quill {
  min-height: 180px;
  height: auto;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--edit-quill-border);
  background: var(--ghost-bg-strong);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.edit-card-quill:focus-within {
  border-color: var(--edit-accent);
  box-shadow: var(--searchbar-input-focus-ring);
}

.edit-card-quill :deep(.ql-toolbar) {
  border: none;
  border-bottom: 1px solid var(--edit-quill-toolbar-border);
  background: var(--modal-surface-bg);
  padding: 6px 8px;
  flex-shrink: 0;
}

.edit-card-quill :deep(.ql-container) {
  border: none;
  min-height: 120px;
  flex: 1;
  font-size: 14px;
  display: flex;
  flex-direction: column;
}

.edit-card-quill :deep(.ql-editor) {
  min-height: 120px;
  height: auto;
  flex: 1;
  padding: 12px 14px;
  overflow-y: auto;
}

.edit-card-quill :deep(.ql-editor.ql-blank::before) {
  font-style: normal;
  color: var(--input-muted);
}

/* AI Rewrite Section */
.edit-ai-section {
  margin-top: 20px;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--edit-ai-bg);
  border: 1px solid var(--edit-ai-border);
}

.edit-ai-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 13px;
  margin-bottom: 12px;
  color: var(--edit-ai-label);
}

.edit-ai-header i {
  color: var(--edit-ai-icon);
  font-size: 14px;
}

.edit-ai-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Edit Footer */
.edit-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.edit-footer-left {
  display: flex;
}

.edit-footer-right {
  display: flex;
  gap: 8px;
}
.md-preview {
  border-radius: 14px;
  padding: 12px;
  border: 1px solid var(--preview-border);
  background: var(--modal-surface-bg);
  min-height: 120px;
  font-size: 13.5px;
  line-height: 1.35;
  opacity: 0.92;
}

/* Dialogs */
.api-info {
  border: 1px solid var(--selection-border);
}
.model-info {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid var(--modal-surface-border);
  background: var(--modal-surface-bg);
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.req { color: var(--required-color); font-weight: 900; margin-left: 6px; }
.opt { opacity: 0.7; margin-left: 6px; }
.err { color: var(--required-color); margin-top: 8px; font-weight: 800; }

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
  background: var(--log-bg);
  border: 1px solid var(--log-border);
}
.log-ts { opacity: 0.7; white-space: nowrap; }
.log-msg { opacity: 0.92; }
.log-row.t-success { border-color: var(--log-success-border); }
.log-row.t-error { border-color: var(--log-error-border); }

/* Pills */
.pill {
  border-radius: 999px;
  font-weight: 900;
}
.pill.subtle { opacity: 0.9; }

.pdf-badge {
  margin-left: 4px;
  font-size: 0.75em;
  opacity: 0.8;
  color: var(--required-color);
  font-weight: 600;
}

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
  background: var(--ghost-bg);
  border: 1px solid var(--ghost-border);
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
  background: var(--status-sep);
}

/* =========================
   Modern Dialog (PrimeVue)
========================= */
:deep(.p-dialog.modern-dialog) {
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid var(--dialog-border);
  background: var(--dialog-bg);
  backdrop-filter: blur(14px);
  box-shadow: var(--dialog-shadow);
}

:deep(.p-dialog.modern-dialog .p-dialog-header) {
  padding: 14px 16px;
  background: var(--dialog-header-bg);
  border-bottom: 1px solid var(--dialog-surface-border);
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
  background: var(--dialog-footer-bg);
  border-top: 1px solid var(--dialog-surface-border);
}

:deep(.p-dialog.modern-dialog .p-dialog-header-icon) {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  background: var(--ghost-bg);
  border: 1px solid var(--ghost-border);
}

:deep(.p-dialog.modern-dialog .p-dialog-header-icon:hover) {
  background: var(--ghost-bg-strong);
}

:deep(.p-dialog-mask) {
  backdrop-filter: blur(8px);
  background: var(--dialog-mask);
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
  box-shadow: var(--focus-ring);
  border-color: var(--focus-border);
}

/* =========================
   Generate Modal Styles (Modern)
========================= */
:deep(.generate-modal) {
  background: var(--p-content-background);
  border-radius: 20px;
  overflow: hidden;
  box-shadow: var(--gen-modal-shadow);
  animation: modalSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

:deep(.generate-modal .p-dialog-header) {
  padding: 1.5rem 1.75rem;
  border-bottom: 1px solid var(--gen-header-border);
  background: var(--gen-header-bg);
  backdrop-filter: blur(20px);
  position: relative;
  overflow: hidden;
}

:deep(.generate-modal .p-dialog-header::before) {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--gen-header-line);
}

:deep(.generate-modal .p-dialog-content) {
  padding: 1.5rem 1.75rem;
  background: var(--p-surface-ground);
}

:deep(.generate-modal .p-dialog-footer) {
  padding: 1.25rem 1.75rem;
  border-top: 1px solid var(--gen-footer-border);
  background: var(--gen-footer-bg);
}

:deep(.generate-modal .generate-modal-header) {
  display: flex;
  align-items: center;
  gap: 1rem;
}

:deep(.generate-modal .generate-modal-header .header-icon) {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: var(--gen-icon-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: var(--gen-icon-shadow), var(--gen-icon-inset);
  position: relative;
  animation: iconPulse 2s ease-in-out infinite;
}

@keyframes iconPulse {
  0%, 100% {
    box-shadow: var(--gen-icon-shadow), var(--gen-icon-inset);
  }
  50% {
    box-shadow:
      0 8px 24px -4px color-mix(in srgb, var(--color-primary) 60%, transparent),
      var(--gen-icon-inset);
  }
}

:deep(.generate-modal .generate-modal-header .header-icon::after) {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 16px;
  background: var(--gen-icon-gloss);
  pointer-events: none;
}

:deep(.generate-modal .generate-modal-header .header-icon i) {
  font-size: 1.6rem;
  color: var(--app-text);
  filter: drop-shadow(0 2px 4px color-mix(in srgb, var(--app-text) 30%, transparent));
}

:deep(.generate-modal .generate-modal-header .header-text h3) {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--p-text-color);
  letter-spacing: -0.02em;
}

:deep(.generate-modal .generate-modal-header .header-text p) {
  margin: 0.35rem 0 0 0;
  font-size: 0.9rem;
  color: var(--p-text-muted-color);
  opacity: 0.85;
}

:deep(.generate-modal .generate-modal-content) {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

:deep(.generate-modal .generate-section) {
  background: var(--p-content-background);
  border: 1px solid var(--gen-section-border);
  border-radius: 16px;
  padding: 1.25rem;
  position: relative;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

:deep(.generate-modal .generate-section::before) {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--gen-section-line);
  opacity: 0;
  transition: opacity 0.25s ease;
}

:deep(.generate-modal .generate-section:hover) {
  border-color: var(--gen-section-hover-border);
  box-shadow: var(--gen-section-hover-shadow);
}

:deep(.generate-modal .generate-section:hover::before) {
  opacity: 1;
}

:deep(.generate-modal .section-header) {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  margin-bottom: 1rem;
}

:deep(.generate-modal .section-icon) {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--gen-section-icon-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: var(--gen-section-icon-shadow);
  position: relative;
}

:deep(.generate-modal .section-icon::after) {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 12px;
  background: var(--gen-section-icon-gloss);
}

:deep(.generate-modal .section-icon.prompt-icon) {
  background: var(--gen-section-icon-prompt-bg);
  box-shadow: var(--gen-section-icon-prompt-shadow);
}

:deep(.generate-modal .section-icon i) {
  color: white;
  font-size: 1.15rem;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.15));
}

:deep(.generate-modal .section-title) {
  display: flex !important;
  flex-direction: column !important;
  gap: 0.35rem;
  flex: 1;
}

:deep(.generate-modal .section-title .title) {
  display: block !important;
  font-weight: 600;
  font-size: 1rem;
  color: var(--p-text-color);
  line-height: 1.4;
  letter-spacing: -0.01em;
}

:deep(.generate-modal .section-title .subtitle) {
  display: block !important;
  font-size: 0.8rem;
  color: var(--p-text-muted-color);
  line-height: 1.4;
  opacity: 0.7;
}

:deep(.generate-modal .quantity-control) {
  padding: 0;
}

:deep(.generate-modal .quantity-toggle) {
  display: flex;
  align-items: center;
  gap: 0.875rem;
}

:deep(.generate-modal .quantity-toggle label) {
  color: var(--p-text-color);
  font-size: 0.9rem;
  cursor: pointer;
  transition: color 0.2s ease;
}

:deep(.generate-modal .quantity-toggle label:hover) {
  color: var(--p-primary-color);
}

:deep(.generate-modal .quantity-slider-wrapper) {
  margin-top: 1.25rem;
  padding: 1.5rem;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.04) 0%, rgba(139, 92, 246, 0.02) 100%);
  border-radius: 14px;
  border: 1px solid rgba(99, 102, 241, 0.12);
  position: relative;
  overflow: hidden;
}

:deep(.generate-modal .quantity-slider-wrapper::before) {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.2), transparent);
}

:deep(.generate-modal .quantity-display) {
  display: flex !important;
  flex-direction: row !important;
  align-items: baseline;
  justify-content: center;
  gap: 0.625rem;
  margin-bottom: 1.5rem;
}

:deep(.generate-modal .quantity-value) {
  display: inline-block;
  font-size: 3.5rem;
  font-weight: 800;
  background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
  letter-spacing: -0.03em;
}

:deep(.generate-modal .quantity-label) {
  display: inline-block;
  font-size: 1.15rem;
  color: var(--p-text-muted-color);
  font-weight: 500;
  opacity: 0.75;
  margin-left: 0.25rem;
}

:deep(.generate-modal .quantity-slider) {
  width: 100%;
}

:deep(.generate-modal .quantity-slider .p-slider-range) {
  background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.4);
}

:deep(.generate-modal .quantity-slider .p-slider-handle) {
  width: 28px;
  height: 28px;
  margin-top: -13px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border: 3px solid white;
  box-shadow:
    0 4px 12px rgba(99, 102, 241, 0.4),
    0 0 0 4px rgba(99, 102, 241, 0.1);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

:deep(.generate-modal .quantity-slider .p-slider-handle:hover) {
  transform: scale(1.15);
  box-shadow:
    0 6px 20px rgba(99, 102, 241, 0.5),
    0 0 0 6px rgba(99, 102, 241, 0.15);
}

:deep(.generate-modal .quantity-slider .p-slider-handle:active) {
  transform: scale(1.1);
}

:deep(.generate-modal .quantity-range-labels) {
  display: flex;
  justify-content: space-between;
  margin-top: 0.875rem;
  font-size: 0.75rem;
  color: var(--p-text-muted-color);
  font-weight: 500;
  opacity: 0.6;
}

:deep(.generate-modal .quantity-auto-hint) {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  margin: 1rem 0 0 0;
  padding: 0.875rem 1rem;
  font-size: 0.85rem;
  color: var(--p-text-muted-color);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(139, 92, 246, 0.03) 100%);
  border-radius: 12px;
  border: 1px dashed rgba(99, 102, 241, 0.2);
}

:deep(.generate-modal .quantity-auto-hint i) {
  color: var(--p-primary-color);
  font-size: 1rem;
}

:deep(.generate-modal .generate-modal-footer) {
  display: flex;
  justify-content: flex-end;
  gap: 0.875rem;
}

:deep(.generate-modal .generate-modal-footer .p-button-secondary) {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--p-text-muted-color);
  transition: all 0.2s ease;
}

:deep(.generate-modal .generate-modal-footer .p-button-secondary:hover) {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.15);
  color: var(--p-text-color);
}

:deep(.generate-modal .generate-modal-footer .cta) {
  min-width: 150px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
  border: none;
  font-weight: 600;
  padding: 0.75rem 1.5rem;
  box-shadow:
    0 4px 16px -2px rgba(99, 102, 241, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.15);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

:deep(.generate-modal .generate-modal-footer .cta::before) {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.5s ease;
}

:deep(.generate-modal .generate-modal-footer .cta:hover) {
  transform: translateY(-2px);
  box-shadow:
    0 8px 24px -4px rgba(99, 102, 241, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

:deep(.generate-modal .generate-modal-footer .cta:hover::before) {
  left: 100%;
}

:deep(.generate-modal .generate-modal-footer .cta:active) {
  transform: translateY(0);
}

:deep(.generate-modal .generate-modal-footer .cta .p-button-icon) {
  font-size: 1rem;
}

/* =========================
   Generate Stepper Styles
========================= */
:deep(.generate-stepper) {
  margin: -1rem;
}

:deep(.generate-stepper .p-stepper-list) {
  padding: 1rem;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(139, 92, 246, 0.04) 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

:deep(.generate-stepper .p-stepper-panels) {
  padding: 1rem;
}

/* Transition for slider */
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.25s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* =========================
   Progress Dialog Styles
========================= */
:deep(.progress-dialog .progress-content) {
  padding: 0.5rem 0;
}

:deep(.progress-dialog .progress-info) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

:deep(.progress-dialog .progress-stage) {
  font-size: 0.95rem;
  color: var(--p-text-color);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

:deep(.progress-dialog .progress-stage-icon) {
  font-size: 1rem;
  color: var(--p-primary-color);
  flex-shrink: 0;
}

:deep(.progress-dialog .progress-percent) {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--p-primary-color);
  min-width: 40px;
  text-align: right;
}

/* Force dark theme on progress pipeline */
:deep(.progress-dialog .progress-pipeline) {
  background: rgba(30, 41, 59, 0.95) !important;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(148, 163, 184, 0.15) !important;
}

:deep(.progress-dialog .pipeline-stats) {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

:deep(.progress-dialog .stat-item) {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
}

:deep(.progress-dialog .stat-item.total) {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
  font-weight: 600;
}

:deep(.progress-dialog .stat-label) {
  color: rgba(148, 163, 184, 0.8) !important;
  min-width: 100px;
}

:deep(.progress-dialog .stat-value) {
  color: rgba(241, 245, 249, 0.95) !important;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

:deep(.progress-dialog .stat-value.success) {
  color: #22c55e !important;
  font-weight: 500;
}

:deep(.progress-dialog .stat-value.danger) {
  color: #f87171 !important;
  font-weight: 500;
}

:deep(.progress-dialog .stat-value i) {
  font-size: 0.75rem;
}

/* =========================
   Espaços dos botões (Cards header)
========================= */
.panel-actions{
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: nowrap;
  min-width: 0;
  flex-shrink: 1;
}

.editor-zen-group{
  display: flex;
  align-items: center;
  gap: 8px;
}

.editor-switch{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.45), rgba(15, 23, 42, 0.65));
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.08);
  backdrop-filter: blur(8px);
  transition: transform 0.15s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.editor-switch:hover{
  transform: translateY(-1px);
  border-color: rgba(99, 102, 241, 0.4);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.25), 0 0 10px rgba(99, 102, 241, 0.18);
}

.editor-switch-label{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 0.75rem;
  color: rgba(226, 232, 240, 0.9);
  letter-spacing: 0.01em;
}

.editor-switch-label i{
  font-size: 0.9rem;
}

.zen-switch:deep(.p-inputswitch-slider){
  background: rgba(71, 85, 105, 0.55);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.35);
}

.zen-switch:deep(.p-inputswitch.p-highlight .p-inputswitch-slider){
  background: linear-gradient(135deg, #a855f7, #6366f1);
  box-shadow:
    0 0 0 1px rgba(168, 85, 247, 0.45),
    0 0 14px rgba(168, 85, 247, 0.35);
}

.line-switch:deep(.p-inputswitch-slider){
  background: rgba(71, 85, 105, 0.55);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.35);
}

.line-switch:deep(.p-inputswitch.p-highlight .p-inputswitch-slider){
  background: linear-gradient(135deg, #a855f7, #6366f1);
  box-shadow:
    0 0 0 1px rgba(168, 85, 247, 0.45),
    0 0 14px rgba(168, 85, 247, 0.35);
}

.export-group{
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.export-btn{
  flex-shrink: 0;
}

/* Cards panel-title — overflow handling para pills */
.panel-output .panel-title {
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
}

.cards-total-pill {
  flex-shrink: 0;
}

.generation-source-tag {
  flex-shrink: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* =========================
   Container Queries — Editor Header (colapso por prioridade)
========================= */

/* < 800px — esconde stats de texto (palavras, tempo de leitura) */
@container editor-panel (max-width: 800px) {
  .text-stats {
    display: none;
  }
}

/* < 650px — colapsa labels dos switches (fica só ícone + toggle) */
@container editor-panel (max-width: 650px) {
  .editor-switch-label {
    font-size: 0;
    gap: 0;
  }
  .editor-switch-label i {
    font-size: 0.9rem;
  }
  .editor-switch {
    padding: 6px 8px;
    gap: 6px;
  }
  .editor-zen-group {
    gap: 4px;
  }
  .panel-actions {
    gap: 8px;
  }
}

/* < 500px — esconde grupo zen inteiro */
@container editor-panel (max-width: 500px) {
  .editor-zen-group {
    display: none;
  }
}

/* =========================
   Container Queries — Cards Header (colapso por prioridade)
========================= */

/* < 600px — esconde tag de fonte da geração */
@container cards-panel (max-width: 600px) {
  .generation-source-tag {
    display: none !important;
  }
}

/* < 480px — esconde undo/redo e tags secundárias do título */
@container cards-panel (max-width: 480px) {
  .undo-redo-group {
    display: none;
  }
  .panel-title .pill:not(.cards-total-pill) {
    display: none;
  }
}

/* < 380px — esconde botão de modo seleção e busca */
@container cards-panel (max-width: 380px) {
  .panel-output .panel-actions > :deep(.p-button):not(:last-child) {
    display: none;
  }
  .search-wrap {
    display: none;
  }
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
  position: relative;
  overflow: hidden;
}

/* Overlay de segmentação de tópicos */
.segmentation-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  border-radius: inherit;
  pointer-events: auto;
}

.segmentation-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 2rem;
  background: var(--p-surface-800);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.segmentation-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.segmentation-text .stage {
  font-size: 0.95rem;
  font-weight: 500;
  color: var(--p-surface-0);
}

.segmentation-text .percent {
  font-size: 0.8rem;
  color: var(--p-surface-200);
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

/* ✅ Quando usa paginação do PDF, desabilita colunas para mostrar uma página de cada vez */
.reader-mode.reader-pdf-pagination .reader-surface :deep(.ql-editor){
  column-width: unset !important;
  column-gap: unset !important;
  column-fill: unset !important;
  width: 100% !important;
  max-width: var(--reader-page-width);
  margin: 0 auto !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  /* Transição suave para mudança de conteúdo */
  animation: fadeInPage 0.25s ease-out;
}

/* Animação de entrada da página */
@keyframes fadeInPage {
  from {
    opacity: 0.6;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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
   Tema Sépia (conforto visual)
========================= */
.reader-mode.reader-sepia .panel-editor{
  background: #f4ecd8 !important;
}

.reader-mode.reader-sepia .reader-surface :deep(.ql-container),
.reader-mode.reader-sepia .reader-surface :deep(.ql-editor){
  background: #f4ecd8 !important;
  color: #5c4b37 !important;
}

.reader-mode.reader-sepia .reader-surface :deep(.ql-toolbar){
  background: rgba(244,236,216,0.95) !important;
  border: 0 !important;
  border-bottom: 1px solid rgba(92,75,55,0.15) !important;
  color: #5c4b37 !important;
}

.reader-mode.reader-sepia .reader-page-float,
.reader-mode.reader-sepia .reader-progress-label {
  background: rgba(92, 75, 55, 0.85) !important;
  color: #f4ecd8 !important;
}

.reader-mode.reader-sepia .reader-progress-bar {
  background: rgba(92, 75, 55, 0.2) !important;
}

.reader-mode.reader-sepia .reader-progress-fill {
  background: linear-gradient(90deg, #8b7355 0%, #6b5344 100%) !important;
}

.reader-mode.reader-sepia .nav-zone i {
  color: #5c4b37 !important;
}

/* =========================
   Tema escuro (mantém look atual)
========================= */
.reader-mode.reader-dark .panel-editor{
  background: rgba(17, 24, 39, 0.98);
}

.reader-mode.reader-dark .reader-surface :deep(.ql-container),
.reader-mode.reader-dark .reader-surface :deep(.ql-editor){
  background: #0f172a !important;
  color: #e2e8f0 !important;
}

/* =========================
   Barra de Progresso
========================= */
.reader-progress-wrapper {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(12px);
  border-radius: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.reader-progress-bar {
  width: 200px;
  height: 6px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
  overflow: hidden;
}

.reader-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
  border-radius: 3px;
  transition: width 0.3s ease-out;
}

.reader-progress-label {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  min-width: 36px;
  text-align: right;
}

/* Animação de entrada/saída da barra de progresso */
.progress-bar-enter-active,
.progress-bar-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.progress-bar-enter-from,
.progress-bar-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-10px);
}

/* =========================
   Indicador de Página Flutuante
========================= */
.reader-page-float {
  position: absolute;
  bottom: 20px;
  right: 24px;
  z-index: 100;
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 10px 18px;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(12px);
  border-radius: 20px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
}

.float-page {
  font-size: 22px;
  font-weight: 700;
  color: #ffffff;
}

.float-sep {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  font-weight: 400;
}

.float-total {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.7);
}

/* =========================
   Paginator do Modo Leitura (PDF)
========================= */
.reader-paginator {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  gap: 4px;
}

.reader-paginator :deep(.p-paginator-first),
.reader-paginator :deep(.p-paginator-prev),
.reader-paginator :deep(.p-paginator-next),
.reader-paginator :deep(.p-paginator-last) {
  background: rgba(255, 255, 255, 0.1) !important;
  border: none !important;
  color: #ffffff !important;
  min-width: 32px !important;
  height: 32px !important;
  border-radius: 8px !important;
  transition: background 0.2s ease, transform 0.15s ease;
}

.reader-paginator :deep(.p-paginator-first):hover,
.reader-paginator :deep(.p-paginator-prev):hover,
.reader-paginator :deep(.p-paginator-next):hover,
.reader-paginator :deep(.p-paginator-last):hover {
  background: rgba(255, 255, 255, 0.25) !important;
  transform: scale(1.05);
}

.reader-paginator :deep(.p-paginator-first):disabled,
.reader-paginator :deep(.p-paginator-prev):disabled,
.reader-paginator :deep(.p-paginator-next):disabled,
.reader-paginator :deep(.p-paginator-last):disabled {
  opacity: 0.3 !important;
  transform: none !important;
}

.reader-paginator :deep(.p-paginator-current) {
  color: #ffffff !important;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  font-size: 15px;
  font-weight: 600;
  padding: 0 12px;
  min-width: auto;
}

/* Tema kindle para o paginator */
.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-first),
.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-prev),
.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-next),
.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-last) {
  background: rgba(0, 0, 0, 0.08) !important;
  color: #111827 !important;
}

.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-first):hover,
.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-prev):hover,
.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-next):hover,
.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-last):hover {
  background: rgba(0, 0, 0, 0.15) !important;
}

.reader-mode.reader-kindle .reader-paginator :deep(.p-paginator-current) {
  color: #111827 !important;
}

/* Tema sepia para o paginator */
.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-first),
.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-prev),
.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-next),
.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-last) {
  background: rgba(92, 75, 55, 0.15) !important;
  color: #5c4b37 !important;
}

.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-first):hover,
.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-prev):hover,
.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-next):hover,
.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-last):hover {
  background: rgba(92, 75, 55, 0.25) !important;
}

.reader-mode.reader-sepia .reader-paginator :deep(.p-paginator-current) {
  color: #5c4b37 !important;
}

/* =========================
   Zonas de Navegação Laterais
========================= */
.reader-nav-zones {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 50;
  pointer-events: none;
}

.nav-zone {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 80px;
  background: transparent;
  border: none;
  cursor: pointer;
  pointer-events: all;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.25s ease, background 0.25s ease;
}

.nav-zone:hover {
  opacity: 1;
  background: linear-gradient(90deg, rgba(0,0,0,0.08) 0%, transparent 100%);
}

.nav-zone-left {
  left: 0;
}

.nav-zone-left:hover {
  background: linear-gradient(90deg, rgba(0,0,0,0.12) 0%, transparent 100%);
}

.nav-zone-right {
  right: 0;
}

.nav-zone-right:hover {
  background: linear-gradient(-90deg, rgba(0,0,0,0.12) 0%, transparent 100%);
}

.nav-zone i {
  font-size: 28px;
  color: rgba(255, 255, 255, 0.6);
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  transition: transform 0.2s ease;
}

.nav-zone:hover i {
  transform: scale(1.15);
}

.nav-zone:disabled {
  cursor: default;
  opacity: 0 !important;
}

/* Tema claro - ajusta cores das zonas */
.reader-mode.reader-kindle .nav-zone i {
  color: rgba(0, 0, 0, 0.4);
  text-shadow: none;
}

.reader-mode.reader-kindle .nav-zone:hover {
  background: linear-gradient(90deg, rgba(0,0,0,0.06) 0%, transparent 100%);
}

.reader-mode.reader-kindle .nav-zone-right:hover {
  background: linear-gradient(-90deg, rgba(0,0,0,0.06) 0%, transparent 100%);
}

.reader-mode.reader-kindle .reader-page-float,
.reader-mode.reader-kindle .reader-progress-wrapper {
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.reader-mode.reader-kindle .float-page {
  color: #111827;
}

.reader-mode.reader-kindle .float-sep {
  color: rgba(17, 24, 39, 0.4);
}

.reader-mode.reader-kindle .float-total {
  color: rgba(17, 24, 39, 0.6);
}

.reader-mode.reader-kindle .reader-progress-bar {
  background: rgba(0, 0, 0, 0.1);
}

.reader-mode.reader-kindle .reader-progress-label {
  color: #111827;
}

/* =========================
   Controles do Modo Leitura
========================= */
.reader-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.reader-nav-group,
.reader-font-group,
.reader-layout-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.page-indicator {
  display: flex;
  align-items: baseline;
  gap: 4px;
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  font-family: ui-monospace, SFMono-Regular, monospace;
}

.page-current {
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.page-sep {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
}

.page-total {
  font-size: 13px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.6);
}

.font-scale-label {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.8);
  min-width: 40px;
  text-align: center;
  padding: 0 4px;
}

.theme-selector {
  display: flex;
  gap: 2px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 20px;
  padding: 3px;
}

.theme-selector .theme-active {
  background: rgba(99, 102, 241, 0.3) !important;
}

/* Fade animation */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Indicador de fonte de geração */
.generation-source-tag {
  font-size: 0.72rem;
  padding: 0.2rem 0.6rem;
  cursor: help;
  gap: 6px;
  display: inline-flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.25);
}

.generation-source-tag .source-label {
  font-weight: 800;
  letter-spacing: 0.2px;
}

.generation-source-tag .source-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
  position: relative;
  padding-left: 10px;
}

.generation-source-tag .source-count::before {
  content: '•';
  position: absolute;
  left: 2px;
  opacity: 0.6;
}

.cards-total-pill {
  font-size: 0.72rem;
  padding: 0.2rem 0.6rem;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(34, 197, 94, 0.05));
  border: 1px solid rgba(34, 197, 94, 0.35);
  box-shadow: 0 6px 18px rgba(16, 185, 129, 0.2);
}

.cards-total-pill .total-label {
  font-weight: 700;
  opacity: 0.8;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  font-size: 0.6rem;
}

.cards-total-pill .total-sep {
  opacity: 0.6;
}

.cards-total-pill .total-value {
  font-weight: 900;
  font-size: 0.82rem;
}

/* Auto-hide controles */
.controls-hidden .app-header {
  opacity: 0;
  transform: translateY(-100%);
  transition: opacity 0.4s ease, transform 0.4s ease;
}

.controls-hidden:hover .app-header {
  opacity: 1;
  transform: translateY(0);
}

.controls-hidden .reader-progress-wrapper {
  opacity: 0.3;
}

.controls-hidden:hover .reader-progress-wrapper {
  opacity: 1;
}

/* =========================
   Panel body no modo leitura
========================= */
.reader-mode .panel-body {
  position: relative;
}

/* =========================
   Responsivo
========================= */
@media (max-width: 768px) {
  .reader-progress-bar {
    width: 120px;
  }
  
  .nav-zone {
    width: 50px;
  }
  
  .reader-page-float {
    bottom: 12px;
    right: 12px;
    padding: 8px 14px;
  }
  
  .float-page {
    font-size: 18px;
  }
  
  .theme-selector {
    display: none;
  }
  
  .reader-nav-group,
  .reader-font-group {
    gap: 2px;
  }
}

@media (max-width: 520px){
  .reader-mode .reader-surface :deep(.ql-container){
    padding: 28px 22px;
  }
  .reader-mode .reader-surface :deep(.ql-editor){
    font-size: calc(18px * var(--reader-scale));
  }
  
  .reader-progress-wrapper {
    padding: 6px 12px;
  }
  
  .reader-progress-bar {
    width: 80px;
  }
  
  .reader-page-float {
    bottom: 8px;
    right: 8px;
    padding: 6px 10px;
    border-radius: 14px;
  }
  
  .float-page {
    font-size: 16px;
  }
  
  .float-total {
    font-size: 12px;
  }
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-tags {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.model-tag {
  font-size: 10px;
  padding: 2px 6px;
  font-weight: 500;
}

/* Confirmation dialog */
.confirmation-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 20px 10px;
  gap: 12px;
}

.confirmation-icon {
  font-size: 48px;
  color: #f59e0b;
  margin-bottom: 8px;
}

.confirmation-text {
  font-size: 16px;
  line-height: 1.5;
  margin: 0;
}

.confirmation-warning {
  font-size: 14px;
  opacity: 0.7;
  margin: 0;
}

/* Clear all button */
.clear-all-btn {
  width: 40px;
  height: 40px;
  transition: all 0.2s ease;
}

.clear-all-btn:not(:disabled):hover {
  background: rgba(239, 68, 68, 0.15) !important;
  transform: scale(1.08);
}

.clear-all-btn svg {
  transition: all 0.2s ease;
}

.clear-all-btn:not(:disabled):hover svg {
  transform: scale(1.1);
}

/* Topic Confirm Modal */
.topic-confirm-content {
  text-align: center;
  padding: 1rem 0;
}

.topic-confirm-content .confirm-icon {
  margin-bottom: 1rem;
}

.topic-confirm-content .confirm-text {
  font-size: 1rem;
  color: var(--p-surface-700);
  margin-bottom: 0.75rem;
  line-height: 1.5;
}

.topic-confirm-content .confirm-subtext {
  font-size: 0.85rem;
  color: var(--p-surface-500);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.topic-confirm-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

/* =========================
   Intro Modal (Onboarding)
========================= */
:deep(.intro-modal-dialog) {
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.12);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(255, 255, 255, 0.03) inset;
}

:deep(.intro-modal-dialog .p-dialog-header) {
  background:
    radial-gradient(600px 300px at 50% -50%, rgba(16, 185, 129, 0.15), transparent 70%),
    linear-gradient(180deg, rgba(17, 24, 39, 0.98), rgba(15, 23, 42, 0.95));
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  padding: 1rem 1.5rem;
}

:deep(.intro-modal-dialog .p-dialog-content) {
  background:
    radial-gradient(800px 400px at 20% 100%, rgba(99, 102, 241, 0.08), transparent 60%),
    radial-gradient(600px 300px at 80% 0%, rgba(16, 185, 129, 0.06), transparent 50%),
    linear-gradient(180deg, rgba(15, 23, 42, 0.95), rgba(17, 24, 39, 0.98));
  padding: 1.5rem;
}

:deep(.intro-modal-dialog .p-dialog-footer) {
  background:
    radial-gradient(600px 200px at 50% 150%, rgba(16, 185, 129, 0.1), transparent 70%),
    linear-gradient(180deg, rgba(15, 23, 42, 0.95), rgba(17, 24, 39, 0.98));
  border-top: 1px solid rgba(148, 163, 184, 0.1);
  padding: 1rem 1.5rem;
}

/* =========================
   Ollama Selection Modal
========================= */
:deep(.ollama-selection-dialog) {
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.12);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(255, 255, 255, 0.03) inset;
}

:deep(.ollama-selection-dialog .p-dialog-header) {
  background:
    radial-gradient(600px 300px at 50% -50%, rgba(16, 185, 129, 0.15), transparent 70%),
    linear-gradient(180deg, rgba(17, 24, 39, 0.98), rgba(15, 23, 42, 0.95));
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  padding: 1rem 1.5rem;
}

:deep(.ollama-selection-dialog .p-dialog-content) {
  background:
    radial-gradient(800px 400px at 20% 100%, rgba(99, 102, 241, 0.08), transparent 60%),
    radial-gradient(600px 300px at 80% 0%, rgba(16, 185, 129, 0.06), transparent 50%),
    linear-gradient(180deg, rgba(15, 23, 42, 0.95), rgba(17, 24, 39, 0.98));
  padding: 1.5rem;
}

.ollama-model-item:hover {
  background: rgba(16, 185, 129, 0.15) !important;
  border-color: rgba(16, 185, 129, 0.3) !important;
  transform: translateX(4px);
}

.ollama-model-item:hover .pi-chevron-right {
  color: #10b981 !important;
}

/* =========================
   Anki Export Modal
========================= */
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

.anki-export-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 640px) {
  .anki-export-row {
    grid-template-columns: 1fr;
  }
}

.anki-export-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.875rem;
  color: rgba(255, 255, 255, 0.9);
}

.anki-export-label i {
  color: #10b981;
  font-size: 0.875rem;
}

.anki-export-optional {
  font-weight: 400;
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
}

.anki-export-hint {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 0.25rem;
}
</style>
