<!-- frontend/src/pages/DashBoardPage.vue -->
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
import Skeleton from 'primevue/skeleton'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const toast = useToast()

function notify(message, severity = 'info', life = 3200) {
  toast.add({ severity, summary: message, life })
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
  { key: 'generator', label: 'Generator', icon: 'pi pi-bolt', iconColor: '#10B981', tooltip: 'Gerar flashcards', command: () => { router.push('/'); closeSidebar() } },
  { key: 'browser', label: 'Browser', icon: 'pi pi-database', iconColor: '#3B82F6', tooltip: 'Navegar pelos cards salvos', command: () => { router.push('/browser'); closeSidebar() } },
  { key: 'dashboard', label: 'Dashboard', icon: 'pi pi-chart-bar', iconColor: '#F59E0B', tooltip: 'Estatísticas de estudo', active: true },
  { separator: true },
  {
    key: 'actions',
    label: 'Ações',
    icon: 'pi pi-cog',
    iconColor: '#64748B',
    tooltip: 'Ações rápidas',
    submenu: [
      { label: 'Atualizar dados', icon: 'pi pi-refresh', iconColor: '#10B981', command: () => { fetchDashboard(); closeSidebar() } }
    ]
  }
])

const sidebarFooterActions = computed(() => [
  { icon: 'pi pi-question-circle', tooltip: 'Ajuda', command: () => notify('Documentação em breve!', 'info') },
  { icon: 'pi pi-moon', tooltip: 'Tema', command: () => notify('Tema alternativo em breve!', 'info') }
])

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

function formatInt(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return new Intl.NumberFormat('pt-BR').format(Math.trunc(n))
}
function format2(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(2).replace('.', ',')
}

// --- state ---
const loading = ref(true)
const errorMsg = ref('')

// payloads do backend
const summary = ref(null) // { totalCards, totalDecks, createdTotal, avgPerDay, statusBreakdown, segmentsMeta }
const byDay = ref([]) // [{day:"YYYY-MM-DD", created:123}]
const topDecks = ref([]) // [{deckName, count}]
const segments = ref([]) // [{segment, count, avgInterval, avgEase, avgLapses, avgReps}]

// ---------- KPIs ----------
const kpiTotalCards = computed(() => summary.value?.totalCards ?? null)
const kpiCreated = computed(() => summary.value?.createdTotal ?? summary.value?.totalCards ?? null)
const kpiDecks = computed(() => summary.value?.totalDecks ?? null)
const kpiAvg = computed(() => summary.value?.avgPerDay ?? null)

const firstDay = computed(() => (byDay.value?.length ? byDay.value[0]?.day : null))
const lastDay = computed(() => (byDay.value?.length ? byDay.value[byDay.value.length - 1]?.day : null))

// ---------- Doughnut meta ----------
const statusItems = computed(() => {
  const items = Array.isArray(summary.value?.statusBreakdown) ? summary.value.statusBreakdown : []
  const total = items.reduce((s, x) => s + Number(x?.count || 0), 0) || 0
  return items
    .map((x) => {
      const c = Number(x?.count || 0)
      return { status: x?.status ?? '—', count: c, pct: total ? (100 * c) / total : 0 }
    })
    .sort((a, b) => b.count - a.count)
})
const statusTotal = computed(() => statusItems.value.reduce((s, x) => s + (x.count || 0), 0))

// ---------- Charts ----------
const lineData = computed(() => {
  const labels = byDay.value.map((x) => x.day)
  const data = byDay.value.map((x) => Number(x.created || 0))
  return {
    labels,
    datasets: [
      {
        label: 'Cards criados (all-time)',
        data,
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        pointHitRadius: 10
      }
    ]
  }
})

const lineOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: {
      display: true,
      labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true }
    },
    tooltip: { mode: 'index', intersect: false }
  },
  scales: {
    x: {
      ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 10 },
      grid: { display: false }
    },
    y: {
      beginAtZero: true,
      ticks: { maxTicksLimit: 6 },
      grid: { drawBorder: false }
    }
  }
}))

