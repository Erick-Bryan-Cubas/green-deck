<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

// PrimeVue
import Toolbar from 'primevue/toolbar'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Card from 'primevue/card'
import Chart from 'primevue/chart'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import SelectButton from 'primevue/selectbutton'
import Skeleton from 'primevue/skeleton'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const toast = useToast()

function notify(message, severity = 'info', life = 3200) {
  toast.add({ severity, summary: message, life })
}

// --- helpers ---
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

// --- state ---
const loading = ref(true)
const errorMsg = ref('')

const rangeOptions = [
  { label: '7d', value: 7 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
  { label: '365d', value: 365 }
]
const days = ref(30)

// payloads do backend
const summary = ref(null) // { totalCards, totalDecks, totalTags, createdInRange, avgPerDay }
const byDay = ref([]) // [{day:"2025-12-01", created:123}]
const topDecks = ref([]) // [{deckName, count}]
const topTags = ref([]) // [{tag, count}]

// charts
const lineData = computed(() => {
  const labels = byDay.value.map((x) => x.day)
  const data = byDay.value.map((x) => Number(x.created || 0))
  return {
    labels,
    datasets: [
      {
        label: `Cards criados (${days.value}d)`,
        data,
        tension: 0.35,
        fill: true
      }
    ]
  }
})

const lineOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: true }
  },
  scales: {
    x: { ticks: { maxRotation: 0, autoSkip: true } },
    y: { beginAtZero: true }
  }
}))

const doughnutData = computed(() => {
  const items = topDecks.value.slice(0, 8)
  const labels = items.map((x) => x.deckName || '—')
  const data = items.map((x) => Number(x.count || 0))
  return {
    labels,
    datasets: [{ label: 'Top decks', data }]
  }
})

const doughnutOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'bottom' } }
}))

// --- fetch ---
async function fetchDashboard() {
  loading.value = true
  errorMsg.value = ''

  try {
    // summary
    {
      const r = await fetch(`/api/dashboard/summary?days=${encodeURIComponent(String(days.value))}`)
      const data = await readJsonSafe(r)
      if (data?.__nonJson) throw new Error(`summary non-JSON: ${data.__head}`)
      if (r.status >= 400 || data?.success === false) throw new Error(data?.error || `summary HTTP ${r.status}`)
      summary.value = data
    }

    // by-day
    {
      const r = await fetch(`/api/dashboard/by-day?days=${encodeURIComponent(String(days.value))}`)
      const data = await readJsonSafe(r)
      if (data?.__nonJson) throw new Error(`by-day non-JSON: ${data.__head}`)
      if (r.status >= 400 || data?.success === false) throw new Error(data?.error || `by-day HTTP ${r.status}`)
      byDay.value = Array.isArray(data?.items) ? data.items : []
    }

    // top decks
    {
      const r = await fetch(`/api/dashboard/top-decks?limit=12`)
      const data = await readJsonSafe(r)
      if (data?.__nonJson) throw new Error(`top-decks non-JSON: ${data.__head}`)
      if (r.status >= 400 || data?.success === false) throw new Error(data?.error || `top-decks HTTP ${r.status}`)
      topDecks.value = Array.isArray(data?.items) ? data.items : []
    }

    // top tags (opcional)
    {
      const r = await fetch(`/api/dashboard/top-tags?limit=16`)
      const data = await readJsonSafe(r)
      if (data?.__nonJson) {
        // se você ainda não tiver tags no backend, não quebra o dashboard
        topTags.value = []
      } else if (r.status >= 400 || data?.success === false) {
        topTags.value = []
      } else {
        topTags.value = Array.isArray(data?.items) ? data.items : []
      }
    }
  } catch (e) {
    errorMsg.value = e?.message || String(e)
    notify(errorMsg.value, 'error', 7000)
  } finally {
    loading.value = false
  }
}

onMounted(fetchDashboard)

const kpiTotalCards = computed(() => summary.value?.totalCards ?? '—')
const kpiCreated = computed(() => summary.value?.createdInRange ?? '—')
const kpiDecks = computed(() => summary.value?.totalDecks ?? '—')
const kpiAvg = computed(() => {
  const v = summary.value?.avgPerDay
  if (v === null || v === undefined) return '—'
  return Number(v).toFixed(2)
})
</script>

