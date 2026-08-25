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
import DatePicker from 'primevue/datepicker'
import MultiSelect from 'primevue/multiselect'
import Dialog from 'primevue/dialog'
import Divider from 'primevue/divider'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'

// App components - with lazy loading for performance
import SidebarMenu from '@/components/SidebarMenu.vue'
import LazyChart from '@/components/LazyChart.vue'
import ApiKeysDialog from '@/components/modals/ApiKeysDialog.vue'
import ModelSelectionDialog from '@/components/modals/ModelSelectionDialog.vue'
import PromptSettingsDialog from '@/components/modals/PromptSettingsDialog.vue'
import { sidebarIconColors } from '@/config/theme'

// Composables
import { useDashboardFilters } from '@/composables/useDashboardFilters'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { useSidebar } from '@/composables/useSidebar'
import { useApiKeysDialog } from '@/composables/useApiKeysDialog'
import { useModelSelectionDialog } from '@/composables/useModelSelectionDialog'
import { usePromptSettingsDialog } from '@/composables/usePromptSettingsDialog'
import { useAppNotifications } from '@/composables/useAppNotifications'
import { useAppToast } from '@/composables/useAppToast'
import { useTheme } from '@/composables/useTheme'

const router = useRouter()
const { isDark } = useTheme()
const { addNotification } = useAppNotifications()
const { notify: notifyToast } = useAppToast()

// Filters
const { dateRange, selectedDecks, hasActiveFilters, queryString, clearFilters } = useDashboardFilters()
const filtersExpanded = ref(true)

// Aba ativa — persistida para não voltar à "Visão geral" a cada visita
const TAB_STORAGE_KEY = 'green-deck.dashboard-tab'
const TAB_IDS = ['overview', 'performance', 'collection', 'maturity']
const activeTab = ref('overview')

try {
  const saved = localStorage.getItem(TAB_STORAGE_KEY)
  if (saved && TAB_IDS.includes(saved)) activeTab.value = saved
} catch {
  // localStorage indisponível — segue no padrão
}

watch(activeTab, (value) => {
  try {
    localStorage.setItem(TAB_STORAGE_KEY, value)
  } catch {
    // ignora: preferência de aba não é crítica
  }
})

// Lista de decks para o filtro. Antes vinha de `topDecks`, que é (a) limitado
// aos 12 maiores e (b) já filtrado por `selectedDecks` — então a lista encolhia
// conforme você filtrava e nunca mostrava a coleção inteira.
const allDeckNames = ref([])
const deckOptions = computed(() =>
  allDeckNames.value.map((name) => ({ label: name, value: name }))
)

async function fetchDeckOptions() {
  try {
    const res = await fetch('/api/anki-decks')
    const data = await readJsonSafe(res)
    if (data?.__nonJson || !res.ok || data?.success === false) return
    allDeckNames.value = Array.isArray(data.decks) ? [...data.decks].sort() : []
  } catch {
    allDeckNames.value = []
  }
}

// Refetch com debounce: alternar vários decks disparava uma reconstrução
// completa por clique. O guard anterior (`if (!loading)`) descartava a mudança
// quando havia busca em andamento, deixando a tela fora de sincronia com os
// filtros — agora a busca mais recente sempre vence.
let filterDebounce = null
watch([dateRange, selectedDecks], () => {
  if (filterDebounce) clearTimeout(filterDebounce)
  filterDebounce = setTimeout(fetchDashboard, 350)
}, { deep: true })

// Sidebar ref
const sidebarRef = ref(null)

// Dialog states
const deckDetailVisible = ref(false)
const selectedDeck = ref(null)
const dayDetailVisible = ref(false)
const selectedDay = ref(null)

function notify(message, severity = 'info', life = 3200) {
  const summary = String(message || '').trim()
  notifyToast({ message: summary, type: severity, duration: life })
  addNotification({ message: summary, severity, source: 'Dashboard' })
}

// ============================================================
// Sidebar — menu unificado (mesma estrutura em todas as páginas)
// ============================================================
const {
  visible: apiKeysVisible,
  storedKeys: apiKeysStored,
  hasStoredKeys: hasStoredApiKeys,
  open: openApiKeys,
  onSave: onApiKeysSave,
  onClear: onApiKeysClear
} = useApiKeysDialog({ notify })

// Seleção de modelo IA — abre localmente, persiste no localStorage
const {
  visible: modelSelectionVisible,
  availableModels: genAvailableModels,
  isLoadingModels: genModelsLoading,
  selectedModel: genModel,
  selectedValidationModel: genValidationModel,
  selectedAnalysisModel: genAnalysisModel,
  open: openModelSelection,
  save: saveModelSelection,
  fetchModels: refreshGenModels
} = useModelSelectionDialog({ notify })

// Prompts de geração — abre localmente, persiste no localStorage
const {
  visible: promptSettingsVisible,
  savedPrompts: genSavedPrompts,
  hasCustomPrompts: genHasCustomPrompts,
  open: openPromptSettings,
  onSave: onPromptsSave,
  onReset: onPromptsReset
} = usePromptSettingsDialog({ notify })

