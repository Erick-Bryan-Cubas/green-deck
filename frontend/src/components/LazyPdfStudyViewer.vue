<!-- frontend/src/components/LazyPdfStudyViewer.vue -->
<!-- Wrapper do PdfStudyViewer: carrega o chunk do PDF.js sob demanda e lê os
     bytes do arquivo antes de montar o viewer. Os bytes vão em memória para o
     PDF.js — blob URLs são bloqueados pela CSP do backend (connect-src). -->
<script setup>
import { defineAsyncComponent, ref, shallowRef } from 'vue'

const props = defineProps({
  file: {
    type: File,
    required: true
  },
  generating: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'selection-changed',
  'highlights-changed',
  'generate',
  'add-to-editor',
  'close'
])

// Sem loadingComponent com template string: o runtime de produção do Vue não
// compila templates — o estado de carregamento é renderizado por este wrapper.
const PdfStudyViewer = defineAsyncComponent(() => import('./PdfStudyViewer.vue'))

const pdfData = shallowRef(null)
const readError = ref('')

props.file
  .arrayBuffer()
  .then((buf) => {
    pdfData.value = new Uint8Array(buf)
  })
  .catch((e) => {
    readError.value = e?.message || 'Falha ao ler o arquivo PDF'
  })

const viewerRef = shallowRef(null)

defineExpose({
  getSelectedText: () => viewerRef.value?.getSelectedText?.() || '',
  getHighlights: () =>
    viewerRef.value?.getHighlights?.() || { count: 0, combined: '', items: [] },
  clearSelection: () => viewerRef.value?.clearSelection?.(),
  goToPage: (p) => viewerRef.value?.goToPage?.(p)
})
</script>

<template>
  <div v-if="readError" class="lazy-pdf-loading">
    <i class="pi pi-exclamation-circle" style="font-size: 1.5rem; color: var(--color-danger)" />
    <span>{{ readError }}</span>
  </div>

  <div v-else-if="!pdfData" class="lazy-pdf-loading">
    <i class="pi pi-spin pi-spinner" style="font-size: 1.5rem; color: var(--color-primary)" />
    <span>Carregando leitor de PDF...</span>
  </div>

  <PdfStudyViewer
    v-else
    ref="viewerRef"
    :file="file"
    :data="pdfData"
    :generating="generating"
    @selection-changed="emit('selection-changed', $event)"
    @highlights-changed="emit('highlights-changed', $event)"
    @generate="emit('generate', $event)"
    @add-to-editor="emit('add-to-editor', $event)"
    @close="emit('close')"
  />
</template>

<style scoped>
.lazy-pdf-loading {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  color: var(--app-text-muted);
  font-size: 0.9rem;
}
</style>
