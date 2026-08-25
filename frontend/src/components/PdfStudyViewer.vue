<!-- frontend/src/components/PdfStudyViewer.vue -->
<!-- Leitor de PDF para estudo: renderiza o PDF original (PDF.js via @tato30/vue-pdf)
     em rolagem contínua, com camada de texto selecionável. Seleção exibe toolbar
     flutuante para gerar cartões, marcar trechos (4 cores), enviar ao editor ou
     copiar. Marcações viram objetos clicáveis na página: dá para selecionar,
     trocar a cor, editar o texto, gerar cartões só dela ou apagar. Marcações e
     posição de leitura persistem no localStorage por documento (nome + tamanho).
     Só as páginas próximas do viewport são rasterizadas (janela de render). -->
<script>
// Registra o worker real do PDF.js (empacotado pelo Vite) ANTES do vue-pdf rodar:
// o fallback do vue-pdf é um worker em data-URI, que o Chromium bloqueia
// ("Failed to fetch dynamically imported module: data:..."). workerPort tem
// prioridade sobre workerSrc no PDF.js, então isso neutraliza o fallback.
import { GlobalWorkerOptions } from 'pdfjs-dist'
import PdfJsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker'

if (!GlobalWorkerOptions.workerPort) {
  GlobalWorkerOptions.workerPort = new PdfJsWorker()
}
</script>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import { VuePDF, usePDF } from '@tato30/vue-pdf'
import '@tato30/vue-pdf/style.css'

const props = defineProps({
  file: {
    type: File,
    required: true
  },
  // Bytes do PDF (lidos pelo wrapper). Passar dados em memória evita blob URLs,
  // que a CSP do backend bloqueia em connect-src.
  data: {
    type: Uint8Array,
    required: true
  },
  generating: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'selection-changed',
  'highlights-changed',
  'generate',
  'add-to-editor',
  'close'
])

// Respiro ao rolar até uma página (px de tela)
const SCROLL_MARGIN = 12
// Páginas rasterizadas além das visíveis (antes e depois)
const RENDER_MARGIN = 1
// Fallback A4 quando não é possível medir a página
const FALLBACK_SIZE = Object.freeze({ width: 595, height: 842 })

// ============================================================
// Identidade do documento + estado de leitura persistido
// ============================================================
const docKey = `${props.file.name}::${props.file.size}`
const READING_LS_KEY = 'green-deck.pdf-reading.v1'

let savedReading
try {
  savedReading = JSON.parse(localStorage.getItem(READING_LS_KEY) || '{}')[docKey] || null
} catch {
  savedReading = null
}

// ============================================================
// Carregamento do PDF
// ============================================================
const loadError = ref('')

// slice(): o PDF.js transfere o buffer para o worker (detach); a cópia preserva
// os bytes originais no wrapper para um eventual remount
const { pdf, pages } = usePDF(props.data.slice(), {
  onError: (e) => {
    loadError.value = e?.message || 'Falha ao carregar o PDF'
  }
})

const isReady = computed(() => !loadError.value && pages.value > 0)

// ============================================================
// Layout da rolagem contínua
// ============================================================
const scrollRef = ref(null)
const viewerRootRef = ref(null)

// Elementos das páginas (índice = página - 1). Array simples: é lido só fora do
// render, então não precisa (nem deve) ser reativo.
let slotEls = []
// Vira true quando a posição de leitura salva já foi aplicada
let restored = false
// Deslocamento e altura de cada página dentro da área de rolagem, em px de tela.
// Recalculado a cada mudança de layout (zoom, resize, painel abrindo).
let pageOffsets = []

function setSlotEl(el, index) {
  slotEls[index] = el || null
}

// Dimensões de cada página em scale = 1. Medidas de uma vez para que os
// espaços reservados tenham a altura certa antes de qualquer rasterização.
const pageSizes = ref([])
const layoutReady = computed(() => pageSizes.value.length > 0)

async function measurePages() {
  if (!pdf.value) return
  try {
    const doc = await pdf.value.promise
    const sizes = []
    for (let p = 1; p <= doc.numPages; p++) {
      const page = await doc.getPage(p)
      const vp = page.getViewport({ scale: 1 })
      sizes.push({ width: vp.width, height: vp.height })
    }
    slotEls = new Array(sizes.length).fill(null)
    pageSizes.value = sizes
  } catch {
    // Sem as medidas reais, assume A4 para todas as páginas
    const n = pages.value || 1
    slotEls = new Array(n).fill(null)
    pageSizes.value = Array.from({ length: n }, () => ({ ...FALLBACK_SIZE }))
  }
}

// Largura de referência para "ajustar à largura": a maior página do documento,
// para que nenhuma delas estoure a horizontal
const baseWidth = computed(() =>
  pageSizes.value.reduce((max, s) => Math.max(max, s.width), 0)
)

// Estilos memoizados: identidade estável evita repatch de style em todas as
// páginas a cada rolagem que muda a janela de render
const slotStyles = computed(() => {
  const s = scale.value || 1
  return pageSizes.value.map((size) => ({
    width: `${Math.round((size?.width || FALLBACK_SIZE.width) * s)}px`,
    height: `${Math.round((size?.height || FALLBACK_SIZE.height) * s)}px`
  }))
})

function rebuildLayout() {
  const holder = scrollRef.value
  if (!holder) return
  const base = holder.getBoundingClientRect().top - holder.scrollTop
  pageOffsets = pageSizes.value.map((_, i) => {
    const el = slotEls[i]
    return el ? el.getBoundingClientRect().top - base : 0
  })
}

// Página que contém um deslocamento vertical (busca binária nos offsets)
function pageAtOffset(y) {
  if (!pageOffsets.length) return 1
  let lo = 0
  let hi = pageOffsets.length - 1
  let ans = 0
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (pageOffsets[mid] <= y) {
      ans = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return ans + 1
}

// ============================================================
// Navegação de páginas (retoma da última página lida)
// ============================================================
const currentPage = ref(savedReading?.page || 1)
const visibleStart = ref(1)
const visibleEnd = ref(1)
const readProgress = ref(0)

function shouldRender(page) {
  return page >= visibleStart.value - RENDER_MARGIN && page <= visibleEnd.value + RENDER_MARGIN
}

function goToPage(p, smooth = true) {
  const total = pages.value || 1
  const target = Math.min(Math.max(1, Math.round(p) || 1), total)
  currentPage.value = target
  const holder = scrollRef.value
  const offset = pageOffsets[target - 1]
  if (!holder || offset == null) return
  holder.scrollTo({
    top: Math.max(0, offset - SCROLL_MARGIN),
    behavior: smooth ? 'smooth' : 'auto'
  })
}

function onPageInput(event) {
  goToPage(Number(event.target.value), false)
  event.target.value = String(currentPage.value)
}

function onKeydown(event) {
  if (event.target?.tagName === 'INPUT' || event.target?.tagName === 'TEXTAREA') return
  switch (event.key) {
    case 'ArrowRight':
    case 'PageDown':
      event.preventDefault()
      goToPage(currentPage.value + 1)
      break
    case 'ArrowLeft':
    case 'PageUp':
      event.preventDefault()
      goToPage(currentPage.value - 1)
      break
    case 'Home':
      event.preventDefault()
      goToPage(1)
      break
    case 'End':
      event.preventDefault()
      goToPage(pages.value)
      break
    case 'Escape':
      if (activeHighlightId.value) {
        event.preventDefault()
        deselectHighlight()
      }
      break
    case 'Delete':
    case 'Backspace':
      if (activeHighlightId.value) {
        event.preventDefault()
        removeHighlight(activeHighlightId.value)
      }
      break
    default: {
      // 1..4 marcam a seleção atual com a cor correspondente
      const idx = Number(event.key)
      if (lastSelection.value && idx >= 1 && idx <= HIGHLIGHT_COLORS.length) {
        event.preventDefault()
        markSelection(HIGHLIGHT_COLORS[idx - 1].key)
      }
    }
  }
}

// Rolagem: atualiza página atual, janela de render, progresso e as toolbars
let scrollRaf = 0

function onScroll() {
  if (scrollRaf) return
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = 0
    updateVisiblePages()
    updateFloatingPositions()
  })
}