const { sidebarMenuItems, sidebarFooterActions } = useSidebar({
  activePage: 'dashboard',
  settings: {
    onModel: openModelSelection,
    onPrompts: openPromptSettings,
    onKeys: openApiKeys,
    promptsBadge: () => (genHasCustomPrompts.value ? '✓' : null)
  },
  topItems: () => [
    {
      key: 'refresh',
      label: 'Atualizar dados',
      icon: 'pi pi-refresh',
      iconColor: sidebarIconColors.generator,
      tooltip: 'Recarregar estatísticas do dashboard',
      command: fetchDashboard
    }
  ]
})

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
// Deck vem como "Pai::Filho::Neto" — nas tabelas mostramos só a folha
function deckLeaf(name) {
  const parts = String(name || '').split('::')
  return parts[parts.length - 1] || String(name || '')
}

// Espelha DASHBOARD_LEECH_MIN_LAPSES no backend (default do Anki para leech)
const leechMinLapses = 8

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

// Só a primeira carga mostra esqueleto. Depois disso os gráficos permanecem
// montados e apenas recebem dados novos — trocar entre Skeleton e LazyChart
// destruía e reconstruía os seis gráficos (e seus IntersectionObserver) a cada
// atualização de filtro.
const hasLoadedOnce = ref(false)
const showSkeletons = computed(() => loading.value && !hasLoadedOnce.value)
const isRefreshing = computed(() => loading.value && hasLoadedOnce.value)

// payloads do backend
const summary = ref(null) // { totalCards, totalDecks, statusBreakdown, segmentsMeta, reviewKpis }
const reviewsByDay = ref([]) // [{day, reviews}]
const studyTimeByDay = ref([]) // [{day, minutes}]
const successRateByDay = ref([]) // [{day, rate, correct, total}]
const topDecks = ref([]) // [{deckName, count}]
const segments = ref([]) // [{segment, count, avgInterval, avgEase, avgLapses, avgReps}]

// --- novas análises ---
const answerButtons = ref([])       // [{button, count, pct}]
const reviewsByHour = ref([])       // [{hour, reviews}]
const reviewsByWeekday = ref([])    // [{weekday, reviews}]
const retentionByInterval = ref([]) // [{bucket, total, correct, rate}]
const intervalDistribution = ref([])// [{bucket, count}]
const easeDistribution = ref([])    // [{bucket, count}]
const dueForecast = ref([])         // [{dayOffset, count}]
const leeches = ref([])             // [{cardId, deckName, lapses, reps, interval, ease, question}]

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

// Chart.js não lê CSS custom properties, então as cores de eixo/tooltip precisam
// ser resolvidas aqui. Como isto é computed sobre `isDark`, os gráficos se
// reajustam sozinhos na troca de tema — antes os eixos usavam o padrão escuro
// do Chart.js e ficavam ilegíveis no tema claro.
const chartTheme = computed(() => {
  const dark = isDark.value
  return {
    tick: dark ? 'rgba(226, 232, 240, 0.65)' : 'rgba(15, 23, 42, 0.6)',
    grid: dark ? 'rgba(148, 163, 184, 0.12)' : 'rgba(15, 23, 42, 0.08)',
    tooltipBg: dark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.97)',
    tooltipText: dark ? '#e5e7eb' : '#0f172a',
    tooltipBorder: dark ? 'rgba(148, 163, 184, 0.25)' : 'rgba(15, 23, 42, 0.12)'
  }
})

function themedTooltip(extra = {}) {
  const t = chartTheme.value
  return {
    backgroundColor: t.tooltipBg,
    titleColor: t.tooltipText,
    bodyColor: t.tooltipText,
    borderColor: t.tooltipBorder,
    borderWidth: 1,
    padding: 10,
    cornerRadius: 10,
    displayColors: false,
    ...extra
  }
}

