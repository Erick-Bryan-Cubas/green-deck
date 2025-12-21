<script setup>
import { computed, ref } from 'vue'

// PrimeVue components (v4: Dropdown -> Select, Sidebar -> Drawer, etc.) :contentReference[oaicite:6]{index=6}
import Button from 'primevue/button'
import Select from 'primevue/select'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Checkbox from 'primevue/checkbox'
import Textarea from 'primevue/textarea'
import Tag from 'primevue/tag'
import Menu from 'primevue/menu'
import Splitter from 'primevue/splitter'
import SplitterPanel from 'primevue/splitterpanel'
import Drawer from 'primevue/drawer'

import AnkiStatus from './components/AnkiStatus.vue'
import TextEditor from './components/TextEditor.vue'

// sua service já existe em frontend/src/services/claude-api.js
import {
  analyzeTextWithClaude,
  generateCardsWithStream,
  getStoredApiKeys,
  storeApiKeys,
  validateAnthropicApiKey
} from '@/services/claude-api.js'

// -------------------- state --------------------
const cards = ref([])
const selectedText = ref('')
const documentContext = ref('')
const decks = ref({ General: 'general' }) // deckName -> deckId
const currentDeck = ref('General')

const isAnalyzing = ref(false)
const isGenerating = ref(false)

const timerVisible = ref(false)
const timerText = ref('Processing...')
const timerSeconds = ref(0)
let timerHandle = null

const logsOpen = ref(false)
const logs = ref([]) // {ts, type, msg}

const apiDialogOpen = ref(false)
const ankiDialogOpen = ref(false)

const anthropicApiKey = ref(getStoredApiKeys()?.anthropicApiKey || '')
const mochiApiKey = ref(getStoredApiKeys()?.mochiApiKey || '')
const storeLocally = ref(true)
const anthropicApiKeyError = ref('')

const ankiModelsData = ref(null)
const ankiModel = ref('')
const ankiFrontField = ref('')
const ankiBackField = ref('')
const ankiDeckField = ref('')
const ankiTags = ref('')

const cardType = ref('basic')
const cardTypeOptions = [
  { label: 'Gerar Cartões Básicos', value: 'basic' },
  { label: 'Gerar Cartões Cloze', value: 'cloze' },
  { label: 'Gerar Cartões Básicos e Cloze', value: 'both' }
]

// PrimeVue menu
const menuRef = ref(null)

const hasCards = computed(() => cards.value.length > 0)
const hasSelection = computed(() => selectedText.value.trim().length > 0)

const exportLabel = computed(() => (getStoredApiKeys()?.mochiApiKey ? 'Exportar para Mochi' : 'Exportar Markdown'))

const menuItems = computed(() => ([
  {
    label: exportLabel.value,
    icon: 'pi pi-upload',
    command: () => exportToMochiOrMarkdown(),
    disabled: !hasCards.value
  },
  {
    label: 'Exportar para Anki',
    icon: 'pi pi-book',
    command: () => openAnkiDialog(),
    disabled: !hasCards.value
  },
  { separator: true },
  {
    label: 'Limpar cards',
    icon: 'pi pi-trash',
    command: () => clearCards(),
    disabled: !hasCards.value
  },
  {
    label: 'API Keys',
    icon: 'pi pi-key',
    command: () => (apiDialogOpen.value = true)
  }
]))

function addLog(msg, type = 'info') {
  logs.value.push({
    ts: new Date().toLocaleTimeString(),
    type,
    msg
  })
}

// -------------------- timer helpers --------------------
function startTimer(text) {
  timerText.value = text
  timerSeconds.value = 0
  timerVisible.value = true
  if (timerHandle) clearInterval(timerHandle)
  timerHandle = setInterval(() => (timerSeconds.value += 1), 1000)
}
function stopTimer() {
  if (timerHandle) clearInterval(timerHandle)
  timerHandle = null
  timerVisible.value = false
}

// -------------------- decks (Mochi) --------------------
async function fetchDecks() {
  const key = getStoredApiKeys()?.mochiApiKey
  if (!key) {
    decks.value = { General: 'general' }
    currentDeck.value = 'General'
    return
  }

  try {
    const res = await fetch(`/api/mochi-decks?userMochiKey=${encodeURIComponent(key)}`)
    if (!res.ok) throw new Error('Falha ao buscar decks no backend')
    const data = await res.json()

    if (data?.success && data?.decks) {
      decks.value = data.decks
      currentDeck.value = Object.keys(decks.value)[0] || 'General'
      addLog(`Decks carregados (${Object.keys(decks.value).length})`, 'success')
      return
    }
    throw new Error('Resposta inesperada ao buscar decks')
  } catch (e) {
    decks.value = { General: 'general' }
    currentDeck.value = 'General'
    addLog(`Fallback de decks: ${e.message}`, 'error')
  }
}

