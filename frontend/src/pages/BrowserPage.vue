<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

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
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const toast = useToast()

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
const ollamaHealth = ref({ ok: null, error: '', modelAvailable: null, timeoutS: null, model: null })
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
      modelAvailable: data.modelAvailable ?? null,
      timeoutS: data.timeoutS ?? null,
      model: data.model ?? null
    }
  } catch (e) {
    ollamaHealth.value = { ok: false, error: e?.message || String(e), modelAvailable: null, timeoutS: null, model: null }
  }
}

const ankiStatusTitle = computed(() => {
  if (ankiHealth.value.ok) return `AnkiConnect OK (version=${ankiHealth.value.ankiConnectVersion})`
  if (ankiHealth.value.ok === null) return 'AnkiConnect: verificando...'
  return `AnkiConnect OFF: ${ankiHealth.value.error || 'erro desconhecido'}`
})

const ollamaStatusTitle = computed(() => {
  if (ollamaHealth.value.ok) {
    const avail = ollamaHealth.value.modelAvailable ? 'model OK' : 'model NÃO encontrado'
    return `Ollama OK (${avail}) • model=${ollamaHealth.value.model || '—'} • timeout=${ollamaHealth.value.timeoutS ?? '—'}s`
  }
  if (ollamaHealth.value.ok === null) return 'Ollama: verificando...'
  return `Ollama OFF: ${ollamaHealth.value.error || 'erro desconhecido'}`
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
// paginação / dados
// ----------------------
const loading = ref(false)
const items = ref([])
const total = ref(0)
const first = ref(0)
const rows = ref(50)

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

// Debounce filtros
let debounce = null
watch([deck, status, text, advancedQuery], () => {
  first.value = 0
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(fetchCards, 450)
})

function onPage(e) {
  first.value = e.first
  rows.value = e.rows
  fetchCards()
}

// ----------------------
// Note Types (com suporte vindo do backend)
// ----------------------
const noteTypesVisible = ref(false)
const noteTypesLoaded = ref(false)
const noteTypes = ref([]) // [{name, supported, family, supportLabel}]
const supportedNoteTypes = computed(() => noteTypes.value.filter((x) => !!x.supported))

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
// Modal Recreate (SLM/Ollama)
// ----------------------
const recreating = ref(false)
const recreateTargetDeck = ref('')

const recreateDialogVisible = ref(false)
const recreateSuspendOriginal = ref(true)
const recreateCountPerNote = ref(1)

const difficultyOptions = [
  { label: 'Fácil', value: 'easy' },
  { label: 'Difícil (neutra)', value: 'hard_neutral' },
  { label: 'Difícil (técnica)', value: 'hard_technical' }
]
const recreateDifficulty = ref('easy')

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

function openRecreateDialog() {
  if (!selected.value?.length) {
    notify('Selecione 1+ cards para recriar.', 'warn', 4200)
    return
  }
  recreateDialogVisible.value = true
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
    addLog(`Health: Anki=${ankiHealth.value.ok ? 'ON' : 'OFF'} | Ollama=${ollamaHealth.value.ok ? 'ON' : 'OFF'}`, ankiHealth.value.ok && ollamaHealth.value.ok ? 'info' : 'warn')
    if (!ankiHealth.value.ok) addLog(`Health Anki error: ${ankiHealth.value.error}`, 'error')
    if (!ollamaHealth.value.ok) addLog(`Health Ollama error: ${ollamaHealth.value.error}`, 'error')
    if (ollamaHealth.value.ok && ollamaHealth.value.modelAvailable === false) {
      addLog(`Ollama: modelo "${ollamaHealth.value.model}" não encontrado em /api/tags`, 'warn')
    }

    const cardIds = selected.value.map((x) => x.cardId)
    const payload = {
      cardIds,
      targetDeckName: recreateTargetDeck.value || null,

      // tags: manter as mesmas do card original (backend)
      // NÃO enviar addTag aqui

      allowDuplicate: true,
      suspendOriginal: !!recreateSuspendOriginal.value,
      countPerNote: Number(recreateCountPerNote.value || 1),
      targetModelNames: [...selectedTargetModels.value],

      // NOVO: dificuldade da recriação
      difficulty: recreateDifficulty.value
    }

    addLog(
      `Recreate(SLM) start: cards=${cardIds.length} targetModels=${payload.targetModelNames.join(', ')} difficulty=${payload.difficulty} countPerNote=${payload.countPerNote} suspend=${payload.suspendOriginal}`,
      'info'
    )

    const r = await fetch('/api/anki-recreate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    addLog(`Recreate(SLM) HTTP status=${r.status} ${r.statusText || ''}`, r.status >= 400 ? 'error' : r.status === 207 ? 'warn' : 'info')

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
      addLog(`Recreate timings: cardsInfo=${ms(data.timings.cardsInfoMs)} modelFields=${ms(data.timings.modelFieldNamesMs)} total=${ms(data.timings.totalMs)}`, 'info')
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

    addLog(`Recreate(SLM) done: notes=${notes} created=${created} failed=${failed} suspendedCards=${suspended}`, failed ? 'warn' : 'success')

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

  await fetchDecks()
  await fetchCards()
})

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
})
</script>