// Eixos e tooltip compartilhados pelos gráficos de linha
function lineScaffold(extraY = {}) {
  const t = chartTheme.value
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      // Série única: a legenda só repetia o título do card
      legend: { display: false },
      tooltip: themedTooltip({ mode: 'index', intersect: false })
    },
    scales: {
      x: {
        ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8, color: t.tick, font: { size: 11 } },
        border: { display: false },
        grid: { display: false }
      },
      y: {
        beginAtZero: true,
        ticks: { maxTicksLimit: 5, color: t.tick, font: { size: 11 } },
        border: { display: false },
        grid: { color: t.grid },
        ...extraY
      }
    }
  }
}

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
  ...lineScaffold(),
  onClick: (event, elements) => {
    if (elements.length > 0) {
      const dataIndex = elements[0].index
      const clickedDay = reviewsByDay.value[dataIndex]
      if (clickedDay) openDayDetail(clickedDay)
    }
  },
  onHover: (event, elements) => {
    event.native.target.style.cursor = elements.length ? 'pointer' : 'default'
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

const studyTimeOptions = computed(() => {
  const base = lineScaffold()
  return {
    ...base,
    plugins: {
      ...base.plugins,
      tooltip: {
        ...base.plugins.tooltip,
        callbacks: { label: (ctx) => formatStudyTime(ctx.parsed.y) }
      }
    }
  }
})

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

const successRateOptions = computed(() => {
  const t = chartTheme.value
  const base = lineScaffold({
    max: 100,
    ticks: { maxTicksLimit: 5, color: t.tick, font: { size: 11 }, callback: (v) => `${v}%` }
  })
  return {
    ...base,
    plugins: {
      ...base.plugins,
      tooltip: {
        ...base.plugins.tooltip,
        callbacks: {
          label: (ctx) => {
            const dayData = successRateByDay.value[ctx.dataIndex]
            return `${ctx.parsed.y.toFixed(1)}% (${dayData?.correct ?? 0}/${dayData?.total ?? 0})`
          }
        }
      }
    }
  }
})

// Doughnut: Tipos/Status do Anki
const statusDoughnutData = computed(() => {
  const labels = statusItems.value.map((x) => x.status)
  const data = statusItems.value.map((x) => Number(x.count || 0))
  return { labels, datasets: [{ label: 'Tipos', data, borderWidth: 0, hoverOffset: 6 }] }
})

const doughnutOptions = computed(() => {
  return {
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
      // A lista abaixo do gráfico (.mini-legend) já traz rótulo, contagem e %,
      // então a legenda nativa era uma segunda legenda mais pobre.
      legend: { display: false },
      tooltip: themedTooltip({
        callbacks: {
          label: (ctx) => {
            const label = ctx.label || '—'
            const val = ctx.parsed || 0
            const total = statusTotal.value || 0
            const pct = total ? ((100 * val) / total).toFixed(1).replace('.', ',') : '0,0'
            return `${label}: ${formatInt(val)} (${pct}%) — clique para filtrar`
          }
        }
      })
    }
  }
})

// Barras: Total por deck (melhor legibilidade = horizontal)
const deckBarData = computed(() => {
  const items = topDecks.value || []
  const labels = items.map((x) => x.deckName || '—')
  const data = items.map((x) => Number(x.count || 0))
  return { labels, datasets: [{ label: 'Cartões por deck (Top 12)', data, borderRadius: 10 }] }
})

const deckBarOptions = computed(() => {
  const t = chartTheme.value
  return {
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
      legend: { display: false },
      tooltip: themedTooltip({
        callbacks: { label: (ctx) => `${formatInt(ctx.parsed.x)} cartões — clique para detalhes` }
      })
    },
    scales: {
      x: {
        beginAtZero: true,
        ticks: { maxTicksLimit: 5, color: t.tick, font: { size: 11 } },
        border: { display: false },
        grid: { color: t.grid }
      },
      y: {
        // Nomes de deck são longos ("Pai::Filho::Neto") e estouravam o eixo
        ticks: {
          autoSkip: false,
          color: t.tick,
          font: { size: 11 },
          callback(value) {
            const raw = String(this.getLabelForValue(value) ?? '')
            const leaf = raw.split('::').pop() || raw
            return leaf.length > 22 ? `${leaf.slice(0, 21)}…` : leaf
          }
        },
        border: { display: false },
        grid: { display: false }
      }
    }
  }
})

// Barras: Segmentos (KMeans)
const segmentsBarData = computed(() => {
  const items = segments.value || []
  const labels = items.map((x) => x.segment || '—')
  const data = items.map((x) => Number(x.count || 0))
  return { labels, datasets: [{ label: 'Distribuição por segmento', data, borderRadius: 10 }] }
})

const segmentsBarOptions = computed(() => {
  const t = chartTheme.value
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: themedTooltip({
        callbacks: { label: (ctx) => `${formatInt(ctx.parsed.y)} cartões` }
      })
    },
    scales: {
      x: { ticks: { color: t.tick, font: { size: 11 } }, border: { display: false }, grid: { display: false } },
      y: {
        beginAtZero: true,
        ticks: { maxTicksLimit: 5, color: t.tick, font: { size: 11 } },
        border: { display: false },
        grid: { color: t.grid }
      }
    }
  }
})

const segmentsMetaText = computed(() => {
  const m = summary.value?.segmentsMeta
  if (!m) return ''
  const k = m.k ?? '—'
  const sampled = m.sampled ?? '—'
  return `K=${k} · amostra=${sampled}`
})

// ---------- Novas análises ----------

// Cores dos botões seguem o significado da resposta, não uma paleta arbitrária:
// errar é vermelho, acertar com folga é verde.
const ANSWER_COLORS = {
  Again: '#EF4444',
  Hard: '#F59E0B',
  Good: '#10B981',
  Easy: '#3B82F6'
}