function updateVisiblePages() {
  const holder = scrollRef.value
  if (!holder || !pageOffsets.length) return
  const top = holder.scrollTop
  const height = holder.clientHeight
  visibleStart.value = pageAtOffset(top)
  visibleEnd.value = pageAtOffset(top + height)
  // Página "atual" = a que ocupa o terço superior da janela (onde o olho está)
  const focus = pageAtOffset(top + height * 0.35)
  if (focus !== currentPage.value) currentPage.value = focus
  const max = holder.scrollHeight - height
  readProgress.value = max > 8 ? Math.min(100, Math.round((top / max) * 100)) : 100
}

// A página restaurada pode exceder o total (documento trocado de tamanho)
watch(pages, (total) => {
  if (total && currentPage.value > total) currentPage.value = total
})

// ============================================================
// Zoom / ajuste à largura / página escura
// ============================================================
const scale = ref(savedReading?.scale || 1)
const fitWidth = ref(savedReading?.fitWidth !== false)
const pageDark = ref(!!savedReading?.pageDark)

function applyFitWidth() {
  const holder = scrollRef.value
  // clientWidth 0 = viewer oculto (v-show) — não recalcular
  if (!baseWidth.value || !holder || !holder.clientWidth) return
  const target = Math.min(Math.max((holder.clientWidth - 40) / baseWidth.value, 0.4), 4)
  // Evita loop de rerender por diferenças mínimas
  if (Math.abs(target - scale.value) > 0.02) {
    scale.value = Math.round(target * 100) / 100
  }
}

function zoomIn() {
  fitWidth.value = false
  scale.value = Math.min(4, Math.round((scale.value + 0.15) * 100) / 100)
}

function zoomOut() {
  fitWidth.value = false
  scale.value = Math.max(0.4, Math.round((scale.value - 0.15) * 100) / 100)
}

function toggleFitWidth() {
  fitWidth.value = true
  applyFitWidth()
}

// Ctrl + roda do mouse = zoom (como leitores de PDF nativos)
function onWheel(event) {
  if (!event.ctrlKey) return
  event.preventDefault()
  if (event.deltaY < 0) zoomIn()
  else zoomOut()
}

// Ao mudar o zoom, mantém o ponto de leitura: guarda a distância até o topo da
// página atual e reaplica proporcionalmente depois do relayout
watch(scale, (val, old) => {
  const holder = scrollRef.value
  // Antes da restauração inicial não há posição a preservar (e os offsets
  // ainda estão zerados) — o primeiro "ajustar à largura" cai aqui
  if (!holder || !restored) return
  const page = currentPage.value
  const delta = holder.scrollTop - (pageOffsets[page - 1] ?? 0)
  const ratio = old ? val / old : 1
  nextTick(() => {
    rebuildLayout()
    const offset = pageOffsets[page - 1]
    if (offset != null) holder.scrollTop = Math.max(0, offset + delta * ratio)
    updateVisiblePages()
    updateFloatingPositions()
  })
})

let resizeObserver = null
let persistTimer = null

// Persiste posição de leitura, zoom e preferências por documento
function persistReading() {
  try {
    const all = JSON.parse(localStorage.getItem(READING_LS_KEY) || '{}')
    all[docKey] = {
      page: currentPage.value,
      scale: scale.value,
      fitWidth: fitWidth.value,
      pageDark: pageDark.value
    }
    localStorage.setItem(READING_LS_KEY, JSON.stringify(all))
  } catch {
    /* localStorage indisponível — sem persistência */
  }
}

// Debounce: currentPage agora muda a cada rolagem
watch([currentPage, scale, fitWidth, pageDark], () => {
  clearTimeout(persistTimer)
  persistTimer = setTimeout(persistReading, 400)
})

// ============================================================
// Busca no documento
// ============================================================
const searchOpen = ref(false)
const searchQuery = ref('')
const activeSearch = ref('') // termo confirmado (destacado nas páginas)
const searchPages = ref([]) // páginas que contêm o termo
const searchIdx = ref(-1)
const searching = ref(false)
const searchInputRef = ref(null)
let searchToken = 0

function toggleSearch() {
  searchOpen.value = !searchOpen.value
  if (searchOpen.value) {
    nextTick(() => searchInputRef.value?.focus())
  } else {
    closeSearch()
  }
}

// Chamado pelo Ctrl+F da página quando o PDF é o que está visível
function openSearch() {
  searchOpen.value = true
  nextTick(() => searchInputRef.value?.focus())
}

async function runSearch() {
  const term = searchQuery.value.trim()
  // Enter com o mesmo termo já buscado = próxima ocorrência
  if (term && term === activeSearch.value && searchPages.value.length) {
    stepSearch(1)
    return
  }
  activeSearch.value = term
  searchPages.value = []
  searchIdx.value = -1
  if (!term || !pdf.value) return

  const token = ++searchToken
  searching.value = true
  try {
    const docProxy = await pdf.value.promise
    const needle = term.toLowerCase()
    const found = []
    for (let p = 1; p <= docProxy.numPages; p++) {
      if (token !== searchToken) return // nova busca iniciada — aborta esta
      const page = await docProxy.getPage(p)
      const tc = await page.getTextContent()
      const text = tc.items.map((i) => i.str).join(' ').toLowerCase()
      if (text.includes(needle)) found.push(p)
    }
    if (token !== searchToken) return
    searchPages.value = found
    if (found.length) {
      searchIdx.value = 0
      goToPage(found[0])
    }
  } catch {
    /* falha na varredura — mantém estado vazio */
  } finally {
    if (token === searchToken) searching.value = false
  }
}

function stepSearch(dir) {
  const list = searchPages.value
  if (!list.length) return
  searchIdx.value = (searchIdx.value + dir + list.length) % list.length
  goToPage(list[searchIdx.value])
}

function closeSearch() {
  searchOpen.value = false
  searchQuery.value = ''
  activeSearch.value = ''
  searchPages.value = []
  searchIdx.value = -1
  searchToken++
  searching.value = false
}

const searchStatusLabel = computed(() => {
  if (searching.value) return 'Buscando...'
  if (!activeSearch.value) return ''
  if (!searchPages.value.length) return 'Nada encontrado'
  return `pág. ${searchIdx.value + 1} de ${searchPages.value.length} com ocorrências`
})

// ============================================================
// Páginas sem camada de texto (PDF digitalizado sem OCR)
// ============================================================
const pagesWithoutText = ref([])

function onTextLoaded(page) {
  nextTick(() => {
    const tl = slotEls[page - 1]?.querySelector('.textLayer')
    const empty = !tl || !(tl.textContent || '').trim().length
    const list = pagesWithoutText.value
    if (empty && !list.includes(page)) pagesWithoutText.value = [...list, page]
    else if (!empty && list.includes(page)) pagesWithoutText.value = list.filter((p) => p !== page)
  })
}

const currentPageHasNoText = computed(() => pagesWithoutText.value.includes(currentPage.value))

// ============================================================
// Seleção de texto + toolbar flutuante
// ============================================================
const selectedText = ref('')
const selToolbar = ref({ visible: false, x: 0, y: 0 })
const copied = ref(false)
// Snapshot da seleção no momento do mouseup: cliques na toolbar podem colapsar
// a seleção viva do browser, então "Marcar" usa este snapshot
const lastSelection = shallowRef(null) // { text, page, rects }
// Âncora em coordenadas da página (scale 1) — a toolbar acompanha a rolagem
const selAnchor = shallowRef(null) // { page, x, y }