<template>
  <Toast />

  <div class="app-shell">
    <Toolbar class="app-header">
      <template #start>
        <div class="brand">
          <img src="/green-header.svg" alt="Green Deck" class="brand-header-logo" />
          <Tag severity="success" class="pill">/browser</Tag>

          <!-- Status badges -->
          <div class="svc-wrap">
            <span class="svc-pill" :class="ankiHealth.ok ? 'on' : ankiHealth.ok === null ? 'idle' : 'off'" :title="ankiStatusTitle">
              <i class="pi" :class="ankiHealth.ok ? 'pi-check-circle' : ankiHealth.ok === null ? 'pi-spin pi-spinner' : 'pi-times-circle'"></i>
              <span>Anki</span>
            </span>

            <span class="svc-pill" :class="ollamaHealth.ok ? 'on' : ollamaHealth.ok === null ? 'idle' : 'off'" :title="ollamaStatusTitle">
              <i class="pi" :class="ollamaHealth.ok ? 'pi-check-circle' : ollamaHealth.ok === null ? 'pi-spin pi-spinner' : 'pi-times-circle'"></i>
              <span>Ollama</span>
            </span>
          </div>
        </div>
      </template>

      <template #end>
        <div class="hdr-actions">
          <Button icon="pi pi-list" label="Logs" severity="secondary" outlined @click="logsVisible = true" />
          <Button icon="pi pi-arrow-left" label="Generator" outlined @click="router.push('/')" />
        </div>
      </template>
    </Toolbar>

    <div class="main">
      <div class="filters card-surface">
        <div class="filters-row">
          <Select
            v-model="deck"
            :options="[{ label: 'Todos os decks', value: '' }, ...decks.map(d => ({ label: d, value: d }))]"
            optionLabel="label"
            optionValue="value"
            filter
            class="w-22"
            placeholder="Deck"
          />

          <Select v-model="status" :options="statusOptions" optionLabel="label" optionValue="value" class="w-18" />

          <InputText v-model="text" class="w-22" placeholder="Buscar texto (Anki query terms)..." />

          <InputText v-model="advancedQuery" class="w-34" placeholder='Query avançada (ex: deck:"X" is:review tag:y)' />

          <Button icon="pi pi-refresh" label="Atualizar" outlined @click="fetchCards" />
        </div>

        <div class="query-hint">
          <span class="muted">Query:</span>
          <code class="q">{{ queryBuilt }}</code>
          <span class="muted">Total:</span>
          <b>{{ total }}</b>
        </div>
      </div>

      <div class="recreate-bar card-surface">
        <div class="recreate-left">
          <Select
            v-model="recreateTargetDeck"
            :options="[{ label: 'Deck original', value: '' }, ...decks.map(d => ({ label: d, value: d }))]"
            optionLabel="label"
            optionValue="value"
            filter
            class="w-22"
            placeholder="Deck destino"
          />
        </div>

        <div class="recreate-right">
          <Button icon="pi pi-copy" label="Recriar (SLM)" :disabled="!selected.length" @click="openRecreateDialog" />
          <Tag severity="secondary" class="pill">Selecionados: {{ selected.length }}</Tag>
        </div>
      </div>

      <div class="table-card card-surface">
        <DataTable
          :value="items"
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
          @page="onPage"
          class="dt modern-dt"
          tableStyle="min-width: 62rem"
          @rowDblclick="openPreview($event.data)"
        >
          <template #header>
            <div class="dt-header">
              <div class="dt-title">
                <span class="title">Anki Browser</span>
                <span class="subtitle">Duplo clique para preview • Recriação via SLM/Ollama</span>
              </div>
              <div class="dt-actions">
                <Button icon="pi pi-refresh" rounded raised @click="fetchCards" title="Atualizar" />
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
      <Dialog v-model:visible="previewVisible" header="Card Preview (Anki HTML)" modal style="width:min(980px,96vw)">
        <div v-if="previewCard" class="preview">
          <div class="pv-meta">
            <Tag class="pill" severity="secondary"><i class="pi pi-hashtag mr-2" /> cardId: {{ previewCard.cardId }}</Tag>
            <Tag class="pill" severity="secondary"><i class="pi pi-file mr-2" /> noteId: {{ previewCard.noteId || previewCard.note || '—' }}</Tag>
            <Tag class="pill" :severity="queueSeverity(previewCard.queue)"><i class="pi pi-circle-fill mr-2" /> {{ queueLabel(previewCard.queue) }}</Tag>
            <Tag class="pill" severity="info"><i class="pi pi-tag mr-2" /> {{ previewCard.deckName }}</Tag>
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
          <Button label="Fechar" icon="pi pi-times" outlined @click="previewVisible=false" />
        </template>
      </Dialog>

      <!-- Modal Recreate (SLM/Ollama) -->
      <Dialog v-model:visible="recreateDialogVisible" header="Recriar via SLM/Ollama" modal style="width:min(980px,96vw)">
        <div class="recreate-modal">
          <div class="row">
            <Tag severity="secondary" class="pill">Selecionados: {{ selected.length }}</Tag>
            <div class="muted help">
              Selecione 1+ Note Types <b>Suportados</b>. Dificuldade controla como o SLM “reescreve” o conteúdo.
            </div>
          </div>

          <Divider />

          <div class="grid">
            <div class="blk">
              <div class="lbl">Dificuldade</div>
              <Select v-model="recreateDifficulty" :options="difficultyOptions" optionLabel="label" optionValue="value" class="w-100" />
              <div class="muted tiny" style="margin-top:8px;">
                {{ difficultyHelp }}
              </div>
            </div>

            <div class="blk">
              <div class="lbl">Suspender originais?</div>
              <div class="inline">
                <InputSwitch v-model="recreateSuspendOriginal" />
                <span class="muted">
                  {{ recreateSuspendOriginal ? 'Sim (suspende todas as cards das notas)' : 'Não (mantém tudo)' }}
                </span>
              </div>
            </div>

            <div class="blk" style="grid-column: 1 / -1;">
              <div class="lbl">Quantas (por nota)</div>
              <div class="qty">
                <Slider v-model="recreateCountPerNote" :min="1" :max="20" class="qty-slider" />
                <InputNumber v-model="recreateCountPerNote" :min="1" :max="50" showButtons />
              </div>
              <div class="muted tiny">
                Ex.: 3 notas selecionadas, 2 Note Types, quantidade 2 → cria 3 * 2 * 2 = 12 novas notas.
              </div>
            </div>
          </div>

          <Divider />

          <div class="blk">
            <div class="lbl">Note Types (alvo)</div>

            <MultiSelect
              v-model="selectedTargetModels"
              :options="noteTypes.map(x => ({ label: `${x.name} — ${x.supportLabel}`, value: x.name, disabled: !x.supported }))"
              optionLabel="label"
              optionValue="value"
              optionDisabled="disabled"
              filter
              display="chip"
              placeholder="Selecione 1+ Note Types"
              class="w-100"
            />

            <div class="support">
              <!-- ✅ correção: sem JS multi-linha dentro do template -->
              <Button icon="pi pi-list" label="Consultar Note Types" severity="secondary" outlined @click="openNoteTypesDialog" />
              <Tag v-if="selectedTargetModels.length" severity="success" class="pill">
                Selecionados: {{ selectedTargetModels.length }}
              </Tag>
            </div>
          </div>

          <div class="row actions">
            <div class="spacer"></div>
            <Button label="Cancelar" icon="pi pi-times" severity="secondary" outlined @click="recreateDialogVisible=false" />
            <Button label="Recriar agora" icon="pi pi-check" :disabled="!canConfirmRecreate" :loading="recreating" @click="confirmRecreate" />
          </div>
        </div>
      </Dialog>

      <!-- Consultar Note Types -->
      <Dialog v-model:visible="noteTypesVisible" header="Note Types disponíveis no Anki" modal style="width:min(780px,96vw)">
        <div class="types-list">
          <div v-if="!noteTypesLoaded" class="muted">Carregando...</div>
          <div v-else-if="!noteTypes.length" class="muted">Nenhum Note Type encontrado.</div>
          <div v-else>
            <div v-for="(t, i) in noteTypes" :key="i" class="type-row">
              <span class="type-name">{{ t.name }}</span>
              <Tag v-if="t.supported" severity="success" class="pill">Suportado</Tag>
              <Tag v-else severity="secondary" class="pill">Sem suporte</Tag>
            </div>
          </div>
        </div>

        <template #footer>
          <Button label="Fechar" icon="pi pi-times" @click="noteTypesVisible=false" />
        </template>
      </Dialog>

      <!-- Logs -->
      <Dialog v-model:visible="logsVisible" header="🔍 Logs (Browser)" modal style="width:min(980px,96vw);">
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
    </div>
  </div>
