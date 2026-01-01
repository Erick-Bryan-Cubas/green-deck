<!-- frontend/src/components/PdfUpload.vue -->
<script setup>
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'
import Checkbox from 'primevue/checkbox'
import Skeleton from 'primevue/skeleton'
import { useToast } from 'primevue/usetoast'
import { VuePDF, usePDF } from '@tato30/vue-pdf'
import { 
  getDocumentExtractionStatus, 
  getPdfPagesPreview,
  extractSelectedPages 
} from '@/services/api.js'

const emit = defineEmits(['extracted', 'error'])
const toast = useToast()

// ============================================================
// State
// ============================================================
const isDialogVisible = ref(false)
const currentStep = ref('upload') // 'upload' | 'pages' | 'result'
const isLoading = ref(false)
const loadingMessage = ref('')
const selectedFile = ref(null)
const pagesPreview = ref(null)
const selectedPages = ref([])
const extractedResult = ref(null)
const extractionError = ref(null)
const isServiceAvailable = ref(null)
const dragOver = ref(false)

// File input ref
const fileInputRef = ref(null)

// PDF visual rendering
const pdfSource = ref(null)
const pdfData = ref(null)
const totalPdfPages = ref(0)
const loadedThumbnails = ref(new Set())
const thumbnailScale = ref(0.5)

// Lazy loading with Intersection Observer
const visiblePages = ref(new Set())
const pagesGridRef = ref(null)
let intersectionObserver = null

// ============================================================
// Computed
// ============================================================
const hasFile = computed(() => !!selectedFile.value)
const hasPages = computed(() => totalPdfPages.value > 0)
const hasResult = computed(() => !!extractedResult.value?.text)

// Array de números de páginas para iterar
const pageNumbers = computed(() => {
  if (!totalPdfPages.value) return []
  return Array.from({ length: totalPdfPages.value }, (_, i) => i + 1)
})
const allPagesSelected = computed(() => {
  if (!totalPdfPages.value) return false
  return selectedPages.value.length === totalPdfPages.value
})

