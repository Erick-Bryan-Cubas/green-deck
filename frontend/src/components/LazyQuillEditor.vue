<!-- frontend/src/components/LazyQuillEditor.vue -->
<!-- Lazy-loaded wrapper for QuillEditor to improve initial page load -->
<script setup>
import { defineAsyncComponent, ref, shallowRef } from 'vue'

const props = defineProps({
  placeholder: {
    type: String,
    default: 'Cole ou digite o texto aqui, selecione trechos e gere cards...'
  }
})

const emit = defineEmits([
  'selection-changed',
  'content-changed',
  'editor-ready',
  'context-menu'
])

// Lazy load QuillEditor with loading state
const QuillEditor = defineAsyncComponent({
  loader: () => import('./QuillEditor.vue'),
  loadingComponent: {
    template: `
      <div class="lazy-editor-loading">
        <div class="loading-skeleton">
          <div class="skeleton-toolbar"></div>
          <div class="skeleton-content">
            <i class="pi pi-spin pi-spinner" style="font-size: 1.5rem; color: var(--primary-color);"></i>
            <span>Carregando editor...</span>
          </div>
        </div>
      </div>
    `
  },
  delay: 100,
  timeout: 30000
})

const editorRef = shallowRef(null)

// Expose methods from the underlying QuillEditor
function getHtml() {
  return editorRef.value?.getHtml?.() || ''
}

function getText() {
  return editorRef.value?.getText?.() || ''
}

function clearContent() {
  return editorRef.value?.clearContent?.()
}

function setContent(html) {
  return editorRef.value?.setContent?.(html)
}

function focus() {
  return editorRef.value?.focus?.()
}

function getDelta() {
  return editorRef.value?.getDelta?.()
}

function setDelta(delta) {
  return editorRef.value?.setDelta?.(delta)
}

defineExpose({
  getHtml,
  getText,
  clearContent,
  setContent,
  focus,
  getDelta,
  setDelta
})
</script>

<template>
  <QuillEditor
    ref="editorRef"
    :placeholder="placeholder"
    @selection-changed="emit('selection-changed', $event)"
    @content-changed="emit('content-changed', $event)"
    @editor-ready="emit('editor-ready', $event)"
    @context-menu="emit('context-menu', $event)"
  />
</template>

<style scoped>
.lazy-editor-loading {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.loading-skeleton {
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  overflow: hidden;
}

.skeleton-toolbar {
  height: 42px;
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.skeleton-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  color: var(--text-color-secondary, rgba(229, 231, 235, 0.65));
  font-size: 0.9rem;
}
</style>