// -------------------- analyze (debounce) --------------------
let analyzeDebounce = null
function onPlainTextChange(fullText) {
  // debounce simples (1.5s)
  if (analyzeDebounce) clearTimeout(analyzeDebounce)
  analyzeDebounce = setTimeout(() => {
    const t = (fullText || '').trim()
    if (t.length > 100) analyzeDocument(t)
  }, 1500)
}

async function analyzeDocument(text) {
  if (isAnalyzing.value) return
  isAnalyzing.value = true
  startTimer('Analyzing text...')
  addLog('Starting text analysis...', 'info')

  try {
    const context = await analyzeTextWithClaude(text)
    if (context) {
      documentContext.value = context
      addLog('Text analysis completed', 'success')
    }
  } catch (e) {
    addLog(`Analysis error: ${e.message}`, 'error')
  } finally {
    stopTimer()
    isAnalyzing.value = false
  }
}

// -------------------- generate cards --------------------
async function generateCards(typeOverride = null, textOverride = null) {
  const text = (textOverride ?? selectedText.value).trim()
  if (!text) return

  const type = typeOverride ?? cardType.value

  isGenerating.value = true
  startTimer('Generating cards...')
  addLog(`Starting card generation (${type})...`, 'info')

  try {
    const deckNames = Object.keys(decks.value).join(', ')
    const newCards = await generateCardsWithStream(
      text,
      deckNames,
      documentContext.value,
      type,
      ({ stage, data }) => {
        if (stage === 'stage' && data?.stage) addLog(`Stage: ${data.stage}`, 'info')
      }
    )

    cards.value = [...cards.value, ...(newCards || [])]
    addLog(`Generated ${newCards.length} cards successfully`, 'success')
  } catch (e) {
    addLog(`Generation error: ${e.message}`, 'error')
  } finally {
    stopTimer()
    isGenerating.value = false
  }
}

// -------------------- export --------------------
function formatCardsForMochi() {
  const deckMap = decks.value
  const data = { version: 2, cards: [] }

  for (const c of cards.value) {
    const deckId = deckMap[c.deck] || deckMap[currentDeck.value]
    if (!deckId) continue
    data.cards.push({
      content: `${c.front}\n---\n${c.back}`,
      'deck-id': deckId
    })
  }
  return data
}

async function exportToMochiOrMarkdown() {
  const key = getStoredApiKeys()?.mochiApiKey
  if (!key) return exportAsMarkdown()

  try {
    const mochiData = formatCardsForMochi()
    const res = await fetch('/api/upload-to-mochi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cards: mochiData.cards, userMochiKey: key })
    })
    if (!res.ok) throw new Error('Falha ao exportar para Mochi')

    const out = await res.json()
    addLog(`Mochi export: ${out.totalSuccess}/${out.totalCards}`, 'success')
  } catch (e) {
    addLog(`Mochi export error: ${e.message} (fallback markdown)`, 'error')
    exportAsMarkdown()
  }
}