// Doughnut: Tipos/Status do Anki
const statusDoughnutData = computed(() => {
  const labels = statusItems.value.map((x) => x.status)
  const data = statusItems.value.map((x) => Number(x.count || 0))
  return { labels, datasets: [{ label: 'Tipos', data, borderWidth: 0, hoverOffset: 6 }] }
})

const doughnutOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  cutout: '72%',
  plugins: {
    legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
    tooltip: {
      callbacks: {
        label: (ctx) => {
          const label = ctx.label || '—'
          const val = ctx.parsed || 0
          const total = statusTotal.value || 0
          const pct = total ? ((100 * val) / total).toFixed(1).replace('.', ',') : '0,0'
          return `${label}: ${formatInt(val)} (${pct}%)`
        }
      }
    }
  }
}))

// Barras: Total por deck (melhor legibilidade = horizontal)
const deckBarData = computed(() => {
  const items = topDecks.value || []
  const labels = items.map((x) => x.deckName || '—')
  const data = items.map((x) => Number(x.count || 0))
  return { labels, datasets: [{ label: 'Cards por deck (Top 12)', data, borderRadius: 10 }] }
})

const deckBarOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  indexAxis: 'y',
  plugins: {
    legend: { display: true, labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
    tooltip: {
      callbacks: {
        label: (ctx) => `${formatInt(ctx.parsed.x)} cards`
      }
    }
  },
  scales: {
    x: { beginAtZero: true, ticks: { maxTicksLimit: 6 }, grid: { drawBorder: false } },
    y: { ticks: { autoSkip: false }, grid: { display: false } }
  }
}))

// Barras: Segmentos (KMeans)
const segmentsBarData = computed(() => {
  const items = segments.value || []
  const labels = items.map((x) => x.segment || '—')
  const data = items.map((x) => Number(x.count || 0))
  return { labels, datasets: [{ label: 'Distribuição por segmento', data, borderRadius: 10 }] }
})

const segmentsBarOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: true, labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } }
  },
  scales: {
    x: { grid: { display: false } },
    y: { beginAtZero: true, ticks: { maxTicksLimit: 6 }, grid: { drawBorder: false } }
  }
}))

const segmentsMetaText = computed(() => {
  const m = summary.value?.segmentsMeta
  if (!m) return ''
  const k = m.k ?? '—'
  const sampled = m.sampled ?? '—'
  return `K=${k} · amostra=${sampled}`
})

// --- fetch ---
async function fetchDashboard() {
  loading.value = true
  errorMsg.value = ''

  try {
    // summary
    {
      const r = await fetch('/api/dashboard/summary')
      const data = await readJsonSafe(r)
      if (data?.__nonJson) throw new Error(`summary non-JSON: ${data.__head}`)
      if (r.status >= 400 || data?.success === false) throw new Error(data?.error || `summary HTTP ${r.status}`)
      summary.value = data
    }

    // by-day
    {
      const r = await fetch('/api/dashboard/by-day')
      const data = await readJsonSafe(r)
      if (data?.__nonJson) throw new Error(`by-day non-JSON: ${data.__head}`)
      if (r.status >= 400 || data?.success === false) throw new Error(data?.error || `by-day HTTP ${r.status}`)
      byDay.value = Array.isArray(data?.items) ? data.items : []
    }

    // top decks
    {
      const r = await fetch('/api/dashboard/top-decks?limit=12')
      const data = await readJsonSafe(r)
      if (data?.__nonJson) throw new Error(`top-decks non-JSON: ${data.__head}`)
      if (r.status >= 400 || data?.success === false) throw new Error(data?.error || `top-decks HTTP ${r.status}`)
      topDecks.value = Array.isArray(data?.items) ? data.items : []
    }

    // segments (KMeans)
    {
      const r = await fetch('/api/dashboard/segments')
      const data = await readJsonSafe(r)
      if (data?.__nonJson) throw new Error(`segments non-JSON: ${data.__head}`)
      if (r.status >= 400 || data?.success === false) throw new Error(data?.error || `segments HTTP ${r.status}`)
      segments.value = Array.isArray(data?.items) ? data.items : []
    }
  } catch (e) {
    errorMsg.value = e?.message || String(e)
    notify(errorMsg.value, 'error', 7000)
  } finally {
    loading.value = false
  }
}

