<!-- frontend/src/pages/DashBoardPage.vue -->
<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

// PrimeVue
import Toolbar from 'primevue/toolbar'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Card from 'primevue/card'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Skeleton from 'primevue/skeleton'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import DatePicker from 'primevue/datepicker'
import MultiSelect from 'primevue/multiselect'
import Dialog from 'primevue/dialog'
import Divider from 'primevue/divider'

// App components - with lazy loading for performance
import SidebarMenu from '@/components/SidebarMenu.vue'
import LazyChart from '@/components/LazyChart.vue'
import { sidebarIconColors } from '@/config/theme'

// Composables
import { useDashboardFilters } from '@/composables/useDashboardFilters'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { useTheme } from '@/composables/useTheme'

const router = useRouter()
const toast = useToast()
const { isDark, toggleTheme } = useTheme()

// Filters
const { dateRange, selectedDecks, hasActiveFilters, queryString, clearFilters } = useDashboardFilters()
const filtersExpanded = ref(true)

// Deck options for filter (populated from topDecks)
const deckOptions = computed(() =>
  topDecks.value.map(d => ({ label: d.deckName, value: d.deckName }))
)

// Watch filters to refetch data
watch([dateRange, selectedDecks], () => {
  if (!loading.value) {
    fetchDashboard()
  }
}, { deep: true })

// Sidebar ref
const sidebarRef = ref(null)

// Dialog states
const deckDetailVisible = ref(false)
const selectedDeck = ref(null)
const dayDetailVisible = ref(false)
const selectedDay = ref(null)

function notify(message, severity = 'info', life = 3200) {
  toast.add({ severity, summary: message, life })
}

// ============================================================
// Sidebar Menu Items
// ============================================================
const sidebarMenuItems = computed(() => [
  { key: 'generator', label: 'Generator', icon: 'pi pi-bolt', iconColor: sidebarIconColors.generator, tooltip: 'Gerar flashcards', command: () => router.push('/') },
  { key: 'browser', label: 'Browser', icon: 'pi pi-database', iconColor: sidebarIconColors.browser, tooltip: 'Navegar pelos cards salvos', command: () => router.push('/browser') },
  { key: 'dashboard', label: 'Dashboard', icon: 'pi pi-chart-bar', iconColor: sidebarIconColors.dashboard, tooltip: 'Estatísticas de estudo', active: true },
  { separator: true },
  {
    key: 'actions',
    label: 'Ações',
    icon: 'pi pi-cog',
    iconColor: sidebarIconColors.settings,
    tooltip: 'Ações rápidas',
    submenu: [
      { label: 'Atualizar dados', icon: 'pi pi-refresh', iconColor: sidebarIconColors.generator, command: fetchDashboard }
    ]
  }
])