function exportAsMarkdown() {
  let md = `# Flashcards - ${new Date().toLocaleDateString()}\n\n`
  const groups = {}

  for (const c of cards.value) {
    const d = c.deck || 'General'
    groups[d] = groups[d] || []
    groups[d].push(c)
  }

  for (const [deckName, list] of Object.entries(groups)) {
    md += `## ${deckName}\n\n`
    list.forEach((c, i) => {
      md += `### Card ${i + 1}\n\n`
      md += `**Question:** ${c.front}\n\n---\n\n**Answer:** ${c.back}\n\n`
    })
  }

  const blob = new Blob([md], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `flashcards-${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(url)

  addLog(`Exported ${cards.value.length} cards as markdown`, 'success')
}

// -------------------- anki flow --------------------
async function openAnkiDialog() {
  try {
    const res = await fetch('/api/anki-models')
    if (!res.ok) throw new Error('Não conectou no Anki. Verifique Anki + AnkiConnect.')
    const data = await res.json()
    ankiModelsData.value = data

    const modelNames = Object.keys(data.models || {})
    ankiModel.value = modelNames[0] || ''
    syncAnkiFields()

    ankiDialogOpen.value = true
    addLog('Anki configuration ready', 'success')
  } catch (e) {
    addLog(`Anki error: ${e.message}`, 'error')
  }
}

function syncAnkiFields() {
  const fields = ankiModelsData.value?.models?.[ankiModel.value] || []
  ankiFrontField.value = fields[0] || ''
  ankiBackField.value = fields[1] || fields[0] || ''
}

async function exportToAnki() {
  try {
    const res = await fetch('/api/upload-to-anki', {
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
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.error || 'Falha ao exportar pro Anki')
    }
    const out = await res.json()
    addLog(`Anki export: ${out.totalSuccess}/${out.totalCards}`, 'success')
    ankiDialogOpen.value = false
  } catch (e) {
    addLog(`Anki export error: ${e.message}`, 'error')
  }
}

// -------------------- api keys dialog --------------------
function saveApiKeys() {
  anthropicApiKeyError.value = ''
  const akey = anthropicApiKey.value.trim()
  const mkey = mochiApiKey.value.trim()

  if (akey && !validateAnthropicApiKey(akey)) {
    anthropicApiKeyError.value = 'Claude API Key inválida (esperado: começa com sk-ant-)'
    return
  }

  storeApiKeys(akey, mkey, storeLocally.value)
  apiDialogOpen.value = false
  fetchDecks()
  addLog('API keys saved', 'success')
}

function clearCards() {
  cards.value = []
  addLog('All cards cleared', 'info')
}

// init
fetchDecks()
</script>

<template>
  <div class="app p-3">
    <!-- Header -->
    <div class="flex align-items-center justify-content-between gap-3 mb-3 flex-wrap">
      <div class="flex flex-column">
        <div class="text-2xl font-bold">Flash Card Generator</div>
        <div class="text-sm text-color-secondary">
          by <a href="https://github.com/Erick-Bryan-Cubas" target="_blank">Erick Bryan</a> •
          <a href="https://github.com/Erick-Bryan-Cubas/spaced-rep" target="_blank">GitHub</a>
        </div>
      </div>

      <div class="flex align-items-center gap-2 flex-wrap">
        <AnkiStatus />

        <Select
          v-model="cardType"
          :options="cardTypeOptions"
          optionLabel="label"
          optionValue="value"
          class="w-20rem"
        />

        <Button
          label="Create Cards"
          icon="pi pi-bolt"
          :disabled="!hasSelection || isGenerating || isAnalyzing"
          @click="generateCards()"
        />

        <Tag v-if="timerVisible" severity="info">
          <span class="mr-2">⏱️</span>{{ timerText }} <b class="ml-2">{{ timerSeconds }}s</b>
        </Tag>

        <Button label="Logs" icon="pi pi-list" severity="secondary" @click="logsOpen = true" />

        <Button icon="pi pi-ellipsis-v" severity="secondary" @click="menuRef.toggle($event)" />
        <Menu ref="menuRef" popup :model="menuItems" />
      </div>
    </div>

    <!-- Main -->
    <div style="height: calc(100vh - 140px); min-height: 520px;">
      <Splitter v-if="hasCards" layout="vertical" style="height: 100%;">
        <SplitterPanel :size="50" :minSize="20">
          <div class="h-full surface-card border-1 border-round border-200 p-2">
            <TextEditor
              class="h-full"
              @selection-change="selectedText = $event"
              @plain-text-change="onPlainTextChange"
              @reanalyze-request="analyzeDocument"
              @generate-request="generateCards($event.type, $event.text)"
            />
          </div>
        </SplitterPanel>

        <SplitterPanel :size="50" :minSize="20">
          <div class="h-full surface-card border-1 border-round border-200 p-2 overflow-auto">
            <div class="text-lg font-semibold mb-2">Cards ({{ cards.length }})</div>

            <div class="flex flex-column gap-2">
              <div v-for="(c, idx) in cards" :key="idx" class="surface-0 border-1 border-round border-200 p-2">
                <div class="flex align-items-center justify-content-between mb-2">
                  <Tag severity="secondary">{{ c.deck || 'General' }}</Tag>
                  <Button icon="pi pi-times" text severity="danger" @click="cards.splice(idx, 1)" />
                </div>

                <div class="grid">
                  <div class="col-12 md:col-6">
                    <div class="text-sm text-color-secondary mb-1">Front</div>
                    <Textarea v-model="c.front" autoResize rows="3" class="w-full" />
                  </div>
                  <div class="col-12 md:col-6">
                    <div class="text-sm text-color-secondary mb-1">Back</div>
                    <Textarea v-model="c.back" autoResize rows="3" class="w-full" />
                  </div>
                </div>
              </div>
            </div>

          </div>
        </SplitterPanel>
      </Splitter>

      <div v-else class="h-full surface-card border-1 border-round border-200 p-2">
        <TextEditor
          class="h-full"
          @selection-change="selectedText = $event"
          @plain-text-change="onPlainTextChange"
          @reanalyze-request="analyzeDocument"
          @generate-request="generateCards($event.type, $event.text)"
        />
      </div>
    </div>

    <!-- Logs Drawer -->
    <Drawer v-model:visible="logsOpen" header="🔍 Logs" position="right" style="width: 34rem;">
      <div class="flex justify-content-end mb-2">
        <Button label="Clear" icon="pi pi-trash" severity="secondary" @click="logs = []" />
      </div>

      <div class="flex flex-column gap-2">
        <div v-for="(l, i) in logs" :key="i" class="border-1 border-round border-200 p-2">
          <div class="text-xs text-color-secondary">[{{ l.ts }}]</div>
          <div class="text-sm">{{ l.msg }}</div>
        </div>
      </div>
    </Drawer>

    <!-- API Keys Dialog -->
    <Dialog v-model:visible="apiDialogOpen" modal header="API Key Setup" style="width: 40rem;">
      <div class="mb-3 p-2 border-round surface-100">
        ⚠️ I vibe coded this whole thing. I know nothing about security. Não use chaves com saldo alto.
      </div>

      <div class="flex flex-column gap-3">
        <div>
          <label class="font-semibold">Claude API Key</label>
          <InputText v-model="anthropicApiKey" class="w-full" placeholder="sk-ant-api03-..." />
          <small class="text-red-400">{{ anthropicApiKeyError }}</small>
        </div>

        <div>
          <label class="font-semibold">Mochi API Key (opcional)</label>
          <InputText v-model="mochiApiKey" class="w-full" placeholder="..." />
        </div>

        <div class="flex align-items-center gap-2">
          <Checkbox v-model="storeLocally" binary />
          <label>Remember API keys on this device</label>
        </div>

        <div class="flex justify-content-end gap-2">
          <Button label="Cancel" severity="secondary" @click="apiDialogOpen = false" />
          <Button label="Save" icon="pi pi-check" @click="saveApiKeys" />
        </div>
      </div>
    </Dialog>

    <!-- Anki Config Dialog -->
    <Dialog v-model:visible="ankiDialogOpen" modal header="Anki Export Configuration" style="width: 44rem;">
      <div v-if="ankiModelsData" class="flex flex-column gap-3">
        <div>
          <label class="font-semibold">Note Type (Model)</label>
          <Select
            v-model="ankiModel"
            :options="Object.keys(ankiModelsData.models || {})"
            class="w-full"
            @update:modelValue="syncAnkiFields"
          />
        </div>

        <div class="grid">
          <div class="col-12 md:col-6">
            <label class="font-semibold">Front Field</label>
            <Select v-model="ankiFrontField" :options="ankiModelsData.models?.[ankiModel] || []" class="w-full" />
          </div>
          <div class="col-12 md:col-6">
            <label class="font-semibold">Back Field</label>
            <Select v-model="ankiBackField" :options="ankiModelsData.models?.[ankiModel] || []" class="w-full" />
          </div>
        </div>

        <div>
          <label class="font-semibold">Deck (optional)</label>
          <Select v-model="ankiDeckField" :options="['', ...(ankiModelsData.decks || [])]" class="w-full" />
        </div>

        <div>
          <label class="font-semibold">Tags (comma-separated)</label>
          <InputText v-model="ankiTags" class="w-full" placeholder="tag1, tag2" />
        </div>

        <div class="flex justify-content-end gap-2">
          <Button label="Cancel" severity="secondary" @click="ankiDialogOpen = false" />
          <Button label="Export" icon="pi pi-upload" @click="exportToAnki" />
        </div>
      </div>
    </Dialog>
  </div>
</template>

<style scoped>
.app a {
  color: var(--p-primary-color);
  text-decoration: none;
}
.app a:hover {
  text-decoration: underline;
}
</style>