onMounted(fetchDashboard)
</script>

<template>
  <Toast />

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
        v-tooltip.right="sidebarExpanded ? 'Recolher menu' : 'Expandir menu'"
      />
    </div>

    <nav class="sidebar-nav">
      <template v-for="(item, idx) in sidebarMenuItems" :key="idx">
        <div v-if="item.separator" class="sidebar-separator"></div>
        
        <div v-else-if="item.submenu" class="sidebar-item has-submenu">
          <button 
            class="sidebar-link" 
            :class="{ 'expanded': expandedMenus.has(item.key), 'active': item.active }"
            @click="toggleSubmenu(item.key)"
            v-tooltip.right="!sidebarExpanded ? { value: item.tooltip || item.label, showDelay: 300 } : null"
          >
            <span class="sidebar-icon-wrap" :style="{ '--icon-color': item.iconColor }">
              <i :class="item.icon" class="sidebar-icon"></i>
            </span>
            <Transition name="fade">
              <span v-if="sidebarExpanded" class="sidebar-label">{{ item.label }}</span>
            </Transition>
            <Transition name="fade">
              <Tag v-if="sidebarExpanded && item.badge" :severity="item.badge > 0 ? 'success' : 'secondary'" class="sidebar-badge">{{ item.badge }}</Tag>
            </Transition>
            <Transition name="fade">
              <i v-if="sidebarExpanded" class="pi pi-chevron-down sidebar-chevron"></i>
            </Transition>
          </button>
          
          <Transition name="submenu">
            <div v-if="sidebarExpanded && expandedMenus.has(item.key)" class="sidebar-submenu">
              <template v-for="(sub, subIdx) in item.submenu" :key="subIdx">
                <div v-if="sub.separator" class="submenu-separator"></div>
                <button 
                  v-else
                  class="submenu-link" 
                  :class="{ 'disabled': sub.disabled, 'active': sub.active, 'danger': sub.danger }"
                  :disabled="sub.disabled"
                  @click="sub.command?.()"
                >
                  <span class="submenu-icon-wrap" :style="{ '--icon-color': sub.iconColor }">
                    <i :class="sub.icon" class="submenu-icon"></i>
                  </span>
                  <div class="submenu-text">
                    <span class="submenu-label">{{ sub.label }}</span>
                    <span v-if="sub.sublabel" class="submenu-sublabel">{{ sub.sublabel }}</span>
                  </div>
                  <i v-if="sub.active" class="pi pi-check submenu-check"></i>
                </button>
              </template>
            </div>
          </Transition>
        </div>

        <button 
          v-else 
          class="sidebar-link" 
          :class="{ 'active': item.active }"
          @click="item.command?.()"
          v-tooltip.right="!sidebarExpanded ? { value: item.tooltip || item.label, showDelay: 300 } : null"
        >
          <span class="sidebar-icon-wrap" :style="{ '--icon-color': item.iconColor }">
            <i :class="item.icon" class="sidebar-icon"></i>
          </span>
          <Transition name="fade">
            <span v-if="sidebarExpanded" class="sidebar-label">{{ item.label }}</span>
          </Transition>
        </button>
      </template>
    </nav>

    <div class="sidebar-footer">
      <div class="sidebar-footer-actions">
        <button
          v-for="(action, idx) in sidebarFooterActions"
          :key="idx"
          class="sidebar-footer-btn"
          @click="action.command?.()"
          v-tooltip.top="action.tooltip"
        >
          <i :class="action.icon"></i>
        </button>
      </div>
      <Transition name="fade">
        <div v-if="sidebarExpanded" class="sidebar-version">
          <span>v1.0.0</span>
        </div>
      </Transition>
    </div>
  </aside>

  <div class="app-shell">
    <Toolbar class="app-header">
      <template #start>
        <div class="header-left">
          <Button icon="pi pi-bars" text rounded @click="toggleSidebar" class="menu-toggle" title="Menu" v-if="!sidebarOpen" />
          
          <div class="brand">
            <div class="brand-text">
              <img class="brand-header-logo" src="/green-header.svg" alt="Green Deck" />
              <div class="brand-subtitle">
                Estatísticas da Coleção · <span v-if="firstDay && lastDay">{{ firstDay }} → {{ lastDay }}</span>
                <span v-else>histórico completo</span>
              </div>
            </div>
          </div>

          <div class="header-badges">
            <Tag severity="success" class="pill">/dashboard</Tag>
          </div>
        </div>
      </template>

      <template #end>
        <div class="header-right">
          <Button icon="pi pi-refresh" label="Atualizar" outlined @click="fetchDashboard" />
        </div>
      </template>
    </Toolbar>

    <div class="main">
      <div v-if="errorMsg" class="err card-surface">
        <div class="err-ico"><i class="pi pi-exclamation-triangle"></i></div>
        <div>
          <div class="err-title">Falha ao carregar o Dashboard</div>
          <div class="err-sub muted">{{ errorMsg }}</div>
        </div>
      </div>

      <!-- KPIs -->
      <div class="kpis">
        <Card class="kpi kpi-accent-1">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-clone" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Total de cards</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="9rem" height="1.7rem" />
                  <span v-else>{{ formatInt(kpiTotalCards) }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi kpi-accent-2">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-plus-circle" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Criados (total)</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="9rem" height="1.7rem" />
                  <span v-else>{{ formatInt(kpiCreated) }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi kpi-accent-3">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-sitemap" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Decks no DB</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="9rem" height="1.7rem" />
                  <span v-else>{{ formatInt(kpiDecks) }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi kpi-accent-4">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-chart-line" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Média / dia (all-time)</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="9rem" height="1.7rem" />
                  <span v-else>{{ format2(kpiAvg) }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>
      </div>

      <!-- Charts row 1 -->
      <div class="grid">
        <div class="card-surface chart-card">
          <div class="card-head">
            <div>
              <div class="card-title">Criação de cards</div>
              <div class="card-sub muted">Série diária (all-time)</div>
            </div>
            <Tag class="pill" severity="secondary">Linha</Tag>
          </div>

          <div class="chart-wrap">
            <Skeleton v-if="loading" width="100%" height="290px" />
            <Chart v-else type="line" :data="lineData" :options="lineOptions" style="height: 300px" />
          </div>
        </div>

        <div class="card-surface chart-card">
          <div class="card-head">
            <div>
              <div class="card-title">Tipos de cards (Anki)</div>
              <div class="card-sub muted">Novos · Aprendendo · Revisão · Due · Suspensos</div>
            </div>
            <Tag class="pill" severity="secondary">{{ formatInt(statusTotal) }}</Tag>
          </div>

          <div class="chart-wrap">
            <Skeleton v-if="loading" width="100%" height="290px" />
            <Chart v-else type="doughnut" :data="statusDoughnutData" :options="doughnutOptions" style="height: 300px" />
          </div>

          <div v-if="!loading" class="mini-legend">
            <div v-for="it in statusItems" :key="it.status" class="mini-row">
              <div class="mini-left">
                <span class="mini-dot"></span>
                <span class="mini-label">{{ it.status }}</span>
              </div>
              <div class="mini-right">
                <span class="mini-count">{{ formatInt(it.count) }}</span>
                <span class="mini-pct muted">{{ it.pct.toFixed(1).replace('.', ',') }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Charts row 2 -->
      <div class="grid">
        <div class="card-surface chart-card">
          <div class="card-head">
            <div>
              <div class="card-title">Total por deck</div>
              <div class="card-sub muted">Ranking (Top 12) — melhor legibilidade em modo horizontal</div>
            </div>
            <Tag class="pill" severity="secondary">Barras</Tag>
          </div>

          <div class="chart-wrap">
            <Skeleton v-if="loading" width="100%" height="290px" />
            <Chart v-else type="bar" :data="deckBarData" :options="deckBarOptions" style="height: 300px" />
          </div>
        </div>

        <div class="card-surface chart-card">
          <div class="card-head">
            <div>
              <div class="card-title">Segmentos de maturidade</div>
              <div class="card-sub muted">KMeans (scikit-learn) — agrupamento por comportamento</div>
            </div>
            <Tag class="pill" severity="secondary">{{ segmentsMetaText || '—' }}</Tag>
          </div>

          <div class="chart-wrap">
            <Skeleton v-if="loading" width="100%" height="290px" />
            <Chart v-else type="bar" :data="segmentsBarData" :options="segmentsBarOptions" style="height: 300px" />
          </div>
        </div>
      </div>

      <!-- Tables -->
      <div class="grid">
        <div class="card-surface table-card">
          <div class="card-head">
            <div>
              <div class="card-title">Top decks</div>
              <div class="card-sub muted">Concentração por deck</div>
            </div>
            <Tag class="pill" severity="secondary">{{ topDecks.length }}</Tag>
          </div>

          <DataTable
            :value="topDecks"
            stripedRows
            rowHover
            class="modern-dt"
            :loading="loading"
            :paginator="topDecks.length > 8"
            :rows="8"
            :rowsPerPageOptions="[8, 12, 20]"
            responsiveLayout="scroll"
          >
            <Column field="deckName" header="Deck" sortable />
            <Column field="count" header="Cards" sortable style="width: 9rem">
              <template #body="{ data }">{{ formatInt(data.count) }}</template>
            </Column>
          </DataTable>
        </div>

        <div class="card-surface table-card">
          <div class="card-head">
            <div>
              <div class="card-title">Segmentos (KMeans)</div>
              <div class="card-sub muted">Médias por grupo (intervalo · ease · lapses · reps)</div>
            </div>
            <Tag class="pill" severity="secondary">{{ segments.length }}</Tag>
          </div>

          <div v-if="!loading && !segments.length" class="empty muted">
            <div class="empty-ico"><i class="pi pi-info-circle"></i></div>
            <div>
              Sem dados suficientes para segmentar (ou coleção pequena).
              <div class="muted tiny">Dica: reduza o K (env DASHBOARD_SEGMENTS_K) ou aumente o sample no backend.</div>
            </div>
          </div>

          <DataTable
            v-else
            :value="segments"
            stripedRows
            rowHover
            class="modern-dt"
            :loading="loading"
            responsiveLayout="scroll"
          >
            <Column field="segment" header="Segmento" sortable />
            <Column field="count" header="Qtd" sortable style="width: 6rem">
              <template #body="{ data }">{{ formatInt(data.count) }}</template>
            </Column>

            <Column field="avgInterval" header="Intervalo méd. (d)" sortable style="width: 12rem">
              <template #body="{ data }">{{ Number(data.avgInterval || 0).toFixed(1).replace('.', ',') }}</template>
            </Column>

            <Column field="avgEase" header="Ease méd." sortable style="width: 9rem">
              <template #body="{ data }">{{ Number(data.avgEase || 0).toFixed(2).replace('.', ',') }}</template>
            </Column>

            <Column field="avgLapses" header="Lapses méd." sortable style="width: 10rem">
              <template #body="{ data }">{{ Number(data.avgLapses || 0).toFixed(2).replace('.', ',') }}</template>
            </Column>

            <Column field="avgReps" header="Reps méd." sortable style="width: 9rem">
              <template #body="{ data }">{{ Number(data.avgReps || 0).toFixed(2).replace('.', ',') }}</template>
            </Column>
          </DataTable>
        </div>
      </div>

      <div class="footer-space" />
    </div>
  </div>
</template>

<style scoped>
/* =========================
   Sidebar Menu - Modern Design
========================= */
.sidebar {
  position: fixed;
  left: 12px;
  top: 12px;
  bottom: 12px;
  width: 80px;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.95) 0%, rgba(17, 24, 39, 0.98) 100%);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 24px;
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(255, 255, 255, 0.05) inset;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar.expanded {
  width: 300px;
}

.sidebar-header {
  padding: 16px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(180deg, rgba(16, 185, 129, 0.1) 0%, transparent 100%);
  min-height: auto;
  overflow: visible;
  gap: 10px;
  border-radius: 23px 23px 0 0;
}

.sidebar.expanded .sidebar-header {
  padding: 18px 20px;
}

.sidebar-logo {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  filter: drop-shadow(0 2px 8px rgba(16, 185, 129, 0.3));
  transition: transform 0.3s ease;
}

.sidebar:hover .sidebar-logo {
  transform: scale(1.05);
}

.sidebar-toggle {
  width: 24px;
  height: 24px;
  min-width: 24px;
  flex-shrink: 0;
  transition: all 0.2s ease;
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
}

.sidebar.expanded .sidebar-toggle {
  width: 24px;
  height: 24px;
}

.sidebar-toggle:hover {
  background: transparent !important;
  transform: scale(1.15);
}

.sidebar-toggle :deep(.p-button-icon) {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.5);
  transition: color 0.2s ease;
}

.sidebar-toggle:hover :deep(.p-button-icon) {
  color: #10B981;
}

.sidebar.expanded .sidebar-toggle :deep(.p-button-icon) {
  font-size: 14px;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 8px;
  scrollbar-width: thin;
  scrollbar-color: rgba(16, 185, 129, 0.3) transparent;
}

.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: rgba(16, 185, 129, 0.3);
  border-radius: 4px;
}

.sidebar-nav::-webkit-scrollbar-thumb:hover {
  background: rgba(16, 185, 129, 0.5);
}

.sidebar-separator {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(148, 163, 184, 0.15) 50%, transparent 100%);
  margin: 12px 16px;
}

.sidebar-item {
  margin-bottom: 4px;
  overflow: visible;
}

.sidebar-link {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 6px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.85);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 14px;
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  position: relative;
  overflow: visible;
}

