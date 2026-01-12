<!--
  DEPRECATED: This component is kept for backward compatibility.
  Use DocumentUpload.vue instead, which supports all Docling formats.
-->
<script setup>
import DocumentUpload from './DocumentUpload.vue'
import { ref } from 'vue'

const documentUploadRef = ref(null)

// Forward all events
const emit = defineEmits(['extracted', 'error'])

function onExtracted(data) {
  emit('extracted', data)
}

function onError(error) {
  emit('error', error)
}

// Expose methods
defineExpose({
  openDialog: () => documentUploadRef.value?.openDialog(),
  closeDialog: () => documentUploadRef.value?.closeDialog()
})
</script>

<template>
  <DocumentUpload
    ref="documentUploadRef"
    @extracted="onExtracted"
    @error="onError"
  />
</template>