<template>
  <Toast />

  <div class="app-shell">
    <Toolbar class="app-header">
      <template #start>
        <div class="brand">
          <img src="/green-header.svg" alt="Green Deck" class="brand-header-logo" />
          <Tag severity="success" class="pill">/dashboard</Tag>

          <div class="range">
            <span class="muted">Range:</span>
            <SelectButton v-model="days" :options="rangeOptions" optionLabel="label" optionValue="value" />
          </div>
        </div>
      </template>

      <template #end>
        <div class="hdr-actions">
          <Button icon="pi pi-refresh" label="Atualizar" outlined @click="fetchDashboard" />
          <Button icon="pi pi-list" label="Browser" outlined @click="router.push('/browser')" />
          <Button icon="pi pi-arrow-left" label="Generator" outlined @click="router.push('/')" />
        </div>
      </template>
    </Toolbar>

    <div class="main">
      <div v-if="errorMsg" class="err card-surface">
        <i class="pi pi-exclamation-triangle"></i>
        <div>
          <div class="err-title">Falha ao carregar o Dashboard</div>
          <div class="err-sub muted">{{ errorMsg }}</div>
        </div>
      </div>

      <!-- KPIs -->
      <div class="kpis">
        <Card class="kpi card-surface">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-clone" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Total de cards</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="8rem" height="1.6rem" />
                  <span v-else>{{ kpiTotalCards }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi card-surface">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-plus-circle" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Criados no período</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="8rem" height="1.6rem" />
                  <span v-else>{{ kpiCreated }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi card-surface">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-sitemap" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Decks no DB</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="8rem" height="1.6rem" />
                  <span v-else>{{ kpiDecks }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi card-surface">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-chart-line" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Média / dia</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="8rem" height="1.6rem" />
                  <span v-else>{{ kpiAvg }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>
      </div>

      <!-- Charts row -->
      <div class="grid">
        <div class="card-surface chart-card">
          <div class="chart-h">
            <div class="chart-title">Criação de cards (por dia)</div>
            <Tag class="pill" severity="secondary">{{ days }}d</Tag>
          </div>

          <div class="chart-body">
            <Skeleton v-if="loading" width="100%" height="260px" />
            <Chart v-else type="line" :data="lineData" :options="lineOptions" style="height: 280px;" />
          </div>
        </div>

        <div class="card-surface chart-card">
          <div class="chart-h">
            <div class="chart-title">Top decks (distribuição)</div>
            <Tag class="pill" severity="secondary">Top 8</Tag>
          </div>

          <div class="chart-body">
            <Skeleton v-if="loading" width="100%" height="260px" />
            <Chart v-else type="doughnut" :data="doughnutData" :options="doughnutOptions" style="height: 280px;" />
          </div>
        </div>
      </div>

      <!-- Tables -->
      <div class="grid">
        <div class="card-surface table-card">
          <div class="chart-h">
            <div class="chart-title">Top decks</div>
            <Tag class="pill" severity="secondary">{{ topDecks.length }}</Tag>
          </div>

          <DataTable :value="topDecks" stripedRows rowHover class="modern-dt" :loading="loading">
            <Column field="deckName" header="Deck" />
            <Column field="count" header="Cards" style="width: 8rem;" />
          </DataTable>
        </div>

        <div class="card-surface table-card">
          <div class="chart-h">
            <div class="chart-title">Top tags</div>
            <Tag class="pill" severity="secondary">{{ topTags.length }}</Tag>
          </div>

          <div v-if="!loading && !topTags.length" class="muted pad">
            (Opcional) Se o seu DB ainda não guarda tags, essa seção pode ficar vazia.
          </div>

          <DataTable v-else :value="topTags" stripedRows rowHover class="modern-dt" :loading="loading">
            <Column field="tag" header="Tag" />
            <Column field="count" header="Cards" style="width: 8rem;" />
          </DataTable>
        </div>
      </div>
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

.brand{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.brand-header-logo{ height:40px; width:auto; display:block; filter: drop-shadow(0 10px 24px rgba(0,0,0,0.25)); }

.hdr-actions{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.range{ display:flex; gap:10px; align-items:center; margin-left:8px; flex-wrap:wrap; }

.card-surface{
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(17, 24, 39, 0.58);
  backdrop-filter: blur(10px);
  box-shadow: 0 14px 30px rgba(0,0,0,0.26);
  padding: 12px;
}

.kpis{
  display:grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 980px){
  .kpis{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px){
  .kpis{ grid-template-columns: 1fr; }
}

.kpi{ padding: 0; }
.kpi :deep(.p-card-body){ padding: 12px; }
.kpi-top{ display:flex; gap: 12px; align-items:center; }
.kpi-ico{
  width: 44px; height: 44px;
  border-radius: 14px;
  display:flex; align-items:center; justify-content:center;
  background: rgba(0,0,0,0.22);
  border: 1px solid rgba(148, 163, 184, 0.16);
}
.kpi-ico i{ font-size: 18px; opacity: .95; }
.kpi-lbl{ font-weight: 900; font-size: 12px; opacity: .75; }
.kpi-val{ margin-top: 4px; font-size: 18px; font-weight: 950; letter-spacing: -0.3px; }

.grid{
  margin-top: 12px;
  display:grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 980px){
  .grid{ grid-template-columns: 1fr; }
}

.chart-card{ min-height: 360px; }
.table-card{ padding: 12px; }

.chart-h{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.chart-title{ font-weight: 950; letter-spacing: -0.2px; }
.chart-body{ min-height: 300px; }

.pill{ border-radius:999px; font-weight:900; }
.muted{ opacity:.75; }
.pad{ padding: 10px 4px; }

:deep(.modern-dt .p-datatable-thead > tr > th){
  background: rgba(255,255,255,0.03);
  border-color: rgba(148,163,184,0.14);
  font-weight: 900;
}
:deep(.modern-dt .p-datatable-tbody > tr > td){ border-color: rgba(148,163,184,0.12); }

.err{
  display:flex; gap: 12px; align-items:flex-start;
  margin-bottom: 12px;
}
.err i{ font-size: 18px; margin-top: 2px; }
.err-title{ font-weight: 950; }
</style>