.sidebar.expanded .sidebar-link {
  justify-content: flex-start;
  padding: 10px 14px;
}

.sidebar-link::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%) scaleY(0);
  width: 4px;
  height: 24px;
  background: linear-gradient(180deg, #10B981 0%, #34D399 100%);
  border-radius: 0 4px 4px 0;
  transition: transform 0.2s ease;
}

.sidebar-link:hover {
  background: rgba(99, 102, 241, 0.12);
  color: #fff;
}

.sidebar-link:hover::before {
  transform: translateY(-50%) scaleY(1);
}

.sidebar-link.expanded,
.sidebar-link.active {
  background: rgba(99, 102, 241, 0.18);
  color: #fff;
}

.sidebar-link.expanded::before,
.sidebar-link.active::before {
  transform: translateY(-50%) scaleY(1);
  background: linear-gradient(180deg, #6366F1 0%, #8B5CF6 100%);
}

.sidebar-icon-wrap {
  width: 46px;
  height: 46px;
  min-width: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.sidebar.expanded .sidebar-icon-wrap {
  width: 38px;
  height: 38px;
  min-width: 38px;
  border-radius: 10px;
}

.sidebar-link:hover .sidebar-icon-wrap {
  background: color-mix(in srgb, var(--icon-color, #6366F1) 18%, transparent);
  transform: scale(1.08);
}

.sidebar-icon {
  font-size: 17px;
  color: var(--icon-color, rgba(255, 255, 255, 0.8));
  transition: color 0.2s ease;
}

.sidebar-link:hover .sidebar-icon {
  color: var(--icon-color, #fff);
}

.sidebar-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 800;
  flex-shrink: 0;
}

.sidebar-chevron {
  font-size: 11px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  opacity: 0.6;
  flex-shrink: 0;
}

.sidebar-link.expanded .sidebar-chevron {
  transform: rotate(180deg);
  opacity: 1;
}

.sidebar-submenu {
  padding: 6px 0 6px 20px;
  margin-top: 4px;
  overflow: hidden;
  border-left: 2px solid rgba(99, 102, 241, 0.2);
  margin-left: 28px;
}

.submenu-separator {
  height: 1px;
  background: rgba(148, 163, 184, 0.08);
  margin: 8px 12px;
}

.submenu-link {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.75);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  text-align: left;
  margin-bottom: 2px;
  position: relative;
}

.submenu-link:hover:not(.disabled) {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  transform: translateX(4px);
}

.submenu-link.active {
  background: rgba(16, 185, 129, 0.15);
  color: #10B981;
}

.submenu-link.danger:hover:not(.disabled) {
  background: rgba(239, 68, 68, 0.12);
  color: #EF4444;
}

.submenu-link.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.submenu-icon-wrap {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.submenu-link:hover:not(.disabled) .submenu-icon-wrap {
  background: color-mix(in srgb, var(--icon-color, #6366F1) 20%, transparent);
}

.submenu-icon {
  font-size: 13px;
  color: var(--icon-color, rgba(255, 255, 255, 0.7));
  transition: color 0.2s ease;
}

.submenu-link:hover:not(.disabled) .submenu-icon {
  color: var(--icon-color, #fff);
}

.submenu-link.active .submenu-icon {
  color: #10B981;
}

.submenu-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.submenu-label {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.submenu-sublabel {
  font-size: 11px;
  opacity: 0.55;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.submenu-check {
  font-size: 12px;
  color: #10B981;
  flex-shrink: 0;
}

.submenu-enter-active {
  animation: submenu-expand 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.submenu-leave-active {
  animation: submenu-collapse 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes submenu-expand {
  from {
    opacity: 0;
    max-height: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    max-height: 800px;
    transform: translateY(0);
  }
}

@keyframes submenu-collapse {
  from {
    opacity: 1;
    max-height: 800px;
  }
  to {
    opacity: 0;
    max-height: 0;
  }
}

/* Fade transition for labels */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Sidebar Footer */
.sidebar-footer {
  padding: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.08);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border-radius: 0 0 23px 23px;
}

.sidebar.expanded .sidebar-footer {
  justify-content: space-between;
  padding: 12px 14px;
}

.sidebar-footer-actions {
  display: flex;
  gap: 6px;
}

.sidebar-footer-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
}

.sidebar-footer-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #10B981;
  transform: scale(1.1);
}

.sidebar-version {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
  font-weight: 500;
  padding-right: 4px;
}

.menu-toggle {
  width: 42px;
  height: 42px;
}

/* =========================
   Base Layout
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

.sidebar.expanded ~ .app-shell {
  margin-left: 324px;
}

.main {
  flex: 1;
  min-height: 0;
  padding: 14px;
  overflow: auto;
  width: 100%;
  max-width: none;
  margin: 0;
}

/* (Opcional) melhora a “sensação” de full-bleed em telas grandes */
@media (min-width: 1400px) {
  .main {
    padding-left: 20px;
    padding-right: 20px;
  }
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 50;
  border: 0;
  padding: 14px;
  backdrop-filter: blur(10px);
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
}

/* Cards */
.card-surface {
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(17, 24, 39, 0.56);
  backdrop-filter: blur(10px);
  box-shadow: 0 16px 42px rgba(0, 0, 0, 0.28);
  padding: 14px;
  position: relative;
  overflow: hidden;
}

.card-surface::before {
  content: '';
  position: absolute;
  inset: -2px;
  background: radial-gradient(500px 220px at 12% 0%, rgba(255, 255, 255, 0.06), transparent 55%);
  pointer-events: none;
}

.card-surface:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.32);
}

/* Shared heading blocks in cards */
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.card-title {
  font-weight: 950;
  letter-spacing: -0.25px;
  line-height: 1.1;
}

.card-sub {
  margin-top: 4px;
  font-size: 12px;
}

/* KPIs */
.kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 980px) {
  .kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 640px) {
  .kpis {
    grid-template-columns: 1fr;
  }
}

.kpi {
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(17, 24, 39, 0.56);
  backdrop-filter: blur(10px);
  box-shadow: 0 16px 42px rgba(0, 0, 0, 0.28);
  overflow: hidden;
  position: relative;
}

.kpi::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.07), transparent 45%);
  opacity: 0.6;
  pointer-events: none;
}

.kpi :deep(.p-card-body) {
  padding: 14px;
}

.kpi-top {
  display: flex;
  gap: 12px;
  align-items: center;
}

.kpi-ico {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.22);
  border: 1px solid rgba(148, 163, 184, 0.14);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03);
}

