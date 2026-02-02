<!-- frontend/src/components/DocumentUpload.vue -->
<script setup>
import { ref, computed, onBeforeUnmount, nextTick } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'
import Checkbox from 'primevue/checkbox'
import Skeleton from 'primevue/skeleton'
import SelectButton from 'primevue/selectbutton'
import { useToast } from 'primevue/usetoast'
import {
  getDocumentExtractionStatus,
  getDocumentPagesPreview,
  getPdfMetadata,
  getPdfThumbnails,
  extractDocumentTextStream,
  extractPagesWithWebSocket
} from '@/services/api.js'

const emit = defineEmits(['extracted', 'error'])
const toast = useToast()

// ============================================================
// Supported Formats
// ============================================================
const SUPPORTED_FORMATS = {
  // Documents
  '.pdf': { name: 'PDF', icon: 'pi-file-pdf', color: 'var(--red-500)' },
  '.docx': { name: 'Word', icon: 'pi-file-word', color: 'var(--blue-500)' },
  '.doc': { name: 'Word', icon: 'pi-file-word', color: 'var(--blue-500)' },
  '.pptx': { name: 'PowerPoint', icon: 'pi-file', color: 'var(--orange-500)' },
  '.ppt': { name: 'PowerPoint', icon: 'pi-file', color: 'var(--orange-500)' },
  '.xlsx': { name: 'Excel', icon: 'pi-file-excel', color: 'var(--green-500)' },
  '.xls': { name: 'Excel', icon: 'pi-file-excel', color: 'var(--green-500)' },
  // Markup
  '.html': { name: 'HTML', icon: 'pi-code', color: 'var(--cyan-500)' },
  '.htm': { name: 'HTML', icon: 'pi-code', color: 'var(--cyan-500)' },
  '.md': { name: 'Markdown', icon: 'pi-file-edit', color: 'var(--gray-600)' },
  '.markdown': { name: 'Markdown', icon: 'pi-file-edit', color: 'var(--gray-600)' },
  '.adoc': { name: 'AsciiDoc', icon: 'pi-file-edit', color: 'var(--purple-500)' },
  '.asciidoc': { name: 'AsciiDoc', icon: 'pi-file-edit', color: 'var(--purple-500)' },
  // Images (OCR)
  '.png': { name: 'PNG', icon: 'pi-image', color: 'var(--pink-500)' },
  '.jpg': { name: 'JPEG', icon: 'pi-image', color: 'var(--pink-500)' },
  '.jpeg': { name: 'JPEG', icon: 'pi-image', color: 'var(--pink-500)' },
  '.tiff': { name: 'TIFF', icon: 'pi-image', color: 'var(--pink-500)' },
  '.tif': { name: 'TIFF', icon: 'pi-image', color: 'var(--pink-500)' },
  '.bmp': { name: 'BMP', icon: 'pi-image', color: 'var(--pink-500)' },
}

const PAGINATED_FORMATS = ['.pdf', '.pptx', '.ppt']
const IMAGE_FORMATS = ['.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp']

// Build accept string for file input
const acceptedFormats = computed(() => Object.keys(SUPPORTED_FORMATS).join(','))

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
const supportedFormatsFromServer = ref({})
const dragOver = ref(false)
const extractionProgress = ref(0)
const extractionProgressMessage = ref('')
const isExtractingWithProgress = ref(false)
const extractionAbortController = ref(null)
const processedPages = ref(new Set())

// File input ref
const fileInputRef = ref(null)

// PDF visual rendering (only for PDF files)
const totalPdfPages = ref(0)
const thumbnailsCache = ref({}) // { pageNum: base64DataUrl }
const loadingThumbnails = ref(new Set()) // Pages currently being loaded

// Document preview (for non-PDF files)
const documentPreview = ref(null)

// PDF Extractor selection
const selectedExtractor = ref('docling')
const extractorOptions = ref([
  { label: 'Docling', value: 'docling', icon: 'pi pi-file-edit', description: 'Melhor estrutura' },
  { label: 'pdfplumber', value: 'pdfplumber', icon: 'pi pi-bolt', description: 'Mais rapido' }
])

// Lazy loading with Intersection Observer
const visiblePages = ref(new Set())
const pagesGridRef = ref(null)
let intersectionObserver = null