function pageOfNode(node) {
  const el = node?.nodeType === 1 ? node : node?.parentElement
  const slot = el?.closest?.('[data-pdf-page]')
  return slot ? Number(slot.dataset.pdfPage) : 0
}

function onTextSelection() {
  // Aguarda o browser consolidar a seleção após o mouseup
  nextTick(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
      hideSelectionToolbar()
      return
    }
    const range = sel.getRangeAt(0)
    const page = pageOfNode(range.startContainer)
    if (!page) {
      hideSelectionToolbar()
      return
    }
    const text = sel.toString().replace(/\s+/g, ' ').trim()
    if (!text) {
      hideSelectionToolbar()
      return
    }

    deselectHighlight()
    selectedText.value = text
    const rects = selectionRects(range, page)
    lastSelection.value = { text, page, rects }
    emit('selection-changed', text)

    const last = rects[rects.length - 1]
    selAnchor.value = last
      ? { page, x: last.x + last.w / 2, y: last.y + last.h }
      : null
    updateFloatingPositions()
  })
}

function hideSelectionToolbar() {
  selToolbar.value = { ...selToolbar.value, visible: false }
  selAnchor.value = null
  // Sem toolbar não há mais o que marcar: descarta o snapshot para os
  // atalhos 1–4 não reaproveitarem uma seleção antiga
  lastSelection.value = null
  if (selectedText.value) {
    selectedText.value = ''
    emit('selection-changed', '')
  }
}

function clearSelectionState() {
  try {
    window.getSelection()?.removeAllRanges()
  } catch {
    /* seleção pode não existir */
  }
  lastSelection.value = null
  hideSelectionToolbar()
}

function onGenerateFromSelection() {
  if (!selectedText.value) return
  emit('generate', {
    text: selectedText.value,
    source: 'selection',
    label: 'Trecho selecionado no PDF'
  })
}

function onSendToEditor() {
  if (!selectedText.value) return
  emit('add-to-editor', selectedText.value)
  clearSelectionState()
}

async function copyText(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1400)
  } catch {
    /* clipboard indisponível (http) — sem fallback */
  }
}

// ============================================================
// Marcações (highlights) — 4 cores, persistidas por documento
// ============================================================
const HIGHLIGHTS_LS_KEY = 'green-deck.pdf-highlights.v1'

const HIGHLIGHT_COLORS = [
  { key: 'yellow', label: 'amarelo', bg: 'rgba(255, 205, 60, 0.34)', solid: '#f59e0b' },
  { key: 'green', label: 'verde', bg: 'rgba(74, 222, 128, 0.30)', solid: '#22c55e' },
  { key: 'blue', label: 'azul', bg: 'rgba(96, 165, 250, 0.30)', solid: '#3b82f6' },
  { key: 'pink', label: 'rosa', bg: 'rgba(244, 114, 182, 0.30)', solid: '#ec4899' }
]

function colorInfo(key) {
  return HIGHLIGHT_COLORS.find((c) => c.key === key) || HIGHLIGHT_COLORS[0]
}

const highlights = ref([]) // { id, page, text, color, rects: [{x,y,w,h}] } — rects em scale 1
const showHighlightsPanel = ref(false)
const colorFilter = ref('') // '' = todas as cores

const highlightsByPage = computed(() => {
  const map = new Map()
  for (const h of highlights.value) {
    const list = map.get(h.page)
    if (list) list.push(h)
    else map.set(h.page, [h])
  }
  return map
})

// Ordem de leitura: página e, dentro dela, posição vertical
const sortedHighlights = computed(() =>
  [...highlights.value].sort(
    (a, b) => a.page - b.page || (a.rects?.[0]?.y ?? 0) - (b.rects?.[0]?.y ?? 0)
  )
)

const usedColors = computed(() => {
  const keys = new Set(highlights.value.map((h) => h.color))
  return HIGHLIGHT_COLORS.filter((c) => keys.has(c.key))
})

const visibleHighlights = computed(() =>
  colorFilter.value
    ? sortedHighlights.value.filter((h) => h.color === colorFilter.value)
    : sortedHighlights.value
)

function loadHighlights() {
  try {
    const all = JSON.parse(localStorage.getItem(HIGHLIGHTS_LS_KEY) || '{}')
    highlights.value = Array.isArray(all[docKey]) ? all[docKey] : []
  } catch {
    highlights.value = []
  }
}

function persistHighlights() {
  try {
    const all = JSON.parse(localStorage.getItem(HIGHLIGHTS_LS_KEY) || '{}')
    if (highlights.value.length > 0) {
      all[docKey] = highlights.value
    } else {
      delete all[docKey]
    }
    localStorage.setItem(HIGHLIGHTS_LS_KEY, JSON.stringify(all))
  } catch {
    /* localStorage cheio/indisponível — marcações seguem em memória */
  }
}

function makeId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
}