.kpi-ico i {
  font-size: 18px;
  opacity: 0.95;
}

.kpi-lbl {
  font-weight: 900;
  font-size: 12px;
  opacity: 0.75;
}

.kpi-val {
  margin-top: 4px;
  font-size: 20px;
  font-weight: 1000;
  letter-spacing: -0.4px;
}

/* KPI accent strip */
.kpi::after {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: rgba(99, 102, 241, 0.85);
  opacity: 0.9;
}
.kpi-accent-1::after { background: rgba(99, 102, 241, 0.9); }
.kpi-accent-2::after { background: rgba(16, 185, 129, 0.9); }
.kpi-accent-3::after { background: rgba(236, 72, 153, 0.85); }
.kpi-accent-4::after { background: rgba(245, 158, 11, 0.9); }

/* Grid blocks */
.grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* ✅ Em telas grandes, abre mais o layout */
@media (min-width: 1400px) {
  .grid {
    grid-template-columns: 1.25fr 0.75fr; /* dá mais espaço pros gráficos “largos” */
  }
}

@media (max-width: 980px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

.chart-card {
  min-height: 380px;
}

.table-card {
  padding: 14px;
}

/* Chart container */
.chart-wrap {
  padding: 6px 0 0;
}

:deep(.p-chart) {
  border-radius: 14px;
}
:deep(.p-chart canvas) {
  border-radius: 14px;
}

/* Small legend for doughnut */
.mini-legend {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
  display: grid;
  gap: 8px;
}

.mini-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.mini-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.mini-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.06);
  flex: 0 0 auto;
}