const answerButtonsData = computed(() => ({
  labels: answerButtons.value.map((x) => x.button),
  datasets: [{
    data: answerButtons.value.map((x) => Number(x.count || 0)),
    backgroundColor: answerButtons.value.map((x) => ANSWER_COLORS[x.button] || '#64748B'),
    borderWidth: 0,
    borderRadius: 8
  }]
}))

const answerButtonsOptions = computed(() => {
  const t = chartTheme.value
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: themedTooltip({
        callbacks: {
          label: (ctx) => {
            const row = answerButtons.value[ctx.dataIndex]
            return `${formatInt(row?.count)} respostas (${format2(row?.pct)}%)`
          }
        }
      })
    },
    scales: {
      x: { ticks: { color: t.tick, font: { size: 11 } }, border: { display: false }, grid: { display: false } },
      y: {
        beginAtZero: true,
        ticks: { maxTicksLimit: 5, color: t.tick, font: { size: 11 } },
        border: { display: false },
        grid: { color: t.grid }
      }
    }
  }
})

const reviewsByHourData = computed(() => ({
  labels: reviewsByHour.value.map((x) => `${String(x.hour).padStart(2, '0')}h`),
  datasets: [{
    data: reviewsByHour.value.map((x) => Number(x.reviews || 0)),
    backgroundColor: '#6366F1',
    borderRadius: 6,
    borderWidth: 0
  }]
}))

const reviewsByWeekdayData = computed(() => ({
  labels: reviewsByWeekday.value.map((x) => x.weekday),
  datasets: [{
    data: reviewsByWeekday.value.map((x) => Number(x.reviews || 0)),
    backgroundColor: '#8B5CF6',
    borderRadius: 8,
    borderWidth: 0
  }]
}))

// Barras simples com eixo Y de contagem — reaproveitado por hora/dia da semana
function countBarOptions(unitLabel = 'reviews') {
  const t = chartTheme.value
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: themedTooltip({
        callbacks: { label: (ctx) => `${formatInt(ctx.parsed.y)} ${unitLabel}` }
      })
    },
    scales: {
      x: {
        ticks: { color: t.tick, font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
        border: { display: false },
        grid: { display: false }
      },
      y: {
        beginAtZero: true,
        ticks: { maxTicksLimit: 5, color: t.tick, font: { size: 11 } },
        border: { display: false },
        grid: { color: t.grid }
      }
    }
  }
}

const reviewsByHourOptions = computed(() => countBarOptions('reviews'))
const reviewsByWeekdayOptions = computed(() => countBarOptions('reviews'))

const retentionData = computed(() => ({
  labels: retentionByInterval.value.map((x) => x.bucket),
  datasets: [{
    data: retentionByInterval.value.map((x) => Number(x.rate || 0)),
    backgroundColor: '#10B981',
    borderRadius: 8,
    borderWidth: 0
  }]
}))

const retentionOptions = computed(() => {
  const t = chartTheme.value
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: themedTooltip({
        callbacks: {
          label: (ctx) => {
            const row = retentionByInterval.value[ctx.dataIndex]
            return `${format2(row?.rate)}% de acerto (${formatInt(row?.correct)}/${formatInt(row?.total)})`
          }
        }
      })
    },
    scales: {
      x: { ticks: { color: t.tick, font: { size: 11 } }, border: { display: false }, grid: { display: false } },
      y: {
        beginAtZero: true,
        max: 100,
        ticks: { maxTicksLimit: 5, color: t.tick, font: { size: 11 }, callback: (v) => `${v}%` },
        border: { display: false },
        grid: { color: t.grid }
      }
    }
  }
})

const intervalDistData = computed(() => ({
  labels: intervalDistribution.value.map((x) => x.bucket),
  datasets: [{
    data: intervalDistribution.value.map((x) => Number(x.count || 0)),
    backgroundColor: '#6366F1',
    borderRadius: 8,
    borderWidth: 0
  }]
}))

const easeDistData = computed(() => ({
  labels: easeDistribution.value.map((x) => x.bucket),
  datasets: [{
    data: easeDistribution.value.map((x) => Number(x.count || 0)),
    backgroundColor: '#F59E0B',
    borderRadius: 8,
    borderWidth: 0
  }]
}))

const cardCountBarOptions = computed(() => countBarOptions('cartões'))

// Previsão de carga: rótulo em "hoje / amanhã / +N d" é mais legível que a data
const forecastData = computed(() => ({
  labels: dueForecast.value.map((x) => {
    if (x.dayOffset === 0) return 'hoje'
    if (x.dayOffset === 1) return 'amanhã'
    return `+${x.dayOffset}d`
  }),
  datasets: [{
    data: dueForecast.value.map((x) => Number(x.count || 0)),
    backgroundColor: '#0EA5E9',
    borderRadius: 5,
    borderWidth: 0
  }]
}))

const forecastOptions = computed(() => countBarOptions('cartões a vencer'))

const forecastTotal = computed(() =>
  dueForecast.value.reduce((sum, x) => sum + Number(x.count || 0), 0)
)
const forecastPeak = computed(() =>
  dueForecast.value.reduce((max, x) => Math.max(max, Number(x.count || 0)), 0)
)