function selectionRects(range, page) {
  const slot = slotEls[page - 1]
  const wrapRect = slot?.getBoundingClientRect()
  if (!wrapRect) return []
  const s = scale.value || 1
  const out = []
  const seen = new Set()
  for (const r of range.getClientRects()) {
    if (r.width < 2 || r.height < 2) continue
    // Seleção que atravessa páginas: guarda só a parte da página de origem
    const cy = r.top + r.height / 2
    if (cy < wrapRect.top - 2 || cy > wrapRect.bottom + 2) continue
    const rect = {
      x: Math.round(((r.left - wrapRect.left) / s) * 100) / 100,
      y: Math.round(((r.top - wrapRect.top) / s) * 100) / 100,
      w: Math.round((r.width / s) * 100) / 100,
      h: Math.round((r.height / s) * 100) / 100
    }
    const key = `${Math.round(rect.x)}:${Math.round(rect.y)}:${Math.round(rect.w)}:${Math.round(rect.h)}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(rect)
  }
  // Remove retângulos que englobam outros (duplicação de linhas da camada de texto)
  return out.filter(
    (a) =>
      !out.some(
        (b) =>
          b !== a &&
          b.x >= a.x - 1 &&
          b.y >= a.y - 1 &&
          b.x + b.w <= a.x + a.w + 2 &&
          b.y + b.h <= a.y + a.h + 2 &&
          b.w * b.h < a.w * a.h * 0.9
      )
  )
}

function markSelection(colorKey = 'yellow') {
  // Usa o snapshot: o clique no botão pode já ter colapsado a seleção viva
  const snap = lastSelection.value
  if (!snap || !snap.text || snap.rects.length === 0) return

  const id = makeId()
  highlights.value.push({
    id,
    page: snap.page,
    text: snap.text,
    color: colorKey,
    rects: snap.rects
  })
  clearSelectionState()
  // A marcação recém-criada já nasce selecionada, pronta para ajuste
  nextTick(() => selectHighlight(id))
}

function removeHighlight(id) {
  highlights.value = highlights.value.filter((h) => h.id !== id)
  if (activeHighlightId.value === id) deselectHighlight()
  if (editingId.value === id) editingId.value = ''
}

function clearAllHighlights() {
  highlights.value = []
  deselectHighlight()
  editingId.value = ''
  colorFilter.value = ''
}

function generateFromHighlights() {
  if (highlights.value.length === 0) return
  clearSelectionState()
  const { count, combined } = getHighlights()
  emit('generate', {
    text: combined,
    source: 'highlight',
    count,
    label: `${count} marcação${count > 1 ? 'ões' : ''} do PDF`
  })
}

function getHighlights() {
  const items = sortedHighlights.value
  return {
    count: items.length,
    combined: items.map((h) => h.text).join('\n\n'),
    items
  }
}

watch(
  highlights,
  () => {
    persistHighlights()
    emit('highlights-changed', highlights.value.length)
  },
  { deep: true }
)

// ============================================================
// Marcação como objeto: selecionar, editar, recolorir, apagar
// ============================================================
const activeHighlightId = ref('')
const hoverHighlightId = ref('')
const hlToolbar = ref({ visible: false, x: 0, y: 0 })
const editingId = ref('')
const editText = ref('')
const editInputRef = ref(null)
const panelListRef = ref(null)

const activeHighlight = computed(
  () => highlights.value.find((h) => h.id === activeHighlightId.value) || null
)

// Ponto do clique convertido para coordenadas da página em scale 1
function pointFromEvent(event) {
  const slot = event.target?.closest?.('[data-pdf-page]')
  if (!slot) return null
  const rect = slot.getBoundingClientRect()
  const s = scale.value || 1
  return {
    page: Number(slot.dataset.pdfPage),
    x: (event.clientX - rect.left) / s,
    y: (event.clientY - rect.top) / s
  }
}

// Hit-test manual: os retângulos ficam com pointer-events none para não
// atrapalhar a seleção de texto, então o clique é resolvido por geometria
function highlightAtPoint(pt) {
  const list = highlightsByPage.value.get(pt.page)
  if (!list) return null
  for (let i = list.length - 1; i >= 0; i--) {
    const h = list[i]
    const hit = h.rects?.some(
      (r) => pt.x >= r.x - 1 && pt.x <= r.x + r.w + 1 && pt.y >= r.y - 1 && pt.y <= r.y + r.h + 1
    )
    if (hit) return h
  }
  return null
}

function onPagesClick(event) {
  const sel = window.getSelection()
  // Seleção de texto tem prioridade sobre a seleção de marcação
  if (sel && !sel.isCollapsed && sel.toString().trim()) return
  const pt = pointFromEvent(event)
  const hit = pt ? highlightAtPoint(pt) : null
  if (hit) selectHighlight(hit.id)
  else deselectHighlight()
}

let hoverRaf = 0

function onPagesMouseMove(event) {
  if (hoverRaf) return
  const target = event.target
  const clientX = event.clientX
  const clientY = event.clientY
  hoverRaf = requestAnimationFrame(() => {
    hoverRaf = 0
    const pt = pointFromEvent({ target, clientX, clientY })
    hoverHighlightId.value = pt ? highlightAtPoint(pt)?.id || '' : ''
  })
}

function selectHighlight(id) {
  hideSelectionToolbar()
  activeHighlightId.value = id
  updateFloatingPositions()
}

function deselectHighlight() {
  activeHighlightId.value = ''
  hlToolbar.value = { ...hlToolbar.value, visible: false }
}

function focusHighlight(h) {
  activeHighlightId.value = h.id
  hideSelectionToolbar()
  const holder = scrollRef.value
  const offset = pageOffsets[h.page - 1]
  if (holder && offset != null) {
    const y = offset + (h.rects?.[0]?.y ?? 0) * scale.value
    holder.scrollTo({ top: Math.max(0, y - holder.clientHeight * 0.3), behavior: 'smooth' })
  }
  currentPage.value = h.page
}

function setHighlightColor(id, colorKey) {
  const h = highlights.value.find((x) => x.id === id)
  if (h) h.color = colorKey
}

function startEditHighlight(id) {
  const h = highlights.value.find((x) => x.id === id)
  if (!h) return
  showHighlightsPanel.value = true
  activeHighlightId.value = id
  editingId.value = id
  editText.value = h.text
  nextTick(() => {
    // ref dentro de v-for chega como array
    const el = Array.isArray(editInputRef.value) ? editInputRef.value[0] : editInputRef.value
    el?.focus?.()
    panelListRef.value
      ?.querySelector(`[data-hl-id="${id}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  })
}

function saveEditHighlight() {
  const h = highlights.value.find((x) => x.id === editingId.value)
  const text = editText.value.trim()
  if (h && text) h.text = text
  editingId.value = ''
}

function cancelEditHighlight() {
  editingId.value = ''
}

function onEditKeydown(event) {
  // Não deixa Esc/Delete chegarem aos atalhos do leitor
  event.stopPropagation()
  if (event.key === 'Escape') {
    event.preventDefault()
    cancelEditHighlight()
  } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    saveEditHighlight()
  }
}

function generateFromHighlight(h) {
  if (!h?.text) return
  clearSelectionState()
  emit('generate', {
    text: h.text,
    source: 'highlight',
    count: 1,
    label: `1 marcação do PDF (p. ${h.page})`
  })
}

function sendHighlightToEditor(h) {
  if (!h?.text) return
  emit('add-to-editor', h.text)
}

// ============================================================
// Posição das toolbars flutuantes (acompanham a rolagem e o zoom)
// ============================================================
function anchorToScreen(anchor) {
  const slot = slotEls[anchor.page - 1]
  const root = viewerRootRef.value
  if (!slot || !root) return null
  const sr = slot.getBoundingClientRect()
  const rr = root.getBoundingClientRect()
  const rawY = sr.top - rr.top + anchor.y * scale.value
  // Âncora rolou para fora da área visível — esconde em vez de grudar na borda
  if (rawY < 40 || rawY > rr.height - 16) return null
  const halfWidth = 150
  return {
    x: Math.min(
      Math.max(sr.left - rr.left + anchor.x * scale.value, halfWidth),
      Math.max(halfWidth, rr.width - halfWidth)
    ),
    y: Math.min(Math.max(rawY + 10, 52), rr.height - 56)
  }
}

function updateFloatingPositions() {
  const sel = selAnchor.value
  if (sel) {
    const pos = anchorToScreen(sel)
    selToolbar.value = pos ? { visible: true, ...pos } : { ...selToolbar.value, visible: false }
  } else if (selToolbar.value.visible) {
    selToolbar.value = { ...selToolbar.value, visible: false }
  }

  const h = activeHighlight.value
  const last = h?.rects?.[h.rects.length - 1]
  if (h && last) {
    const pos = anchorToScreen({ page: h.page, x: last.x + last.w / 2, y: last.y + last.h })
    hlToolbar.value = pos ? { visible: true, ...pos } : { ...hlToolbar.value, visible: false }
  } else if (hlToolbar.value.visible) {
    hlToolbar.value = { ...hlToolbar.value, visible: false }
  }
}

// ============================================================
// Ciclo de vida
// ============================================================
function restoreReadingPosition() {
  if (restored || !layoutReady.value) return
  const holder = scrollRef.value
  if (!holder || !holder.clientWidth) return // ainda oculto (v-show)
  restored = true
  rebuildLayout()
  if (savedReading?.page > 1) goToPage(savedReading.page, false)
  updateVisiblePages()
}

watch(pdf, measurePages, { immediate: true })

// Dois ticks: o primeiro rende os espaços das páginas, o segundo garante que
// um eventual reajuste de escala já está no DOM antes de medir os offsets
function relayoutAndRestore() {
  if (fitWidth.value) applyFitWidth()
  nextTick(() => {
    rebuildLayout()
    restoreReadingPosition()
    updateVisiblePages()
    updateFloatingPositions()
  })
}

watch(layoutReady, (ready) => {
  if (ready) nextTick(relayoutAndRestore)
})

onMounted(() => {
  loadHighlights()
  emit('highlights-changed', highlights.value.length)

  if (scrollRef.value) {
    resizeObserver = new ResizeObserver(relayoutAndRestore)
    resizeObserver.observe(scrollRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  if (hoverRaf) cancelAnimationFrame(hoverRaf)
  clearTimeout(persistTimer)
  persistReading()
})

defineExpose({
  getSelectedText: () => selectedText.value,
  getHighlights,
  clearSelection: clearSelectionState,
  goToPage,
  openSearch
})
</script>

<template>
  <div ref="viewerRootRef" class="pdf-study-viewer">
    <!-- Toolbar -->
    <div class="pdf-toolbar">
      <div class="pdf-toolbar-left" :title="file.name">
        <i class="pi pi-file-pdf pdf-file-icon" />
        <span class="pdf-file-name">{{ file.name }}</span>
      </div>

      <div class="pdf-toolbar-center">
        <Button
          icon="pi pi-angle-double-left"
          severity="secondary"
          text
          rounded
          size="small"
          :disabled="currentPage <= 1"
          title="Primeira página (Home)"
          aria-label="Primeira página"
          @click="goToPage(1)"
        />
        <Button
          icon="pi pi-angle-left"
          severity="secondary"
          text
          rounded
          size="small"
          :disabled="currentPage <= 1"
          title="Página anterior (←)"
          aria-label="Página anterior"
          @click="goToPage(currentPage - 1)"
        />
        <span class="pdf-page-indicator">
          <input
            class="pdf-page-input"
            type="text"
            inputmode="numeric"
            :value="currentPage"
            aria-label="Página atual"
            @change="onPageInput"
            @keydown.enter="onPageInput"
          />
          <span class="pdf-page-total">/ {{ pages || '–' }}</span>
        </span>
        <Button
          icon="pi pi-angle-right"
          severity="secondary"
          text
          rounded
          size="small"
          :disabled="currentPage >= pages"
          title="Próxima página (→)"
          aria-label="Próxima página"
          @click="goToPage(currentPage + 1)"
        />
        <Button
          icon="pi pi-angle-double-right"
          severity="secondary"
          text
          rounded
          size="small"
          :disabled="currentPage >= pages"
          title="Última página (End)"
          aria-label="Última página"
          @click="goToPage(pages)"
        />
      </div>

      <div class="pdf-toolbar-right">
        <Button
          icon="pi pi-search"
          severity="secondary"
          :text="!searchOpen"
          :outlined="searchOpen"
          rounded
          size="small"
          title="Buscar no documento"
          aria-label="Buscar no documento"
          @click="toggleSearch"
        />

        <span class="pdf-toolbar-sep" aria-hidden="true"></span>

        <Button
          icon="pi pi-search-minus"
          severity="secondary"
          text
          rounded
          size="small"
          title="Diminuir zoom (Ctrl + roda do mouse)"
          aria-label="Diminuir zoom"
          @click="zoomOut"
        />
        <span class="pdf-zoom-label">{{ Math.round(scale * 100) }}%</span>
        <Button
          icon="pi pi-search-plus"
          severity="secondary"
          text
          rounded
          size="small"
          title="Aumentar zoom (Ctrl + roda do mouse)"
          aria-label="Aumentar zoom"
          @click="zoomIn"
        />
        <Button
          icon="pi pi-arrows-h"
          severity="secondary"
          :text="!fitWidth"
          :outlined="fitWidth"
          rounded
          size="small"
          title="Ajustar à largura"
          aria-label="Ajustar à largura"
          @click="toggleFitWidth"
        />
        <Button
          :icon="pageDark ? 'pi pi-sun' : 'pi pi-moon'"
          severity="secondary"
          :text="!pageDark"
          :outlined="pageDark"
          rounded
          size="small"
          :title="pageDark ? 'Página clara (original)' : 'Página escura (conforto noturno)'"
          aria-label="Alternar página escura"
          @click="pageDark = !pageDark"
        />

        <span class="pdf-toolbar-sep" aria-hidden="true"></span>

        <span class="pdf-hl-btn-wrap">
          <Button
            icon="pi pi-bookmark"
            severity="secondary"
            :text="!showHighlightsPanel"
            :outlined="showHighlightsPanel"
            rounded
            size="small"
            title="Marcações"
            aria-label="Marcações"
            @click="showHighlightsPanel = !showHighlightsPanel"
          />
          <span v-if="highlights.length" class="pdf-hl-badge">{{ highlights.length }}</span>
        </span>

        <Button
          icon="pi pi-times"
          severity="secondary"
          text
          rounded
          size="small"
          title="Fechar PDF e voltar ao editor"
          aria-label="Fechar PDF"
          @click="emit('close')"
        />
      </div>
    </div>

    <!-- Barra de busca -->
    <Transition name="pdf-slide">
      <div v-if="searchOpen" class="pdf-searchbar">
        <i class="pi pi-search pdf-searchbar-icon" />
        <input
          ref="searchInputRef"
          v-model="searchQuery"
          class="pdf-search-input"
          type="text"
          placeholder="Buscar no documento... (Enter)"
          @keydown.enter="runSearch"
          @keydown.esc="toggleSearch"
        />
        <span v-if="searchStatusLabel" class="pdf-search-count">{{ searchStatusLabel }}</span>
        <Button
          icon="pi pi-chevron-up"
          severity="secondary"
          text
          rounded
          size="small"
          :disabled="!searchPages.length"
          title="Página anterior com ocorrências"
          aria-label="Ocorrência anterior"
          @click="stepSearch(-1)"
        />
        <Button
          icon="pi pi-chevron-down"
          severity="secondary"
          text
          rounded
          size="small"
          :disabled="!searchPages.length"
          title="Próxima página com ocorrências"
          aria-label="Próxima ocorrência"
          @click="stepSearch(1)"
        />
        <Button
          icon="pi pi-times"
          severity="secondary"
          text
          rounded
          size="small"
          title="Fechar busca (Esc)"
          aria-label="Fechar busca"
          @click="toggleSearch"
        />
      </div>
    </Transition>

    <!-- Progresso de leitura do documento -->
    <div v-if="isReady && layoutReady" class="pdf-progress" aria-hidden="true">
      <div class="pdf-progress-fill" :style="{ width: readProgress + '%' }"></div>
    </div>

    <!-- Área principal -->
    <div class="pdf-main">
      <!-- Página digitalizada sem camada de texto: nada para selecionar -->
      <Transition name="pdf-fade-plain">
        <div v-if="isReady && currentPageHasNoText" class="pdf-no-text-hint">
          <i class="pi pi-info-circle" />
          <span>
            Esta página não tem texto selecionável (PDF digitalizado).
            Use "Extrair Texto" no diálogo de documento para aplicar OCR.
          </span>
        </div>
      </Transition>

      <div
        ref="scrollRef"
        class="pdf-scroll"
        tabindex="0"
        @keydown="onKeydown"
        @mouseup="onTextSelection"
        @wheel="onWheel"
        @scroll="onScroll"
      >
        <div v-if="loadError" class="pdf-status pdf-error">
          <i class="pi pi-exclamation-circle" />
          <span>{{ loadError }}</span>
        </div>

        <div v-else-if="!isReady || !layoutReady" class="pdf-status">
          <i class="pi pi-spin pi-spinner" />
          <span>Carregando PDF...</span>
        </div>

        <!-- Rolagem contínua: todas as páginas existem no fluxo, mas só as
             próximas do viewport são rasterizadas -->
        <div
          v-show="isReady && layoutReady"
          class="pdf-pages"
          :class="{ 'page-dark': pageDark, 'is-hl-hover': !!hoverHighlightId }"
          @click="onPagesClick"
          @mousemove="onPagesMouseMove"
          @mouseleave="hoverHighlightId = ''"
        >
          <div
            v-for="(_size, i) in pageSizes"
            :key="i"
            :ref="(el) => setSlotEl(el, i)"
            class="pdf-page-slot"
            :data-pdf-page="i + 1"
            :style="slotStyles[i]"
          >
            <span class="pdf-page-ph">{{ i + 1 }}</span>

            <div v-if="shouldRender(i + 1)" class="pdf-page-canvas">
              <VuePDF
                :pdf="pdf"
                :page="i + 1"
                :scale="scale"
                text-layer
                :highlight-text="activeSearch || null"
                :highlight-options="{ completeWords: false, ignoreCase: true }"
                @text-loaded="onTextLoaded(i + 1)"
              />
            </div>

            <!-- Camada de marcações da página -->
            <div class="pdf-highlight-layer" aria-hidden="true">
              <template v-for="h in highlightsByPage.get(i + 1) || []" :key="h.id">
                <div
                  v-for="(r, ri) in h.rects"
                  :key="h.id + '-' + ri"
                  class="pdf-highlight-rect"
                  :class="{
                    'is-active': h.id === activeHighlightId,
                    'is-hover': h.id === hoverHighlightId
                  }"
                  :style="{
                    left: r.x * scale + 'px',
                    top: r.y * scale + 'px',
                    width: r.w * scale + 'px',
                    height: r.h * scale + 'px',
                    background: colorInfo(h.color).bg,
                    '--hl-solid': colorInfo(h.color).solid
                  }"
                ></div>
              </template>
            </div>

            <span class="pdf-page-badge">{{ i + 1 }}</span>
          </div>
        </div>
      </div>

      <!-- Painel de marcações -->
      <Transition name="pdf-panel">
        <aside v-if="showHighlightsPanel" class="pdf-highlights-panel">
          <div class="pdf-hl-head">
            <span class="pdf-hl-title">
              <i class="pi pi-bookmark" />
              Marcações
              <span v-if="highlights.length" class="pdf-hl-count">{{ highlights.length }}</span>
            </span>
            <span v-if="highlights.length" class="pdf-hl-head-actions">
              <Button
                :icon="copied ? 'pi pi-check' : 'pi pi-copy'"
                severity="secondary"
                text
                rounded
                size="small"
                :title="copied ? 'Copiado!' : 'Copiar todas as marcações'"
                aria-label="Copiar todas as marcações"
                @click="copyText(getHighlights().combined)"
              />
              <Button
                icon="pi pi-trash"
                severity="secondary"
                text
                rounded
                size="small"
                title="Limpar todas as marcações"
                aria-label="Limpar todas"
                @click="clearAllHighlights"
              />
            </span>
          </div>

          <div v-if="usedColors.length > 1" class="pdf-hl-filters">
            <button
              type="button"
              class="pdf-hl-filter"
              :class="{ 'is-on': !colorFilter }"
              title="Todas as cores"
              @click="colorFilter = ''"
            >
              todas
            </button>
            <button
              v-for="c in usedColors"
              :key="c.key"
              type="button"
              class="pdf-hl-filter is-dot"
              :class="{ 'is-on': colorFilter === c.key }"
              :style="{ '--hl-solid': c.solid }"
              :title="'Só as marcações em ' + c.label"
              :aria-label="'Filtrar por ' + c.label"
              @click="colorFilter = colorFilter === c.key ? '' : c.key"
            ></button>
          </div>

          <div v-if="!highlights.length" class="pdf-hl-empty">
            Selecione um trecho no PDF e toque numa das <strong>cores</strong> do balão
            — ou tecle <strong>1–4</strong> — para guardá-lo aqui. Depois é só clicar
            na marcação na página para editar, recolorir ou apagar.
          </div>

          <div v-else ref="panelListRef" class="pdf-hl-list">
            <div
              v-for="h in visibleHighlights"
              :key="h.id"
              class="pdf-hl-item"
              :class="{ 'is-active': h.id === activeHighlightId }"
              :data-hl-id="h.id"
              role="button"
              tabindex="0"
              :style="{ borderLeftColor: colorInfo(h.color).solid }"
              :title="'Ir para a marcação (página ' + h.page + ')'"
              @click="focusHighlight(h)"
              @keydown.enter="focusHighlight(h)"
            >
              <div class="pdf-hl-item-head">
                <Tag class="pdf-hl-page-tag" severity="secondary">p. {{ h.page }}</Tag>
                <div class="pdf-hl-item-actions">
                  <Button
                    icon="pi pi-pencil"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    title="Editar o texto da marcação"
                    aria-label="Editar marcação"
                    @click.stop="startEditHighlight(h.id)"
                  />
                  <Button
                    icon="pi pi-bolt"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    :disabled="generating"
                    title="Gerar cartões só desta marcação"
                    aria-label="Gerar desta marcação"
                    @click.stop="generateFromHighlight(h)"
                  />
                  <Button
                    icon="pi pi-times"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    title="Remover marcação"
                    aria-label="Remover marcação"
                    @click.stop="removeHighlight(h.id)"
                  />
                </div>
              </div>

              <template v-if="editingId === h.id">
                <textarea
                  ref="editInputRef"
                  v-model="editText"
                  class="pdf-hl-edit"
                  rows="4"
                  aria-label="Texto da marcação"
                  @click.stop
                  @keydown="onEditKeydown"
                ></textarea>
                <div class="pdf-hl-edit-actions" @click.stop>
                  <span class="pdf-hl-edit-colors">
                    <button
                      v-for="c in HIGHLIGHT_COLORS"
                      :key="c.key"
                      type="button"
                      class="pdf-color-dot is-sm"
                      :class="{ 'is-on': h.color === c.key }"
                      :style="{ background: c.solid }"
                      :title="'Mudar para ' + c.label"
                      :aria-label="'Mudar para ' + c.label"
                      @click="setHighlightColor(h.id, c.key)"
                    ></button>
                  </span>
                  <Button
                    label="Cancelar"
                    severity="secondary"
                    text
                    size="small"
                    @click="cancelEditHighlight"
                  />
                  <Button label="Salvar" size="small" @click="saveEditHighlight" />
                </div>
              </template>

              <p v-else class="pdf-hl-text">
                {{ h.text.length > 160 ? h.text.slice(0, 160) + '…' : h.text }}
              </p>
            </div>
          </div>

          <div v-if="highlights.length" class="pdf-hl-footer">
            <Button
              icon="pi pi-bolt"
              :label="`Gerar dos marcados (${highlights.length})`"
              size="small"
              :disabled="generating"
              @click="generateFromHighlights"
            />
          </div>
        </aside>
      </Transition>
    </div>

    <!-- Toolbar flutuante de seleção -->
    <!-- mousedown.prevent: sem isso o clique colapsa a seleção do browser
         antes do handler do botão rodar -->
    <Transition name="pdf-fade">
      <div
        v-if="selToolbar.visible"
        class="pdf-sel-toolbar"
        :style="{ left: selToolbar.x + 'px', top: selToolbar.y + 'px' }"
        @mousedown.prevent
        @mouseup.stop
        @click.stop
      >
        <button
          type="button"
          class="pdf-sel-btn is-primary"
          :disabled="generating"
          title="Gerar cartões a partir da seleção"
          @click="onGenerateFromSelection"
        >
          <i class="pi pi-bolt" />
          <span>Gerar cartões</span>
        </button>

        <span class="pdf-sel-colors" role="group" aria-label="Marcar com cor">
          <button
            v-for="(c, ci) in HIGHLIGHT_COLORS"
            :key="c.key"
            type="button"
            class="pdf-color-dot"
            :style="{ background: c.solid }"
            :title="`Marcar em ${c.label} (${ci + 1})`"
            :aria-label="'Marcar em ' + c.label"
            @click="markSelection(c.key)"
          ></button>
        </span>

        <button
          type="button"
          class="pdf-sel-btn"
          title="Adicionar o trecho ao editor de texto"
          @click="onSendToEditor"
        >
          <i class="pi pi-file-edit" />
          <span>Editor</span>
        </button>
        <button
          type="button"
          class="pdf-sel-btn is-icon"
          :title="copied ? 'Copiado!' : 'Copiar seleção'"
          @click="copyText(selectedText)"
        >
          <i :class="copied ? 'pi pi-check' : 'pi pi-copy'" />
        </button>
      </div>
    </Transition>

    <!-- Toolbar flutuante da marcação selecionada -->
    <Transition name="pdf-fade">
      <div
        v-if="hlToolbar.visible && activeHighlight"
        class="pdf-sel-toolbar is-hl"
        :style="{ left: hlToolbar.x + 'px', top: hlToolbar.y + 'px' }"
        @mousedown.prevent
        @mouseup.stop
        @click.stop
      >
        <span class="pdf-sel-colors" role="group" aria-label="Cor da marcação">
          <button
            v-for="c in HIGHLIGHT_COLORS"
            :key="c.key"
            type="button"
            class="pdf-color-dot"
            :class="{ 'is-on': activeHighlight.color === c.key }"
            :style="{ background: c.solid }"
            :title="'Mudar para ' + c.label"
            :aria-label="'Mudar para ' + c.label"
            @click="setHighlightColor(activeHighlight.id, c.key)"
          ></button>
        </span>

        <span class="pdf-sel-sep" aria-hidden="true"></span>

        <button
          type="button"
          class="pdf-sel-btn is-primary"
          :disabled="generating"
          title="Gerar cartões desta marcação"
          @click="generateFromHighlight(activeHighlight)"
        >
          <i class="pi pi-bolt" />
          <span>Gerar</span>
        </button>
        <button
          type="button"
          class="pdf-sel-btn"
          title="Adicionar o trecho ao editor de texto"
          @click="sendHighlightToEditor(activeHighlight)"
        >
          <i class="pi pi-file-edit" />
          <span>Editor</span>
        </button>
        <button
          type="button"
          class="pdf-sel-btn is-icon"
          title="Editar o texto da marcação"
          aria-label="Editar marcação"
          @click="startEditHighlight(activeHighlight.id)"
        >
          <i class="pi pi-pencil" />
        </button>
        <button
          type="button"
          class="pdf-sel-btn is-icon"
          :title="copied ? 'Copiado!' : 'Copiar marcação'"
          aria-label="Copiar marcação"
          @click="copyText(activeHighlight.text)"
        >
          <i :class="copied ? 'pi pi-check' : 'pi pi-copy'" />
        </button>
        <button
          type="button"
          class="pdf-sel-btn is-icon is-danger"
          title="Apagar marcação (Delete)"
          aria-label="Apagar marcação"
          @click="removeHighlight(activeHighlight.id)"
        >
          <i class="pi pi-trash" />
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.pdf-study-viewer {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  overflow: hidden;
  background: var(--app-card);
}

/* ---------- Toolbar ---------- */
.pdf-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--panel-head-border);
  background: var(--panel-head-bg);
  flex: 0 0 auto;
  min-width: 0;
}

