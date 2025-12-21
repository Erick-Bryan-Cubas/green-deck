<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

// PrimeVue
import Toolbar from 'primevue/toolbar'
import Button from 'primevue/button'
import Select from 'primevue/select'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import Toast from 'primevue/toast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const toast = useToast()

function notify(message, severity = 'info', life = 3200) {
  toast.add({ severity, summary: message, life })
}

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

function flagLabel(f) {
  const m = { 0: '—', 1: 'Red', 2: 'Orange', 3: 'Green', 4: 'Blue' }
  return m[String(f)] || String(f)
}

// ----------------------
// filtros / estado
// ----------------------
const decks = ref([])
const deck = ref('') // vazio = todos
const status = ref('is:review') // aprendidos por default
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

async function fetchDecks() {
  try {
    const r = await fetch('/api/anki-decks')
    const data = await r.json()
    if (!data?.success) throw new Error(data?.error || 'Falha ao buscar decks')
    decks.value = Array.isArray(data.decks) ? data.decks : []
  } catch (e) {
    notify(e?.message || String(e), 'warn', 6000)
  }
}

async function fetchCards() {
  loading.value = true
  try {
    const offset = first.value
    const limit = rows.value

    const url = `/api/anki-cards?query=${encodeURIComponent(queryBuilt.value)}&offset=${offset}&limit=${limit}`
    const r = await fetch(url)
    const data = await r.json()
    if (!data?.success) throw new Error(data?.error || 'Falha ao buscar cards')

    items.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    notify(e?.message || String(e), 'error', 7000)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

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
// recriar cards aprendidos
// ----------------------
const recreating = ref(false)
const recreateTargetDeck = ref('') // opcional
const recreateTag = ref('greendeck_recreated')

async function recreateSelected() {
  if (!selected.value?.length) {
    notify('Selecione 1+ cards para recriar.', 'warn', 4200)
    return
  }

  recreating.value = true
  try {
    const cardIds = selected.value.map((x) => x.cardId)

    const r = await fetch('/api/anki-recreate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cardIds,
        targetDeckName: recreateTargetDeck.value || null,
        addTag: recreateTag.value || null,
        allowDuplicate: true
      })
    })
    const data = await r.json()
    if (!data?.success) throw new Error(data?.error || 'Falha ao recriar')

    notify(`Recriados: ${data.totalCreated}/${data.totalDedupNotes} notas`, 'success', 5200)

    // opcional: atualiza lista
    await fetchCards()
  } catch (e) {
    notify(e?.message || String(e), 'error', 8000)
  } finally {
    recreating.value = false
  }
}

onMounted(async () => {
  await fetchDecks()
  await fetchCards()
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
        </div>
      </template>

      <template #end>
        <div class="hdr-actions">
          <Button icon="pi pi-arrow-left" label="Generator" outlined @click="router.push('/')" />
        </div>
      </template>
    </Toolbar>

    <div class="main">
      <div class="filters">
        <Select
          v-model="deck"
          :options="[{ label: 'Todos os decks', value: '' }, ...decks.map(d => ({ label: d, value: d }))]"
          optionLabel="label"
          optionValue="value"
          filter
          class="w-22"
          placeholder="Deck"
        />

        <Select
          v-model="status"
          :options="statusOptions"
          optionLabel="label"
          optionValue="value"
          class="w-18"
        />

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

      <div class="recreate-bar">
        <InputText v-model="recreateTag" class="w-18" placeholder="Tag extra (opcional)" />
        <Select
          v-model="recreateTargetDeck"
          :options="[{ label: 'Deck original', value: '' }, ...decks.map(d => ({ label: d, value: d }))]"
          optionLabel="label"
          optionValue="value"
          filter
          class="w-22"
          placeholder="Deck destino"
        />

        <Button
          icon="pi pi-copy"
          label="Recriar selecionados (novo)"
          :loading="recreating"
          :disabled="!selected.length"
          @click="recreateSelected"
        />
        <Tag severity="secondary" class="pill">
          Selecionados: {{ selected.length }}
        </Tag>
      </div>

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
        @page="onPage"
        class="dt"
        @rowDblclick="openPreview($event.data)"
      >
        <Column selectionMode="multiple" headerStyle="width:3rem" />
        <Column field="deckName" header="Deck" />
        <Column field="modelName" header="Modelo" />
        <Column header="Queue">
          <template #body="{ data }">
            <Tag :severity="data.queue === 2 ? 'success' : 'secondary'" class="pill">
              {{ queueLabel(data.queue) }}
            </Tag>
          </template>
        </Column>
        <Column field="interval" header="Int (d)" style="width: 7rem;" />
        <Column header="Ease">
          <template #body="{ data }">
            {{ Math.round((data.factor || 0) / 10) }}%
          </template>
        </Column>
        <Column field="reps" header="Reps" style="width: 6rem;" />
        <Column field="lapses" header="Lapses" style="width: 7rem;" />
        <Column header="Flag">
          <template #body="{ data }">
            <span class="muted">{{ flagLabel(data.flags) }}</span>
          </template>
        </Column>
        <Column header="Preview">
          <template #body="{ data }">
            <Button icon="pi pi-eye" text @click="openPreview(data)" />
          </template>
        </Column>
      </DataTable>

      <Dialog v-model:visible="previewVisible" header="Card Preview (Anki HTML)" modal style="width:min(980px,96vw)">
        <div v-if="previewCard" class="preview">
          <div class="pv-col">
            <div class="pv-title">Question</div>
            <div class="pv-box" v-html="previewCard.question"></div>
          </div>
          <div class="pv-col">
            <div class="pv-title">Answer</div>
            <div class="pv-box" v-html="previewCard.answer"></div>
          </div>
        </div>
        <template #footer>
          <Button label="Fechar" icon="pi pi-times" outlined @click="previewVisible=false" />
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

.filters{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.recreate-bar{ margin-top:10px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.query-hint{ margin:10px 0; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.muted{ opacity:.7; }
.q{ padding:2px 8px; border-radius:10px; background: rgba(0,0,0,0.25); border:1px solid rgba(148,163,184,0.16); }

.w-18{ width: 18rem; }
.w-22{ width: 22rem; }
.w-34{ width: 34rem; }

.dt{ margin-top: 12px; }

.preview{ display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 920px){
  .preview{ grid-template-columns: 1fr; }
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

.pill{ border-radius:999px; font-weight:900; }
</style>