// Resumo textual dos hábitos: qual a hora e o dia mais produtivos
const peakHour = computed(() => {
  if (!reviewsByHour.value.length) return null
  return reviewsByHour.value.reduce((best, x) => (x.reviews > (best?.reviews ?? -1) ? x : best), null)
})
const peakWeekday = computed(() => {
  if (!reviewsByWeekday.value.length) return null
  return reviewsByWeekday.value.reduce((best, x) => (x.reviews > (best?.reviews ?? -1) ? x : best), null)
})

function openLeechInBrowser(row) {
  router.push({ path: '/browser', query: { filter: `cid:${row.cardId}` } })
}

// --- fetch ---
// Uma requisição só: /api/dashboard/all devolve o payload inteiro. Antes eram
// seis chamadas paralelas e cada uma reconstruía/retornava o mesmo conjunto
// completo — cinco cópias eram baixadas e descartadas.
let inFlight = null
let requestSeq = 0

function itemsOf(block) {
  return Array.isArray(block?.items) ? block.items : []
}

async function fetchDashboard() {
  // Cancela a busca anterior: sem isso, respostas antigas podiam chegar depois
  // das novas e sobrescrever a tela com dados de outro filtro.
  inFlight?.abort()
  const controller = new AbortController()
  inFlight = controller
  const seq = ++requestSeq

  loading.value = true
  errorMsg.value = ''

  const qs = queryString.value
  const url = `/api/dashboard/all${qs ? `${qs}&` : '?'}top_decks_limit=12`

  try {
    const res = await fetch(url, { signal: controller.signal })
    const data = await readJsonSafe(res)

    if (data?.__nonJson) throw new Error(`dashboard: resposta não-JSON — ${data.__head}`)
    if (data?.__jsonParseError) throw new Error(`dashboard: JSON inválido — ${data.__message}`)
    if (!res.ok || data?.success === false) {
      throw new Error(data?.error || data?.detail || `dashboard: HTTP ${res.status}`)
    }

    // Descarta respostas que já não são a mais recente
    if (seq !== requestSeq) return

    summary.value = data.summary ?? null
    reviewsByDay.value = itemsOf(data.reviews_by_day)
    studyTimeByDay.value = itemsOf(data.study_time_by_day)
    successRateByDay.value = itemsOf(data.success_rate_by_day)
    topDecks.value = itemsOf(data.top_decks)
    segments.value = itemsOf(data.segments)

    answerButtons.value = itemsOf(data.answer_buttons)
    reviewsByHour.value = itemsOf(data.reviews_by_hour)
    reviewsByWeekday.value = itemsOf(data.reviews_by_weekday)
    retentionByInterval.value = itemsOf(data.retention_by_interval)
    intervalDistribution.value = itemsOf(data.interval_distribution)
    easeDistribution.value = itemsOf(data.ease_distribution)
    dueForecast.value = itemsOf(data.due_forecast)
    leeches.value = itemsOf(data.leeches)

    hasLoadedOnce.value = true
  } catch (e) {
    if (e?.name === 'AbortError') return  // substituída por uma busca mais nova
    if (seq !== requestSeq) return
    errorMsg.value = e?.message || String(e)
    notify(errorMsg.value, 'error', 7000)
  } finally {
    if (seq === requestSeq) {
      loading.value = false
      inFlight = null
    }
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
  // 1-4 = troca de aba
  if (['1', '2', '3', '4'].includes(e.key) && !e.ctrlKey && !e.metaKey) {
    e.preventDefault()
    activeTab.value = TAB_IDS[Number(e.key) - 1]
  }
  // Escape = Close any open dialog
  if (e.key === 'Escape') {
    deckDetailVisible.value = false
    dayDetailVisible.value = false
  }
}

onMounted(() => {
  fetchDeckOptions()
  fetchDashboard()
  document.addEventListener('keydown', handleKeyboard)
})

onUnmounted(() => {
  if (filterDebounce) clearTimeout(filterDebounce)
  inFlight?.abort()
  document.removeEventListener('keydown', handleKeyboard)
})
</script>

<template>
  <!-- Sidebar -->
  <SidebarMenu
    ref="sidebarRef"
    :menu-items="sidebarMenuItems"
    :footer-actions="sidebarFooterActions"
  />

  <div class="app-shell" :class="{ 'sidebar-expanded': sidebarRef?.sidebarExpanded, 'sidebar-closed': sidebarRef && !sidebarRef.sidebarOpen }">
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
            Atalhos: <kbd>R</kbd> atualizar · <kbd>F</kbd> filtros · <kbd>1</kbd>–<kbd>4</kbd> abas · <kbd>Esc</kbd> fechar dialogs
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
                  <Skeleton v-if="showSkeletons" width="9rem" height="1.7rem" />
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
                  <Skeleton v-if="showSkeletons" width="9rem" height="1.7rem" />
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
                  <Skeleton v-if="showSkeletons" width="9rem" height="1.7rem" />
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
                  <Skeleton v-if="showSkeletons" width="9rem" height="1.7rem" />
                  <span v-else>{{ format2(animatedSuccessRate) }}%</span>
                </div>
              </div>
            </div>
          </template>
        </Card>
      </div>

      <Tabs v-model:value="activeTab" lazy class="dash-tabs">
        <TabList>
          <Tab value="overview"><i class="pi pi-home mr-2" />Visão geral</Tab>
          <Tab value="performance"><i class="pi pi-chart-line mr-2" />Desempenho</Tab>
          <Tab value="collection"><i class="pi pi-database mr-2" />Coleção</Tab>
          <Tab value="maturity"><i class="pi pi-sparkles mr-2" />Maturidade</Tab>
        </TabList>
        <TabPanels>
          <TabPanel value="overview">
          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Reviews por dia</div>
                <div class="card-sub muted">Histórico de revisões</div>
              </div>
            </div>

            <div class="chart-wrap is-clickable" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="line" :data="reviewsLineData" :options="reviewsLineOptions" height="300px" />
            </div>
          </div>

          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Tipos de cartões (Anki)</div>
                <div class="card-sub muted">Novos · Aprendendo · Revisão · Due · Suspensos</div>
              </div>
              <Tag class="pill" severity="secondary">{{ formatInt(statusTotal) }}</Tag>
            </div>

            <div class="chart-wrap is-clickable" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="doughnut" :data="statusDoughnutData" :options="doughnutOptions" height="300px" />
            </div>

            <div v-if="!showSkeletons" class="mini-legend">
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

          <div class="grid grid-single">
            <div class="card-surface chart-card">
              <div class="card-head">
                <div>
                  <div class="card-title">Previsão de carga</div>
                  <div class="card-sub muted">Cartões a vencer nos próximos 30 dias</div>
                </div>
                <div class="card-head-tags">
                  <Tag class="pill" severity="secondary">{{ formatInt(forecastTotal) }} no total</Tag>
                  <Tag class="pill" :severity="forecastPeak > 200 ? 'warn' : 'secondary'">
                    pico {{ formatInt(forecastPeak) }}/dia
                  </Tag>
                </div>
              </div>
              <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
                <Skeleton v-if="showSkeletons" width="100%" height="290px" />
                <LazyChart v-else type="bar" :data="forecastData" :options="forecastOptions" height="300px" />
              </div>
            </div>
          </div>
          </TabPanel>

          <TabPanel value="performance">
          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Tempo de estudo</div>
                <div class="card-sub muted">Minutos por dia</div>
              </div>
            </div>

            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="line" :data="studyTimeLineData" :options="studyTimeOptions" height="300px" />
            </div>
          </div>

          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Taxa de acerto</div>
                <div class="card-sub muted">% de acertos ao longo do tempo</div>
              </div>
            </div>

            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="line" :data="successRateLineData" :options="successRateOptions" height="300px" />
            </div>
          </div>

          <div class="grid">
          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Botões de resposta</div>
                <div class="card-sub muted">Distribuição entre Again · Hard · Good · Easy</div>
              </div>
            </div>
            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="bar" :data="answerButtonsData" :options="answerButtonsOptions" height="300px" />
            </div>
          </div>

          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Retenção por intervalo</div>
                <div class="card-sub muted">% de acerto conforme o intervalo anterior do cartão</div>
              </div>
            </div>
            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="bar" :data="retentionData" :options="retentionOptions" height="300px" />
            </div>
          </div>
          </div>

          <div class="grid">
          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Reviews por hora</div>
                <div class="card-sub muted">Quando você estuda (horário local)</div>
              </div>
              <Tag class="pill" severity="secondary">{{ peakHour ? `pico ${String(peakHour.hour).padStart(2, "0")}h` : "—" }}</Tag>
            </div>
            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="bar" :data="reviewsByHourData" :options="reviewsByHourOptions" height="300px" />
            </div>
          </div>

          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Reviews por dia da semana</div>
                <div class="card-sub muted">Distribuição semanal do esforço</div>
              </div>
              <Tag class="pill" severity="secondary">{{ peakWeekday ? `pico ${peakWeekday.weekday}` : "—" }}</Tag>
            </div>
            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="bar" :data="reviewsByWeekdayData" :options="reviewsByWeekdayOptions" height="300px" />
            </div>
          </div>
          </div>
          </TabPanel>

          <TabPanel value="collection">
          <div class="grid">
          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Distribuição de intervalos</div>
                <div class="card-sub muted">Quantos cartões em cada faixa de intervalo</div>
              </div>
            </div>
            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="bar" :data="intervalDistData" :options="cardCountBarOptions" height="300px" />
            </div>
          </div>

          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Distribuição de ease</div>
                <div class="card-sub muted">Facilidade acumulada dos cartões</div>
              </div>
            </div>
            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="bar" :data="easeDistData" :options="cardCountBarOptions" height="300px" />
            </div>
          </div>
          </div>

          <div class="grid">
          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Total por deck</div>
                <div class="card-sub muted">Ranking (Top 12) — melhor legibilidade em modo horizontal</div>
              </div>
            </div>

            <div class="chart-wrap is-clickable" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="bar" :data="deckBarData" :options="deckBarOptions" height="300px" />
            </div>
          </div>

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
              <Column field="count" header="Cartões" sortable style="width: 9rem">
                <template #body="{ data }">{{ formatInt(data.count) }}</template>
              </Column>
            </DataTable>
          </div>
          </div>
          </TabPanel>

          <TabPanel value="maturity">
          <div class="grid">
          <div class="card-surface chart-card">
            <div class="card-head">
              <div>
                <div class="card-title">Segmentos de maturidade</div>
                <div class="card-sub muted">KMeans (scikit-learn) — agrupamento por comportamento</div>
              </div>
              <Tag class="pill" severity="secondary">{{ segmentsMetaText || '—' }}</Tag>
            </div>

            <div class="chart-wrap" :class="{ 'is-refreshing': isRefreshing }">
              <Skeleton v-if="showSkeletons" width="100%" height="290px" />
              <LazyChart v-else type="bar" :data="segmentsBarData" :options="segmentsBarOptions" height="300px" />
            </div>
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

            <div class="grid grid-single">
        <div class="card-surface table-card">
          <div class="card-head">
            <div>
              <div class="card-title">Cartões problemáticos</div>
              <div class="card-sub muted">
                Mais de {{ leechMinLapses }} lapsos — candidatos a reformular ou suspender
              </div>
            </div>
            <Tag class="pill" :severity="leeches.length ? 'warn' : 'secondary'">
              {{ formatInt(summary?.leechCount ?? 0) }}
            </Tag>
          </div>

          <div v-if="!showSkeletons && !leeches.length" class="empty muted">
            <div class="empty-ico"><i class="pi pi-check-circle"></i></div>
            <div>
              Nenhum cartão problemático nos filtros atuais.
              <div class="muted tiny">Bom sinal: nenhum cartão acumulou lapsos demais.</div>
            </div>
          </div>

          <DataTable
            v-else
            :value="leeches"
            stripedRows
            rowHover
            class="modern-dt"
            :loading="loading"
            :paginator="leeches.length > 10"
            :rows="10"
            responsiveLayout="scroll"
            @rowClick="openLeechInBrowser($event.data)"
          >
            <Column field="question" header="Cartão" sortable>
              <template #body="{ data }">
                <span class="leech-q" :title="data.question">{{ data.question || '—' }}</span>
              </template>
            </Column>
            <Column field="deckName" header="Deck" sortable style="width: 14rem">
              <template #body="{ data }">
                <span class="leech-deck" :title="data.deckName">{{ deckLeaf(data.deckName) }}</span>
              </template>
            </Column>
            <Column field="lapses" header="Lapsos" sortable style="width: 7rem">
              <template #body="{ data }">
                <span class="leech-lapses">{{ formatInt(data.lapses) }}</span>
              </template>
            </Column>
            <Column field="reps" header="Reps" sortable style="width: 6rem">
              <template #body="{ data }">{{ formatInt(data.reps) }}</template>
            </Column>
            <Column field="ease" header="Ease" sortable style="width: 6rem">
              <template #body="{ data }">{{ format2(data.ease) }}</template>
            </Column>
          </DataTable>
        </div>
      </div>
          </TabPanel>
        </TabPanels>
      </Tabs>

      <div class="footer-space" />
    </div>
  </div>

  <!-- Configurações (menu lateral) — diálogos hospedados nesta página -->
  <ApiKeysDialog
    v-model:visible="apiKeysVisible"
    :stored-keys="apiKeysStored"
    :has-stored-keys="hasStoredApiKeys"
    @save="onApiKeysSave"
    @clear="onApiKeysClear"
  />

  <ModelSelectionDialog
    v-model:visible="modelSelectionVisible"
    :available-models="genAvailableModels"
    :selected-model="genModel"
    :selected-validation-model="genValidationModel"
    :selected-analysis-model="genAnalysisModel"
    :is-loading-models="genModelsLoading"
    @update:selected-model="genModel = $event"
    @update:selected-validation-model="genValidationModel = $event"
    @update:selected-analysis-model="genAnalysisModel = $event"
    @save="saveModelSelection"
    @refresh="refreshGenModels"
  />

  <PromptSettingsDialog
    v-model:visible="promptSettingsVisible"
    :saved-prompts="genSavedPrompts"
    :has-custom-prompts="genHasCustomPrompts"
    @save="onPromptsSave"
    @reset="onPromptsReset"
  />

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
          <div class="deck-stat-label muted">Total de cartões</div>
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
  margin-left: 96px; /* 12px + sidebar 72px + 12px */
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

/* Sidebar fechada (via ×): o shell recupera a largura toda */
.app-shell.sidebar-closed {
  margin-left: 12px;
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

/* Pesos acima de 900 são recortados para 900 pelo navegador — usar 950/1000 em
   tudo achatava a hierarquia. Título forte, subtítulo discreto. */
.card-title {
  font-weight: 800;
  font-size: 15px;
  letter-spacing: -0.25px;
  line-height: 1.15;
}

.card-sub {
  margin-top: 3px;
  font-size: 12px;
  opacity: 0.7;
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

.kpi :deep(.p-card-body) {
  padding: 16px;
}

.kpi-top {
  display: flex;
  gap: 12px;
  align-items: center;
}

.kpi-ico {
  width: 42px;
  height: 42px;
  border-radius: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--ghost-bg-strong);
  border: 1px solid var(--ghost-border);
}

.kpi-ico i {
  font-size: 17px;
}

/* O ícone herda o acento do card, para faixa e ícone contarem a mesma história */
.kpi-accent-1 .kpi-ico i { color: var(--color-primary); }
.kpi-accent-2 .kpi-ico i { color: var(--color-success); }
.kpi-accent-3 .kpi-ico i { color: var(--color-pink); }
.kpi-accent-4 .kpi-ico i { color: var(--color-warning); }

.kpi-accent-1 .kpi-ico { background: color-mix(in srgb, var(--color-primary) 12%, transparent); }
.kpi-accent-2 .kpi-ico { background: color-mix(in srgb, var(--color-success) 12%, transparent); }
.kpi-accent-3 .kpi-ico { background: color-mix(in srgb, var(--color-pink) 12%, transparent); }
.kpi-accent-4 .kpi-ico { background: color-mix(in srgb, var(--color-warning) 12%, transparent); }

.kpi-lbl {
  font-weight: 600;
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  opacity: 0.6;
}

.kpi-val {
  margin-top: 5px;
  font-size: 26px;
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.8px;
  font-variant-numeric: tabular-nums;
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

/* =========================
   Abas
========================= */
.dash-tabs {
  margin-top: 12px;
}

.dash-tabs :deep(.p-tablist-tab-list) {
  background: transparent;
  border-bottom: 1px solid var(--app-border);
  gap: 4px;
}

.dash-tabs :deep(.p-tab) {
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  padding: 10px 16px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--app-text-muted);
  transition: color 0.15s ease, border-color 0.15s ease;
}

.dash-tabs :deep(.p-tab:hover) {
  color: var(--app-text);
}

.dash-tabs :deep(.p-tab[data-p-active='true']) {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.dash-tabs :deep(.p-tabpanels) {
  background: transparent;
  padding: 0;
}

/* A primeira grade de cada aba não precisa do respiro que separa linhas irmãs */
.dash-tabs :deep(.p-tabpanel) > .grid:first-child {
  margin-top: 14px;
}

/* Grid blocks */
.grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* Linha de card único (ex.: previsão de carga, leeches) */
.grid-single {
  grid-template-columns: 1fr;
}

.card-head-tags {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

/* Tabela de cartões problemáticos */
.leech-q {
  display: block;
  max-width: 52ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.leech-deck {
  display: block;
  max-width: 18ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.8;
}
.leech-lapses {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--color-warning);
}

/* Em telas grandes só a primeira linha é assimétrica (série temporal larga +
   rosca estreita). Antes o 1.25/0.75 valia para TODAS as linhas, deixando
   torto até onde os dois cards são pares — dois gráficos de linha, duas
   tabelas. */
@media (min-width: 1400px) {
  .grid-wide-first {
    grid-template-columns: 1.35fr 0.65fr;
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

/* Os gráficos ficam montados durante a atualização (não são mais destruídos),
   então o estado de carregamento precisa aparecer sobre eles. */
.chart-wrap.is-refreshing {
  position: relative;
  pointer-events: none;
}
/* Esmaece o gráfico, não o wrapper — senão o spinner abaixo some junto */
.chart-wrap.is-refreshing > * {
  opacity: 0.45;
  transition: opacity 0.2s ease;
}
/* Usa ::before para não disputar o ::after com a dica de clique */
.chart-wrap.is-refreshing::before {
  content: '';
  position: absolute;
  z-index: 1;
  top: 10px;
  left: 50%;
  width: 18px;
  height: 18px;
  margin-left: -9px;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
  border-top-color: var(--color-primary);
  animation: chart-spin 0.7s linear infinite;
}
@keyframes chart-spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .chart-wrap.is-refreshing::before { animation: none; }
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

/* Dica de clique — só nos gráficos que realmente respondem ao clique.
   Antes valia para .chart-wrap inteiro, prometendo interação também em
   "Tempo de estudo", "Taxa de acerto" e "Segmentos", que não têm onClick. */
.chart-wrap.is-clickable::after {
  content: 'Clique para detalhes';
  position: absolute;
  bottom: 10px;
  right: 10px;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--ghost-bg-strong);
  border: 1px solid var(--ghost-border);
  color: var(--app-text);
  font-size: 11px;
  font-weight: 600;
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
}

.chart-wrap.is-clickable:hover::after {
  opacity: 0.9;
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