const fileInfo = computed(() => {
  if (!selectedFile.value) return null
  const size = selectedFile.value.size
  const sizeKB = Math.round(size / 1024)
  const sizeMB = (size / (1024 * 1024)).toFixed(2)
  return {
    name: selectedFile.value.name,
    size: size > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`,
    type: selectedFile.value.type || 'application/pdf'
  }
})

const selectedPagesCount = computed(() => selectedPages.value.length)

// ============================================================
// Methods
// ============================================================
async function checkServiceStatus() {
  try {
    const status = await getDocumentExtractionStatus()
    isServiceAvailable.value = status.available
    if (!status.available) {
      toast.add({
        severity: 'warn',
        summary: 'Serviço indisponível',
        detail: 'Instale docling para extrair PDFs: pip install docling',
        life: 5000
      })
    }
  } catch (error) {
    isServiceAvailable.value = false
    console.error('Error checking extraction status:', error)
  }
}

function openDialog() {
  isDialogVisible.value = true
  currentStep.value = 'upload'
  extractionError.value = null
  extractedResult.value = null
  selectedFile.value = null
  pagesPreview.value = null
  selectedPages.value = []
  pdfSource.value = null
  pdfData.value = null
  totalPdfPages.value = 0
  loadedThumbnails.value = new Set()
  visiblePages.value = new Set()
  cleanupIntersectionObserver()
  checkServiceStatus()
}

function closeDialog() {
  isDialogVisible.value = false
  selectedFile.value = null
  pagesPreview.value = null
  selectedPages.value = []
  extractedResult.value = null
  extractionError.value = null
  currentStep.value = 'upload'
  pdfSource.value = null
  pdfData.value = null
  totalPdfPages.value = 0
  loadedThumbnails.value = new Set()
  visiblePages.value = new Set()
  cleanupIntersectionObserver()
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

function onFileSelected(event) {
  const file = event.target.files?.[0]
  if (file) {
    handleFile(file)
  }
  event.target.value = ''
}

function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    toast.add({
      severity: 'error',
      summary: 'Formato inválido',
      detail: 'Apenas arquivos PDF são suportados.',
      life: 3000
    })
    return
  }

  const maxSizeMB = 50
  if (file.size > maxSizeMB * 1024 * 1024) {
    toast.add({
      severity: 'error',
      summary: 'Arquivo muito grande',
      detail: `O arquivo deve ter no máximo ${maxSizeMB}MB.`,
      life: 3000
    })
    return
  }

  selectedFile.value = file
  extractedResult.value = null
  extractionError.value = null
  pagesPreview.value = null
  selectedPages.value = []
}

function onDragOver(event) {
  event.preventDefault()
  dragOver.value = true
}

function onDragLeave(event) {
  event.preventDefault()
  dragOver.value = false
}

function onDrop(event) {
  event.preventDefault()
  dragOver.value = false
  
  const file = event.dataTransfer?.files?.[0]
  if (file) {
    handleFile(file)
  }
}

async function loadPagesPreview() {
  if (!selectedFile.value) return

  isLoading.value = true
  loadingMessage.value = 'Carregando preview do PDF...'
  extractionError.value = null

  try {
    // Converter File para ArrayBuffer para o vue-pdf
    const arrayBuffer = await selectedFile.value.arrayBuffer()
    
    // Criar URL do blob para o PDF
    const blob = new Blob([arrayBuffer], { type: 'application/pdf' })
    const blobUrl = URL.createObjectURL(blob)
    pdfSource.value = blobUrl
    
    // Usar usePDF para obter informações do PDF
    const { pdf, pages } = usePDF(blobUrl)
    
    // Aguardar o PDF carregar
    await new Promise((resolve, reject) => {
      const checkLoaded = setInterval(() => {
        if (pages.value && pdf.value) {
          clearInterval(checkLoaded)
          pdfData.value = pdf.value
          totalPdfPages.value = pages.value
          // Seleciona todas as páginas por padrão
          selectedPages.value = Array.from({ length: pages.value }, (_, i) => i + 1)
          resolve()
        }
      }, 100)
      
      // Timeout após 30 segundos
      setTimeout(() => {
        clearInterval(checkLoaded)
        if (!pages.value) {
          reject(new Error('Timeout ao carregar PDF'))
        }
      }, 30000)
    })

    currentStep.value = 'pages'
    
    // Inicializar lazy loading após o DOM atualizar
    await nextTick()
    setupIntersectionObserver()

    toast.add({
      severity: 'info',
      summary: 'PDF carregado',
      detail: `${totalPdfPages.value} páginas encontradas`,
      life: 3000
    })
  } catch (error) {
    console.error('Preview error:', error)
    extractionError.value = error.message
    toast.add({
      severity: 'error',
      summary: 'Erro ao carregar PDF',
      detail: error.message,
      life: 5000
    })
    emit('error', error)
  } finally {
    isLoading.value = false
    loadingMessage.value = ''
  }
}

// ============================================================
// Lazy Loading com Intersection Observer
// ============================================================
function setupIntersectionObserver() {
  // Limpar observer anterior se existir
  cleanupIntersectionObserver()
  
  // Carregar as primeiras páginas imediatamente (viewport inicial)
  const initialVisibleCount = Math.min(8, totalPdfPages.value)
  for (let i = 1; i <= initialVisibleCount; i++) {
    visiblePages.value.add(i)
  }
  
  // Criar observer para lazy loading das demais
  intersectionObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const pageNum = parseInt(entry.target.dataset.page, 10)
        if (entry.isIntersecting && !visiblePages.value.has(pageNum)) {
          visiblePages.value.add(pageNum)
        }
      })
    },
    {
      root: pagesGridRef.value,
      rootMargin: '100px', // Pre-load 100px antes de entrar na viewport
      threshold: 0.1
    }
  )
  
  // Observar todos os placeholders de página
  nextTick(() => {
    const pageCards = document.querySelectorAll('.page-card[data-page]')
    pageCards.forEach((card) => {
      intersectionObserver.observe(card)
    })
  })
}

function cleanupIntersectionObserver() {
  if (intersectionObserver) {
    intersectionObserver.disconnect()
    intersectionObserver = null
  }
}

// Limpar observer ao desmontar componente
onBeforeUnmount(() => {
  cleanupIntersectionObserver()
})

// Handler para quando thumbnail carrega
function onThumbnailLoaded(pageNum) {
  loadedThumbnails.value.add(pageNum)
}

// Handler para erro no thumbnail
function onThumbnailError(pageNum, error) {
  console.error(`Erro ao carregar thumbnail da página ${pageNum}:`, error)
}

function togglePageSelection(pageNumber) {
  const idx = selectedPages.value.indexOf(pageNumber)
  if (idx === -1) {
    selectedPages.value.push(pageNumber)
  } else {
    selectedPages.value.splice(idx, 1)
  }
}

function toggleAllPages() {
  if (allPagesSelected.value) {
    selectedPages.value = []
  } else {
    selectedPages.value = Array.from({ length: totalPdfPages.value }, (_, i) => i + 1)
  }
}

async function extractSelectedText() {
  if (!selectedFile.value || selectedPages.value.length === 0) return

  isLoading.value = true
  loadingMessage.value = 'Extraindo texto das páginas selecionadas...'
  extractionError.value = null

  try {
    const result = await extractSelectedPages(
      selectedFile.value,
      selectedPages.value,
      'cleaned'
    )

    extractedResult.value = result
    currentStep.value = 'result'

    toast.add({
      severity: 'success',
      summary: 'Extração concluída',
      detail: `${result.word_count} palavras extraídas de ${result.pages} páginas`,
      life: 3000
    })
  } catch (error) {
    console.error('Extraction error:', error)
    extractionError.value = error.message
    toast.add({
      severity: 'error',
      summary: 'Erro na extração',
      detail: error.message,
      life: 5000
    })
    emit('error', error)
  } finally {
    isLoading.value = false
    loadingMessage.value = ''
  }
}

function useExtractedText() {
  if (!extractedResult.value?.text) return
  
  emit('extracted', {
    text: extractedResult.value.text,
    filename: extractedResult.value.filename,
    pages: extractedResult.value.pages,
    wordCount: extractedResult.value.word_count,
    pagesContent: extractedResult.value.pages_content || [],
    metadata: extractedResult.value.metadata || {}
  })
  
  closeDialog()
  
  toast.add({
    severity: 'info',
    summary: 'Texto carregado',
    detail: 'O texto do PDF foi inserido no editor.',
    life: 3000
  })
}

function goBackToPages() {
  currentStep.value = 'pages'
  extractedResult.value = null
}

function goBackToUpload() {
  currentStep.value = 'upload'
  pagesPreview.value = null
  selectedPages.value = []
  pdfSource.value = null
  pdfData.value = null
  totalPdfPages.value = 0
  loadedThumbnails.value = new Set()
  visiblePages.value = new Set()
  cleanupIntersectionObserver()
}

function clearFile() {
  selectedFile.value = null
  extractedResult.value = null
  extractionError.value = null
  pagesPreview.value = null
  selectedPages.value = []
  pdfSource.value = null
  pdfData.value = null
  totalPdfPages.value = 0
  loadedThumbnails.value = new Set()
  visiblePages.value = new Set()
  cleanupIntersectionObserver()
}

// Expose methods for parent component
defineExpose({
  openDialog,
  closeDialog
})
</script>

<template>
  <!-- Trigger Button -->
  <Button
    icon="pi pi-file-pdf"
    label="PDF"
    severity="secondary"
    outlined
    @click="openDialog"
    title="Importar texto de PDF"
    class="pdf-upload-btn"
  />

  <!-- Upload Dialog -->
  <Dialog
    v-model:visible="isDialogVisible"
    :header="currentStep === 'upload' ? 'Importar PDF' : currentStep === 'pages' ? 'Selecionar Páginas' : 'Resultado'"
    :modal="true"
    :closable="!isLoading"
    :style="{ width: currentStep === 'pages' ? '90vw' : '550px', maxWidth: currentStep === 'pages' ? '1200px' : '550px' }"
    class="pdf-upload-dialog"
  >
    <!-- Service Status Warning -->
    <div v-if="isServiceAvailable === false" class="service-warning">
      <i class="pi pi-exclamation-triangle" />
      <div>
        <strong>Serviço de extração não disponível</strong>
        <p>Execute no terminal: <code>pip install docling</code></p>
      </div>
    </div>

    <!-- Hidden File Input -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".pdf,application/pdf"
      style="display: none"
      @change="onFileSelected"
    />

    <!-- ============================================== -->
    <!-- STEP 1: Upload -->
    <!-- ============================================== -->
    <template v-if="currentStep === 'upload'">
      <!-- Drop Zone -->
      <div
        v-if="!hasFile"
        class="drop-zone"
        :class="{ 'drag-over': dragOver, 'disabled': isServiceAvailable === false }"
        @click="triggerFileInput"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
      >
        <i class="pi pi-file-pdf drop-icon" />
        <div class="drop-text">
          <strong>Arraste um PDF aqui</strong>
          <span>ou clique para selecionar</span>
        </div>
        <Tag severity="secondary" class="drop-hint">
          Máx. 50MB • Apenas PDF
        </Tag>
      </div>

      <!-- Selected File Info -->
      <div v-else class="file-info">
        <div class="file-card">
          <i class="pi pi-file-pdf file-icon" />
          <div class="file-details">
            <div class="file-name">{{ fileInfo?.name }}</div>
            <div class="file-size">{{ fileInfo?.size }}</div>
          </div>
          <Button
            icon="pi pi-times"
            severity="secondary"
            text
            rounded
            size="small"
            @click="clearFile"
            title="Remover arquivo"
            :disabled="isLoading"
          />
        </div>

        <!-- Progress -->
        <div v-if="isLoading" class="upload-progress">
          <ProgressBar mode="indeterminate" style="height: 6px" />
          <span class="progress-label">{{ loadingMessage }}</span>
        </div>

        <!-- Error Message -->
        <div v-if="extractionError" class="extraction-error">
          <i class="pi pi-exclamation-circle" />
          <span>{{ extractionError }}</span>
        </div>
      </div>
    </template>

    <!-- ============================================== -->
    <!-- STEP 2: Select Pages (Visual Thumbnails) -->
    <!-- ============================================== -->
    <template v-if="currentStep === 'pages' && hasPages">
      <div class="pages-selection">
        <!-- Header with Select All -->
        <div class="pages-header">
          <div class="pages-info">
            <Tag severity="info">
              <i class="pi pi-file mr-1" /> {{ totalPdfPages }} páginas
            </Tag>
            <Tag :severity="selectedPagesCount > 0 ? 'success' : 'secondary'">
              <i class="pi pi-check-square mr-1" /> {{ selectedPagesCount }} selecionadas
            </Tag>
          </div>
          <Button
            :label="allPagesSelected ? 'Desmarcar todas' : 'Selecionar todas'"
            :icon="allPagesSelected ? 'pi pi-times' : 'pi pi-check-square'"
            severity="secondary"
            text
            size="small"
            @click="toggleAllPages"
          />
        </div>

        <!-- Pages Grid with Visual Thumbnails -->
        <div ref="pagesGridRef" class="pages-grid">
          <div
            v-for="pageNum in pageNumbers"
            :key="pageNum"
            :data-page="pageNum"
            class="page-card"
            :class="{ 'selected': selectedPages.includes(pageNum) }"
            @click="togglePageSelection(pageNum)"
          >
            <!-- Checkbox overlay -->
            <div class="page-checkbox-overlay">
              <Checkbox
                :modelValue="selectedPages.includes(pageNum)"
                :binary="true"
                @click.stop
                @update:modelValue="togglePageSelection(pageNum)"
              />
            </div>
            
            <!-- Visual PDF Thumbnail (Lazy Loaded) -->
            <div class="thumbnail-container">
              <!-- Skeleton placeholder enquanto não carregou -->
              <Skeleton 
                v-if="!loadedThumbnails.has(pageNum)" 
                width="100%" 
                height="180px" 
                class="thumbnail-skeleton"
              />
              <!-- Renderizar VuePDF apenas quando visível (lazy loading) -->
              <VuePDF
                v-if="pdfData && visiblePages.has(pageNum)"
                :pdf="pdfData"
                :page="pageNum"
                :scale="thumbnailScale"
                class="pdf-thumbnail"
                @loaded="onThumbnailLoaded(pageNum)"
                @error="(e) => onThumbnailError(pageNum, e)"
              />
            </div>
            
            <!-- Page number badge -->
            <div class="page-number-badge">
              {{ pageNum }}
            </div>
          </div>
        </div>

        <!-- Loading -->
        <div v-if="isLoading" class="upload-progress">
          <ProgressBar mode="indeterminate" style="height: 6px" />
          <span class="progress-label">{{ loadingMessage }}</span>
        </div>

        <!-- Error -->
        <div v-if="extractionError" class="extraction-error">
          <i class="pi pi-exclamation-circle" />
          <span>{{ extractionError }}</span>
        </div>
      </div>
    </template>

    <!-- ============================================== -->
    <!-- STEP 3: Result -->
    <!-- ============================================== -->
    <template v-if="currentStep === 'result' && hasResult">
      <div class="extraction-result">
        <div class="result-header">
          <Tag severity="success">
            <i class="pi pi-check mr-1" /> Extração concluída
          </Tag>
          <div class="result-stats">
            <Tag severity="secondary">
              <i class="pi pi-file mr-1" /> {{ extractedResult.pages }} páginas
            </Tag>
            <Tag severity="secondary">
              <i class="pi pi-align-left mr-1" /> {{ extractedResult.word_count }} palavras
            </Tag>
          </div>
        </div>

        <div class="result-preview">
          <div class="preview-label">Preview do texto:</div>
          <div class="preview-text">{{ extractedResult.text.substring(0, 1000) }}{{ extractedResult.text.length > 1000 ? '...' : '' }}</div>
        </div>
      </div>
    </template>

    <!-- Dialog Footer -->
    <template #footer>
      <div class="dialog-footer">
        <!-- Step 1: Upload -->
        <template v-if="currentStep === 'upload'">
          <Button
            label="Cancelar"
            severity="secondary"
            text
            @click="closeDialog"
            :disabled="isLoading"
          />
          <Button
            v-if="hasFile"
            label="Analisar Páginas"
            icon="pi pi-search"
            @click="loadPagesPreview"
            :loading="isLoading"
            :disabled="isServiceAvailable === false"
          />
        </template>

        <!-- Step 2: Pages -->
        <template v-if="currentStep === 'pages'">
          <Button
            label="Voltar"
            severity="secondary"
            text
            icon="pi pi-arrow-left"
            @click="goBackToUpload"
            :disabled="isLoading"
          />
          <Button
            label="Extrair Texto"
            icon="pi pi-download"
            @click="extractSelectedText"
            :loading="isLoading"
            :disabled="selectedPagesCount === 0"
          />
        </template>

        <!-- Step 3: Result -->
        <template v-if="currentStep === 'result'">
          <Button
            label="Voltar"
            severity="secondary"
            text
            icon="pi pi-arrow-left"
            @click="goBackToPages"
          />
          <Button
            label="Usar no Editor"
            icon="pi pi-check"
            @click="useExtractedText"
          />
        </template>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.pdf-upload-btn {
  gap: 0.5rem;
}

.pdf-upload-dialog :deep(.p-dialog-content) {
  padding: 1.5rem;
}

.service-warning {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--yellow-50);
  border: 1px solid var(--yellow-200);
  border-radius: 8px;
  margin-bottom: 1rem;
  color: var(--yellow-900);
}

.service-warning i {
  font-size: 1.25rem;
  color: var(--yellow-600);
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.service-warning p {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
}

.service-warning code {
  background: var(--yellow-100);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-family: monospace;
}

/* Drop Zone */
.drop-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 3rem 2rem;
  border: 2px dashed var(--surface-300);
  border-radius: 12px;
  background: var(--surface-50);
  cursor: pointer;
  transition: all 0.2s ease;
}

.drop-zone:hover:not(.disabled) {
  border-color: var(--primary-400);
  background: var(--primary-50);
}

.drop-zone.drag-over {
  border-color: var(--primary-500);
  background: var(--primary-100);
  transform: scale(1.02);
}

.drop-zone.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.drop-icon {
  font-size: 3rem;
  color: var(--red-400);
}

.drop-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  text-align: center;
}

.drop-text strong {
  font-size: 1rem;
  color: var(--text-color);
}

.drop-text span {
  font-size: 0.875rem;
  color: var(--text-color-secondary);
}

.drop-hint {
  font-size: 0.75rem;
}

/* File Info */
.file-info {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: var(--surface-50);
  border: 1px solid var(--surface-200);
  border-radius: 8px;
}

.file-icon {
  font-size: 2rem;
  color: var(--red-500);
}

.file-details {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-weight: 600;
  color: var(--text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-size {
  font-size: 0.875rem;
  color: var(--text-color-secondary);
}

/* Progress */
.upload-progress {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.upload-progress :deep(.p-progressbar) {
  height: 6px;
  border-radius: 3px;
}

.progress-label {
  font-size: 0.875rem;
  color: var(--text-color-secondary);
  text-align: center;
}

.extraction-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--red-50);
  border: 1px solid var(--red-200);
  border-radius: 6px;
  color: var(--red-700);
  font-size: 0.875rem;
}

.extraction-error i {
  color: var(--red-500);
}

/* Pages Selection */
.pages-selection {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.pages-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.pages-info {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

/* Pages Grid - Visual Thumbnails */
.pages-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 1rem;
  max-height: 60vh;
  overflow-y: auto;
  padding: 0.5rem;
}

.page-card {
  position: relative;
  display: flex;
  flex-direction: column;
  border: 3px solid var(--surface-200);
  border-radius: 8px;
  background: var(--surface-0);
  cursor: pointer;
  transition: all 0.2s ease;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.page-card:hover {
  border-color: var(--primary-300);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

.page-card.selected {
  border-color: var(--primary-500);
  box-shadow: 0 0 0 3px var(--primary-100), 0 4px 12px rgba(0, 0, 0, 0.1);
}

.page-card.selected .page-checkbox-overlay {
  opacity: 1;
}

/* Checkbox overlay */
.page-checkbox-overlay {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  z-index: 10;
  opacity: 0;
  transition: opacity 0.2s ease;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  padding: 2px;
}

.page-card:hover .page-checkbox-overlay {
  opacity: 1;
}

/* Thumbnail container */
.thumbnail-container {
  position: relative;
  width: 100%;
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-100);
  overflow: hidden;
}

.thumbnail-skeleton {
  position: absolute;
  top: 0;
  left: 0;
}

.pdf-thumbnail {
  width: 100%;
  height: auto;
  display: block;
}

.pdf-thumbnail :deep(canvas) {
  width: 100% !important;
  height: auto !important;
  display: block;
}

/* Page number badge */
.page-number-badge {
  position: absolute;
  bottom: 0.5rem;
  right: 0.5rem;
  background: rgba(0, 0, 0, 0.75);
  color: white;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  z-index: 5;
}

/* Result */
.extraction-result {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.result-stats {
  display: flex;
  gap: 0.5rem;
}

.result-preview {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.preview-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-color-secondary);
}

.preview-text {
  padding: 1rem;
  background: var(--surface-50);
  border: 1px solid var(--surface-200);
  border-radius: 8px;
  font-size: 0.875rem;
  line-height: 1.6;
  max-height: 250px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}
</style>