.pdf-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1 1 auto;
}

.pdf-file-icon {
  color: var(--color-danger);
  font-size: var(--icon-md, 15px);
  flex-shrink: 0;
}

.pdf-file-name {
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  color: var(--app-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pdf-toolbar-center,
.pdf-toolbar-right {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 0 0 auto;
}

.pdf-page-indicator {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  margin: 0 2px;
}

.pdf-page-input {
  width: 38px;
  padding: 2px 4px;
  text-align: center;
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  color: var(--app-text);
  background: var(--sidebar-icon-bg, rgba(148, 163, 184, 0.12));
  border: 1px solid var(--app-border);
  border-radius: 6px;
  outline: none;
}

.pdf-page-input:focus {
  border-color: var(--color-primary);
}

.pdf-page-total {
  font-size: var(--fs-xs, 12px);
  color: var(--app-text-muted);
  white-space: nowrap;
}

.pdf-zoom-label {
  min-width: 40px;
  text-align: center;
  font-size: var(--fs-2xs, 11px);
  font-weight: 600;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}

.pdf-toolbar-sep {
  width: 1px;
  height: 18px;
  background: var(--app-border);
  margin: 0 4px;
}

.pdf-hl-btn-wrap {
  position: relative;
  display: inline-flex;
}

.pdf-hl-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
  color: #fff;
  background: var(--color-warning);
  border-radius: 999px;
  pointer-events: none;
}

/* ---------- Barra de busca ---------- */
.pdf-searchbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-bottom: 1px solid var(--panel-head-border);
  background: var(--panel-head-bg);
  flex: 0 0 auto;
}

