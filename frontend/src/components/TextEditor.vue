<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import Quill from 'quill'
import ContextMenu from 'primevue/contextmenu'

const props = defineProps({
  placeholder: { type: String, default: 'Cole ou digite seu texto e selecione trechos para gerar cards...' }
})

const emit = defineEmits([
  'selection-change',      // (selectedText: string)
  'plain-text-change',     // (fullText: string)
  'reanalyze-request',     // (fullText: string)
  'generate-request'       // ({ type: 'basic'|'cloze', text: string })
])

const editorHost = ref(null)
const menuRef = ref(null)

let quill = null
const savedRange = ref(null)
const selectedText = ref('')
const hasSelection = computed(() => selectedText.value.trim().length > 0)

function getHasHighlight() {
  if (!quill || !savedRange.value) return false
  const r = savedRange.value
  if (!r || r.length <= 0) return false
  const fmt = quill.getFormat(r.index, r.length)
  return !!fmt.background
}

function applyHighlight(color) {
  if (!quill || !savedRange.value) return
  quill.setSelection(savedRange.value)
  quill.format('background', color)
}

function removeHighlight() {
  if (!quill || !savedRange.value) return
  quill.setSelection(savedRange.value)
  quill.format('background', false)
}

const colorItems = [
  { label: 'Amarelo', color: '#fef08a' },
  { label: 'Verde', color: '#bbf7d0' },
  { label: 'Azul', color: '#bfdbfe' },
  { label: 'Rosa', color: '#fbcfe8' },
  { label: 'Roxo', color: '#ddd6fe' },
  { label: 'Laranja', color: '#fed7aa' }
].map(c => ({
  label: c.label,
  command: () => applyHighlight(c.color)
}))

const menuModel = computed(() => ([
  {
    label: 'Marcar texto',
    icon: 'pi pi-palette',
    items: colorItems,
    disabled: !hasSelection.value
  },
  {
    label: 'Remover marcação',
    icon: 'pi pi-eraser',
    command: () => removeHighlight(),
    disabled: !getHasHighlight()
  },
  { separator: true },
  {
    label: 'Analisar texto novamente',
    icon: 'pi pi-search',
    command: () => emit('reanalyze-request', quill?.getText() ?? '')
  },
  { separator: true },
  {
    label: 'Gerar cartão básico',
    icon: 'pi pi-file',
    disabled: !hasSelection.value,
    command: () => emit('generate-request', { type: 'basic', text: selectedText.value })
  },
  {
    label: 'Gerar cartão cloze',
    icon: 'pi pi-clone',
    disabled: !hasSelection.value,
    command: () => emit('generate-request', { type: 'cloze', text: selectedText.value })
  }
]))

function onRightClick(e) {
  e.preventDefault()
  if (!quill) return

  const range = quill.getSelection()
  savedRange.value = range

  if (range && range.length > 0) {
    selectedText.value = quill.getText(range.index, range.length).trim()
  } else {
    selectedText.value = ''
  }

  emit('selection-change', selectedText.value)
  menuRef.value?.show(e) // PrimeVue ContextMenu :contentReference[oaicite:5]{index=5}
}

onMounted(() => {
  quill = new Quill(editorHost.value, {
    theme: 'snow',
    placeholder: props.placeholder,
    modules: {
      toolbar: [
        [{ header: [1, 2, 3, false] }],
        ['bold', 'italic'],
        [{ list: 'ordered' }, { list: 'bullet' }],
        [{ background: [] }]
      ]
    }
  })

  quill.on('selection-change', (range) => {
    if (range && range.length > 0) {
      selectedText.value = quill.getText(range.index, range.length).trim()
    } else {
      selectedText.value = ''
    }
    savedRange.value = range
    emit('selection-change', selectedText.value)
  })

  quill.on('text-change', () => {
    emit('plain-text-change', quill.getText())
  })
})

onBeforeUnmount(() => {
  quill = null
})
</script>

<template>
  <div class="editor-shell" @contextmenu="onRightClick">
    <div ref="editorHost" class="editor-host" />
    <ContextMenu ref="menuRef" :model="menuModel" />
  </div>
</template>

<style scoped>
.editor-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.editor-host :deep(.ql-container) {
  height: 100%;
}
</style>
