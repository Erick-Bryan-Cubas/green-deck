<!-- frontend/src/pages/BrowserPage.vue -->
<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

// PrimeVue
import Toolbar from 'primevue/toolbar'
import Button from 'primevue/button'
import Select from 'primevue/select'
import MultiSelect from 'primevue/multiselect'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import InputSwitch from 'primevue/inputswitch'
import Slider from 'primevue/slider'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import Toast from 'primevue/toast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Divider from 'primevue/divider'
import Textarea from 'primevue/textarea'
import ProgressBar from 'primevue/progressbar'
import Popover from 'primevue/popover'
import { useToast } from 'primevue/usetoast'

// App components
import AnkiStatus from '@/components/AnkiStatus.vue'
import OllamaStatus from '@/components/OllamaStatus.vue'
import SidebarMenu from '@/components/SidebarMenu.vue'

// API service
import { getStoredApiKeys } from '@/services/api.js'

const router = useRouter()
const route = useRoute()
const toast = useToast()

// Sidebar ref
const sidebarRef = ref(null)

// ============================================================
// Sidebar Menu Items
// ============================================================
const sidebarMenuItems = computed(() => [
  { key: 'generator', label: 'Generator', icon: 'pi pi-bolt', iconColor: '#10B981', tooltip: 'Gerar flashcards', command: () => router.push('/') },
  { key: 'browser', label: 'Browser', icon: 'pi pi-database', iconColor: '#3B82F6', tooltip: 'Navegar pelos cards salvos', active: true },
  { key: 'dashboard', label: 'Dashboard', icon: 'pi pi-chart-bar', iconColor: '#F59E0B', tooltip: 'Estatísticas de estudo', command: () => router.push('/dashboard') },
  { separator: true },
  { key: 'logs', label: 'Logs', icon: 'pi pi-wave-pulse', iconColor: '#EF4444', tooltip: 'Ver registros do sistema', command: () => { logsVisible.value = true } }
])

const sidebarFooterActions = computed(() => [
  { icon: 'pi pi-question-circle', tooltip: 'Ajuda', command: () => notify('Documentação em breve!', 'info') },
  { icon: 'pi pi-moon', tooltip: 'Tema', command: () => notify('Tema alternativo em breve!', 'info') }
])

// ----------------------
// Toast + Logs
// ----------------------
function notify(message, severity = 'info', life = 3200) {
  toast.add({ severity, summary: message, life })
}

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

// ----------------------
// helpers
// ----------------------
function deckQuerySafe(deckName) {
  return String(deckName || '').replaceAll('"', '\\"')
}

function queueLabel(q) {
  const m = {
    0: 'New',
    1: 'Learning',
    2: 'Review (Aprendido)',
    3: 'Relearning',
    '-1': 'Suspended',
    '-2': 'Buried',
    '-3': 'Buried (Manual)'
  }
  return m[String(q)] || String(q)
}

function queueSeverity(q) {
  switch (Number(q)) {
    case 2:
      return 'success'
    case 1:
      return 'warn'
    case 0:
      return 'info'
    case 3:
      return 'danger'
    case -1:
      return 'danger'
    case -2:
    case -3:
      return 'secondary'
    default:
      return 'secondary'
  }
}

function flagLabel(f) {
  const m = { 0: '—', 1: 'Red', 2: 'Orange', 3: 'Green', 4: 'Blue' }
  return m[String(f)] || String(f)
}
function flagClass(f) {
  const n = Number(f)
  if (n === 1) return 'flag-red'
  if (n === 2) return 'flag-orange'
  if (n === 3) return 'flag-green'
  if (n === 4) return 'flag-blue'
  return 'flag-none'
}

// noteId robusto (cardsInfo pode vir com noteId ou note)
function noteIdOf(row) {
  const raw = row?.noteId ?? row?.note ?? row?.note_id ?? row?.noteID
  const n = Number(raw)
  if (!Number.isFinite(n)) return null
  return n
}
function isSuspendedRow(row) {
  return Number(row?.queue) === -1
}

// Lê JSON de forma segura e detecta “200 mas HTML”
async function readJsonSafe(resp) {
  const ct = (resp.headers.get('content-type') || '').toLowerCase()
  if (!ct.includes('application/json')) {
    const text = await resp.text().catch(() => '')
    const head = text.slice(0, 220).replace(/\s+/g, ' ').trim()
    return { __nonJson: true, __contentType: ct || '(no content-type)', __head: head }
  }
  try {
    return await resp.json()
  } catch (e) {
    return { __jsonParseError: true, __message: e?.message || String(e) }
  }
}

function ms(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return `${v}ms`
}