.pdf-searchbar-icon {
  color: var(--app-text-muted);
  font-size: var(--icon-sm, 13px);
  flex-shrink: 0;
}

.pdf-search-input {
  flex: 1;
  min-width: 0;
  padding: 4px 8px;
  font-size: var(--fs-xs, 12px);
  color: var(--app-text);
  background: var(--sidebar-icon-bg, rgba(148, 163, 184, 0.12));
  border: 1px solid var(--app-border);
  border-radius: 8px;
  outline: none;
}

.pdf-search-input:focus {
  border-color: var(--color-primary);
}

.pdf-search-input::placeholder {
  color: var(--app-text-muted);
}

.pdf-search-count {
  font-size: var(--fs-2xs, 11px);
  color: var(--app-text-muted);
  white-space: nowrap;
}

/* ---------- Progresso de leitura ---------- */
.pdf-progress {
  height: 2px;
  flex: 0 0 auto;
  background: var(--app-border);
}

.pdf-progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.12s linear;
}

/* ---------- Área do PDF ---------- */
.pdf-main {
  display: flex;
  flex: 1;
  min-height: 0;
  position: relative;
}

.pdf-no-text-hint {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 15;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: min(92%, 560px);
  padding: 7px 12px;
  border-radius: 10px;
  background: linear-gradient(180deg, var(--sidebar-popup-bg-start), var(--sidebar-popup-bg-end));
  border: 1px solid rgba(245, 158, 11, 0.55);
  color: var(--sidebar-popup-text);
  font-size: var(--fs-2xs, 11px);
  line-height: 1.4;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
  pointer-events: none;
}