</template>

<style scoped>
.app-shell{
  height: 100vh;
  display:flex;
  flex-direction:column;
  background:
    radial-gradient(1200px 700px at 12% -10%, rgba(99, 102, 241, 0.25), transparent 55%),
    radial-gradient(900px 600px at 95% 10%, rgba(16, 185, 129, 0.18), transparent 60%),
    radial-gradient(900px 600px at 60% 110%, rgba(236, 72, 153, 0.14), transparent 55%),
    linear-gradient(180deg, rgba(10, 10, 12, 0.0), rgba(10, 10, 12, 0.35));
}
.main{ flex:1; min-height:0; padding:14px; overflow:auto; }
.app-header{ position:sticky; top:0; z-index:50; border:0; padding:14px; backdrop-filter: blur(10px); }
:deep(.p-toolbar){ background: rgba(17, 24, 39, 0.60); border-bottom: 1px solid rgba(148, 163, 184, 0.18); }

.brand{ display:flex; align-items:center; gap:10px; }
.brand-header-logo{ height:40px; width:auto; display:block; filter: drop-shadow(0 10px 24px rgba(0,0,0,0.25)); }
.hdr-actions{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }

.svc-wrap{ display:flex; gap:8px; align-items:center; margin-left:6px; flex-wrap:wrap; }
.svc-pill{
  display:inline-flex;
  gap:8px;
  align-items:center;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(148,163,184,0.16);
  background: rgba(0,0,0,0.25);
  font-weight: 900;
  font-size: 12px;
  cursor: default;
}
.svc-pill i{ font-size: 14px; }
.svc-pill.on{ border-color: rgba(16, 185, 129, 0.35); }
.svc-pill.off{ border-color: rgba(239, 68, 68, 0.35); }
.svc-pill.idle{ border-color: rgba(148, 163, 184, 0.25); opacity: .9; }
.svc-pill.on i{ color: #22c55e; }
.svc-pill.off i{ color: #ef4444; }
.svc-pill.idle i{ color: rgba(148, 163, 184, 0.9); }

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
}

/* Logs */
.logs-wrap{ max-height: 60vh; overflow: auto; padding: 6px 2px; }
.logs-empty{ opacity: 0.75; padding: 10px; }
.log-row{
  display:flex;
  gap:10px;
  padding: 6px 8px;
  border-radius: 10px;
  margin-bottom: 6px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(148, 163, 184, 0.10);
}
.log-ts{ opacity: 0.7; white-space: nowrap; }
.log-msg{ opacity: 0.92; }
.log-row.t-success{ border-color: rgba(16, 185, 129, 0.25); }
.log-row.t-warn{ border-color: rgba(251, 191, 36, 0.25); }
.log-row.t-error{ border-color: rgba(239, 68, 68, 0.25); }

/* Recreate modal */
.recreate-modal{ display:flex; flex-direction:column; gap: 10px; }
.recreate-modal .row{ display:flex; gap: 10px; align-items:center; flex-wrap: wrap; }
.recreate-modal .actions{ margin-top: 6px; }
.recreate-modal .spacer{ flex:1; }
.recreate-modal .grid{
  display:grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 920px){
  .recreate-modal .grid{ grid-template-columns: 1fr; }
}
.blk{
  border-radius: 14px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(255,255,255,0.02);
  padding: 12px;
}
.lbl{ font-weight: 900; opacity: .9; margin-bottom: 8px; }
.inline{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.qty{ display:flex; gap: 12px; align-items:center; }
.qty-slider{ flex: 1; }
.tiny{ font-size: 12px; opacity: .75; margin-top: 6px; }
.support{ display:flex; gap: 10px; align-items:center; flex-wrap:wrap; margin-top: 10px; }

/* Note types list */
.types-list{ max-height: 60vh; overflow:auto; padding: 4px; }
.type-row{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(148,163,184,0.10);
  background: rgba(255,255,255,0.02);
  margin-bottom: 8px;
}
.type-name{ opacity: .92; }
</style>