const sidebarFooterActions = computed(() => [
  { icon: 'pi pi-question-circle', tooltip: 'Documentação', command: () => router.push('/docs') },
  { icon: isDark.value ? 'pi pi-sun' : 'pi pi-moon', tooltip: isDark.value ? 'Ativar modo claro' : 'Ativar modo escuro', command: toggleTheme }
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
function formatStudyTime(totalMinutes) {
  const n = Number(totalMinutes)
  if (!Number.isFinite(n) || n <= 0) return '0 min'
  if (n < 60) return `${n.toFixed(0)} min`
  const h = Math.floor(n / 60)
  const m = Math.round(n % 60)
  return m > 0 ? `${h}h ${m}min` : `${h}h`
}

// --- state ---
const loading = ref(true)
const errorMsg = ref('')

// payloads do backend
const summary = ref(null) // { totalCards, totalDecks, statusBreakdown, segmentsMeta, reviewKpis }
const reviewsByDay = ref([]) // [{day, reviews}]
const studyTimeByDay = ref([]) // [{day, minutes}]
const successRateByDay = ref([]) // [{day, rate, correct, total}]
const topDecks = ref([]) // [{deckName, count}]
const segments = ref([]) // [{segment, count, avgInterval, avgEase, avgLapses, avgReps}]

// ---------- KPIs ----------
const kpiTotalCards = computed(() => summary.value?.totalCards ?? 0)
const kpiTotalReviews = computed(() => summary.value?.reviewKpis?.totalReviews ?? 0)
const kpiAvgReviewsPerDay = computed(() => summary.value?.reviewKpis?.avgReviewsPerDay ?? 0)
const kpiTotalStudyTimeMin = computed(() => summary.value?.reviewKpis?.totalStudyTimeMin ?? 0)
const kpiSuccessRate = computed(() => summary.value?.reviewKpis?.successRate ?? 0)

// Animated KPI values
const animatedTotalReviews = useAnimatedNumber(kpiTotalReviews)
const animatedAvgReviews = useAnimatedNumber(kpiAvgReviewsPerDay)
const animatedStudyTime = useAnimatedNumber(kpiTotalStudyTimeMin)
const animatedSuccessRate = useAnimatedNumber(kpiSuccessRate)

// ---------- Drill-down functions ----------
function openDeckDetail(deck) {
  selectedDeck.value = deck
  deckDetailVisible.value = true
}

function openDayDetail(dayData) {
  selectedDay.value = dayData
  dayDetailVisible.value = true
}

function navigateToBrowserWithStatus(statusKey) {
  const queryMap = {
    'Novos': 'is:new',
    'Aprendendo': 'is:learn',
    'Revisão': 'is:review',
    'Vencidos': 'is:due',
    'Suspensos': 'is:suspended'
  }
  router.push({
    path: '/browser',
    query: { filter: queryMap[statusKey] || 'deck:*' }
  })
}

function navigateToBrowserWithDeck(deckName) {
  router.push({
    path: '/browser',
    query: { filter: `deck:"${deckName}"` }
  })
}

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

// Reviews por dia (substitui "Cards criados")
const reviewsLineData = computed(() => {
  const labels = reviewsByDay.value.map((x) => x.day)
  const data = reviewsByDay.value.map((x) => Number(x.reviews || 0))
  return {
    labels,
    datasets: [
      {
        label: 'Reviews por dia',
        data,
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        pointHitRadius: 10,
        borderColor: '#6366F1',
        backgroundColor: 'rgba(99, 102, 241, 0.15)'
      }
    ]
  }
})

const reviewsLineOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  onClick: (event, elements) => {
    if (elements.length > 0) {
      const dataIndex = elements[0].index
      const clickedDay = reviewsByDay.value[dataIndex]
      if (clickedDay) openDayDetail(clickedDay)
    }
  },
  onHover: (event, elements) => {
    event.native.target.style.cursor = elements.length ? 'pointer' : 'default'
  },
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

// Tempo de estudo por dia
const studyTimeLineData = computed(() => {
  const labels = studyTimeByDay.value.map((x) => x.day)
  const data = studyTimeByDay.value.map((x) => Number(x.minutes || 0))
  return {
    labels,
    datasets: [
      {
        label: 'Tempo de estudo (min)',
        data,
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        pointHitRadius: 10,
        borderColor: '#10B981',
        backgroundColor: 'rgba(16, 185, 129, 0.15)'
      }
    ]
  }
})

const studyTimeOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: { display: true, labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
    tooltip: {
      mode: 'index', intersect: false,
      callbacks: {
        label: (ctx) => `${ctx.parsed.y.toFixed(1)} min`
      }
    }
  },
  scales: {
    x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 10 }, grid: { display: false } },
    y: { beginAtZero: true, ticks: { maxTicksLimit: 6 }, grid: { drawBorder: false } }
  }
}))

// Taxa de acerto ao longo do tempo
const successRateLineData = computed(() => {
  const labels = successRateByDay.value.map((x) => x.day)
  const data = successRateByDay.value.map((x) => Number(x.rate || 0))
  return {
    labels,
    datasets: [
      {
        label: 'Taxa de acerto (%)',
        data,
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        pointHitRadius: 10,
        borderColor: '#F59E0B',
        backgroundColor: 'rgba(245, 158, 11, 0.15)'
      }
    ]
  }
})

const successRateOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: { display: true, labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
    tooltip: {
      mode: 'index', intersect: false,
      callbacks: {
        label: (ctx) => {
          const dayData = successRateByDay.value[ctx.dataIndex]
          return `${ctx.parsed.y.toFixed(1)}% (${dayData?.correct ?? 0}/${dayData?.total ?? 0})`
        }
      }
    }
  },
  scales: {
    x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 10 }, grid: { display: false } },
    y: {
      beginAtZero: true,
      max: 100,
      ticks: { maxTicksLimit: 6, callback: (v) => `${v}%` },
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
  onClick: (event, elements) => {
    if (elements.length > 0) {
      const dataIndex = elements[0].index
      const status = statusItems.value[dataIndex]
      if (status) navigateToBrowserWithStatus(status.status)
    }
  },
  onHover: (event, elements) => {
    event.native.target.style.cursor = elements.length ? 'pointer' : 'default'
  },
  plugins: {
    legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
    tooltip: {
      callbacks: {
        label: (ctx) => {
          const label = ctx.label || '—'
          const val = ctx.parsed || 0
          const total = statusTotal.value || 0
          const pct = total ? ((100 * val) / total).toFixed(1).replace('.', ',') : '0,0'
          return `${label}: ${formatInt(val)} (${pct}%) — Clique para filtrar`
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
  onClick: (event, elements) => {
    if (elements.length > 0) {
      const dataIndex = elements[0].index
      const deck = topDecks.value[dataIndex]
      if (deck) openDeckDetail(deck)
    }
  },
  onHover: (event, elements) => {
    event.native.target.style.cursor = elements.length ? 'pointer' : 'default'
  },
  plugins: {
    legend: { display: true, labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
    tooltip: {
      callbacks: {
        label: (ctx) => `${formatInt(ctx.parsed.x)} cards — Clique para detalhes`
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

  // Build query string from filters
  const qs = queryString.value
  const qsTopDecks = qs ? `?limit=12&${qs.slice(1)}` : '?limit=12'

  try {
    // Parallel fetch for better performance
    const [summaryRes, reviewsByDayRes, studyTimeByDayRes, successRateByDayRes, topDecksRes, segmentsRes] = await Promise.all([
      fetch(`/api/dashboard/summary${qs}`),
      fetch(`/api/dashboard/reviews-by-day${qs}`),
      fetch(`/api/dashboard/study-time-by-day${qs}`),
      fetch(`/api/dashboard/success-rate-by-day${qs}`),
      fetch(`/api/dashboard/top-decks${qsTopDecks}`),
      fetch(`/api/dashboard/segments${qs}`)
    ])

    // Parse all responses
    const [summaryData, reviewsByDayData, studyTimeByDayData, successRateByDayData, topDecksData, segmentsData] = await Promise.all([
      readJsonSafe(summaryRes),
      readJsonSafe(reviewsByDayRes),
      readJsonSafe(studyTimeByDayRes),
      readJsonSafe(successRateByDayRes),
      readJsonSafe(topDecksRes),
      readJsonSafe(segmentsRes)
    ])

    // Validate and assign summary
    if (summaryData?.__nonJson) throw new Error(`summary non-JSON: ${summaryData.__head}`)
    if (summaryRes.status >= 400 || summaryData?.success === false) throw new Error(summaryData?.error || `summary HTTP ${summaryRes.status}`)
    summary.value = summaryData

    // Validate and assign reviewsByDay
    if (reviewsByDayData?.__nonJson) throw new Error(`reviews-by-day non-JSON: ${reviewsByDayData.__head}`)
    if (reviewsByDayRes.status >= 400 || reviewsByDayData?.success === false) throw new Error(reviewsByDayData?.error || `reviews-by-day HTTP ${reviewsByDayRes.status}`)
    reviewsByDay.value = Array.isArray(reviewsByDayData?.items) ? reviewsByDayData.items : []

    // Validate and assign studyTimeByDay
    if (studyTimeByDayData?.__nonJson) throw new Error(`study-time-by-day non-JSON: ${studyTimeByDayData.__head}`)
    if (studyTimeByDayRes.status >= 400 || studyTimeByDayData?.success === false) throw new Error(studyTimeByDayData?.error || `study-time-by-day HTTP ${studyTimeByDayRes.status}`)
    studyTimeByDay.value = Array.isArray(studyTimeByDayData?.items) ? studyTimeByDayData.items : []

    // Validate and assign successRateByDay
    if (successRateByDayData?.__nonJson) throw new Error(`success-rate-by-day non-JSON: ${successRateByDayData.__head}`)
    if (successRateByDayRes.status >= 400 || successRateByDayData?.success === false) throw new Error(successRateByDayData?.error || `success-rate-by-day HTTP ${successRateByDayRes.status}`)
    successRateByDay.value = Array.isArray(successRateByDayData?.items) ? successRateByDayData.items : []

    // Validate and assign topDecks
    if (topDecksData?.__nonJson) throw new Error(`top-decks non-JSON: ${topDecksData.__head}`)
    if (topDecksRes.status >= 400 || topDecksData?.success === false) throw new Error(topDecksData?.error || `top-decks HTTP ${topDecksRes.status}`)
    topDecks.value = Array.isArray(topDecksData?.items) ? topDecksData.items : []

    // Validate and assign segments
    if (segmentsData?.__nonJson) throw new Error(`segments non-JSON: ${segmentsData.__head}`)
    if (segmentsRes.status >= 400 || segmentsData?.success === false) throw new Error(segmentsData?.error || `segments HTTP ${segmentsRes.status}`)
    segments.value = Array.isArray(segmentsData?.items) ? segmentsData.items : []

  } catch (e) {
    errorMsg.value = e?.message || String(e)
    notify(errorMsg.value, 'error', 7000)
  } finally {
    loading.value = false
  }
}

// ---------- Keyboard shortcuts ----------
function handleKeyboard(e) {
  // Ignore if user is typing in an input
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return

  // R = Refresh
  if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
    e.preventDefault()
    fetchDashboard()
    notify('Atualizando dados...', 'info', 1500)
  }
  // F = Toggle filters
  if (e.key === 'f' && !e.ctrlKey && !e.metaKey) {
    e.preventDefault()
    filtersExpanded.value = !filtersExpanded.value
  }
  // Escape = Close any open dialog
  if (e.key === 'Escape') {
    deckDetailVisible.value = false
    dayDetailVisible.value = false
  }
}

onMounted(() => {
  fetchDashboard()
  document.addEventListener('keydown', handleKeyboard)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyboard)
})
</script>

<template>
  <Toast />

  <!-- Sidebar -->
  <SidebarMenu
    ref="sidebarRef"
    :menu-items="sidebarMenuItems"
    :footer-actions="sidebarFooterActions"
  />

  <div class="app-shell" :class="{ 'sidebar-expanded': sidebarRef?.sidebarExpanded }">
    <Toolbar class="app-header">
      <template #start>
        <div class="header-left">
          <Button icon="pi pi-bars" text rounded @click="sidebarRef?.toggleSidebar()" class="menu-toggle" title="Menu" v-if="!sidebarRef?.sidebarOpen" />
          
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
      <!-- Filter Bar -->
      <Transition name="slide-fade">
        <div v-if="filtersExpanded" class="filter-bar card-surface">
          <div class="filter-row">
            <div class="filter-group">
              <label class="filter-label muted">Periodo</label>
              <DatePicker
                v-model="dateRange"
                selectionMode="range"
                placeholder="Selecione o periodo"
                showIcon
                dateFormat="dd/mm/yy"
                class="filter-date"
                :showButtonBar="true"
              />
            </div>
            <div class="filter-group">
              <label class="filter-label muted">Decks</label>
              <MultiSelect
                v-model="selectedDecks"
                :options="deckOptions"
                optionLabel="label"
                optionValue="value"
                placeholder="Filtrar por deck"
                filter
                display="chip"
                class="filter-decks"
                :maxSelectedLabels="2"
              />
            </div>
            <Button
              v-if="hasActiveFilters"
              icon="pi pi-filter-slash"
              label="Limpar"
              text
              severity="secondary"
              @click="clearFilters"
              class="filter-clear"
            />
          </div>
          <div class="filter-hint muted">
            <i class="pi pi-info-circle" />
            Atalhos: <kbd>R</kbd> atualizar · <kbd>F</kbd> filtros · <kbd>Esc</kbd> fechar dialogs
          </div>
        </div>
      </Transition>

      <div class="filter-toggle-row">
        <Button
          :icon="filtersExpanded ? 'pi pi-chevron-up' : 'pi pi-filter'"
          :label="filtersExpanded ? 'Ocultar filtros' : 'Filtros'"
          text
          size="small"
          @click="filtersExpanded = !filtersExpanded"
        />
        <Tag v-if="hasActiveFilters" severity="info" class="pill">Filtros ativos</Tag>
      </div>

      <div v-if="errorMsg" class="err card-surface">
        <div class="err-ico"><i class="pi pi-exclamation-triangle"></i></div>
        <div>
          <div class="err-title">Falha ao carregar o Dashboard</div>
          <div class="err-sub muted">{{ errorMsg }}</div>
        </div>
      </div>

      <!-- KPIs -->
      <div class="kpis">
        <Card class="kpi kpi-accent-1 kpi-anim-1">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-history" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Total de reviews</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="9rem" height="1.7rem" />
                  <span v-else>{{ formatInt(animatedTotalReviews) }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi kpi-accent-2 kpi-anim-2">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-chart-line" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Média reviews/dia</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="9rem" height="1.7rem" />
                  <span v-else>{{ format2(animatedAvgReviews) }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi kpi-accent-3 kpi-anim-3">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-clock" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Tempo total de estudo</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="9rem" height="1.7rem" />
                  <span v-else>{{ formatStudyTime(animatedStudyTime) }}</span>
                </div>
              </div>
            </div>
          </template>
        </Card>

        <Card class="kpi kpi-accent-4 kpi-anim-4">
          <template #content>
            <div class="kpi-top">
              <div class="kpi-ico"><i class="pi pi-check-circle" /></div>
              <div class="kpi-txt">
                <div class="kpi-lbl muted">Taxa de acerto</div>
                <div class="kpi-val">
                  <Skeleton v-if="loading" width="9rem" height="1.7rem" />
                  <span v-else>{{ format2(animatedSuccessRate) }}%</span>
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
              <div class="card-title">Reviews por dia</div>
              <div class="card-sub muted">Histórico de revisões</div>
            </div>
            <Tag class="pill" severity="secondary">Linha</Tag>
          </div>

          <div class="chart-wrap">
            <Skeleton v-if="loading" width="100%" height="290px" />
            <LazyChart v-else type="line" :data="reviewsLineData" :options="reviewsLineOptions" height="300px" />
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
            <LazyChart v-else type="doughnut" :data="statusDoughnutData" :options="doughnutOptions" height="300px" />
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

      <!-- Charts row 2: Tempo de estudo + Taxa de acerto -->
      <div class="grid">
        <div class="card-surface chart-card">
          <div class="card-head">
            <div>
              <div class="card-title">Tempo de estudo</div>
              <div class="card-sub muted">Minutos por dia</div>
            </div>
            <Tag class="pill" severity="secondary">Linha</Tag>
          </div>

          <div class="chart-wrap">
            <Skeleton v-if="loading" width="100%" height="290px" />
            <LazyChart v-else type="line" :data="studyTimeLineData" :options="studyTimeOptions" height="300px" />
          </div>
        </div>

        <div class="card-surface chart-card">
          <div class="card-head">
            <div>
              <div class="card-title">Taxa de acerto</div>
              <div class="card-sub muted">% de acertos ao longo do tempo</div>
            </div>
            <Tag class="pill" severity="secondary">Linha</Tag>
          </div>

          <div class="chart-wrap">
            <Skeleton v-if="loading" width="100%" height="290px" />
            <LazyChart v-else type="line" :data="successRateLineData" :options="successRateOptions" height="300px" />
          </div>
        </div>
      </div>

      <!-- Charts row 3: Decks + Segmentos -->
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
            <LazyChart v-else type="bar" :data="deckBarData" :options="deckBarOptions" height="300px" />
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
            <LazyChart v-else type="bar" :data="segmentsBarData" :options="segmentsBarOptions" height="300px" />
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

  <!-- Deck Detail Dialog -->
  <Dialog
    v-model:visible="deckDetailVisible"
    modal
    :draggable="false"
    class="modern-dialog"
    :style="{ width: 'min(500px, 94vw)' }"
  >
    <template #header>
      <div class="dlg-hdr">
        <div class="dlg-hdr-left">
          <div class="dlg-icon"><i class="pi pi-folder"></i></div>
          <div class="dlg-hdr-txt">
            <div class="dlg-title">{{ selectedDeck?.deckName || 'Deck' }}</div>
            <div class="dlg-sub muted">Detalhes do deck</div>
          </div>
        </div>
      </div>
    </template>

    <div class="dlg-body">
      <div class="deck-stats">
        <div class="deck-stat">
          <div class="deck-stat-label muted">Total de cards</div>
          <div class="deck-stat-value">{{ formatInt(selectedDeck?.count) }}</div>
        </div>
        <div class="deck-stat">
          <div class="deck-stat-label muted">Porcentagem</div>
          <div class="deck-stat-value">
            {{ ((selectedDeck?.count / kpiTotalCards) * 100).toFixed(1).replace('.', ',') }}%
          </div>
        </div>
      </div>

      <Divider />

      <div class="deck-actions">
        <Button
          label="Ver no Browser"
          icon="pi pi-external-link"
          @click="navigateToBrowserWithDeck(selectedDeck?.deckName); deckDetailVisible = false"
        />
        <Button
          label="Fechar"
          icon="pi pi-times"
          outlined
          @click="deckDetailVisible = false"
        />
      </div>
    </div>
  </Dialog>

  <!-- Day Detail Dialog -->
  <Dialog
    v-model:visible="dayDetailVisible"
    modal
    :draggable="false"
    class="modern-dialog"
    :style="{ width: 'min(400px, 94vw)' }"
  >
    <template #header>
      <div class="dlg-hdr">
        <div class="dlg-hdr-left">
          <div class="dlg-icon"><i class="pi pi-calendar"></i></div>
          <div class="dlg-hdr-txt">
            <div class="dlg-title">{{ selectedDay?.day || 'Data' }}</div>
            <div class="dlg-sub muted">Detalhes do dia de estudo</div>
          </div>
        </div>
      </div>
    </template>

    <div class="dlg-body">
      <div class="day-stats">
        <div class="day-stat-big">
          <div class="day-stat-value">{{ formatInt(selectedDay?.reviews) }}</div>
          <div class="day-stat-label muted">reviews realizados</div>
        </div>
      </div>

      <Divider />

      <Button
        label="Fechar"
        icon="pi pi-times"
        outlined
        @click="dayDetailVisible = false"
        class="day-close-btn"
      />
    </div>
  </Dialog>
</template>

<style scoped>
/* =========================
   Base Layout
========================= */
.menu-toggle {
  width: 42px;
  height: 42px;
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
  .menu-toggle {
    width: 38px;
    height: 38px;
  }
}

@media (max-width: 1024px) {
  .menu-toggle {
    width: 34px;
    height: 34px;
  }
  .app-header :deep(.p-button) {
    padding: 0.4rem 0.6rem;
  }
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
  border: 1px solid var(--app-border);
  background: var(--app-card);
  backdrop-filter: blur(10px);
  box-shadow: var(--app-shadow);
  padding: 14px;
  position: relative;
  overflow: hidden;
}

.card-surface::before {
  content: '';
  position: absolute;
  inset: -2px;
  background: radial-gradient(500px 220px at 12% 0%, color-mix(in srgb, var(--app-text) 6%, transparent), transparent 55%);
  pointer-events: none;
}

.card-surface:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 50px color-mix(in srgb, var(--app-text) 12%, transparent);
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
  border: 1px solid var(--app-border);
  background: var(--app-card);
  backdrop-filter: blur(10px);
  box-shadow: var(--app-shadow);
  overflow: hidden;
  position: relative;
}

.kpi::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, color-mix(in srgb, var(--app-text) 8%, transparent), transparent 45%);
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
  background: var(--ghost-bg-strong);
  border: 1px solid var(--ghost-border);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--app-text) 6%, transparent);
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
  background: color-mix(in srgb, var(--color-primary) 85%, transparent);
  opacity: 0.9;
}
.kpi-accent-1::after { background: color-mix(in srgb, var(--color-primary) 90%, transparent); }
.kpi-accent-2::after { background: color-mix(in srgb, var(--color-success) 90%, transparent); }
.kpi-accent-3::after { background: color-mix(in srgb, var(--color-pink) 85%, transparent); }
.kpi-accent-4::after { background: color-mix(in srgb, var(--color-warning) 90%, transparent); }

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
  border-top: 1px solid var(--app-border);
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
  background: color-mix(in srgb, var(--app-text) 55%, transparent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--app-text) 8%, transparent);
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
  background: color-mix(in srgb, var(--app-card) 92%, transparent);
  border-color: var(--app-border);
  font-weight: 950;
}

:deep(.modern-dt .p-datatable-tbody > tr > td) {
  border-color: var(--app-border);
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
  background: color-mix(in srgb, var(--app-card) 92%, transparent);
  border: 1px solid var(--app-border);
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
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-danger) 35%, transparent);
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