function summarizeResults(results = []) {
  const bad = results.filter((x) => x && x.success === false)
  const byStage = {}
  for (const r of bad) {
    const st = String(r.stage || 'unknown')
    byStage[st] = (byStage[st] || 0) + 1
  }
  const lines = Object.entries(byStage)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${k}=${v}`)
  return {
    totalFailedItems: bad.length,
    stageSummary: lines.join(' | '),
    firstErrors: bad.slice(0, 6).map((r) => {
      const base = `stage=${r.stage || 'unknown'} model=${r.modelName || '—'} note=${r.oldNoteId || '—'}`
      const err = (r.error || '').toString().slice(0, 220)
      return `${base} :: ${err}`
    })
  }
}

// ----------------------
// Service status (Anki / Ollama)
// ----------------------
const ankiHealth = ref({ ok: null, error: '', ankiConnectVersion: null })

// backend novo retorna required.{easy_or_neutral,hard_technical}
const ollamaHealth = ref({
  ok: null,
  error: '',
  timeoutS: null,
  modelsCount: null,
  required: null
})

let healthTimer = null

async function fetchHealth() {
  // Anki
  try {
    const r = await fetch('/api/health/anki')
    const data = await readJsonSafe(r)
    if (data?.__nonJson) throw new Error(`non-JSON: ${data.__head}`)
    ankiHealth.value = { ok: !!data.ok, error: data.error || '', ankiConnectVersion: data.ankiConnectVersion ?? null }
  } catch (e) {
    ankiHealth.value = { ok: false, error: e?.message || String(e), ankiConnectVersion: null }
  }

  // Ollama
  try {
    const r = await fetch('/api/health/ollama')
    const data = await readJsonSafe(r)
    if (data?.__nonJson) throw new Error(`non-JSON: ${data.__head}`)
    ollamaHealth.value = {
      ok: !!data.ok,
      error: data.error || '',
      timeoutS: data.timeoutS ?? null,
      modelsCount: data.modelsCount ?? null,
      required: data.required ?? null
    }
  } catch (e) {
    ollamaHealth.value = { ok: false, error: e?.message || String(e), timeoutS: null, modelsCount: null, required: null }
  }
}

const ankiStatusTitle = computed(() => {
  if (ankiHealth.value.ok) return `AnkiConnect OK (version=${ankiHealth.value.ankiConnectVersion})`
  if (ankiHealth.value.ok === null) return 'AnkiConnect: verificando...'
  return `AnkiConnect OFF: ${ankiHealth.value.error || 'erro desconhecido'}`
})

// ----------------------
// filtros / estado
// ----------------------
const decks = ref([])
const deck = ref('')
const status = ref('is:review')
const text = ref('')
const advancedQuery = ref('')

const statusOptions = [
  { label: 'Aprendidos (Review)', value: 'is:review' },
  { label: 'Novos', value: 'is:new' },
  { label: 'Aprendendo (Learning)', value: 'is:learn' },
  { label: 'Suspensos', value: 'is:suspended' },
  { label: 'Enterrados', value: 'is:buried' },
  { label: 'Todos', value: '' }
]

// Query helper popover
const queryHelpRef = ref(null)

const queryHelpers = [
  { category: 'Status', items: [
    { query: 'is:due', desc: 'Cards para revisar hoje' },
    { query: 'is:new', desc: 'Cards novos (nunca estudados)' },
    { query: 'is:review', desc: 'Cards em revisão (aprendidos)' },
    { query: 'is:learn', desc: 'Cards em aprendizagem' },
    { query: 'is:suspended', desc: 'Cards suspensos' },
    { query: 'is:buried', desc: 'Cards enterrados' }
  ]},
  { category: 'Deck e Modelo', items: [
    { query: 'deck:"Nome do Deck"', desc: 'Filtrar por deck específico' },
    { query: 'deck:current', desc: 'Deck atual selecionado' },
    { query: '"deck:Pai::Filho"', desc: 'Deck com subdecks (hierarquia)' },
    { query: 'note:"Basic"', desc: 'Filtrar por tipo de nota' },
    { query: 'card:1', desc: 'Apenas o primeiro card de cada nota' }
  ]},
  { category: 'Tags', items: [
    { query: 'tag:minhatag', desc: 'Cards com tag específica' },
    { query: '-tag:minhatag', desc: 'Cards SEM essa tag' },
    { query: 'tag:none', desc: 'Cards sem nenhuma tag' }
  ]},
  { category: 'Datas', items: [
    { query: 'added:1', desc: 'Adicionados hoje' },
    { query: 'added:7', desc: 'Adicionados nos últimos 7 dias' },
    { query: 'edited:3', desc: 'Editados nos últimos 3 dias' },
    { query: 'rated:1', desc: 'Revisados hoje' },
    { query: 'rated:7:1', desc: 'Marcados "Again" nos últimos 7 dias' }
  ]},
  { category: 'Intervalos', items: [
    { query: 'prop:ivl>=30', desc: 'Intervalo >= 30 dias' },
    { query: 'prop:ivl<7', desc: 'Intervalo < 7 dias' },
    { query: 'prop:due=0', desc: 'Vence hoje' },
    { query: 'prop:due>0', desc: 'Vence no futuro' },
    { query: 'prop:ease<2.0', desc: 'Ease factor < 200%' },
    { query: 'prop:lapses>3', desc: 'Mais de 3 lapsos' }
  ]},
  { category: 'Conteúdo', items: [
    { query: '"texto exato"', desc: 'Busca texto exato' },
    { query: 'front:palavra', desc: 'Busca no campo Front' },
    { query: 're:\\d{4}', desc: 'Regex: 4 dígitos' },
    { query: 'nc:palavra', desc: 'Busca case-insensitive' }
  ]},
  { category: 'Flags', items: [
    { query: 'flag:1', desc: 'Flag vermelha' },
    { query: 'flag:2', desc: 'Flag laranja' },
    { query: 'flag:3', desc: 'Flag verde' },
    { query: 'flag:4', desc: 'Flag azul' },
    { query: 'flag:0', desc: 'Sem flag' }
  ]},
  { category: 'Combinações', items: [
    { query: 'is:due is:review', desc: 'Reviews para hoje (AND)' },
    { query: '(is:new OR is:learn)', desc: 'Novos OU aprendendo' },
    { query: '-is:suspended', desc: 'Excluir suspensos' }
  ]}
]

function insertQuery(query) {
  const current = advancedQuery.value.trim()
  advancedQuery.value = current ? `${current} ${query}` : query
  queryHelpRef.value?.hide()
}

const deckSelectOptions = computed(() => [{ label: 'Todos os decks', value: '' }, ...decks.value.map((d) => ({ label: d, value: d }))])
const deckTargetOptions = computed(() => [{ label: 'Deck original', value: '' }, ...decks.value.map((d) => ({ label: d, value: d }))])

const queryBuilt = computed(() => {
  const adv = advancedQuery.value.trim()
  if (adv) return adv

  const parts = []
  if (deck.value) parts.push(`deck:"${deckQuerySafe(deck.value)}"`)
  if (status.value) parts.push(status.value)
  if (text.value.trim()) parts.push(text.value.trim())

  return parts.length ? parts.join(' ') : 'is:review'
})

// ----------------------
// paginação / dados / ordenação
// ----------------------
const loading = ref(true)  // Start with loading to avoid flash
const initializing = ref(true)  // Flag to skip watch during URL param setup
const items = ref([])
const total = ref(0)
const first = ref(0)
const rows = ref(50)

// Ordenação local (aplicada aos dados carregados)
const sortField = ref(null)
const sortOrder = ref(null)

// Dados ordenados (ordenação client-side pois API do Anki não suporta sort)
const sortedItems = computed(() => {
  if (!sortField.value || sortOrder.value === null) {
    return items.value
  }

  const field = sortField.value
  const order = sortOrder.value // 1 = asc, -1 = desc

  return [...items.value].sort((a, b) => {
    let valA = a[field]
    let valB = b[field]

    // Handle null/undefined
    if (valA == null && valB == null) return 0
    if (valA == null) return order
    if (valB == null) return -order

    // Numeric comparison for known numeric fields
    const numericFields = ['interval', 'factor', 'reps', 'lapses', 'queue', 'flags', 'cardId', 'noteId']
    if (numericFields.includes(field)) {
      valA = Number(valA) || 0
      valB = Number(valB) || 0
      return (valA - valB) * order
    }

    // String comparison (case-insensitive)
    valA = String(valA).toLowerCase()
    valB = String(valB).toLowerCase()
    return valA.localeCompare(valB) * order
  })
})

function onSort(event) {
  sortField.value = event.sortField
  sortOrder.value = event.sortOrder
}

// seleção + preview
const selected = ref([])
const previewVisible = ref(false)
const previewCard = ref(null)

function openPreview(row) {
  previewCard.value = row
  previewVisible.value = true
}

// ----------------------
// API (decks/cards)
// ----------------------
async function fetchDecks() {
  addLog('Fetching decks...', 'info')
  try {
    const r = await fetch('/api/anki-decks')
    const data = await readJsonSafe(r)

    if (data?.__nonJson) {
      addLog(`Decks: non-JSON response (ct=${data.__contentType}) head="${data.__head}"`, 'error')
      notify('API /anki-decks não retornou JSON.', 'error', 8000)
      decks.value = []
      return
    }
    if (!data?.success) {
      addLog(`Decks error: ${data?.error || 'unknown'}`, 'warn')
      notify(data?.error || 'Falha ao buscar decks', 'warn', 6000)
      decks.value = []
      return
    }

    decks.value = Array.isArray(data.decks) ? data.decks : []
    addLog(`Decks loaded: ${decks.value.length}`, 'success')
  } catch (e) {
    addLog(`Decks fetch exception: ${e?.message || String(e)}`, 'error')
    notify(e?.message || String(e), 'warn', 6000)
    decks.value = []
  }
}

async function fetchCards() {
  loading.value = true
  const offset = first.value
  const limit = rows.value
  const built = queryBuilt.value

  addLog(`Fetching cards: q="${built}" offset=${offset} limit=${limit}`, 'info')

  try {
    const url = `/api/anki-cards?query=${encodeURIComponent(built)}&offset=${offset}&limit=${limit}`
    const r = await fetch(url)
    const data = await readJsonSafe(r)

    if (data?.__nonJson) {
      addLog(`Cards: non-JSON response (ct=${data.__contentType}) head="${data.__head}"`, 'error')
      notify('API /anki-cards não retornou JSON.', 'error', 8500)
      items.value = []
      total.value = 0
      return
    }
    if (data?.__jsonParseError) {
      addLog(`Cards: JSON parse error: ${data.__message}`, 'error')
      notify('Falha ao ler JSON do backend.', 'error', 7000)
      items.value = []
      total.value = 0
      return
    }
    if (data?.success === false) {
      addLog(`Cards error: ${data?.error || 'unknown'}`, 'error')
      notify(data?.error || 'Falha ao buscar cards', 'error', 7000)
      items.value = []
      total.value = 0
      return
    }

    const list = Array.isArray(data?.items) ? data.items : []
    const tot = Number.isFinite(Number(data?.total)) ? Number(data.total) : list.length

    items.value = list
    total.value = tot
    addLog(`Cards loaded: ${list.length} / total=${tot}`, 'success')
  } catch (e) {
    addLog(`Cards fetch exception: ${e?.message || String(e)}`, 'error')
    notify(e?.message || String(e), 'error', 7000)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

// Debounce filtros (skip during initialization to avoid flash)
let debounce = null
watch([deck, status, text, advancedQuery], () => {
  if (initializing.value) return  // Skip during URL param setup
  first.value = 0
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(fetchCards, 450)
})

function onPage(e) {
  first.value = e.first
  rows.value = e.rows
  fetchCards()
}

// Refresh completo: decks + cards
async function refreshAll() {
  addLog('Refreshing all data...', 'info')
  await Promise.all([fetchDecks(), fetchCards()])
  notify('Dados atualizados', 'success', 2500)
}

// ----------------------
// Note Actions (suspend / unsuspend / edit)
// ----------------------
const noteActionDialogVisible = ref(false)
const noteActionLoading = ref(false)
const noteActionType = ref('') // 'suspend' | 'unsuspend'
const noteActionRow = ref(null)

const noteActionTitle = computed(() => {
  if (noteActionType.value === 'unsuspend') return 'Desuspender nota'
  return 'Suspender nota'
})

function openNoteAction(row, type) {
  const nid = noteIdOf(row)
  if (nid === null) {
    notify('noteId não encontrado para este item.', 'warn', 5200)
    addLog(`Note action blocked: missing noteId for cardId=${row?.cardId}`, 'warn')
    return
  }
  noteActionRow.value = row
  noteActionType.value = type
  noteActionDialogVisible.value = true
}

async function confirmNoteAction() {
  const row = noteActionRow.value
  const nid = noteIdOf(row)
  if (nid === null) return

  const suspend = noteActionType.value === 'suspend'
  noteActionLoading.value = true
  const startedAt = performance.now()

  try {
    addLog(`Note action start: ${suspend ? 'suspend' : 'unsuspend'} noteId=${nid}`, 'info')

    const r = await fetch('/api/anki-note-suspend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ noteId: nid, suspend })
    })

    const data = await readJsonSafe(r)
    const elapsed = Math.round(performance.now() - startedAt)

    if (data?.__nonJson) {
      addLog(`Note action: non-JSON response head="${data.__head}"`, 'error')
      notify('API /anki-note-suspend não retornou JSON.', 'error', 9000)
      return
    }
    if (data?.__jsonParseError) {
      addLog(`Note action: JSON parse error: ${data.__message}`, 'error')
      notify('Falha ao ler JSON do backend.', 'error', 9000)
      return
    }
    if (r.status >= 400 || data?.success === false) {
      const msg = data?.error || `Falha ao ${suspend ? 'suspender' : 'desuspender'} (HTTP ${r.status}).`
      addLog(`Note action error: ${msg}`, 'error')
      notify(msg, 'error', 9000)
      return
    }

    const totalCards = Number(data?.totalCards || 0)
    addLog(`Note action OK: noteId=${nid} cards=${totalCards} elapsed=${elapsed}ms`, 'success')
    notify(`${suspend ? 'Suspensa' : 'Desuspensa'}: noteId ${nid} (${totalCards} cards)`, 'success', 6000)

    noteActionDialogVisible.value = false
    await fetchCards()
  } catch (e) {
    addLog(`Note action exception: ${e?.message || String(e)}`, 'error')
    notify(e?.message || String(e), 'error', 9000)
  } finally {
    noteActionLoading.value = false
  }
}

// -------- Edit Note --------
const editDialogVisible = ref(false)
const editLoading = ref(false)
const editSaving = ref(false)
const editRow = ref(null)
const editFields = ref([]) // [{order,name,value}]
const editTags = ref([])

const editNoteId = computed(() => noteIdOf(editRow.value))
const editMeta = computed(() => {
  const r = editRow.value || {}
  return {
    cardId: r?.cardId ?? '—',
    noteId: editNoteId.value ?? '—',
    deckName: r?.deckName ?? '—',
    modelName: r?.modelName ?? '—'
  }
})

async function openEditDialog(row) {
  const nid = noteIdOf(row)
  if (nid === null) {
    notify('noteId não encontrado para este item.', 'warn', 5200)
    addLog(`Edit blocked: missing noteId for cardId=${row?.cardId}`, 'warn')
    return
  }

  editRow.value = row
  editDialogVisible.value = true
  editLoading.value = true
  editFields.value = []
  editTags.value = []

  try {
    const url = `/api/anki-note-info?noteId=${encodeURIComponent(String(nid))}`
    const r = await fetch(url)
    const data = await readJsonSafe(r)

    if (data?.__nonJson) {
      addLog(`Note info: non-JSON head="${data.__head}"`, 'error')
      notify('API /anki-note-info não retornou JSON.', 'error', 9000)
      return
    }
    if (data?.__jsonParseError) {
      addLog(`Note info: JSON parse error: ${data.__message}`, 'error')
      notify('Falha ao ler JSON do backend.', 'error', 9000)
      return
    }
    if (r.status >= 400 || data?.success === false) {
      const msg = data?.error || `Falha ao buscar note info (HTTP ${r.status}).`
      addLog(`Note info error: ${msg}`, 'error')
      notify(msg, 'error', 9000)
      return
    }

    const note = data?.note || {}
    const fieldsOrdered = Array.isArray(note?.fieldsOrdered) ? note.fieldsOrdered : []
    editFields.value = fieldsOrdered.map((f) => ({
      order: Number(f?.order ?? 9999),
      name: String(f?.name ?? ''),
      value: String(f?.value ?? '')
    }))
    editTags.value = Array.isArray(note?.tags) ? note.tags : []

    addLog(`Note info loaded: noteId=${nid} fields=${editFields.value.length}`, 'success')
  } catch (e) {
    addLog(`Note info exception: ${e?.message || String(e)}`, 'error')
    notify(e?.message || String(e), 'error', 9000)
  } finally {
    editLoading.value = false
  }
}

function editFieldsMap() {
  const out = {}
  for (const f of editFields.value || []) {
    if (f?.name) out[String(f.name)] = String(f.value ?? '')
  }
  return out
}

async function saveNoteEdits() {
  const nid = editNoteId.value
  if (nid === null) return

  editSaving.value = true
  const startedAt = performance.now()

  try {
    const payload = { noteId: nid, fields: editFieldsMap() }
    addLog(`Note update start: noteId=${nid} fields=${Object.keys(payload.fields).length}`, 'info')

    const r = await fetch('/api/anki-note-update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const data = await readJsonSafe(r)
    const elapsed = Math.round(performance.now() - startedAt)

    if (data?.__nonJson) {
      addLog(`Note update: non-JSON head="${data.__head}"`, 'error')
      notify('API /anki-note-update não retornou JSON.', 'error', 9000)
      return
    }
    if (data?.__jsonParseError) {
      addLog(`Note update: JSON parse error: ${data.__message}`, 'error')
      notify('Falha ao ler JSON do backend.', 'error', 9000)
      return
    }
    if (r.status >= 400 || data?.success === false) {
      const msg = data?.error || `Falha ao atualizar nota (HTTP ${r.status}).`
      addLog(`Note update error: ${msg}`, 'error')
      notify(msg, 'error', 9000)
      return
    }

    addLog(`Note update OK: noteId=${nid} elapsed=${elapsed}ms`, 'success')
    notify('Nota atualizada no Anki.', 'success', 5200)

    editDialogVisible.value = false
    await fetchCards()
  } catch (e) {
    addLog(`Note update exception: ${e?.message || String(e)}`, 'error')
    notify(e?.message || String(e), 'error', 9000)
  } finally {
    editSaving.value = false
  }
}

// ----------------------
// Note Types (com suporte vindo do backend)
// ----------------------
const noteTypesVisible = ref(false)
const noteTypesLoaded = ref(false)
const noteTypes = ref([]) // [{name, supported, family, supportLabel}]
const supportedNoteTypes = computed(() => noteTypes.value.filter((x) => !!x.supported))
const supportedCount = computed(() => supportedNoteTypes.value.length)

const noteTypeOptions = computed(() =>
  noteTypes.value.map((x) => ({
    label: `${x.name} — ${x.supportLabel}`,
    value: x.name,
    disabled: !x.supported
  }))
)

async function fetchNoteTypes() {
  addLog('Fetching note types...', 'info')
  try {
    const r = await fetch('/api/anki-note-types')
    const data = await readJsonSafe(r)

    if (data?.__nonJson) {
      addLog(`Note types: non-JSON response head="${data.__head}"`, 'error')
      notify('API /anki-note-types não retornou JSON.', 'error', 8000)
      return
    }
    if (!data?.success) {
      addLog(`Note types error: ${data?.error || 'unknown'}`, 'error')
      notify(data?.error || 'Falha ao buscar Note Types', 'error', 6500)
      return
    }

    noteTypes.value = Array.isArray(data.items) ? data.items : []
    noteTypesLoaded.value = true
    addLog(`Note types loaded: ${noteTypes.value.length}`, 'success')
  } catch (e) {
    addLog(`Note types exception: ${e?.message || String(e)}`, 'error')
    notify(e?.message || String(e), 'error', 7000)
  }
}

function openNoteTypesDialog() {
  noteTypesVisible.value = true
  if (!noteTypesLoaded.value) fetchNoteTypes()
}

// ----------------------
// Modal Translate (Tradução via LLM)
// ----------------------
const translateDialogVisible = ref(false)
const translating = ref(false)

// Progress tracking
const translateProgress = ref(0)
const translateCurrent = ref(0)
const translateTotal = ref(0)
const translateStatus = ref('')  // 'preparing' | 'translating' | 'done' | 'error'
const translateLastNoteStatus = ref('')  // 'success' | 'failed' | 'skipped'

// Progress modal (mostrado durante tradução)
const translateProgressVisible = ref(false)
const translateTranslatedCount = ref(0)
const translateFailedCount = ref(0)
const translateSkippedCount = ref(0)
const translateLastError = ref('')
let translateAbortController = null

// Language detection
const translateDetectingLanguages = ref(false)
const translateAlreadyPtCount = ref(0)
const translateNeedsTranslationCount = ref(0)
const translateDetectError = ref('')
const translateUseEntireDeck = ref(false)

// Model selection for translation
const translateAvailableModels = ref([])
const translateSelectedModel = ref('')
const translateLoadingModels = ref(false)

// Computed: only LLM models (not embedding)
const translateLlmModels = computed(() => translateAvailableModels.value.filter(m => m.type !== 'embedding'))

async function detectCardLanguages() {
  const deckName = deck.value
  const cardIds = selected.value?.map(x => x.cardId) || []
  
  if (!deckName && !cardIds.length) {
    translateDetectError.value = 'Nenhum deck ou cartão selecionado'
    return
  }

  translateDetectingLanguages.value = true
  translateDetectError.value = ''
  translateAlreadyPtCount.value = 0
  translateNeedsTranslationCount.value = 0

  try {
    const payload = translateUseEntireDeck.value 
      ? { deckName }
      : { cardIds }

    const resp = await fetch('/api/detect-card-languages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!resp.ok) {
      const err = await resp.json()
      throw new Error(err.error || `HTTP ${resp.status}`)
    }

    const data = await resp.json()
    if (data.success) {
      translateAlreadyPtCount.value = data.alreadyPortuguese || 0
      translateNeedsTranslationCount.value = data.needsTranslation || 0
      const totalNotes = data.totalNotes || 0
      const ptPercentage = data.summary?.pt_percentage || 0
      addLog(
        `Detectado: ${data.alreadyPortuguese}/${totalNotes} em português (${ptPercentage}%). ${data.needsTranslation} precisam tradução.`,
        'info'
      )
    } else {
      throw new Error(data.error || 'Erro ao detectar idiomas')
    }
  } catch (e) {
    translateDetectError.value = e?.message || String(e)
    addLog(`Erro na detecção: ${translateDetectError.value}`, 'error')
  } finally {
    translateDetectingLanguages.value = false
  }
}

async function fetchTranslateModels() {
  try {
    translateLoadingModels.value = true
    const keys = getStoredApiKeys()

    const headers = {}
    if (keys.openaiApiKey) headers['X-OpenAI-Key'] = keys.openaiApiKey
    if (keys.perplexityApiKey) headers['X-Perplexity-Key'] = keys.perplexityApiKey

    const resp = await fetch('/api/all-models', { headers })
    if (resp.ok) {
      const data = await resp.json()
      translateAvailableModels.value = data.models || []

      // Set default model if not set
      if (!translateSelectedModel.value && translateLlmModels.value.length > 0) {
        // Prefer gpt-4o or claude if available, otherwise first LLM
        const preferred = translateLlmModels.value.find(m =>
          m.name.includes('gpt-4o') || m.name.includes('claude')
        )
        translateSelectedModel.value = preferred?.name || translateLlmModels.value[0].name
      }
    }
  } catch (e) {
    addLog(`Erro ao carregar modelos: ${e?.message || String(e)}`, 'error')
  } finally {
    translateLoadingModels.value = false
  }
}


async function openTranslateDialog() {
  if (!selected.value?.length && !deck.value) {
    notify('Selecione cartões ou um deck para traduzir.', 'warn', 4200)
    return
  }
  
  // Reset state
  translateUseEntireDeck.value = false
  translateAlreadyPtCount.value = 0
  translateNeedsTranslationCount.value = 0
  translateDetectError.value = ''
  
  translateDialogVisible.value = true
  fetchTranslateModels()
  
  // Auto-detect languages se houver cards selecionados
  if (selected.value?.length) {
    setTimeout(() => detectCardLanguages(), 500)
  }
}

function cancelTranslate() {
  if (translateAbortController) {
    translateAbortController.abort()
    translateAbortController = null
    translateLastError.value = 'Tradução cancelada pelo usuário'
    addLog('Tradução cancelada', 'warn')
    translating.value = false
  }
}

async function confirmTranslate() {
  if (!selected.value?.length && !translateUseEntireDeck.value) {
    notify('Selecione cartões ou ative "Traduzir deck inteiro".', 'warn', 4200)
    return
  }

  // Reset progress state
  translating.value = true
  translateDialogVisible.value = false
  translateProgressVisible.value = true
  translateProgress.value = 0
  translateCurrent.value = 0
  translateTotal.value = 0
  translateTranslatedCount.value = 0
  translateFailedCount.value = 0
  translateSkippedCount.value = 0
  translateStatus.value = 'preparing'
  translateLastNoteStatus.value = ''
  translateLastError.value = ''
  translateAbortController = new AbortController()

  const startedAt = performance.now()

  try {
    await fetchHealth()
    addLog(
      `Health: Anki=${ankiHealth.value.ok ? 'ON' : 'OFF'}`,
      ankiHealth.value.ok ? 'info' : 'warn'
    )

    const cardIds = translateUseEntireDeck.value ? [] : selected.value.map((x) => x.cardId)
    const keys = getStoredApiKeys()
    const model = translateSelectedModel.value || null

    const payload = {
      cardIds,
      ...(translateUseEntireDeck.value && { deckName: deck.value }),
      targetLanguage: 'pt-br',
      model,
      openaiApiKey: keys.openaiApiKey || null,
      perplexityApiKey: keys.perplexityApiKey || null,
      anthropicApiKey: keys.anthropicApiKey || null
    }

    const sourceName = translateUseEntireDeck.value ? `deck "${deck.value}"` : `${cardIds.length} cards`
    addLog(`Tradução iniciada: ${sourceName} | modelo=${model || 'default'} idioma=pt-br`, 'info')

    const response = await fetch('/api/anki-translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: translateAbortController.signal
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    // Process SSE stream
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let finalResult = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // Process complete event blocks (separated by double newline)
      let parts = buffer.split('\n\n')
      buffer = parts.pop() // keep incomplete tail

      for (const part of parts) {
        const lines = part.split('\n')
        let event = 'message'
        let data = ''
        for (const line of lines) {
          if (line.startsWith('event:')) event = line.replace('event:', '').trim()
          else if (line.startsWith('data:')) data += line.replace('data:', '').trim()
        }

        try {
          const parsed = data ? JSON.parse(data) : null

          if (event === 'start' && parsed) {
            translateTotal.value = parsed.totalNotes || 0
            translateStatus.value = 'translating'
            addLog(`Tradução iniciada: ${parsed.totalNotes} notas | provider=${parsed.provider} model=${parsed.model}`, 'info')
          } else if (event === 'progress' && parsed) {
            translateCurrent.value = parsed.current || 0
            translateTotal.value = parsed.total || translateTotal.value
            translateProgress.value = parsed.percent || 0
            translateLastNoteStatus.value = parsed.status || ''

            if (parsed.status === 'success') {
              translateTranslatedCount.value++
            } else if (parsed.status === 'failed') {
              translateFailedCount.value++
              translateLastError.value = parsed.error || 'Erro desconhecido'
              addLog(`[${parsed.current}/${parsed.total}] Nota ${parsed.noteId} falhou: ${parsed.error || 'erro'}`, 'warn')
            } else if (parsed.status === 'skipped') {
              translateSkippedCount.value++
              addLog(`[${parsed.current}/${parsed.total}] Nota ${parsed.noteId} pulada: ${parsed.message || 'sem texto'}`, 'info')
            }
          } else if (event === 'result' && parsed) {
            finalResult = parsed
            translateStatus.value = 'done'
            translateProgress.value = 100
          } else if (event === 'error' && parsed) {
            translateStatus.value = 'error'
            translateLastError.value = parsed.error || 'Erro desconhecido'
            throw new Error(parsed.error || 'Translation failed')
          }
        } catch (parseErr) {
          if (event === 'error') throw parseErr
          // Ignore JSON parse errors for intermediate events
        }
      }
    }

    const elapsed = Math.round(performance.now() - startedAt)

    if (!finalResult) {
      throw new Error('Nenhum resultado recebido do stream de tradução')
    }

    const requestId = finalResult.requestId || '—'
    addLog(`Tradução concluída: requestId=${requestId} tempo=${elapsed}ms`, 'info')

    if (finalResult.timings) {
      addLog(
        `Tempos: cardsInfo=${ms(finalResult.timings.cardsInfoMs)} notesInfo=${ms(finalResult.timings.notesInfoMs)} total=${ms(finalResult.timings.totalMs)} média=${ms(finalResult.timings.avgPerNoteMs)}/nota`,
        'info'
      )
    }

    const translated = Number(finalResult.translated || 0)
    const failed = Number(finalResult.failed || 0)
    const notes = Number(finalResult.totalNotes || 0)

    addLog(`Resultado final: notas=${notes} traduzidas=${translated} falhas=${failed}`, failed ? 'warn' : 'success')

    if (translated > 0 && failed === 0) {
      notify(`✓ Traduzidos: ${translated} de ${notes} notas.`, 'success', 6500)
    } else if (translated > 0 && failed > 0) {
      notify(`⚠ Traduzidos: ${translated} (falhas: ${failed})`, 'warn', 7500)
    } else if (failed > 0) {
      notify(`✕ Falha na tradução: ${failed} notas`, 'error', 7500)
    } else {
      notify(`→ Nenhuma nota para traduzir`, 'info', 5000)
    }

    // Keep progress modal open por 1.5s para mostrar conclusão
    await new Promise(resolve => setTimeout(resolve, 1500))
    translateProgressVisible.value = false
    await fetchCards()
  } catch (e) {
    if (e.name === 'AbortError') {
      translateStatus.value = 'cancelled'
      addLog('Tradução cancelada pelo usuário', 'warn')
    } else {
      translateStatus.value = 'error'
      translateLastError.value = e?.message || String(e)
      addLog(`Erro na tradução: ${e?.message || String(e)}`, 'error')
      notify(e?.message || String(e), 'error', 8000)
    }
  } finally {
    translating.value = false
    translateAbortController = null
  }
}

// ----------------------
// Modal Recreate (SLM/Ollama + APIs)
// ----------------------
const recreating = ref(false)
const recreateTargetDeck = ref('')

const recreateDialogVisible = ref(false)
const recreateSuspendOriginal = ref(true)
const recreateCountPerNote = ref(1)

// Seleção de modelo/provider
const recreateAvailableModels = ref([])
const recreateSelectedModel = ref('qwen-flashcard')
const recreateLoadingModels = ref(false)

// Dificuldade (opcional)
const recreateUseDifficulty = ref(false)
const difficultyOptions = [
  { label: 'Fácil', value: 'easy' },
  { label: 'Difícil (neutra)', value: 'hard_neutral' },
  { label: 'Difícil (técnica)', value: 'hard_technical' }
]
const recreateDifficulty = ref('easy')

// Prompts customizados
const recreateUseCustomPrompts = ref(false)
const recreateCustomSystemPrompt = ref('')
const recreateCustomGenerationPrompt = ref('')
const recreateCustomGuidelines = ref('')

// Prompts padrão (carregados da API)
const defaultPrompts = ref({
  system: { basic: '', cloze: '' },
  generation: { default: '' },
  guidelines: { default: '' }
})

// Computed para modelos LLM (excluindo embeddings)
const recreateLlmModels = computed(() => recreateAvailableModels.value.filter(m => m.type !== 'embedding'))

// Helper para info do modelo selecionado
function getRecreateModelInfo(modelName) {
  return recreateAvailableModels.value.find(m => m.name === modelName)
}

// Computed para determinar provider do modelo selecionado
const recreateModelProvider = computed(() => {
  const model = getRecreateModelInfo(recreateSelectedModel.value)
  return model?.provider || 'ollama'
})

// Helpers para severity/label do provider
function getProviderSeverity(provider) {
  if (provider === 'ollama') return 'success'
  if (provider === 'openai') return 'info'
  if (provider === 'anthropic') return 'contrast'
  return 'warning' // perplexity
}

function getProviderLabel(provider) {
  if (provider === 'ollama') return 'Ollama'
  if (provider === 'openai') return 'OpenAI'
  if (provider === 'anthropic') return 'Anthropic'
  return 'Perplexity'
}

// Buscar modelos disponíveis
async function fetchRecreateModels() {
  try {
    recreateLoadingModels.value = true
    const keys = getStoredApiKeys()

    const headers = {}
    if (keys.openaiApiKey) headers['X-OpenAI-Key'] = keys.openaiApiKey
    if (keys.perplexityApiKey) headers['X-Perplexity-Key'] = keys.perplexityApiKey
    if (keys.anthropicApiKey) headers['X-Anthropic-Key'] = keys.anthropicApiKey

    const resp = await fetch('/api/all-models', { headers })
    if (resp.ok) {
      const data = await resp.json()
      recreateAvailableModels.value = data.models || []

      // Se o modelo selecionado não existe, seleciona o primeiro disponível
      if (recreateLlmModels.value.length > 0) {
        const modelExists = recreateLlmModels.value.some(m => m.name === recreateSelectedModel.value)
        if (!modelExists) {
          recreateSelectedModel.value = recreateLlmModels.value[0].name
        }
      }
    }
  } catch (e) {
    notify('Erro ao carregar modelos disponíveis', 'error', 4000)
    addLog(`fetchRecreateModels error: ${e?.message || e}`, 'error')
  } finally {
    recreateLoadingModels.value = false
  }
}

// Buscar prompts padrão
async function fetchDefaultPrompts() {
  try {
    const resp = await fetch('/api/prompts/defaults')
    if (resp.ok) {
      const data = await resp.json()
      defaultPrompts.value = data
      // Inicializa prompts customizados com os padrões
      recreateCustomSystemPrompt.value = data.system?.cloze || ''
      recreateCustomGenerationPrompt.value = data.generation?.default || ''
      recreateCustomGuidelines.value = data.guidelines?.default || ''
    }
  } catch (e) {
    addLog(`fetchDefaultPrompts error: ${e?.message || e}`, 'warn')
  }
}

const difficultyHelp = computed(() => {
  switch (recreateDifficulty.value) {
    case 'easy':
      return 'Foco em 1 cloze (mais direto).'
    case 'hard_neutral':
      return 'Mais clozes, cobrindo termos-chave, sem aprofundar demais.'
    case 'hard_technical':
      return 'Mais técnico (ex.: principals, policies, deny>allow). Backend usa modelo mais forte.'
    default:
      return ''
  }
})

const selectedTargetModels = ref([]) // array de strings (modelNames)

const selectedNotesCount = computed(() => {
  const s = new Set()
  for (const c of selected.value || []) {
    const id = c?.noteId ?? c?.note ?? c?.note_id ?? c?.noteID
    if (id !== null && id !== undefined && String(id).trim() !== '') s.add(String(id))
    else if (c?.cardId !== null && c?.cardId !== undefined) s.add(`card:${String(c.cardId)}`)
  }
  return s.size
})

const estimatedCreates = computed(() => {
  const notes = selectedNotesCount.value
  const models = selectedTargetModels.value?.length || 0
  const per = Number(recreateCountPerNote.value || 0)
  if (!notes || !models || !per) return 0
  return notes * models * per
})

function openRecreateDialog() {
  if (!selected.value?.length) {
    notify('Selecione 1+ cards para recriar.', 'warn', 4200)
    return
  }
  recreateDialogVisible.value = true

  // Carrega modelos LLM disponíveis
  fetchRecreateModels()

  // Carrega prompts padrão (se ainda não carregados)
  if (!defaultPrompts.value.system?.cloze) {
    fetchDefaultPrompts()
  }

  if (!noteTypesLoaded.value) {
    fetchNoteTypes().then(() => {
      if (!selectedTargetModels.value.length && supportedNoteTypes.value.length) {
        selectedTargetModels.value = [supportedNoteTypes.value[0].name]
      }
    })
  } else {
    if (!selectedTargetModels.value.length && supportedNoteTypes.value.length) {
      selectedTargetModels.value = [supportedNoteTypes.value[0].name]
    }
  }
}

const canConfirmRecreate = computed(() => {
  return selected.value?.length > 0 && selectedTargetModels.value?.length > 0
})

async function confirmRecreate() {
  if (!canConfirmRecreate.value) {
    notify('Selecione cards e 1+ Note Types suportados.', 'warn', 6000)
    return
  }

  recreating.value = true
  const startedAt = performance.now()

  try {
    await fetchHealth()
    const provider = recreateModelProvider.value

    addLog(
      `Health: Anki=${ankiHealth.value.ok ? 'ON' : 'OFF'} | Provider=${provider} (${recreateSelectedModel.value})`,
      ankiHealth.value.ok ? 'info' : 'warn'
    )
    if (!ankiHealth.value.ok) addLog(`Health Anki error: ${ankiHealth.value.error}`, 'error')

    const cardIds = selected.value.map((x) => x.cardId)
    const keys = getStoredApiKeys()

    const payload = {
      cardIds,
      targetDeckName: recreateTargetDeck.value || null,
      allowDuplicate: true,
      suspendOriginal: !!recreateSuspendOriginal.value,
      countPerNote: Number(recreateCountPerNote.value || 1),
      targetModelNames: [...selectedTargetModels.value],
      // Modelo e provider selecionados
      model: recreateSelectedModel.value,
      provider: provider,
      // Dificuldade (opcional)
      useDifficulty: recreateUseDifficulty.value,
      difficulty: recreateUseDifficulty.value ? recreateDifficulty.value : null,
      // Prompts customizados (opcional)
      customSystemPrompt: recreateUseCustomPrompts.value ? recreateCustomSystemPrompt.value : null,
      customGenerationPrompt: recreateUseCustomPrompts.value ? recreateCustomGenerationPrompt.value : null,
      customGuidelines: recreateUseCustomPrompts.value ? recreateCustomGuidelines.value : null,
      // API keys
      openaiApiKey: keys.openaiApiKey || null,
      perplexityApiKey: keys.perplexityApiKey || null,
      anthropicApiKey: keys.anthropicApiKey || null
    }

    addLog(
      `Recreate start: cards=${cardIds.length} model=${payload.model} provider=${provider} difficulty=${payload.useDifficulty ? payload.difficulty : 'disabled'} countPerNote=${payload.countPerNote}`,
      'info'
    )

    const r = await fetch('/api/anki-recreate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    addLog(
      `Recreate(SLM) HTTP status=${r.status} ${r.statusText || ''}`,
      r.status >= 400 ? 'error' : r.status === 207 ? 'warn' : 'info'
    )

    const data = await readJsonSafe(r)
    const elapsed = Math.round(performance.now() - startedAt)

    if (data?.__nonJson) {
      addLog(`Recreate(SLM): non-JSON response (ct=${data.__contentType}) head="${data.__head}"`, 'error')
      notify('API /anki-recreate não retornou JSON.', 'error', 9000)
      return
    }
    if (data?.__jsonParseError) {
      addLog(`Recreate(SLM): JSON parse error: ${data.__message}`, 'error')
      notify('Falha ao ler JSON do backend.', 'error', 9000)
      return
    }

    const requestId = data?.requestId ? String(data.requestId) : '—'
    addLog(`Recreate(SLM) requestId=${requestId} elapsed=${elapsed}ms`, 'info')

    if (data?.timings) {
      addLog(
        `Recreate timings: cardsInfo=${ms(data.timings.cardsInfoMs)} modelFields=${ms(data.timings.modelFieldNamesMs)} total=${ms(
          data.timings.totalMs
        )}`,
        'info'
      )
    }

    if (r.status >= 400 || data?.success === false) {
      const msg = data?.error || `Falha ao recriar (HTTP ${r.status}).`
      addLog(`Recreate(SLM) error: ${msg}`, 'error')

      if (Array.isArray(data?.results)) {
        const sum = summarizeResults(data.results)
        addLog(`Recreate failures: items=${sum.totalFailedItems} stages=${sum.stageSummary || '—'}`, 'warn')
        for (const line of sum.firstErrors) addLog(`↳ ${line}`, 'error')
      } else {
        addLog('Recreate: sem "results" no payload.', 'warn')
      }

      notify(msg + ' — veja Logs', 'error', 9000)
      return
    }

    const created = Number(data?.totalCreated || 0)
    const failed = Number(data?.totalFailed || 0)
    const notes = Number(data?.totalSelectedNotes || 0)
    const suspended = Number(data?.totalSuspendedCards || 0)

    addLog(
      `Recreate(SLM) done: notes=${notes} created=${created} failed=${failed} suspendedCards=${suspended}`,
      failed ? 'warn' : 'success'
    )

    if (Array.isArray(data?.results) && failed > 0) {
      const sum = summarizeResults(data.results)
      addLog(`Partial details: stages=${sum.stageSummary || '—'}`, 'warn')
      for (const line of sum.firstErrors) addLog(`↳ ${line}`, 'warn')
    }

    if (created > 0 && failed === 0) {
      notify(`Recriados: ${created} (de ${notes} notas). Suspensos: ${suspended}`, 'success', 6500)
    } else if (created > 0 && failed > 0) {
      notify(`Recriados: ${created} (falhas: ${failed}). Suspensos: ${suspended} — veja Logs`, 'warn', 7500)
    } else {
      notify(`Nenhuma nota criada (falhas: ${failed}) — veja Logs`, 'warn', 7500)
    }

    recreateDialogVisible.value = false
    await fetchCards()
  } catch (e) {
    addLog(`Recreate(SLM) exception: ${e?.message || String(e)}`, 'error')
    notify(e?.message || String(e), 'error', 8000)
  } finally {
    recreating.value = false
  }
}

// ----------------------
// Lifecycle
// ----------------------
onMounted(async () => {
  await fetchHealth()
  healthTimer = setInterval(fetchHealth, 6000)

  // Apply URL filter parameter if present (before any fetch)
  const filterParam = route.query.filter
  if (filterParam) {
    const knownStatuses = statusOptions.map(o => o.value).filter(v => v)
    if (knownStatuses.includes(filterParam)) {
      status.value = filterParam
      addLog(`Applied URL filter to status: ${filterParam}`, 'info')
    } else {
      // For complex queries like "is:due", use advancedQuery
      advancedQuery.value = filterParam
      status.value = ''
      addLog(`Applied URL filter to advancedQuery: ${filterParam}`, 'info')
    }
  }

  await fetchDecks()
  await fetchCards()

  // Enable watch for filter changes after initial load
  initializing.value = false
})

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
})
</script>

<template>
  <Toast />

  <!-- Sidebar -->
  <SidebarMenu 
    ref="sidebarRef"
    :menu-items="sidebarMenuItems"
    :footer-actions="sidebarFooterActions"
    version="v1.0.0"
  />

  <div class="app-shell">
    <Toolbar class="app-header">
      <template #start>
        <div class="header-left">
          <Button icon="pi pi-bars" text rounded @click="sidebarRef?.toggleSidebar()" class="menu-toggle" title="Menu" v-if="!sidebarRef?.sidebarOpen" />
          
          <div class="brand">
            <div class="brand-text">
              <img class="brand-header-logo" src="/green-header.svg" alt="Green Deck" />
              <div class="brand-subtitle">Anki Card Browser</div>
            </div>
          </div>

          <div class="header-badges">
            <Tag severity="success" class="pill">/browser</Tag>
          </div>
        </div>
      </template>

      <template #end>
        <div class="header-right">
          <div class="status-wrap">
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
        </div>
      </template>
    </Toolbar>

    <div class="main">
      <!-- Initial loading indicator -->
      <Transition name="fade">
        <div v-if="initializing" class="initial-loading card-surface">
          <div class="loading-content">
            <i class="pi pi-spin pi-spinner loading-spinner"></i>
            <div class="loading-text">
              <div class="loading-title">Carregando Browser...</div>
              <div class="loading-sub muted">Aplicando filtros e buscando cards</div>
            </div>
          </div>
          <ProgressBar mode="indeterminate" class="loading-bar" />
        </div>
      </Transition>

      <div class="filters card-surface" :class="{ 'filters-disabled': initializing }">
        <div class="filters-row">
          <Select v-model="deck" :options="deckSelectOptions" optionLabel="label" optionValue="value" filter class="w-22" placeholder="Deck" :disabled="initializing" />
          <Select v-model="status" :options="statusOptions" optionLabel="label" optionValue="value" class="w-18" :disabled="initializing" />
          <InputText v-model="text" class="w-22" placeholder="Buscar texto (Anki query terms)..." :disabled="initializing" />
          <div class="query-input-wrap">
            <InputText v-model="advancedQuery" class="query-input" placeholder='Query avançada (ex: deck:"X" is:review tag:y)' :disabled="initializing" />
            <Button icon="pi pi-question-circle" text rounded class="query-help-btn" @click="(e) => queryHelpRef?.toggle(e)" title="Ajuda com sintaxe de busca" :disabled="initializing" />
          </div>
          <Button icon="pi pi-refresh" label="Atualizar" outlined @click="refreshAll" :disabled="initializing" />
        </div>

        <div class="query-hint">
          <span class="muted">Query:</span>
          <code class="q">{{ queryBuilt }}</code>
          <span class="muted">Total:</span>
          <b>{{ loading ? '...' : total }}</b>
        </div>
      </div>

      <!-- Query Helper Popover -->
      <Popover ref="queryHelpRef" class="query-help-popover">
        <div class="query-help-content">
          <div class="query-help-header">
            <i class="pi pi-search"></i>
            <div>
              <div class="query-help-title">Sintaxe de Busca Anki</div>
              <div class="query-help-sub">Clique para inserir na query</div>
            </div>
          </div>
          <div class="query-help-sections">
            <div v-for="section in queryHelpers" :key="section.category" class="query-section">
              <div class="query-section-title">{{ section.category }}</div>
              <div class="query-items">
                <button
                  v-for="item in section.items"
                  :key="item.query"
                  class="query-item"
                  @click="insertQuery(item.query)"
                  :title="item.desc"
                >
                  <code class="query-code">{{ item.query }}</code>
                  <span class="query-desc">{{ item.desc }}</span>
                </button>
              </div>
            </div>
          </div>
          <div class="query-help-footer">
            <a href="https://docs.ankiweb.net/searching.html" target="_blank" rel="noopener" class="query-docs-link">
              <i class="pi pi-external-link"></i>
              Documentação completa
            </a>
          </div>
        </div>
      </Popover>

      <div class="recreate-bar card-surface">
        <div class="recreate-left">
          <Select
            v-model="recreateTargetDeck"
            :options="deckTargetOptions"
            optionLabel="label"
            optionValue="value"
            filter
            class="w-22"
            placeholder="Deck destino"
          />
        </div>

        <div class="recreate-right">
          <Button icon="pi pi-language" label="Traduzir" :disabled="!selected.length" @click="openTranslateDialog" severity="info" />
          <Button icon="pi pi-sparkles" label="Gerar com LLM" :disabled="!selected.length" @click="openRecreateDialog" severity="help" />
          <Tag severity="secondary" class="pill">Selecionados: {{ selected.length }}</Tag>
        </div>
      </div>

      <div class="table-card card-surface">
        <DataTable
          :value="sortedItems"
          dataKey="cardId"
          v-model:selection="selected"
          selectionMode="multiple"
          :loading="loading"
          paginator
          :rows="rows"
          :first="first"
          :totalRecords="total"
          lazy
          stripedRows
          rowHover
          removableSort
          :sortField="sortField"
          :sortOrder="sortOrder"
          @page="onPage"
          @sort="onSort"
          class="dt modern-dt"
          tableStyle="min-width: 70rem"
          @rowDblclick="openPreview($event.data)"
        >
          <template #header>
            <div class="dt-header">
              <div class="dt-title">
                <span class="title">Anki Browser</span>
                <span class="subtitle">Duplo clique para preview • Geração com LLM</span>
              </div>
              <div class="dt-actions">
                <Button icon="pi pi-refresh" rounded raised @click="refreshAll" title="Atualizar tudo (decks + cards)" />
              </div>
            </div>
          </template>

          <Column selectionMode="multiple" headerStyle="width:3rem" />
          <Column field="deckName" header="Deck" sortable style="min-width: 14rem" />
          <Column field="modelName" header="Modelo" sortable style="min-width: 14rem" />

          <Column header="Status" sortable sortField="queue" style="width: 14rem">
            <template #body="{ data }">
              <Tag :value="queueLabel(data.queue)" :severity="queueSeverity(data.queue)" class="pill" />
            </template>
          </Column>

          <Column field="interval" header="Int (d)" sortable style="width: 7rem" />
          <Column header="Ease" sortable sortField="factor" style="width: 7rem">
            <template #body="{ data }">
              {{ Math.round((Number(data.factor) || 0) / 10) }}%
            </template>
          </Column>
          <Column field="reps" header="Reps" sortable style="width: 6rem" />
          <Column field="lapses" header="Lapses" sortable style="width: 7rem" />

          <Column header="Flags" style="width: 7rem">
            <template #body="{ data }">
              <span v-if="Number(data.flags) > 0" class="flag-wrap" :title="flagLabel(data.flags)">
                <i class="pi pi-flag flag-ico" :class="flagClass(data.flags)"></i>
              </span>
              <span v-else class="muted">—</span>
            </template>
          </Column>

          <!-- ✅ Ações da NOTA -->
          <Column header="Ações" style="width: 10rem">
            <template #body="{ data }">
              <div class="actions-cell">
                <Button
                  v-if="isSuspendedRow(data)"
                  icon="pi pi-check"
                  text
                  rounded
                  severity="success"
                  title="Desuspender a NOTA (todos os cards)"
                  @click="openNoteAction(data, 'unsuspend')"
                />
                <Button
                  v-else
                  icon="pi pi-ban"
                  text
                  rounded
                  severity="warning"
                  title="Suspender a NOTA (todos os cards)"
                  @click="openNoteAction(data, 'suspend')"
                />
                <Button
                  icon="pi pi-pencil"
                  text
                  rounded
                  severity="secondary"
                  title="Editar a NOTA (updateNoteFields)"
                  @click="openEditDialog(data)"
                />
              </div>
            </template>
          </Column>

          <Column header="Preview" style="width: 7rem">
            <template #body="{ data }">
              <Button icon="pi pi-eye" text rounded @click="openPreview(data)" />
            </template>
          </Column>

          <template #footer>
            <div class="dt-footer">
              <span>Mostrando {{ items?.length || 0 }} nesta página • Total {{ total }}</span>
            </div>
          </template>
        </DataTable>
      </div>

      <!-- Preview -->
      <Dialog v-model:visible="previewVisible" modal :draggable="false" class="dlg dlg-preview modern-dialog" style="width:min(980px,96vw)" contentStyle="padding: 0;">
        <template #header>
          <div class="dlg-hdr">
            <div class="dlg-hdr-left">
              <div class="dlg-icon"><i class="pi pi-eye"></i></div>
              <div class="dlg-hdr-txt">
                <div class="dlg-title">Card Preview</div>
                <div class="dlg-sub">Render do HTML do Anki (Q/A). Duplo clique na tabela também abre.</div>
              </div>
            </div>

            <div class="dlg-hdr-right">
              <Tag v-if="previewCard" class="pill" severity="secondary">
                <i class="pi pi-hashtag mr-2" /> {{ previewCard.cardId }}
              </Tag>
              <Tag v-if="previewCard" class="pill" :severity="queueSeverity(previewCard.queue)">
                <i class="pi pi-circle-fill mr-2" /> {{ queueLabel(previewCard.queue) }}
              </Tag>
            </div>
          </div>
        </template>

        <div v-if="previewCard" class="dlg-body preview">
          <div class="pv-meta">
            <Tag class="pill" severity="secondary"><i class="pi pi-file mr-2" /> noteId: {{ previewCard.noteId || previewCard.note || '—' }}</Tag>
            <Tag class="pill" severity="info"><i class="pi pi-tag mr-2" /> {{ previewCard.deckName }}</Tag>
            <Tag class="pill" severity="secondary"><i class="pi pi-book mr-2" /> {{ previewCard.modelName }}</Tag>
          </div>

          <Divider />

          <div class="pv-grid">
            <div class="pv-col">
              <div class="pv-title">Question</div>
              <div class="pv-box" v-html="previewCard.question"></div>
            </div>
            <div class="pv-col">
              <div class="pv-title">Answer</div>
              <div class="pv-box" v-html="previewCard.answer"></div>
            </div>
          </div>
        </div>

        <template #footer>
          <div class="dlg-footer">
            <Button label="Fechar" icon="pi pi-times" outlined @click="previewVisible = false" />
          </div>
        </template>
      </Dialog>

      <!-- Confirmar Suspender/Desuspender Nota -->
      <Dialog v-model:visible="noteActionDialogVisible" modal :draggable="false" class="dlg dlg-noteaction modern-dialog" style="width:min(820px,96vw)" contentStyle="padding: 0;">
        <template #header>
          <div class="dlg-hdr">
            <div class="dlg-hdr-left">
              <div class="dlg-icon">
                <i class="pi" :class="noteActionType === 'unsuspend' ? 'pi-check' : 'pi-ban'"></i>
              </div>
              <div class="dlg-hdr-txt">
                <div class="dlg-title">{{ noteActionTitle }}</div>
                <div class="dlg-sub">
                  Esta ação afeta <b>todos os cards</b> do <b>noteId</b> (não só o card da linha).
                </div>
              </div>
            </div>
            <div class="dlg-hdr-right">
              <Tag class="pill" severity="secondary">noteId: <b class="ml-2">{{ noteActionRow ? (noteActionRow.noteId || noteActionRow.note || '—') : '—' }}</b></Tag>
              <Tag v-if="noteActionRow" class="pill" severity="info">{{ noteActionRow.deckName }}</Tag>
            </div>
          </div>
        </template>

        <div class="dlg-body">
          <div class="noteaction-box">
            <div class="noteaction-line">
              <span class="muted">Ação:</span>
              <b>{{ noteActionType === 'unsuspend' ? 'Desuspender' : 'Suspender' }}</b>
            </div>
            <div class="noteaction-line">
              <span class="muted">Modelo:</span>
              <b>{{ noteActionRow?.modelName || '—' }}</b>
            </div>
            <div class="noteaction-line">
              <span class="muted">CardId (referência):</span>
              <b>{{ noteActionRow?.cardId || '—' }}</b>
            </div>
          </div>

          <div class="muted tiny">
            Dica: use o filtro <code class="q">is:suspended</code> para checar rapidamente o resultado.
          </div>
        </div>

        <template #footer>
          <div class="dlg-footer">
            <div class="footer-left"></div>
            <div class="footer-right">
              <Button label="Cancelar" icon="pi pi-times" severity="secondary" outlined @click="noteActionDialogVisible = false" />
              <Button
                :label="noteActionType === 'unsuspend' ? 'Desuspender' : 'Suspender'"
                :icon="noteActionType === 'unsuspend' ? 'pi pi-check' : 'pi pi-ban'"
                :severity="noteActionType === 'unsuspend' ? 'success' : 'warning'"
                :loading="noteActionLoading"
                @click="confirmNoteAction"
              />
            </div>
          </div>
        </template>
      </Dialog>

      <!-- Editar Nota -->
      <Dialog v-model:visible="editDialogVisible" modal :draggable="false" class="dlg dlg-editnote modern-dialog" style="width:min(980px,96vw)" contentStyle="padding: 0;">
        <template #header>
          <div class="dlg-hdr">
            <div class="dlg-hdr-left">
              <div class="dlg-icon"><i class="pi pi-pencil"></i></div>
              <div class="dlg-hdr-txt">
                <div class="dlg-title">Editar nota</div>
                <div class="dlg-sub">Edita fields via <b>updateNoteFields</b>. (Cuidado: isso altera a nota no Anki.)</div>
              </div>
            </div>

            <div class="dlg-hdr-right">
              <Tag class="pill" severity="secondary">noteId: <b class="ml-2">{{ editMeta.noteId }}</b></Tag>
              <Tag class="pill" severity="info">{{ editMeta.deckName }}</Tag>
              <Tag class="pill" severity="secondary">{{ editMeta.modelName }}</Tag>
            </div>
          </div>
        </template>

        <div class="dlg-body editnote">
          <div v-if="editLoading" class="muted pad">Carregando note info...</div>

          <div v-else>
            <div class="editnote-top">
              <div class="editnote-kv">
                <div class="kv"><span class="muted">cardId</span><b>{{ editMeta.cardId }}</b></div>
                <div class="kv"><span class="muted">noteId</span><b>{{ editMeta.noteId }}</b></div>
              </div>

              <div class="editnote-tags" v-if="editTags?.length">
                <span class="muted">Tags:</span>
                <div class="tags-chips">
                  <Tag v-for="(t, i) in editTags" :key="i" class="pill" severity="secondary">{{ t }}</Tag>
                </div>
              </div>
            </div>

            <Divider />

            <div v-if="!editFields.length" class="muted pad">Nenhum field encontrado.</div>

            <div v-else class="fields-grid">
              <div v-for="(f, idx) in editFields" :key="idx" class="field-card">
                <div class="field-h">
                  <div class="field-name">{{ f.name }}</div>
                  <Tag class="pill" severity="secondary">ord: {{ f.order }}</Tag>
                </div>
                <Textarea v-model="f.value" autoResize rows="2" class="w-100" />
                <div class="muted tiny">Dica: preserve HTML do Anki se você estiver usando formatação/cloze.</div>
              </div>
            </div>
          </div>
        </div>

        <template #footer>
          <div class="dlg-footer">
            <div class="footer-left">
              <Tag class="pill" severity="secondary">Fields: <b class="ml-2">{{ editFields.length }}</b></Tag>
            </div>
            <div class="footer-right">
              <Button label="Cancelar" icon="pi pi-times" severity="secondary" outlined @click="editDialogVisible = false" />
              <Button label="Salvar" icon="pi pi-save" :loading="editSaving" :disabled="editLoading || !editFields.length" @click="saveNoteEdits" />
            </div>
          </div>
        </template>
      </Dialog>

      <!-- Modal Translate (Tradução) -->
      <Dialog v-model:visible="translateDialogVisible" modal :draggable="false" class="dlg dlg-translate modern-dialog" style="width:min(720px,96vw)" contentStyle="padding: 0;">
        <template #header>
          <div class="dlg-hdr">
            <div class="dlg-hdr-left">
              <div class="dlg-icon"><i class="pi pi-language"></i></div>
              <div class="dlg-hdr-txt">
                <div class="dlg-title">Traduzir Cards</div>
                <div class="dlg-sub">Traduz o conteúdo dos cards in-place, preservando tags, mídia e clozes.</div>
              </div>
            </div>

            <div class="dlg-hdr-right">
              <span class="svc-mini" :class="ankiHealth.ok ? 'on' : ankiHealth.ok === null ? 'idle' : 'off'" :title="ankiStatusTitle">
                <i class="pi" :class="ankiHealth.ok ? 'pi-check' : ankiHealth.ok === null ? 'pi-spin pi-spinner' : 'pi-times'"></i>
                <span>Anki</span>
              </span>
            </div>
          </div>
        </template>

        <div class="dlg-body translate-modal">
          <div class="translate-hero">
            <div class="hero-left">
              <div class="hero-title">
                <span class="hero-pill">Tradução</span>
                <span class="muted">•</span>
                <span class="muted">Inglês → Português (BR)</span>
              </div>

              <div class="hero-kpis" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
                <div class="kpi" v-if="!translateUseEntireDeck">
                  <div class="kpi-lbl">Cards selecionados</div>
                  <div class="kpi-val">{{ selected.length }}</div>
                </div>
                <div class="kpi" v-if="!translateUseEntireDeck">
                  <div class="kpi-lbl">Notas únicas</div>
                  <div class="kpi-val">{{ selectedNotesCount }}</div>
                </div>
                <div class="kpi" v-if="translateUseEntireDeck">
                  <div class="kpi-lbl">Modo</div>
                  <div class="kpi-val">Deck: {{ deck }}</div>
                </div>
                <div class="kpi" v-if="translateAlreadyPtCount > 0">
                  <div class="kpi-lbl">Já em PT</div>
                  <div class="kpi-val" style="color: #22c55e;">{{ translateAlreadyPtCount }}</div>
                </div>
              </div>
            </div>

            <div class="hero-right">
              <Tag class="pill" severity="info">
                <i class="pi pi-globe mr-2" />
                pt-br
              </Tag>
            </div>
          </div>

          <!-- Opção: Traduzir Deck Inteiro -->
          <div style="display: flex; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(148,163,184,0.12); background: rgba(255,255,255,0.02);">
            <InputSwitch v-model="translateUseEntireDeck" @change="() => { translateAlreadyPtCount = 0; translateDetectError = ''; }" />
            <label style="flex: 1; cursor: pointer; font-size: 13px;">Traduzir deck inteiro "{{ deck }}"</label>
            <Button 
              v-if="translateUseEntireDeck || selected.length"
              icon="pi pi-search" 
              severity="secondary" 
              text 
              @click="detectCardLanguages"
              :loading="translateDetectingLanguages"
              v-tooltip.top="'Detectar quantos já estão em português'"
              style="padding: 6px 8px;"
            />
          </div>

          <!-- Detecção de Idioma -->
          <div v-if="translateDetectError" style="padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(239,68,68,0.35); background: rgba(239,68,68,0.08); color: #ef4444; font-size: 12px;">
            <i class="pi pi-exclamation-circle mr-2" style="color: #ef4444;"></i>
            {{ translateDetectError }}
          </div>

          <div v-if="translateAlreadyPtCount > 0" style="padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(34,197,94,0.35); background: rgba(34,197,94,0.08); font-size: 12px;">
            <i class="pi pi-info-circle mr-2" style="color: #22c55e;"></i>
            <strong>{{ translateAlreadyPtCount }}</strong> cartões já estão em português
            <span v-if="translateNeedsTranslationCount">, <strong>{{ translateNeedsTranslationCount }}</strong> precisam tradução</span>
          </div>

          <!-- Model Selection -->
          <div class="translate-model-section">
            <label class="section-label">Modelo para Tradução</label>
            <div class="model-selector-row">
              <Select
                v-model="translateSelectedModel"
                :options="translateLlmModels"
                optionLabel="name"
                optionValue="name"
                placeholder="Selecione um modelo"
                class="model-select"
                :loading="translateLoadingModels"
                filter
              >
                <template #option="{ option }">
                  <div class="model-option">
                    <span class="model-name">{{ option.name }}</span>
                    <Tag :severity="option.provider === 'ollama' ? 'secondary' : option.provider === 'openai' ? 'success' : option.provider === 'perplexity' ? 'info' : 'warn'" class="provider-tag">
                      {{ option.provider }}
                    </Tag>
                  </div>
                </template>
                <template #value="{ value }">
                  <div v-if="value" class="model-option">
                    <span class="model-name">{{ value }}</span>
                  </div>
                  <span v-else class="muted">Selecione um modelo</span>
                </template>
              </Select>
              <Button
                icon="pi pi-refresh"
                severity="secondary"
                outlined
                @click="fetchTranslateModels"
                :loading="translateLoadingModels"
                v-tooltip.top="'Atualizar lista de modelos'"
              />
            </div>
            <small class="muted" v-if="!translateLlmModels.length && !translateLoadingModels">
              Nenhum modelo disponível. Verifique se Ollama está rodando ou configure API keys em GeneratorPage.
            </small>
          </div>

          <div class="translate-info">
            <div class="info-box">
              <i class="pi pi-info-circle"></i>
              <div>
                <div class="info-title">O que será preservado:</div>
                <ul class="info-list">
                  <li>Tags do Anki (não serão alteradas)</li>
                  <li>Arquivos de mídia (áudio, imagens)</li>
                  <li>Marcações cloze <code v-pre>{{c1::...}}</code></li>
                  <li>Formatação HTML (negrito, itálico, etc.)</li>
                </ul>
              </div>
            </div>
          </div>

          <div class="translate-warning" v-if="!translateUseEntireDeck && selectedNotesCount > 10">
            <i class="pi pi-exclamation-triangle"></i>
            <div class="muted">
              Você selecionou muitas notas. A tradução pode demorar alguns minutos.
              Tempo estimado: ~{{ Math.ceil(selectedNotesCount * 3 / 60) }} min
            </div>
          </div>
        </div>

        <template #footer>
          <div class="dlg-footer">
            <div class="footer-left">
              <Tag class="pill" severity="secondary" v-if="!translateUseEntireDeck">
                <i class="pi pi-file mr-2" /> 
                Notas: {{ selectedNotesCount }}
              </Tag>
              <Tag class="pill" severity="secondary" v-else>
                <i class="pi pi-database mr-2" />
                Deck: {{ deck }}
              </Tag>
            </div>
            <div class="footer-right">
              <Button label="Cancelar" icon="pi pi-times" severity="secondary" outlined @click="translateDialogVisible = false" />
              <Button
                label="Traduzir agora"
                icon="pi pi-language"
                :disabled="(!selected.length && !translateUseEntireDeck) || !ankiHealth.ok || !translateSelectedModel"
                :loading="translating"
                @click="confirmTranslate"
              />
            </div>
          </div>
        </template>
      </Dialog>

      <!-- Modal Progress Tradução -->
      <Dialog v-model:visible="translateProgressVisible" modal :draggable="false" class="dlg dlg-translate-progress modern-dialog" style="width:min(520px,96vw)" :closable="false" contentStyle="padding: 0;">
        <template #header>
          <div class="dlg-hdr">
            <div class="dlg-hdr-left">
              <div class="dlg-icon" :class="{ 'spinning': translateStatus === 'translating' }">
                <i class="pi" :class="translateStatus === 'translating' ? 'pi-spin pi-spinner' : translateStatus === 'done' ? 'pi-check' : 'pi-exclamation-triangle'"></i>
              </div>
              <div class="dlg-hdr-txt">
                <div class="dlg-title">{{ translateStatus === 'done' ? '✓ Tradução Concluída' : 'Traduzindo Cards...' }}</div>
                <div class="dlg-sub" v-if="translateStatus === 'translating'">{{ translateCurrent }}/{{ translateTotal }} notas processadas</div>
              </div>
            </div>
          </div>
        </template>

        <div class="dlg-body translate-progress-modal">
          <!-- Progress Bar -->
          <ProgressBar :value="translateProgress" :show-value="false" />

          <!-- Stats -->
          <div class="progress-stats">
            <div class="stat stat-current">
              <div class="stat-label">Processadas</div>
              <div class="stat-value">{{ translateCurrent }}/{{ translateTotal }}</div>
            </div>
            <div class="stat stat-success">
              <div class="stat-label">Traduzidas</div>
              <div class="stat-value" style="color: #22c55e;">{{ translateTranslatedCount }}</div>
            </div>
            <div class="stat stat-warning" v-if="translateFailedCount > 0">
              <div class="stat-label">Falhas</div>
              <div class="stat-value" style="color: #ef4444;">{{ translateFailedCount }}</div>
            </div>
            <div class="stat stat-info" v-if="translateSkippedCount > 0">
              <div class="stat-label">Puladas</div>
              <div class="stat-value" style="color: #f59e0b;">{{ translateSkippedCount }}</div>
            </div>
          </div>

          <!-- Status Message -->
          <div v-if="translateStatus === 'translating'" class="progress-status">
            <div class="status-item">
              <i class="pi" :class="translateLastNoteStatus === 'success' ? 'pi-check' : translateLastNoteStatus === 'failed' ? 'pi-times' : 'pi-minus'"></i>
              <span>Última: <strong>{{ translateLastNoteStatus || '—' }}</strong></span>
            </div>
            <div v-if="translateLastError" class="status-error">{{ translateLastError }}</div>
          </div>

          <div v-if="translateStatus === 'error'" class="progress-error">
            <i class="pi pi-exclamation-circle"></i>
            <div>
              <div class="error-title">Erro na Tradução</div>
              <div class="error-msg">{{ translateLastError || 'Erro desconhecido' }}</div>
            </div>
          </div>

          <div v-if="translateStatus === 'done'" class="progress-done">
            <i class="pi pi-check-circle"></i>
            <div>
              <div class="done-title">Tradução Finalizada</div>
              <div class="done-msg">
                {{ translateTranslatedCount }} de {{ translateTotal }} notas traduzidas com sucesso.
              </div>
            </div>
          </div>
        </div>

        <template #footer>
          <div class="dlg-footer">
            <div class="footer-left" />
            <div class="footer-right">
              <Button 
                v-if="translateStatus === 'translating'" 
                label="Cancelar" 
                icon="pi pi-times" 
                severity="danger" 
                outlined 
                @click="cancelTranslate" 
              />
              <Button 
                v-if="translateStatus !== 'translating'" 
                label="Fechar" 
                icon="pi pi-times" 
                severity="secondary" 
                outlined 
                @click="translateProgressVisible = false" 
              />
            </div>
          </div>
        </template>
      </Dialog>

      <!-- Modal Gerar com LLM -->
      <Dialog v-model:visible="recreateDialogVisible" modal :draggable="false" class="dlg dlg-recreate modern-dialog" style="width:min(980px,96vw)" contentStyle="padding: 0;">
        <template #header>
          <div class="dlg-hdr">
            <div class="dlg-hdr-left">
              <div class="dlg-icon"><i class="pi pi-sparkles"></i></div>
              <div class="dlg-hdr-txt">
                <div class="dlg-title">Gerar Flashcards com LLM</div>
                <div class="dlg-sub">Cria novas notas com clozes usando modelos de IA (local ou cloud).</div>
              </div>
            </div>

            <div class="dlg-hdr-right">
              <span class="svc-mini" :class="ankiHealth.ok ? 'on' : ankiHealth.ok === null ? 'idle' : 'off'" :title="ankiStatusTitle">
                <i class="pi" :class="ankiHealth.ok ? 'pi-check' : ankiHealth.ok === null ? 'pi-spin pi-spinner' : 'pi-times'"></i>
                <span>Anki</span>
              </span>
            </div>
          </div>
        </template>

        <div class="dlg-body recreate-modal">
          <!-- Hero / resumo -->
          <div class="recreate-hero">
            <div class="hero-left">
              <div class="hero-title">
                <span class="hero-pill">Resumo</span>
                <span class="muted">•</span>
                <span class="muted">revise antes de confirmar</span>
              </div>

              <div class="hero-kpis">
                <div class="kpi">
                  <div class="kpi-lbl">Cards</div>
                  <div class="kpi-val">{{ selected.length }}</div>
                </div>
                <div class="kpi">
                  <div class="kpi-lbl">Notas únicas</div>
                  <div class="kpi-val">{{ selectedNotesCount }}</div>
                </div>
                <div class="kpi">
                  <div class="kpi-lbl">Note Types</div>
                  <div class="kpi-val">{{ selectedTargetModels.length }}</div>
                </div>
                <div class="kpi">
                  <div class="kpi-lbl">Estimativa</div>
                  <div class="kpi-val">{{ estimatedCreates }}</div>
                </div>
              </div>
            </div>

            <div class="hero-right">
              <Tag class="pill" severity="secondary">
                <i class="pi pi-sitemap mr-2" />
                Deck destino: <b class="ml-2">{{ recreateTargetDeck ? recreateTargetDeck : 'Original' }}</b>
              </Tag>

              <Tag class="pill" :severity="getProviderSeverity(recreateModelProvider)">
                <i class="pi pi-microchip mr-2" />
                {{ getProviderLabel(recreateModelProvider) }}: <b class="ml-1">{{ recreateSelectedModel }}</b>
              </Tag>

              <Tag v-if="recreateModelProvider === 'ollama' && !ollamaHealth.ok" class="pill" severity="danger">
                <i class="pi pi-exclamation-triangle mr-2" />
                Ollama offline — selecione outro modelo
              </Tag>
            </div>
          </div>

          <div class="sections">
            <!-- Modelo LLM -->
            <div class="section">
              <div class="section-h">
                <i class="pi pi-microchip"></i>
                <div>
                  <div class="section-title">Modelo LLM</div>
                  <div class="section-sub">Selecione o modelo para geração (Ollama local ou APIs externas)</div>
                </div>
              </div>

              <div class="grid">
                <div class="blk blk-wide">
                  <div class="lbl">Modelo</div>
                  <Select
                    v-model="recreateSelectedModel"
                    :options="recreateLlmModels"
                    optionLabel="name"
                    optionValue="name"
                    :loading="recreateLoadingModels"
                    filter
                    placeholder="Selecione um modelo"
                    class="w-100"
                  >
                    <template #option="{ option }">
                      <div class="model-option">
                        <span>{{ option.name }}</span>
                        <Tag :severity="getProviderSeverity(option.provider)" class="pill ml-2">
                          {{ getProviderLabel(option.provider) }}
                        </Tag>
                      </div>
                    </template>
                    <template #value="{ value }">
                      <div v-if="value" class="model-option">
                        <span>{{ value }}</span>
                        <Tag :severity="getProviderSeverity(getRecreateModelInfo(value)?.provider)" class="pill ml-2">
                          {{ getProviderLabel(getRecreateModelInfo(value)?.provider) }}
                        </Tag>
                      </div>
                      <span v-else>Selecione um modelo</span>
                    </template>
                  </Select>
                  <div class="muted tiny" style="margin-top: 8px;">
                    <span v-if="recreateLlmModels.length === 0 && !recreateLoadingModels">
                      Nenhum modelo disponível. Verifique se Ollama está rodando ou configure API keys em GeneratorPage.
                    </span>
                    <span v-else-if="recreateModelProvider === 'ollama'">
                      Modelo local via Ollama (privacidade total).
                    </span>
                    <span v-else>
                      Modelo via API {{ getProviderLabel(recreateModelProvider) }} (requer chave configurada).
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Config -->
            <div class="section">
              <div class="section-h">
                <i class="pi pi-sliders-h"></i>
                <div>
                  <div class="section-title">Configuração</div>
                  <div class="section-sub">Volume, suspensão e dificuldade (opcional)</div>
                </div>
              </div>

              <div class="grid">
                <div class="blk">
                  <div class="lbl">Suspender originais</div>
                  <div class="inline">
                    <InputSwitch v-model="recreateSuspendOriginal" />
                    <div class="inline-col">
                      <div class="inline-strong">
                        {{ recreateSuspendOriginal ? 'Sim' : 'Não' }}
                        <Tag v-if="recreateSuspendOriginal" severity="warn" class="pill ml-2">impacta estudo</Tag>
                      </div>
                      <div class="muted tiny">
                        {{
                          recreateSuspendOriginal
                            ? 'Suspende todos os cards das notas originais.'
                            : 'Mantém cards originais ativos.'
                        }}
                      </div>
                    </div>
                  </div>
                </div>

                <div class="blk">
                  <div class="lbl">Usar dificuldade</div>
                  <div class="inline">
                    <InputSwitch v-model="recreateUseDifficulty" />
                    <div class="inline-col">
                      <div class="inline-strong">
                        {{ recreateUseDifficulty ? 'Sim' : 'Não' }}
                        <Tag v-if="recreateUseDifficulty" severity="info" class="pill ml-2">controla clozes</Tag>
                      </div>
                      <div class="muted tiny">
                        {{ recreateUseDifficulty ? 'Ajusta quantidade de clozes por dificuldade.' : 'Usa configuração padrão do modelo.' }}
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="recreateUseDifficulty" class="blk">
                  <div class="lbl">Nível de dificuldade</div>
                  <Select v-model="recreateDifficulty" :options="difficultyOptions" optionLabel="label" optionValue="value" class="w-100" />
                  <div class="muted tiny" style="margin-top: 8px;">
                    {{ difficultyHelp }}
                  </div>
                </div>

                <div class="blk blk-wide">
                  <div class="lbl">Quantidade por nota</div>
                  <div class="qty">
                    <Slider v-model="recreateCountPerNote" :min="1" :max="20" class="qty-slider" />
                    <InputNumber v-model="recreateCountPerNote" :min="1" :max="50" showButtons />
                  </div>
                  <div class="muted tiny">
                    Estimativa:
                    <b>{{ selectedNotesCount }}</b> notas × <b>{{ selectedTargetModels.length }}</b> Note Types ×
                    <b>{{ recreateCountPerNote }}</b> por nota = <b>{{ estimatedCreates }}</b>
                  </div>
                </div>
              </div>
            </div>

            <!-- Note Types -->
            <div class="section">
              <div class="section-h">
                <i class="pi pi-box"></i>
                <div>
                  <div class="section-title">Note Types (alvo)</div>
                  <div class="section-sub">Apenas Note Types suportados aparecem habilitados</div>
                </div>

                <div class="section-right">
                  <Tag class="pill" severity="secondary">
                    Suportados: <b class="ml-2">{{ supportedCount }}</b>/<b>{{ noteTypes.length }}</b>
                  </Tag>
                </div>
              </div>

              <div class="blk">
                <MultiSelect
                  v-model="selectedTargetModels"
                  :options="noteTypeOptions"
                  optionLabel="label"
                  optionValue="value"
                  optionDisabled="disabled"
                  filter
                  display="chip"
                  placeholder="Selecione 1+ Note Types"
                  class="w-100"
                />

                <div class="support">
                  <Button icon="pi pi-list" label="Consultar Note Types" severity="secondary" outlined @click="openNoteTypesDialog" />
                  <Tag v-if="selectedTargetModels.length" severity="success" class="pill">
                    <i class="pi pi-check mr-2" /> Selecionados: {{ selectedTargetModels.length }}
                  </Tag>
                  <Tag v-else severity="warn" class="pill">
                    <i class="pi pi-info-circle mr-2" /> Selecione pelo menos 1
                  </Tag>
                </div>
              </div>
            </div>

            <!-- Prompts Customizados -->
            <div class="section">
              <div class="section-h">
                <i class="pi pi-pencil"></i>
                <div>
                  <div class="section-title">Prompts Customizados</div>
                  <div class="section-sub">Personalize os prompts usados para geração (avançado)</div>
                </div>
                <div class="section-right">
                  <div class="inline" style="gap: 0.5rem;">
                    <InputSwitch v-model="recreateUseCustomPrompts" />
                    <span class="muted tiny">{{ recreateUseCustomPrompts ? 'Ativo' : 'Desativado' }}</span>
                  </div>
                </div>
              </div>

              <div v-if="recreateUseCustomPrompts" class="grid">
                <div class="blk blk-wide">
                  <div class="lbl">System Prompt</div>
                  <Textarea
                    v-model="recreateCustomSystemPrompt"
                    rows="4"
                    class="w-100"
                    placeholder="Prompt de sistema que define o comportamento base do modelo..."
                  />
                  <div class="muted tiny" style="margin-top: 4px;">
                    Define o papel e comportamento do modelo.
                  </div>
                </div>

                <div class="blk blk-wide">
                  <div class="lbl">Diretrizes (Guidelines)</div>
                  <Textarea
                    v-model="recreateCustomGuidelines"
                    rows="6"
                    class="w-100"
                    placeholder="Diretrizes de qualidade para criação de flashcards..."
                  />
                  <div class="muted tiny" style="margin-top: 4px;">
                    Regras de qualidade (SuperMemo, Justin Sung, etc).
                  </div>
                </div>

                <div class="blk blk-wide">
                  <div class="support" style="margin-top: 8px;">
                    <Button
                      icon="pi pi-refresh"
                      label="Restaurar padrões"
                      severity="secondary"
                      outlined
                      size="small"
                      @click="() => {
                        recreateCustomSystemPrompt = defaultPrompts.system?.cloze || ''
                        recreateCustomGuidelines = defaultPrompts.guidelines?.default || ''
                      }"
                    />
                  </div>
                </div>
              </div>

              <div v-else class="blk">
                <div class="muted tiny">
                  Ative para personalizar os prompts de geração. Os prompts padrão são otimizados para criar flashcards de alta qualidade.
                </div>
              </div>
            </div>
          </div>

          <div class="recreate-tip">
            <i class="pi pi-lightbulb"></i>
            <div class="muted">
              Dica: se quiser testar, use <b>Quantidade=1</b> primeiro. Depois aumente conforme necessário.
            </div>
          </div>
        </div>

        <template #footer>
          <div class="dlg-footer">
            <div class="footer-left">
              <Tag class="pill" severity="secondary"><i class="pi pi-calculator mr-2" /> Estimativa: {{ estimatedCreates }}</Tag>
              <Tag class="pill" :severity="getProviderSeverity(recreateModelProvider)">
                <i class="pi pi-microchip mr-2" /> {{ getProviderLabel(recreateModelProvider) }}
              </Tag>
            </div>
            <div class="footer-right">
              <Button label="Cancelar" icon="pi pi-times" severity="secondary" outlined @click="recreateDialogVisible = false" />
              <Button
                label="Gerar agora"
                icon="pi pi-sparkles"
                :disabled="!canConfirmRecreate || !ankiHealth.ok || (recreateModelProvider === 'ollama' && !ollamaHealth.ok)"
                :loading="recreating"
                @click="confirmRecreate"
              />
            </div>
          </div>
        </template>
      </Dialog>

      <!-- Consultar Note Types -->
      <Dialog v-model:visible="noteTypesVisible" modal :draggable="false" class="dlg dlg-notetypes modern-dialog" style="width:min(820px,96vw)" contentStyle="padding: 0;">
        <template #header>
          <div class="dlg-hdr">
            <div class="dlg-hdr-left">
              <div class="dlg-icon"><i class="pi pi-list"></i></div>
              <div class="dlg-hdr-txt">
                <div class="dlg-title">Note Types disponíveis</div>
                <div class="dlg-sub">Lista do Anki com indicação de suporte no backend</div>
              </div>
            </div>

            <div class="dlg-hdr-right">
              <Tag class="pill" severity="secondary">Suportados: <b class="ml-2">{{ supportedCount }}</b></Tag>
            </div>
          </div>
        </template>

        <div class="dlg-body types-list">
          <div v-if="!noteTypesLoaded" class="muted pad">Carregando...</div>
          <div v-else-if="!noteTypes.length" class="muted pad">Nenhum Note Type encontrado.</div>
          <div v-else class="types-grid">
            <div v-for="(t, i) in noteTypes" :key="i" class="type-card" :class="t.supported ? 'ok' : 'no'">
              <div class="type-top">
                <div class="type-name">{{ t.name }}</div>
                <Tag v-if="t.supported" severity="success" class="pill"><i class="pi pi-check mr-2" /> Suportado</Tag>
                <Tag v-else severity="secondary" class="pill"><i class="pi pi-minus mr-2" /> Sem suporte</Tag>
              </div>
              <div class="type-sub muted">
                {{ t.supportLabel }}
              </div>
            </div>
          </div>
        </div>

        <template #footer>
          <div class="dlg-footer">
            <Button label="Fechar" icon="pi pi-times" @click="noteTypesVisible = false" />
          </div>
        </template>
      </Dialog>

      <!-- Logs -->
      <Dialog v-model:visible="logsVisible" modal :draggable="false" class="dlg dlg-logs modern-dialog" style="width:min(980px,96vw)" contentStyle="padding: 0;">
        <template #header>
          <div class="dlg-hdr">
            <div class="dlg-hdr-left">
              <div class="dlg-icon"><i class="pi pi-search"></i></div>
              <div class="dlg-hdr-txt">
                <div class="dlg-title">Logs (Browser)</div>
                <div class="dlg-sub">Erros de API, timings e detalhes de recriação</div>
              </div>
            </div>

            <div class="dlg-hdr-right">
              <Tag class="pill" severity="secondary">Linhas: <b class="ml-2">{{ logs.length }}</b></Tag>
            </div>
          </div>
        </template>

        <div class="dlg-body logs-wrap">
          <div v-if="!logs.length" class="logs-empty">Sem logs ainda.</div>
          <div v-else>
            <div v-for="(l, idx) in logs" :key="idx" class="log-row" :class="`t-${l.type}`">
              <span class="log-ts">[{{ l.timestamp }}]</span>
              <span class="log-msg">{{ l.message }}</span>
            </div>
          </div>
        </div>

        <template #footer>
          <div class="dlg-footer">
            <div class="footer-left">
              <Button label="Clear Logs" icon="pi pi-trash" severity="secondary" outlined @click="clearLogs" />
            </div>
            <div class="footer-right">
              <Button label="Close" icon="pi pi-times" @click="logsVisible = false" />
            </div>
          </div>
        </template>
      </Dialog>
    </div>
  </div>
</template>

<style scoped>
/* =========================
   Base
========================= */
.menu-toggle {
  width: 42px;
  height: 42px;
}

/* =========================
   Initial Loading
========================= */
.initial-loading {
  margin-bottom: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.loading-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.loading-spinner {
  font-size: 28px;
  color: #6366F1;
}

.loading-title {
  font-weight: 900;
  font-size: 16px;
  letter-spacing: -0.3px;
}

.loading-sub {
  font-size: 12px;
  margin-top: 2px;
}

.loading-bar {
  height: 4px;
  border-radius: 4px;
}

:deep(.loading-bar .p-progressbar-value) {
  background: linear-gradient(90deg, #6366F1, #8B5CF6, #6366F1);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.filters-disabled {
  opacity: 0.6;
  pointer-events: none;
}

/* Fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

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
  background:
    radial-gradient(1200px 700px at 12% -10%, rgba(99, 102, 241, 0.22), transparent 55%),
    radial-gradient(900px 600px at 95% 10%, rgba(16, 185, 129, 0.16), transparent 60%),
    radial-gradient(900px 600px at 60% 110%, rgba(236, 72, 153, 0.12), transparent 55%),
    linear-gradient(180deg, rgba(17, 24, 39, 0.95), rgba(10, 10, 12, 0.98));
  border: 1px solid rgba(148, 163, 184, 0.12);
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.3),
    0 0 0 1px rgba(255, 255, 255, 0.03) inset;
}

:deep(.sidebar.expanded) ~ .app-shell {
  margin-left: 324px;
}

.main {
  flex: 1;
  min-height: 0;
  padding: 14px;
  overflow: auto;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 50;
  border: 0;
  padding: 12px 16px;
  backdrop-filter: blur(16px);
  border-radius: 24px 24px 0 0;
  background: rgba(17, 24, 39, 0.5);
}

:deep(.p-toolbar) {
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
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

/* deixa o AnkiStatus/OllamaStatus com "cara de chip" igual */
.status-pills :deep(.anki-status),
.status-pills :deep(.ollama-status) {
  border-radius: 10px;
}

/* some com labels em telas pequenas */
@media (max-width: 720px) {
  .status-label { display: none; }
  .status-pills { padding: 6px 8px; gap: 8px; }
}

.card-surface{
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(17, 24, 39, 0.58);
  backdrop-filter: blur(10px);
  box-shadow: 0 14px 30px rgba(0,0,0,0.26);
  padding: 12px;
}

.filters{ display:flex; flex-direction:column; gap:10px; }
.filters-row{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }

.recreate-bar{
  margin-top: 12px;
  display:flex;
  justify-content:space-between;
  gap:10px;
  flex-wrap:wrap;
  align-items:center;
}
.recreate-left, .recreate-right{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }

.query-hint{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.muted{ opacity:.75; }
.q{
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(0,0,0,0.25);
  border: 1px solid rgba(148,163,184,0.16);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
}

.w-18{ width: 18rem; }
.w-22{ width: 22rem; }
.w-34{ width: 34rem; }
.w-100{ width: 100%; }

/* Query input with help button */
.query-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
  width: 34rem;
}
.query-input {
  width: 100%;
  padding-right: 40px;
}
.query-help-btn {
  position: absolute;
  right: 4px;
  width: 32px;
  height: 32px;
  opacity: 0.7;
}
.query-help-btn:hover {
  opacity: 1;
}

/* Query Helper Popover */
:deep(.query-help-popover) {
  max-width: 680px;
  width: 90vw;
}
:deep(.query-help-popover .p-popover-content) {
  padding: 0;
}

.query-help-content {
  display: flex;
  flex-direction: column;
  max-height: 70vh;
}

.query-help-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(99, 102, 241, 0.08);
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}
.query-help-header > i {
  font-size: 20px;
  color: #6366F1;
}
.query-help-title {
  font-weight: 900;
  font-size: 14px;
  letter-spacing: -0.2px;
}
.query-help-sub {
  font-size: 12px;
  opacity: 0.7;
  margin-top: 2px;
}

.query-help-sections {
  padding: 12px;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
@media (max-width: 600px) {
  .query-help-sections {
    grid-template-columns: 1fr;
  }
}

.query-section {
  background: rgba(0, 0, 0, 0.15);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 12px;
  padding: 10px;
}
.query-section-title {
  font-weight: 900;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  opacity: 0.8;
  margin-bottom: 8px;
  padding-left: 4px;
}

.query-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.query-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border: none;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: background 0.15s ease;
  text-align: left;
  width: 100%;
}
.query-item:hover {
  background: rgba(99, 102, 241, 0.15);
}
.query-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  padding: 3px 6px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(148, 163, 184, 0.16);
  color: #a5b4fc;
  white-space: nowrap;
}
.query-desc {
  font-size: 11px;
  opacity: 0.75;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.query-help-footer {
  padding: 10px 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(0, 0, 0, 0.1);
}
.query-docs-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #6366F1;
  text-decoration: none;
  font-weight: 600;
}
.query-docs-link:hover {
  text-decoration: underline;
}

.table-card{ margin-top: 12px; padding: 10px; }
.dt{ width: 100%; }

:deep(.modern-dt .p-datatable-header){ background: transparent; border: 0; padding: 8px 6px 14px 6px; }
:deep(.modern-dt .p-datatable-footer){ background: transparent; border: 0; padding: 12px 6px 6px 6px; }
:deep(.modern-dt .p-datatable-thead > tr > th){
  background: rgba(255,255,255,0.03);
  border-color: rgba(148,163,184,0.14);
  font-weight: 900;
}
:deep(.modern-dt .p-datatable-tbody > tr > td){ border-color: rgba(148,163,184,0.12); }
:deep(.modern-dt .p-datatable-tbody > tr){ background: rgba(255,255,255,0.01); }
:deep(.modern-dt .p-datatable-tbody > tr.p-highlight){
  background: rgba(99, 102, 241, 0.18) !important;
}

.dt-header{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.dt-title .title{ font-size: 16px; font-weight: 950; letter-spacing: -0.2px; }
.dt-title .subtitle{ display:block; margin-top: 4px; font-size: 12.5px; opacity: 0.75; }
.dt-footer{ opacity: 0.78; font-size: 12.5px; }

.pill{ border-radius:999px; font-weight:900; }

/* Flags */
.flag-wrap{ display:inline-flex; align-items:center; justify-content:center; }
.flag-ico{ font-size: 16px; }
.flag-none{ opacity: .5; }
.flag-red{ color: #ef4444; }
.flag-orange{ color: #fb923c; }
.flag-green{ color: #22c55e; }
.flag-blue{ color: #3b82f6; }

/* actions column */
.actions-cell{
  display:flex;
  align-items:center;
  justify-content:center;
  gap: 6px;
}
:deep(.modern-dt .p-button.p-button-text){
  border-radius: 999px;
}

/* Dialog header layout (mantém seu layout interno) */
.dlg-hdr{
  width: 100%;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap: 12px;
}
.dlg-hdr-left{
  display:flex;
  align-items:center;
  gap: 12px;
  min-width: 0;
}
.dlg-icon{
  width: 40px;
  height: 40px;
  border-radius: 14px;
  display:flex;
  align-items:center;
  justify-content:center;
  background: rgba(0,0,0,0.28);
  border: 1px solid rgba(148, 163, 184, 0.18);
}
.dlg-icon i{ font-size: 18px; opacity: .95; }
.dlg-hdr-txt{ min-width:0; }
.dlg-title{
  font-weight: 950;
  letter-spacing: -0.2px;
  line-height: 1.15;
}
.dlg-sub{
  margin-top: 4px;
  font-size: 12.5px;
  opacity: .78;
  max-width: 62ch;
}
.dlg-hdr-right{ display:flex; gap: 8px; align-items:center; flex-wrap:wrap; }

.dlg-body{ padding: 14px; }

/* footer */
.dlg-footer{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap: 10px;
  padding: 12px 14px;
}
.footer-left, .footer-right{ display:flex; gap: 10px; align-items:center; flex-wrap:wrap; }

/* small status pills inside modal header */
.svc-mini{
  display:inline-flex;
  gap: 8px;
  align-items:center;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(148,163,184,0.16);
  background: rgba(0,0,0,0.22);
  font-weight: 900;
  font-size: 12px;
}
.svc-mini i{ font-size: 12px; }
.svc-mini.on{ border-color: rgba(16, 185, 129, 0.35); }
.svc-mini.off{ border-color: rgba(239, 68, 68, 0.35); }
.svc-mini.idle{ border-color: rgba(148, 163, 184, 0.25); opacity: .9; }
.svc-mini.on i{ color: #22c55e; }
.svc-mini.off i{ color: #ef4444; }
.svc-mini.idle i{ color: rgba(148, 163, 184, 0.9); }

/* Preview */
.preview{ display:flex; flex-direction:column; gap: 10px; }
.pv-meta{ display:flex; gap: 8px; flex-wrap:wrap; align-items:center; }
.pv-grid{ display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 920px){
  .pv-grid{ grid-template-columns: 1fr; }
  .w-34,.w-22,.w-18{ width: 100%; }
}
.pv-title{ font-weight:900; opacity:.85; margin-bottom:6px; }
.pv-box{
  border-radius: 14px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.14);
  background: rgba(255,255,255,0.03);
  min-height: 120px;
  max-height: 44vh;
  overflow: auto;
}

/* Logs */
.logs-wrap{ max-height: 62vh; overflow: auto; padding: 12px 14px; }
.logs-empty{ opacity: 0.75; padding: 10px; }
.log-row{
  display:flex;
  gap:10px;
  padding: 8px 10px;
  border-radius: 12px;
  margin-bottom: 8px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(148, 163, 184, 0.10);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
}
.log-ts{ opacity: 0.7; white-space: nowrap; }
.log-msg{ opacity: 0.92; }
.log-row.t-success{ border-color: rgba(16, 185, 129, 0.25); }
.log-row.t-warn{ border-color: rgba(251, 191, 36, 0.25); }
.log-row.t-error{ border-color: rgba(239, 68, 68, 0.25); }

/* Note action dialog */
.noteaction-box{
  border-radius: 16px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(0,0,0,0.16);
  display:flex;
  flex-direction:column;
  gap: 8px;
  margin-bottom: 10px;
}
.noteaction-line{ display:flex; gap: 10px; align-items:center; flex-wrap:wrap; }

/* Edit note */
.editnote{ display:flex; flex-direction:column; gap: 12px; }
.editnote-top{
  display:flex;
  gap: 12px;
  justify-content:space-between;
  flex-wrap:wrap;
  align-items:flex-start;
}
.editnote-kv{ display:flex; gap: 12px; flex-wrap:wrap; }
.kv{
  border-radius: 14px;
  padding: 10px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(0,0,0,0.16);
  display:flex;
  gap: 8px;
  align-items:center;
}
.editnote-tags{ display:flex; gap: 10px; align-items:flex-start; flex-wrap:wrap; }
.tags-chips{ display:flex; gap: 8px; flex-wrap:wrap; }

.fields-grid{
  display:grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
@media (max-width: 920px){
  .fields-grid{ grid-template-columns: 1fr; }
}
.field-card{
  border-radius: 16px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(0,0,0,0.16);
  display:flex;
  flex-direction:column;
  gap: 10px;
}
.field-h{
  display:flex;
  justify-content:space-between;
  gap: 10px;
  flex-wrap:wrap;
  align-items:center;
}
.field-name{ font-weight: 950; letter-spacing: -0.2px; }

/* Translate modal */
.translate-modal{ display:flex; flex-direction:column; gap: 12px; }
.translate-hero{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap: 12px;
  flex-wrap:wrap;
  border-radius: 18px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.14);
  background:
    radial-gradient(600px 180px at 0% 0%, rgba(59,130,246,0.18), transparent 60%),
    radial-gradient(600px 180px at 100% 0%, rgba(16,185,129,0.14), transparent 60%),
    rgba(255,255,255,0.02);
}
.translate-info{
  border-radius: 16px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(0,0,0,0.16);
}
.info-box{
  display:flex;
  gap: 12px;
  align-items:flex-start;
}
.info-box > i{
  font-size: 18px;
  color: #3B82F6;
  margin-top: 2px;
}
.info-title{
  font-weight: 900;
  margin-bottom: 8px;
}
.info-list{
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  opacity: 0.85;
  display:flex;
  flex-direction:column;
  gap: 4px;
}
.info-list code{
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(0,0,0,0.25);
  border: 1px solid rgba(148,163,184,0.16);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
}
.translate-warning{
  display:flex;
  gap: 10px;
  align-items:flex-start;
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px dashed rgba(251,191,36,0.35);
  background: rgba(251,191,36,0.08);
}
.translate-warning > i{
  color: #F59E0B;
  margin-top: 2px;
}
.translate-model-section{
  border-radius: 16px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(0,0,0,0.12);
}
.translate-model-section .section-label{
  display: block;
  font-weight: 700;
  font-size: 13px;
  margin-bottom: 8px;
  opacity: 0.9;
}
.model-selector-row{
  display: flex;
  gap: 8px;
  align-items: center;
}
.model-selector-row .model-select{
  flex: 1;
  min-width: 200px;
}
.model-option{
  display: flex;
  align-items: center;
  gap: 8px;
}
.model-option .model-name{
  font-size: 13px;
}
.model-option .provider-tag{
  font-size: 10px;
  padding: 2px 6px;
}

/* Translate Progress Modal */
.translate-progress-modal{
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 14px;
}

:deep(.translate-progress-modal .p-progressbar) {
  height: 8px;
  border-radius: 4px;
  background: rgba(148, 163, 184, 0.14);
  overflow: hidden;
}

:deep(.translate-progress-modal .p-progressbar-value) {
  background: linear-gradient(90deg, #3B82F6, #10B981);
  transition: width 0.3s ease;
}

.progress-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 12px;
}

.stat {
  display: flex;
  flex-direction: column;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.03);
  text-align: center;
}

.stat-label {
  font-size: 11px;
  font-weight: 900;
  opacity: 0.7;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.stat-value {
  font-size: 20px;
  font-weight: 950;
  letter-spacing: -0.4px;
}

.progress-status {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.02);
}

.status-item {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}

.status-item i {
  font-size: 14px;
  opacity: 0.8;
}

.status-error {
  font-size: 12px;
  color: #ef4444;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.1);
}

.progress-error,
.progress-done {
  display: flex;
  gap: 12px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  align-items: flex-start;
}

.progress-error {
  background: rgba(239, 68, 68, 0.08);
}

.progress-error i {
  color: #ef4444;
  font-size: 20px;
  margin-top: 2px;
}

.progress-done {
  background: rgba(34, 197, 94, 0.08);
}

.progress-done i {
  color: #22c55e;
  font-size: 20px;
  margin-top: 2px;
}

.error-title,
.done-title {
  font-weight: 900;
  margin-bottom: 4px;
  font-size: 13px;
}

.error-msg,
.done-msg {
  font-size: 12px;
  opacity: 0.85;
}

.dlg-icon.spinning i {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Recreate modal */
.recreate-modal{ display:flex; flex-direction:column; gap: 12px; }
.recreate-hero{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap: 12px;
  flex-wrap:wrap;
  border-radius: 18px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.14);
  background:
    radial-gradient(900px 220px at 0% 0%, rgba(99,102,241,0.16), transparent 60%),
    radial-gradient(900px 220px at 100% 0%, rgba(16,185,129,0.12), transparent 60%),
    rgba(255,255,255,0.02);
}
.hero-left{ display:flex; flex-direction:column; gap: 10px; }
.hero-title{ display:flex; gap: 10px; align-items:center; flex-wrap:wrap; }
.hero-pill{
  font-weight: 950;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(148,163,184,0.16);
  background: rgba(0,0,0,0.18);
}
.hero-kpis{
  display:grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 920px){
  .hero-kpis{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.kpi{
  border-radius: 16px;
  padding: 10px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(0,0,0,0.18);
}
.kpi-lbl{ font-size: 12px; opacity: .72; font-weight: 900; }
.kpi-val{ margin-top: 4px; font-size: 18px; font-weight: 950; letter-spacing: -0.4px; }

.hero-right{ display:flex; flex-direction:column; gap: 8px; align-items:flex-start; }

.sections{ display:flex; flex-direction:column; gap: 12px; }
.section{
  border-radius: 18px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(255,255,255,0.02);
  padding: 12px;
}
.section-h{
  display:flex;
  gap: 12px;
  align-items:flex-start;
  justify-content:space-between;
  flex-wrap:wrap;
  margin-bottom: 10px;
}
.section-h > i{
  font-size: 16px;
  padding: 10px;
  border-radius: 14px;
  background: rgba(0,0,0,0.20);
  border: 1px solid rgba(148,163,184,0.14);
}
.section-title{ font-weight: 950; letter-spacing: -0.2px; }
.section-sub{ margin-top: 4px; font-size: 12.5px; opacity: .78; }
.section-right{ display:flex; gap: 8px; align-items:center; }

.grid{
  display:grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 920px){
  .grid{ grid-template-columns: 1fr; }
}
.blk{
  border-radius: 16px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(0,0,0,0.16);
  padding: 12px;
}
.blk-wide{ grid-column: 1 / -1; }
.lbl{ font-weight: 950; opacity: .9; margin-bottom: 8px; }
.inline{ display:flex; gap:10px; align-items:flex-start; flex-wrap:wrap; }
.inline-col{ display:flex; flex-direction:column; gap: 4px; }
.inline-strong{ font-weight: 950; display:flex; align-items:center; flex-wrap:wrap; gap: 8px; }

.qty{ display:flex; gap: 12px; align-items:center; }
.qty-slider{ flex: 1; }
.tiny{ font-size: 12px; opacity: .78; margin-top: 8px; }
.support{ display:flex; gap: 10px; align-items:center; flex-wrap:wrap; margin-top: 10px; }

.recreate-tip{
  display:flex;
  gap: 10px;
  align-items:flex-start;
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px dashed rgba(148,163,184,0.22);
  background: rgba(0,0,0,0.16);
}
.recreate-tip i{ margin-top: 2px; opacity: .9; }

/* Prime controls inside dialogs */
:deep(.dlg .p-inputtext),
:deep(.dlg .p-dropdown),
:deep(.dlg .p-multiselect),
:deep(.dlg .p-inputnumber-input),
:deep(.dlg .p-textarea){
  background: rgba(0,0,0,0.22);
  border-color: rgba(148,163,184,0.18);
}
:deep(.dlg .p-multiselect-label),
:deep(.dlg .p-dropdown-label){
  font-weight: 900;
}
:deep(.dlg .p-multiselect-token){
  border-radius: 999px;
  font-weight: 900;
}

/* Note types list */
.types-list{ max-height: 64vh; overflow:auto; padding: 14px; }
.pad{ padding: 6px 2px; }
.types-grid{
  display:grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
@media (max-width: 920px){
  .types-grid{ grid-template-columns: 1fr; }
}
.type-card{
  border-radius: 16px;
  padding: 12px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(0,0,0,0.16);
}
.type-card.ok{ border-color: rgba(16,185,129,0.20); }
.type-card.no{ border-color: rgba(148,163,184,0.14); opacity: .92; }
.type-top{ display:flex; gap: 10px; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; }
.type-name{ font-weight: 950; letter-spacing: -0.2px; }
.type-sub{ margin-top: 8px; font-size: 12.5px; }

/* small spacing helpers */
.ml-2{ margin-left: 8px; }
.mr-2{ margin-right: 8px; }

/* =========================
   Modern Dialog (PrimeVue)
   (igual GeneratorPage)
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

/* Máscara do modal */
:deep(.p-dialog-mask) {
  backdrop-filter: blur(8px);
  background: rgba(0, 0, 0, 0.55);
}

/* Inputs dentro do dialog mais arredondados/consistentes */
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
</style>