.mini-label {
  font-weight: 800;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mini-right {
  display: flex;
  gap: 10px;
  align-items: baseline;
  justify-content: flex-end;
}

.mini-count {
  font-weight: 950;
}

.mini-pct {
  font-size: 12px;
}

/* Tags */
.pill {
  border-radius: 999px;
  font-weight: 900;
}
.pill-route {
  padding: 0.2rem 0.55rem;
}

.muted {
  opacity: 0.76;
}

/* DataTable */
:deep(.modern-dt .p-datatable-wrapper) {
  border-radius: 14px;
  overflow: hidden;
}

:deep(.modern-dt .p-datatable-thead > tr > th) {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(148, 163, 184, 0.12);
  font-weight: 950;
}

:deep(.modern-dt .p-datatable-tbody > tr > td) {
  border-color: rgba(148, 163, 184, 0.10);
}

:deep(.modern-dt .p-paginator) {
  background: transparent;
  border: 0;
  padding-top: 10px;
}

/* Empty state */
.empty {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 6px 2px;
}

.empty-ico {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.tiny {
  margin-top: 4px;
  font-size: 12px;
}

/* Error card */
.err {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.err-ico {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: rgba(239, 68, 68, 0.10);
  border: 1px solid rgba(239, 68, 68, 0.22);
}

.err i {
  font-size: 18px;
}
.err-title {
  font-weight: 1000;
}
.err-sub {
  margin-top: 2px;
}

.footer-space {
  height: 18px;
}
</style>