// ============================================================
// Computed
// ============================================================
const hasFile = computed(() => !!selectedFile.value)
const hasPages = computed(() => totalPdfPages.value > 0 || (documentPreview.value?.total_pages > 0))
const hasResult = computed(() => !!extractedResult.value?.text)

const isPdfFile = computed(() => {
  if (!selectedFile.value) return false
  return selectedFile.value.name.toLowerCase().endsWith('.pdf')
})

const isImageFile = computed(() => {
  if (!selectedFile.value) return false
  const ext = getFileExtension(selectedFile.value.name)
  return IMAGE_FORMATS.includes(ext)
})

const isPaginatedFormat = computed(() => {
  if (!selectedFile.value) return false
  const ext = getFileExtension(selectedFile.value.name)
  return PAGINATED_FORMATS.includes(ext)
})

const pageNumbers = computed(() => {
  const total = isPdfFile.value ? totalPdfPages.value : (documentPreview.value?.total_pages || 0)
  if (!total) return []
  return Array.from({ length: total }, (_, i) => i + 1)
})

const allPagesSelected = computed(() => {
  const total = isPdfFile.value ? totalPdfPages.value : (documentPreview.value?.total_pages || 0)
  if (!total) return false
  return selectedPages.value.length === total
})

const fileInfo = computed(() => {
  if (!selectedFile.value) return null
  const size = selectedFile.value.size
  const sizeKB = Math.round(size / 1024)
  const sizeMB = (size / (1024 * 1024)).toFixed(2)
  const ext = getFileExtension(selectedFile.value.name)
  const formatInfo = SUPPORTED_FORMATS[ext] || { name: 'Document', icon: 'pi-file', color: 'var(--gray-500)' }

  return {
    name: selectedFile.value.name,
    size: size > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`,
    type: selectedFile.value.type || 'application/octet-stream',
    extension: ext,
    formatName: formatInfo.name,
    formatIcon: formatInfo.icon,
    formatColor: formatInfo.color,
  }
})

const selectedPagesCount = computed(() => selectedPages.value.length)

const dialogTitle = computed(() => {
  if (currentStep.value === 'upload') return 'Importar Documento'
  if (currentStep.value === 'pages') return isPdfFile.value ? 'Selecionar Paginas' : 'Confirmar Extracao'
  return 'Resultado'
})

const dialogWidth = computed(() => {
  if (currentStep.value === 'pages' && isPdfFile.value) {
    return isExtractingWithProgress.value ? '650px' : '90vw'
  }
  return '550px'
})

const dialogMaxWidth = computed(() => {
  if (currentStep.value === 'pages' && isPdfFile.value) {
    return isExtractingWithProgress.value ? '650px' : '1200px'
  }
  return '550px'
})

// ============================================================
// Helper Functions
// ============================================================
function getFileExtension(filename) {
  if (!filename || !filename.includes('.')) return ''
  return '.' + filename.split('.').pop().toLowerCase()
}

function isFormatSupported(filename) {
  const ext = getFileExtension(filename)
  return ext in SUPPORTED_FORMATS
}

// ============================================================
// Methods
// ============================================================
async function checkServiceStatus() {
  try {
    const status = await getDocumentExtractionStatus()
    isServiceAvailable.value = status.available
    if (status.format_descriptions) {
      supportedFormatsFromServer.value = status.format_descriptions
    }
    if (!status.available) {
      toast.add({
        severity: 'warn',
        summary: 'Servico indisponivel',
        detail: 'Instale docling para extrair documentos: pip install docling',
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
  totalPdfPages.value = 0
  documentPreview.value = null
  thumbnailsCache.value = {}
  loadingThumbnails.value = new Set()
  visiblePages.value = new Set()
  selectedExtractor.value = 'docling'
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
  totalPdfPages.value = 0
  documentPreview.value = null
  thumbnailsCache.value = {}
  loadingThumbnails.value = new Set()
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
  if (!isFormatSupported(file.name)) {
    const ext = getFileExtension(file.name)
    toast.add({
      severity: 'error',
      summary: 'Formato nao suportado',
      detail: `O formato ${ext || 'desconhecido'} nao e suportado. Use: PDF, Word, PowerPoint, Excel, HTML, Markdown, ou imagens.`,
      life: 5000
    })
    return
  }

  const maxSizeMB = 50
  if (file.size > maxSizeMB * 1024 * 1024) {
    toast.add({
      severity: 'error',
      summary: 'Arquivo muito grande',
      detail: `O arquivo deve ter no maximo ${maxSizeMB}MB.`,
      life: 3000
    })
    return
  }

  selectedFile.value = file
  extractedResult.value = null
  extractionError.value = null
  pagesPreview.value = null
  selectedPages.value = []
  documentPreview.value = null
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
  extractionError.value = null

  // Mensagem diferente para PDFs grandes
  const fileSizeMB = selectedFile.value.size / (1024 * 1024)
  if (isPdfFile.value && fileSizeMB > 5) {
    loadingMessage.value = `Carregando PDF grande (${fileSizeMB.toFixed(1)} MB). Isso pode levar alguns minutos...`
  } else {
    loadingMessage.value = 'Carregando preview do documento...'
  }

  try {
    if (isPdfFile.value) {
      await loadPdfPreview()
    } else {
      await loadDocumentPreview()
    }
  } catch (error) {
    console.error('Preview error:', error)
    extractionError.value = error.message
    toast.add({
      severity: 'error',
      summary: 'Erro ao carregar documento',
      detail: error.message,
      life: 5000
    })
    emit('error', error)
  } finally {
    isLoading.value = false
    loadingMessage.value = ''
  }
}

async function loadPdfPreview() {
  try {
    // 1. Obter metadados do backend (< 2 segundos para 13MB)
    const metadata = await getPdfMetadata(selectedFile.value)

    if (!metadata.success) {
      throw new Error(metadata.error || 'Falha ao analisar PDF')
    }

    // 2. Armazenar dados do PDF
    totalPdfPages.value = metadata.num_pages

    // 3. Selecionar todas as páginas por padrão
    selectedPages.value = Array.from({ length: metadata.num_pages }, (_, i) => i + 1)

    // 4. Transição para seleção de páginas
    currentStep.value = 'pages'

    // 5. Inicializar observer e carregar primeiros thumbnails
    await nextTick()
    setupIntersectionObserver()

    // 6. Carregar thumbnails das primeiras páginas visíveis
    loadThumbnailsBatch(1, Math.min(18, metadata.num_pages))

    toast.add({
      severity: 'info',
      summary: 'PDF carregado',
      detail: `${metadata.num_pages} páginas encontradas`,
      life: 3000
    })

  } catch (error) {
    console.error('Erro ao carregar PDF:', error)
    throw new Error(`Falha ao processar PDF: ${error.message}`)
  }
}

async function loadThumbnailsBatch(startPage, endPage) {
  // Evitar carregar páginas já carregadas ou em carregamento
  const pagesToLoad = []
  for (let i = startPage; i <= endPage; i++) {
    if (!thumbnailsCache.value[i] && !loadingThumbnails.value.has(i)) {
      pagesToLoad.push(i)
      loadingThumbnails.value.add(i)
    }
  }

  if (pagesToLoad.length === 0) return

  const pagesStr = `${Math.min(...pagesToLoad)}-${Math.max(...pagesToLoad)}`

  try {
    const result = await getPdfThumbnails(selectedFile.value, pagesStr, 150)

    if (result.success && result.thumbnails) {
      for (const thumb of result.thumbnails) {
        if (thumb.data) {
          thumbnailsCache.value[thumb.page] = thumb.data
        }
        loadingThumbnails.value.delete(thumb.page)
      }
    }
  } catch (error) {
    console.error('Erro ao carregar thumbnails:', error)
    // Remover páginas do loading em caso de erro
    for (const page of pagesToLoad) {
      loadingThumbnails.value.delete(page)
    }
  }
}

async function loadDocumentPreview() {
  // Para documentos nao-PDF, usa o endpoint de preview do backend
  const result = await getDocumentPagesPreview(selectedFile.value)

  documentPreview.value = result

  // Seleciona todas as paginas por padrao
  if (result.total_pages > 0) {
    selectedPages.value = Array.from({ length: result.total_pages }, (_, i) => i + 1)
  }

  currentStep.value = 'pages'

  const formatType = result.format_type || fileInfo.value?.formatName || 'Documento'
  toast.add({
    severity: 'info',
    summary: `${formatType} carregado`,
    detail: result.total_pages > 1
      ? `${result.total_pages} secoes encontradas`
      : 'Documento pronto para extracao',
    life: 3000
  })
}

// ============================================================
// Lazy Loading com Intersection Observer (PDF only)
// ============================================================
function setupIntersectionObserver() {
  if (!isPdfFile.value) return

  cleanupIntersectionObserver()

  // Criar observer para lazy loading de thumbnails
  intersectionObserver = new IntersectionObserver(
    (entries) => {
      const pagesToLoad = []

      entries.forEach((entry) => {
        const pageNum = parseInt(entry.target.dataset.page, 10)
        if (entry.isIntersecting) {
          visiblePages.value.add(pageNum)
          // Coletar páginas visíveis que não têm thumbnail
          if (!thumbnailsCache.value[pageNum] && !loadingThumbnails.value.has(pageNum)) {
            pagesToLoad.push(pageNum)
          }
        }
      })

      // Carregar thumbnails em batch para páginas visíveis
      if (pagesToLoad.length > 0) {
        const minPage = Math.min(...pagesToLoad)
        const maxPage = Math.max(...pagesToLoad)
        // Expandir range para carregar algumas páginas extras
        const batchStart = Math.max(1, minPage - 3)
        const batchEnd = Math.min(totalPdfPages.value, maxPage + 3)
        loadThumbnailsBatch(batchStart, batchEnd)
      }
    },
    {
      root: pagesGridRef.value,
      rootMargin: '200px',
      threshold: 0.1
    }
  )

  // Observar todos os placeholders de pagina
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

onBeforeUnmount(() => {
  cleanupIntersectionObserver()
})

function togglePageSelection(pageNumber) {
  const idx = selectedPages.value.indexOf(pageNumber)
  if (idx === -1) {
    selectedPages.value.push(pageNumber)
  } else {
    selectedPages.value.splice(idx, 1)
  }
}

function toggleAllPages() {
  const total = isPdfFile.value ? totalPdfPages.value : (documentPreview.value?.total_pages || 0)
  if (allPagesSelected.value) {
    selectedPages.value = []
  } else {
    selectedPages.value = Array.from({ length: total }, (_, i) => i + 1)
  }
}

async function extractSelectedText() {
  if (!selectedFile.value || selectedPages.value.length === 0) return

  isLoading.value = true
  isExtractingWithProgress.value = true
  extractionProgress.value = 0
  extractionProgressMessage.value = 'Iniciando extração...'
  extractionError.value = null
  processedPages.value = new Set()

  // Create abort controller for cancellation
  extractionAbortController.value = new AbortController()

  try {
    // Progress callback - uses nextTick to ensure Vue reactivity in WebSocket context
    const handleProgress = (percent, message) => {
      console.log(`[Vue] handleProgress called: ${percent}% - ${message}`)
      // Force reactive update immediately
      extractionProgress.value = percent
      extractionProgressMessage.value = message
      if (message) {
        const match = message.match(/p[aá]gina\s+(\d+)/i)
        if (match) {
          const pageNum = Number(match[1])
          if (!Number.isNaN(pageNum)) {
            const next = new Set(processedPages.value)
            next.add(pageNum)
            processedPages.value = next
          }
        }
      }
      // Force Vue to flush updates
      nextTick(() => {
        console.log(`[Vue] After nextTick: progress=${extractionProgress.value}, message=${extractionProgressMessage.value}`)
      })
    }

    const extractionOptions = {
      quality: 'cleaned',
      pdfExtractor: isPdfFile.value ? selectedExtractor.value : 'docling'
    }

    let result

    // For PDFs, use WebSocket-based extraction for real-time progress
    if (isPdfFile.value && selectedPages.value.length > 0) {
      // Extract only selected pages with WebSocket progress (fixes SSE buffering)
      result = await extractPagesWithWebSocket(
        selectedFile.value,
        selectedPages.value,
        extractionOptions,
        handleProgress,
        extractionAbortController.value?.signal // Pass abort signal for cancellation
      )
    } else {
      // For non-PDF files, use the full document extraction
      result = await extractDocumentTextStream(
        selectedFile.value,
        extractionOptions,
        handleProgress,
        extractionAbortController.value.signal
      )
    }

    extractedResult.value = result
    currentStep.value = 'result'

    const pagesInfo = isPdfFile.value ? ` de ${selectedPages.value.length} páginas` : ''
    toast.add({
      severity: 'success',
      summary: 'Extração concluída',
      detail: `${result.word_count} palavras extraídas${pagesInfo}`,
      life: 3000
    })
  } catch (error) {
    // Check if extraction was cancelled
    if (error.message === 'AbortError') {
      toast.add({
        severity: 'info',
        summary: 'Extração cancelada',
        detail: 'A extração foi cancelada pelo usuário.',
        life: 3000
      })
      return
    }

    console.error('Extraction error:', error)

    // Provide helpful error messages based on error type
    let errorDetail = error.message || 'Erro desconhecido'
    let summary = 'Erro na extração'

    if (errorDetail.includes('timeout') || errorDetail.includes('tempo limite')) {
      summary = 'Tempo limite excedido'
      errorDetail = 'O documento é muito grande. Sugestões:\n' +
                    '• Selecione apenas as páginas necessárias\n' +
                    '• Use o extrator "pdfplumber" (mais rápido)\n' +
                    '• Divida o documento em arquivos menores'
    } else if (errorDetail.includes('network') || errorDetail.includes('fetch')) {
      summary = 'Erro de conexão'
      errorDetail = 'Verifique sua conexão com a internet e tente novamente.'
    }

    extractionError.value = errorDetail
    toast.add({
      severity: 'error',
      summary,
      detail: errorDetail,
      life: 8000 // Longer display for error messages
    })
    emit('error', error)
  } finally {
    isLoading.value = false
    isExtractingWithProgress.value = false
    extractionProgress.value = 0
    extractionProgressMessage.value = ''
    extractionAbortController.value = null
  }
}

function cancelExtraction() {
  if (extractionAbortController.value) {
    extractionAbortController.value.abort()
    extractionAbortController.value = null
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
    detail: 'O texto do documento foi inserido no editor.',
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
  totalPdfPages.value = 0
  documentPreview.value = null
  thumbnailsCache.value = {}
  loadingThumbnails.value = new Set()
  visiblePages.value = new Set()
  cleanupIntersectionObserver()
}

function clearFile() {
  selectedFile.value = null
  extractedResult.value = null
  extractionError.value = null
  pagesPreview.value = null
  selectedPages.value = []
  totalPdfPages.value = 0
  documentPreview.value = null
  thumbnailsCache.value = {}
  loadingThumbnails.value = new Set()
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
    icon="pi pi-file-import"
    label="Documento"
    severity="secondary"
    outlined
    @click="openDialog"
    title="Importar texto de documento (PDF, Word, PowerPoint, Excel, HTML, Markdown, Imagens)"
    class="document-upload-btn"
  />

  <!-- Upload Dialog -->
  <Dialog
    v-model:visible="isDialogVisible"
    :header="dialogTitle"
    :modal="true"
    :closable="!isLoading"
    :style="{ width: dialogWidth, maxWidth: dialogMaxWidth }"
    class="document-upload-dialog"
  >
    <!-- Service Status Warning -->
    <div v-if="isServiceAvailable === false" class="service-warning">
      <i class="pi pi-exclamation-triangle" />
      <div>
        <strong>Servico de extracao nao disponivel</strong>
        <p>Execute no terminal: <code>pip install docling</code></p>
      </div>
    </div>

    <!-- Hidden File Input -->
    <input
      ref="fileInputRef"
      type="file"
      :accept="acceptedFormats"
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
        <i class="pi pi-file-import drop-icon" />
        <div class="drop-text">
          <strong>Arraste um documento aqui</strong>
          <span>ou clique para selecionar</span>
        </div>
        <div class="drop-formats">
          <Tag severity="secondary" class="format-tag">PDF</Tag>
          <Tag severity="secondary" class="format-tag">Word</Tag>
          <Tag severity="secondary" class="format-tag">PowerPoint</Tag>
          <Tag severity="secondary" class="format-tag">Excel</Tag>
          <Tag severity="secondary" class="format-tag">HTML</Tag>
          <Tag severity="secondary" class="format-tag">Markdown</Tag>
          <Tag severity="secondary" class="format-tag">Imagens</Tag>
        </div>
        <Tag severity="secondary" class="drop-hint">
          Max. 50MB
        </Tag>
      </div>

      <!-- Selected File Info -->
      <div v-else class="file-info">
        <div class="file-card">
          <i :class="['pi', fileInfo?.formatIcon, 'file-icon']" :style="{ color: fileInfo?.formatColor }" />
          <div class="file-details">
            <div class="file-name">{{ fileInfo?.name }}</div>
            <div class="file-meta">
              <Tag :severity="isPdfFile ? 'danger' : 'info'" size="small">
                {{ fileInfo?.formatName }}
              </Tag>
              <span class="file-size">{{ fileInfo?.size }}</span>
            </div>
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

        <!-- OCR Warning for Images -->
        <div v-if="isImageFile" class="ocr-warning">
          <i class="pi pi-info-circle" />
          <span>Imagens serao processadas com OCR para extrair texto</span>
        </div>

        <!-- Loading indicator -->
        <div v-if="isLoading" class="upload-progress">
          <span class="progress-message">{{ loadingMessage }}</span>
          <ProgressBar mode="indeterminate" style="height: 6px" />
        </div>

        <!-- Error Message -->
        <div v-if="extractionError" class="extraction-error">
          <i class="pi pi-exclamation-circle" />
          <span>{{ extractionError }}</span>
        </div>
      </div>
    </template>

    <!-- ============================================== -->
    <!-- STEP 2: Select Pages (PDF) or Confirm (Other) -->
    <!-- ============================================== -->
    <template v-if="currentStep === 'pages'">
      <!-- Extraction Progress (shown during extraction) -->
      <div v-if="isExtractingWithProgress" class="extraction-progress-container">
        <div class="extraction-file-name">
          <i class="pi pi-file-pdf" />
          <span>{{ fileInfo?.name }}</span>
        </div>

        <div class="extraction-progress-main">
          <ProgressBar
            :value="extractionProgress"
            :showValue="false"
            class="extraction-bar"
          />
          <div class="extraction-stats">
            <span class="extraction-pages">{{ extractionProgressMessage }}</span>
            <span class="extraction-percent">{{ extractionProgress.toFixed(0) }}%</span>
          </div>
        </div>
      </div>

      <!-- PDF with Visual Thumbnails (hidden during extraction) -->
      <div v-else-if="isPdfFile && hasPages" class="pages-selection">
        <div class="pages-header">
          <div class="pages-info">
            <Tag severity="info">
              <i class="pi pi-file mr-1" /> {{ totalPdfPages }} paginas
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

        <div ref="pagesGridRef" class="pages-grid">
          <div
            v-for="pageNum in pageNumbers"
            :key="pageNum"
            :data-page="pageNum"
            class="page-card"
            :class="{ 'selected': selectedPages.includes(pageNum), 'processed': processedPages.has(pageNum) }"
            @click="togglePageSelection(pageNum)"
          >
            <div class="page-checkbox-overlay">
              <Checkbox
                :modelValue="selectedPages.includes(pageNum)"
                :binary="true"
                @click.stop
                @update:modelValue="togglePageSelection(pageNum)"
              />
            </div>

            <div v-if="processedPages.has(pageNum)" class="page-processed-badge">
              <i class="pi pi-check" />
            </div>

            <div class="thumbnail-container">
              <img
                v-if="thumbnailsCache[pageNum]"
                :src="thumbnailsCache[pageNum]"
                :alt="`Página ${pageNum}`"
                class="pdf-thumbnail"
              />
              <Skeleton
                v-else
                width="100%"
                height="180px"
                class="thumbnail-skeleton"
              />
            </div>

            <div class="page-number-badge">
              {{ pageNum }}
            </div>
          </div>
        </div>
      </div>

      <!-- Non-PDF Document Preview -->
      <div v-else-if="documentPreview" class="document-preview">
        <div class="preview-header">
          <div class="preview-info">
            <i :class="['pi', fileInfo?.formatIcon]" :style="{ color: fileInfo?.formatColor }" />
            <div>
              <div class="preview-title">{{ fileInfo?.name }}</div>
              <div class="preview-meta">
                <Tag :severity="'info'" size="small">{{ documentPreview.format_type || fileInfo?.formatName }}</Tag>
                <span>{{ documentPreview.total_pages }} secao(oes)</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="documentPreview.pages?.length > 0" class="preview-sections">
          <div
            v-for="page in documentPreview.pages"
            :key="page.page_number"
            class="preview-section"
          >
            <div class="section-header">
              <Tag severity="secondary" size="small">Secao {{ page.page_number }}</Tag>
              <span class="section-words">{{ page.word_count }} palavras</span>
            </div>
            <div class="section-preview">{{ page.preview }}</div>
          </div>
        </div>

        <div class="preview-summary">
          <i class="pi pi-info-circle" />
          <span>O documento sera extraido completamente</span>
        </div>
      </div>

      <!-- Loading (only for initial loading, not extraction) -->
      <div v-if="isLoading && !isExtractingWithProgress" class="upload-progress pages-loading">
        <div class="progress-card">
          <div class="progress-header">
            <div class="progress-title">
              <i class="pi pi-sync progress-icon" />
              <span>Carregando</span>
            </div>
          </div>
          <ProgressBar mode="indeterminate" class="pdf-progress-bar is-indeterminate" />
          <span class="progress-label">{{ loadingMessage }}</span>
        </div>
      </div>

      <!-- Error -->
      <div v-if="extractionError" class="extraction-error">
        <i class="pi pi-exclamation-circle" />
        <span>{{ extractionError }}</span>
      </div>
    </template>

    <!-- ============================================== -->
    <!-- STEP 3: Result -->
    <!-- ============================================== -->
    <template v-if="currentStep === 'result' && hasResult">
      <div class="extraction-result">
        <div class="result-header">
          <Tag severity="success">
            <i class="pi pi-check mr-1" /> Extracao concluida
          </Tag>
          <div class="result-stats">
            <Tag severity="secondary">
              <i class="pi pi-file mr-1" /> {{ extractedResult.pages }} pagina(s)
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
            :label="isPdfFile ? 'Analisar Paginas' : 'Analisar Documento'"
            icon="pi pi-search"
            @click="loadPagesPreview"
            :loading="isLoading"
            :disabled="isServiceAvailable === false"
          />
        </template>

        <!-- Step 2: Pages/Confirm -->
        <template v-if="currentStep === 'pages'">
          <Button
            label="Voltar"
            severity="secondary"
            text
            icon="pi pi-arrow-left"
            @click="goBackToUpload"
            :disabled="isLoading && !isExtractingWithProgress"
          />

          <!-- PDF Extractor Selection - hidden during extraction -->
          <div v-if="isPdfFile && !isExtractingWithProgress" class="extractor-selector">
            <SelectButton
              v-model="selectedExtractor"
              :options="extractorOptions"
              optionLabel="label"
              optionValue="value"
              :allowEmpty="false"
              :disabled="isLoading"
            >
              <template #option="{ option }">
                <div class="extractor-option">
                  <i :class="option.icon" />
                  <span class="extractor-label">{{ option.label }}</span>
                  <span class="extractor-desc">{{ option.description }}</span>
                </div>
              </template>
            </SelectButton>
          </div>

          <!-- Cancel button during extraction -->
          <Button
            v-if="isExtractingWithProgress"
            label="Cancelar"
            icon="pi pi-times"
            class="cancel-extraction-btn"
            @click="cancelExtraction"
          />
          <!-- Extract button when not extracting -->
          <Button
            v-else
            label="Extrair Texto"
            icon="pi pi-download"
            @click="extractSelectedText"
            :loading="isLoading"
            :disabled="isPdfFile && selectedPagesCount === 0"
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
.document-upload-btn {
  gap: 0.5rem;
}

.document-upload-dialog :deep(.p-dialog-content) {
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
  color: var(--primary-400);
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

.drop-formats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  justify-content: center;
  max-width: 350px;
}

.format-tag {
  font-size: 0.7rem;
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

.file-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.file-size {
  font-size: 0.875rem;
  color: var(--text-color-secondary);
}

.ocr-warning {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--blue-50);
  border: 1px solid var(--blue-200);
  border-radius: 6px;
  color: var(--blue-700);
  font-size: 0.875rem;
}

.ocr-warning i {
  color: var(--blue-500);
}

/* Progress */
.upload-progress {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.pages-loading {
  position: sticky;
  bottom: 0;
  z-index: 5;
  padding-top: 0.5rem;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, var(--surface-0) 45%);
}

.progress-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 0.875rem;
  border-radius: 10px;
  background: var(--surface-50);
  border: 1px solid var(--surface-200);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.05);
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-color);
}

.progress-icon {
  font-size: 0.9rem;
  color: var(--primary-500);
  animation: progress-spin 1.2s linear infinite;
}

.progress-percent {
  font-weight: 700;
  font-size: 0.9rem;
  color: var(--primary-600);
}

.pdf-progress-bar {
  height: 16px;
  border-radius: 999px;
  overflow: hidden;
  box-shadow: inset 0 0 0 1px var(--surface-200);
}

.pdf-progress-bar :deep(.p-progressbar) {
  background: var(--surface-200);
}

.pdf-progress-bar :deep(.p-progressbar-value) {
  background: linear-gradient(90deg, #16a34a, #22c55e);
  transition: width 0.2s ease;
}

.pdf-progress-bar.is-indeterminate :deep(.p-progressbar-value) {
  background: linear-gradient(90deg, #16a34a, #22c55e, #4ade80);
  animation: pdf-progress-shimmer 1.2s ease-in-out infinite;
}

.progress-label {
  font-size: 0.85rem;
  color: var(--text-color-secondary);
}

@keyframes progress-spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

@keyframes pdf-progress-shimmer {
  0% {
    filter: brightness(0.95);
  }
  50% {
    filter: brightness(1.15);
  }
  100% {
    filter: brightness(0.95);
  }
}

.progress-message {
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

/* Extraction Progress */
.extraction-progress-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1.5rem;
  width: 100%;
}

.extraction-file-name {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: var(--text-color-secondary);
  max-width: 100%;
  overflow: hidden;
}

.extraction-file-name i {
  color: var(--red-400);
  flex-shrink: 0;
}

.extraction-file-name span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.extraction-progress-main {
  width: 100%;
}

.extraction-bar {
  height: 14px;
  border-radius: 7px;
  overflow: hidden;
}

.extraction-bar :deep(.p-progressbar) {
  background: var(--surface-200);
  height: 14px;
  border-radius: 7px;
}

.extraction-bar :deep(.p-progressbar-value) {
  background: linear-gradient(
    90deg,
    #16a34a 0%,
    #22c55e 50%,
    #16a34a 100%
  );
  background-size: 200% 100%;
  animation: extraction-shimmer 1.5s ease-in-out infinite;
  border-radius: 7px;
}

@keyframes extraction-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

.extraction-stats {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.4rem;
  font-size: 0.8rem;
}

.extraction-pages {
  color: var(--text-color-secondary);
}

.extraction-percent {
  font-weight: 600;
  color: var(--primary-400);
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

.page-card.processed {
  border-color: #16a34a;
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.15), 0 4px 12px rgba(0, 0, 0, 0.08);
}

.page-processed-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 11;
  background: #16a34a;
  color: #ffffff;
  border-radius: 999px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
}

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

/* Document Preview (non-PDF) */
.document-preview {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.preview-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.preview-info i {
  font-size: 2rem;
}

.preview-title {
  font-weight: 600;
  color: var(--text-color);
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-color-secondary);
}

.preview-sections {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 300px;
  overflow-y: auto;
}

.preview-section {
  padding: 0.75rem;
  background: var(--surface-50);
  border: 1px solid var(--surface-200);
  border-radius: 6px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.section-words {
  font-size: 0.75rem;
  color: var(--text-color-secondary);
}

.section-preview {
  font-size: 0.875rem;
  color: var(--text-color-secondary);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.preview-summary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--surface-100);
  border-radius: 6px;
  color: var(--text-color-secondary);
  font-size: 0.875rem;
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
  align-items: center;
  gap: 0.75rem;
}

/* Extractor Selector */
.extractor-selector {
  margin-right: auto;
}

.extractor-selector :deep(.p-selectbutton) {
  display: flex;
  gap: 0;
}

.extractor-selector :deep(.p-selectbutton .p-togglebutton) {
  padding: 0.5rem 0.75rem;
}

.extractor-option {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.extractor-option i {
  font-size: 0.875rem;
}

.extractor-label {
  font-weight: 500;
  font-size: 0.8125rem;
}

.extractor-desc {
  font-size: 0.75rem;
  color: var(--text-color-secondary);
  margin-left: 0.25rem;
}

.extractor-selector :deep(.p-togglebutton.p-highlight) .extractor-desc {
  color: var(--primary-100);
}

/* Cancel extraction button - purple gradient */
.cancel-extraction-btn {
  background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 50%, #c084fc 100%) !important;
  border: none !important;
  color: white !important;
  font-weight: 600;
  transition: all 0.2s ease;
}

.cancel-extraction-btn:hover {
  background: linear-gradient(135deg, #7c3aed 0%, #9333ea 50%, #a855f7 100%) !important;
  transform: translateY(-1px);
}

.cancel-extraction-btn:active {
  transform: translateY(0);
}
</style>