.pdf-no-text-hint i {
  color: var(--color-warning);
  font-size: var(--icon-md, 15px);
  flex-shrink: 0;
}

.pdf-scroll {
  position: relative;
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 16px 16px 28px;
  outline: none;
  scroll-behavior: auto;
  overscroll-behavior: contain;
}

.pdf-scroll::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.pdf-scroll::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--app-text-muted) 32%, transparent);
  border: 3px solid transparent;
  background-clip: content-box;
  border-radius: 999px;
}

.pdf-scroll::-webkit-scrollbar-thumb:hover {
  background: color-mix(in srgb, var(--app-text-muted) 55%, transparent);
  background-clip: content-box;
}

.pdf-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 100%;
  color: var(--app-text-muted);
  font-size: var(--fs-sm, 13px);
}

.pdf-status i {
  font-size: var(--icon-lg, 18px);
}

.pdf-error {
  color: var(--color-danger);
}

/* ---------- Rolagem contínua ---------- */
.pdf-pages {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  min-width: max-content;
}

.pdf-page-slot {
  position: relative;
  flex: 0 0 auto;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.18);
  overflow: hidden;
}

/* Número da página no espaço reservado (aparece enquanto rasteriza) */
.pdf-page-ph {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  font-weight: 700;
  color: rgba(15, 23, 42, 0.12);
  user-select: none;
}

.pdf-page-canvas {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
}

/* Etiqueta discreta com o número da página, útil na rolagem contínua */
.pdf-page-badge {
  position: absolute;
  right: 8px;
  bottom: 8px;
  z-index: 4;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: rgba(15, 23, 42, 0.45);
  opacity: 0;
  transition: opacity 0.15s ease;
  pointer-events: none;
}

.pdf-page-slot:hover .pdf-page-badge {
  opacity: 1;
}

/* Página escura: inverte o canvas para leitura noturna (texto claro, fundo escuro) */
.pdf-pages.page-dark .pdf-page-slot {
  background: #16181f;
}

.pdf-pages.page-dark .pdf-page-ph {
  color: rgba(226, 232, 240, 0.14);
}

.pdf-pages.page-dark :deep(canvas) {
  filter: invert(0.92) hue-rotate(180deg);
}