/* =========================
   Filter Bar
========================= */
.filter-bar {
  margin-bottom: 12px;
  padding: 16px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 200px;
}

.filter-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.filter-date,
.filter-decks {
  width: 100%;
  min-width: 220px;
}

:deep(.filter-date .p-datepicker-input),
:deep(.filter-decks .p-multiselect-label) {
  background: rgba(0, 0, 0, 0.2);
  border-color: rgba(148, 163, 184, 0.2);
}

.filter-clear {
  margin-left: auto;
}

.filter-hint {
  margin-top: 12px;
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-hint kbd {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  font-family: monospace;
  font-size: 10px;
}

.filter-toggle-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

/* Slide-fade transition */
.slide-fade-enter-active {
  transition: all 0.3s ease-out;
}
.slide-fade-leave-active {
  transition: all 0.2s ease-in;
}
.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* =========================
   KPI Entry Animations
========================= */
@keyframes fadeSlideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.kpi-anim-1,
.kpi-anim-2,
.kpi-anim-3,
.kpi-anim-4 {
  animation: fadeSlideUp 0.5s ease-out forwards;
  opacity: 0;
}

.kpi-anim-1 { animation-delay: 0.1s; }
.kpi-anim-2 { animation-delay: 0.2s; }
.kpi-anim-3 { animation-delay: 0.3s; }
.kpi-anim-4 { animation-delay: 0.4s; }

/* Enhanced KPI hover */
.kpi {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.kpi:hover {
  transform: translateY(-4px) scale(1.02);
  box-shadow:
    0 20px 50px rgba(0, 0, 0, 0.35),
    0 0 0 1px rgba(99, 102, 241, 0.3);
}

.kpi:hover::after {
  height: 4px;
  opacity: 1;
}

/* =========================
   Chart Interactions
========================= */
.chart-card {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.chart-card:hover {
  transform: translateY(-2px);
  border-color: rgba(99, 102, 241, 0.3);
}

.chart-wrap {
  position: relative;
}

/* Clickable indicator */
.chart-wrap::after {
  content: 'Clique para detalhes';
  position: absolute;
  bottom: 10px;
  right: 10px;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.6);
  font-size: 11px;
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
}

.chart-wrap:hover::after {
  opacity: 0.8;
}

/* =========================
   Dialogs
========================= */
:deep(.modern-dialog) {
  border-radius: 18px;
  background: rgba(17, 24, 39, 0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.5);
}

:deep(.modern-dialog .p-dialog-header) {
  background: transparent;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  padding: 16px 20px;
}

:deep(.modern-dialog .p-dialog-content) {
  background: transparent;
  padding: 0;
}

.dlg-hdr {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dlg-hdr-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dlg-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.dlg-icon i {
  font-size: 18px;
  color: #6366F1;
}

.dlg-title {
  font-weight: 900;
  font-size: 16px;
  letter-spacing: -0.3px;
}

.dlg-sub {
  font-size: 12px;
  margin-top: 2px;
}

.dlg-body {
  padding: 20px;
}

/* Deck stats */
.deck-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.deck-stat {
  padding: 16px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(148, 163, 184, 0.1);
  text-align: center;
}

.deck-stat-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.deck-stat-value {
  font-size: 24px;
  font-weight: 1000;
  letter-spacing: -0.5px;
}

.deck-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

/* Day stats */
.day-stats {
  text-align: center;
  padding: 20px 0;
}

.day-stat-big .day-stat-value {
  font-size: 48px;
  font-weight: 1000;
  letter-spacing: -1px;
  background: linear-gradient(135deg, #6366F1, #8B5CF6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.day-stat-big .day-stat-label {
  font-size: 14px;
  margin-top: 4px;
}

.day-close-btn {
  width: 100%;
}

/* Mini legend clickable */
.mini-row {
  cursor: pointer;
  padding: 6px 8px;
  margin: -6px -8px;
  border-radius: 8px;
  transition: background 0.2s ease;
}

.mini-row:hover {
  background: rgba(255, 255, 255, 0.05);
}

@media (max-width: 640px) {
  .filter-row {
    flex-direction: column;
  }

  .filter-group {
    width: 100%;
    min-width: unset;
  }

  .filter-clear {
    margin-left: 0;
    width: 100%;
  }

  .deck-stats {
    grid-template-columns: 1fr;
  }
}
</style>