/* Camada de texto do PDF.js: cor de seleção mais visível */
.pdf-pages :deep(.textLayer) ::selection {
  background: rgba(59, 130, 246, 0.35);
}

/* Cursor de "objeto clicável" quando o ponteiro está sobre uma marcação */
.pdf-pages.is-hl-hover,
.pdf-pages.is-hl-hover :deep(.textLayer),
.pdf-pages.is-hl-hover :deep(.textLayer span) {
  cursor: pointer;
}

/* ---------- Marcações sobre a página ---------- */
.pdf-highlight-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 3;
}

.pdf-highlight-rect {
  position: absolute;
  border-radius: 2px;
  transition: box-shadow 0.12s ease, filter 0.12s ease;
}

.pdf-highlight-rect.is-hover {
  filter: brightness(1.15) saturate(1.2);
  box-shadow: 0 0 0 1px var(--hl-solid);
}

.pdf-highlight-rect.is-active {
  box-shadow: 0 0 0 2px var(--hl-solid), 0 2px 10px rgba(0, 0, 0, 0.18);
  filter: brightness(1.12) saturate(1.25);
}

/* ---------- Painel de marcações ---------- */
.pdf-highlights-panel {
  display: flex;
  flex-direction: column;
  width: 250px;
  flex: 0 0 auto;
  min-height: 0;
  border-left: 1px solid var(--app-border);
  background: var(--app-bg-soft);
}

.pdf-hl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid var(--app-border);
  flex: 0 0 auto;
}

.pdf-hl-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs, 12px);
  font-weight: 700;
  color: var(--app-text);
}

.pdf-hl-title i {
  color: var(--color-warning);
  font-size: var(--icon-sm, 13px);
}

.pdf-hl-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 0;
}

.pdf-hl-count {
  padding: 0 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  color: var(--app-text-muted);
  background: var(--sidebar-icon-bg, rgba(148, 163, 184, 0.16));
}

.pdf-hl-filters {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--app-border);
  flex: 0 0 auto;
}

.pdf-hl-filter {
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 700;
  color: var(--app-text-muted);
  background: transparent;
  border: 1px solid var(--app-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.pdf-hl-filter:hover {
  color: var(--app-text);
}

.pdf-hl-filter.is-on {
  color: var(--app-text);
  border-color: var(--color-primary);
}

.pdf-hl-filter.is-dot {
  width: 16px;
  height: 16px;
  padding: 0;
  border-radius: 50%;
  border: 2px solid transparent;
  background: var(--hl-solid);
  opacity: 0.55;
}

.pdf-hl-filter.is-dot.is-on {
  opacity: 1;
  border-color: var(--app-text);
}

.pdf-hl-empty {
  padding: 14px 12px;
  font-size: var(--fs-xs, 12px);
  line-height: 1.5;
  color: var(--app-text-muted);
}

.pdf-hl-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pdf-hl-item {
  padding: 6px 8px;
  border: 1px solid var(--app-border);
  border-left: 3px solid #f59e0b;
  border-radius: 8px;
  background: var(--app-card);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}

.pdf-hl-item:hover {
  background: var(--app-hover);
}

.pdf-hl-item.is-active {
  background: var(--app-hover);
  box-shadow: 0 0 0 1px var(--color-primary);
}

.pdf-hl-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.pdf-hl-item-actions {
  display: inline-flex;
  align-items: center;
  gap: 0;
  opacity: 0.55;
  transition: opacity 0.15s ease;
}

.pdf-hl-item:hover .pdf-hl-item-actions,
.pdf-hl-item.is-active .pdf-hl-item-actions {
  opacity: 1;
}

.pdf-hl-page-tag {
  font-size: var(--fs-2xs, 11px);
  padding: 1px 6px;
}

.pdf-hl-text {
  margin: 4px 0 0;
  font-size: var(--fs-2xs, 11px);
  line-height: 1.45;
  color: var(--app-text-muted);
  word-break: break-word;
}

.pdf-hl-edit {
  width: 100%;
  margin-top: 6px;
  padding: 6px 8px;
  font: inherit;
  font-size: var(--fs-2xs, 11px);
  line-height: 1.45;
  color: var(--app-text);
  background: var(--app-bg-soft);
  border: 1px solid var(--color-primary);
  border-radius: 6px;
  resize: vertical;
  outline: none;
}

.pdf-hl-edit-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 6px;
}

.pdf-hl-edit-colors {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-right: auto;
}

.pdf-hl-footer {
  padding: 8px 10px;
  border-top: 1px solid var(--app-border);
  flex: 0 0 auto;
}

.pdf-hl-footer :deep(.p-button) {
  width: 100%;
  justify-content: center;
}

/* ---------- Toolbars flutuantes ---------- */
.pdf-sel-toolbar {
  position: absolute;
  transform: translateX(-50%);
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
  background: linear-gradient(180deg, var(--sidebar-popup-bg-start), var(--sidebar-popup-bg-end));
  border: 1px solid var(--sidebar-popup-border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.32);
}

.pdf-sel-toolbar.is-hl {
  border-color: color-mix(in srgb, var(--color-primary) 45%, var(--sidebar-popup-border));
}

.pdf-sel-sep {
  width: 1px;
  height: 18px;
  background: var(--sidebar-popup-border);
  margin: 0 3px;
}

.pdf-sel-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  font-size: var(--fs-2xs, 11px);
  font-weight: 600;
  color: var(--sidebar-popup-text);
  background: transparent;
  border: none;
  border-radius: 7px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}

.pdf-sel-btn i {
  font-size: var(--icon-sm, 13px);
}

.pdf-sel-btn:hover:not(:disabled) {
  background: var(--sidebar-popup-hover);
}

.pdf-sel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pdf-sel-btn.is-primary {
  color: #fff;
  background: #28ca73;
}

.pdf-sel-btn.is-primary:hover:not(:disabled) {
  background: #22b866;
}

.pdf-sel-btn.is-icon {
  padding: 5px 7px;
}

.pdf-sel-btn.is-danger:hover:not(:disabled) {
  color: #fff;
  background: var(--color-danger);
}

.pdf-sel-colors {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 7px;
}

.pdf-color-dot {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.85);
  border-radius: 50%;
  padding: 0;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.pdf-color-dot:hover {
  transform: scale(1.25);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.25);
}

.pdf-color-dot.is-on {
  box-shadow: 0 0 0 2px var(--app-text);
}

.pdf-color-dot.is-sm {
  width: 13px;
  height: 13px;
  border-width: 1px;
}

/* ---------- Transições ---------- */
.pdf-fade-enter-active,
.pdf-fade-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.pdf-fade-enter-from,
.pdf-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}

.pdf-fade-plain-enter-active,
.pdf-fade-plain-leave-active {
  transition: opacity 0.15s ease;
}

.pdf-fade-plain-enter-from,
.pdf-fade-plain-leave-to {
  opacity: 0;
}

.pdf-slide-enter-active,
.pdf-slide-leave-active {
  transition: opacity 0.15s ease;
}

.pdf-slide-enter-from,
.pdf-slide-leave-to {
  opacity: 0;
}

.pdf-panel-enter-active,
.pdf-panel-leave-active {
  transition: width 0.18s ease, opacity 0.18s ease;
  overflow: hidden;
}

.pdf-panel-enter-from,
.pdf-panel-leave-to {
  width: 0;
  opacity: 0;
}

/* ---------- Responsivo (dentro do painel do editor) ---------- */
@container editor-panel (max-width: 700px) {
  .pdf-file-name {
    display: none;
  }

  .pdf-sel-btn span {
    display: none;
  }
}

@container editor-panel (max-width: 540px) {
  .pdf-highlights-panel {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 20;
    box-shadow: -8px 0 24px rgba(0, 0, 0, 0.18);
  }

  .pdf-zoom-label {
    display: none;
  }
}
</style>
