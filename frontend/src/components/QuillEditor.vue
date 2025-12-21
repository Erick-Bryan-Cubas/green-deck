<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Quill from 'quill'
import 'quill/dist/quill.snow.css'

/**
 * QuillEditor.vue (Vue 3 + Quill via NPM)
 *
 * Melhorias incluídas:
 * 1) Context menu abre no mouse: emite `originalEvent` (MouseEvent real)
 * 2) Marcação (background) agora ajusta a cor da fonte automaticamente (color) para manter legibilidade
 * 3) Remover marcação remove também `color` (evita texto “preso” escuro)
 * 4) Normaliza marcações antigas (se já existiam highlights com texto branco)
 * 5) Color picker: reposiciona pra não estourar viewport e fecha ao scroll/resize/click fora
 * 6) Captura seleção antes de abrir o picker (mousedown)
 * 7) Wheel leak: impede scroll “vazar” para a página quando rolar dentro do editor
 */

const props = defineProps({
  placeholder: {
    type: String,
    default: 'Paste or type your text here, then highlight sections to generate cards...'
  }
})

const emit = defineEmits([
  'selection-changed', // { selectedText, range, hasSelection, hasHighlight }
  'content-changed',   // { fullText, html }
  'editor-ready',      // quill instance
  'context-menu'       // { originalEvent, hasSelection, hasHighlight, selectedText, range }
])

const toolbarRef = ref(null)
const editorRef = ref(null)

let quill = null
let textChangeTimeout = null

// Salva a última seleção (range) para aplicar formatação ao clicar em menus/pickers
let savedRange = null

// ----------------------------
// Mapeamento: background -> cor do texto (legibilidade)
// ----------------------------
const BG_TO_TEXT = {
  '#fef08a': '#111827', // Amarelo -> quase preto
  '#bbf7d0': '#052e16', // Verde -> verde bem escuro
  '#bfdbfe': '#0b1f3a', // Azul -> azul bem escuro
  '#fbcfe8': '#3b0a22', // Rosa -> vinho escuro
  '#ddd6fe': '#1e1b4b', // Roxo -> índigo escuro
  '#fed7aa': '#3a1f00'  // Laranja -> marrom escuro
}

function textColorForBackground(bg) {
  return BG_TO_TEXT[bg] || '#111827'
}

// ----------------------------
// Helpers de seleção / formatação
// ----------------------------
function getSelectedText(range) {
  if (!quill || !range || !range.length) return ''
  return quill.getText(range.index, range.length).trim()
}

function selectionHasHighlight(range) {
  if (!quill || !range || !range.length) return false
  const fmt = quill.getFormat(range.index, range.length)
  return !!fmt.background
}

function hasValidSavedRange() {
  return !!(savedRange && typeof savedRange.index === 'number' && savedRange.length > 0)
}

function applyFormatsToSavedRange(formats) {
  if (!quill) return
  if (!hasValidSavedRange()) return

  quill.setSelection(savedRange)
  quill.format('background', formats.background ?? false)
  quill.format('color', formats.color ?? false)
}

function formatBackground(bg) {
  if (!quill) return
  if (!hasValidSavedRange()) return

  if (bg === 'transparent') {
    applyFormatsToSavedRange({ background: false, color: false })
    return
  }

  applyFormatsToSavedRange({
    background: bg,
    color: textColorForBackground(bg)
  })
}

function clearHighlight() {
  if (!quill) return
  if (!hasValidSavedRange()) return
  applyFormatsToSavedRange({ background: false, color: false })
}

function clearSelection() {
  if (!quill) return
  quill.setSelection(null)
}

// ----------------------------
// Picker custom (🖍️) para background + auto-color
// ----------------------------
const PICKER_CLASS = 'custom-color-picker'
let pickerCleanupFns = []

function removePicker() {
  const existing = document.querySelector(`.${PICKER_CLASS}`)
  if (existing) existing.remove()

  // remove listeners registrados
  pickerCleanupFns.forEach((fn) => {
    try { fn() } catch {}
  })
  pickerCleanupFns = []
}

function positionPicker(pickerEl, anchorRect) {
  const margin = 8
  const pickerWidth = 140
  const pickerHeight = 8 + (3 * 36) + (2 * 6) // aprox (padding + grid)
  let left = anchorRect.left
  let top = anchorRect.bottom + 6

  // Ajuste horizontal
  if (left + pickerWidth + margin > window.innerWidth) {
    left = Math.max(margin, window.innerWidth - pickerWidth - margin)
  }
  if (left < margin) left = margin

  // Ajuste vertical (se estourar embaixo, joga pra cima)
  if (top + pickerHeight + margin > window.innerHeight) {
    top = anchorRect.top - pickerHeight - 6
    if (top < margin) top = margin
  }

  pickerEl.style.left = `${left}px`
  pickerEl.style.top = `${top}px`
}

function showBackgroundPicker(buttonEl) {
  // Salva seleção atual se possível
  savedRange = quill?.getSelection() || savedRange

  // Sem seleção => não faz sentido marcar
  if (!hasValidSavedRange()) return

  const existing = document.querySelector(`.${PICKER_CLASS}`)
  if (existing) {
    removePicker()
    return
  }

  const colors = [
    { color: '#fef08a', label: 'Amarelo' },
    { color: '#bbf7d0', label: 'Verde' },
    { color: '#bfdbfe', label: 'Azul' },
    { color: '#fbcfe8', label: 'Rosa' },
    { color: '#ddd6fe', label: 'Roxo' },
    { color: '#fed7aa', label: 'Laranja' },
    { color: 'transparent', label: 'Remover' }
  ]

  const picker = document.createElement('div')
  picker.className = PICKER_CLASS
  picker.style.cssText = `
    position: fixed;
    background: #111827;
    border: 1px solid #374151;
    border-radius: 8px;
    padding: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    z-index: 9999;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
    width: 140px;
  `

  // posiciona
  const rect = buttonEl.getBoundingClientRect()
  positionPicker(picker, rect)

  colors.forEach(({ color, label }) => {
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.title = label
    btn.style.cssText = `
      width: 36px;
      height: 36px;
      border-radius: 6px;
      border: 2px solid #374151;
      background-color: ${color};
      cursor: pointer;
      transition: all 0.15s ease;
      ${color === 'transparent'
        ? 'background-image: linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc), linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc); background-size: 8px 8px; background-position: 0 0, 4px 4px;'
        : ''
      }
    `

    btn.addEventListener('mouseenter', () => {
      btn.style.transform = 'scale(1.08)'
      btn.style.borderColor = '#ffffff'
    })
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = 'scale(1)'
      btn.style.borderColor = '#374151'
    })

    btn.addEventListener('mousedown', (e) => {
      // evita Quill perder seleção ao clicar no botão
      e.preventDefault()
      e.stopPropagation()
    })

    btn.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      formatBackground(color)
      removePicker()
    })

    picker.appendChild(btn)
  })

  document.body.appendChild(picker)

  // Fecha ao clicar fora
  const onDocClick = (e) => {
    if (!picker.contains(e.target) && e.target !== buttonEl) {
      removePicker()
    }
  }
  document.addEventListener('click', onDocClick)
  pickerCleanupFns.push(() => document.removeEventListener('click', onDocClick))

  // Fecha ao scroll/resize (senão fica “voando”)
  const onScroll = () => removePicker()
  const onResize = () => removePicker()
  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onResize)
  pickerCleanupFns.push(() => window.removeEventListener('scroll', onScroll, true))
  pickerCleanupFns.push(() => window.removeEventListener('resize', onResize))
}

// ----------------------------
// Normaliza highlights antigos (background aplicado, mas texto branco)
// ----------------------------
function normalizeHighlightTextColors() {
  if (!quill) return

  const delta = quill.getContents()
  let idx = 0

  delta.ops.forEach((op) => {
    const ins = op.insert
    const len = typeof ins === 'string' ? ins.length : 1
    const bg = op.attributes?.background

    if (bg && BG_TO_TEXT[bg]) {
      // aplica a cor de texto correspondente
      quill.formatText(idx, len, { color: textColorForBackground(bg) })
    }

    idx += len
  })
}

// ----------------------------
// Wheel leak: evita scroll do body
// ----------------------------
function preventWheelLeak(e) {
  const el = e.currentTarget
  const contentHeight = el.scrollHeight
  const visibleHeight = el.clientHeight
  const scrollTop = el.scrollTop

  const isAtTop = scrollTop === 0
  const isAtBottom = scrollTop + visibleHeight >= contentHeight - 1

  // se estiver no limite e o usuário tentar ir além, deixa a página rolar
  if ((isAtTop && e.deltaY < 0) || (isAtBottom && e.deltaY > 0)) return

  e.preventDefault()
  el.scrollTop += e.deltaY
}

// ----------------------------
// Context menu: emite MouseEvent real pro App abrir ContextMenu no cursor
// ----------------------------
function onContextMenu(e) {
  e.preventDefault()
  removePicker()

  if (!quill) return

  const range = quill.getSelection()
  savedRange = range

  const hasSel = !!(range && range.length > 0)
  const selText = hasSel ? getSelectedText(range) : ''
  const hl = hasSel ? selectionHasHighlight(range) : false

  emit('context-menu', {
    originalEvent: e, // ✅ O App deve chamar contextMenu.show(e)
    hasSelection: hasSel,
    hasHighlight: hl,
    selectedText: selText,
    range
  })
}

// ----------------------------
// Lifecycle
// ----------------------------
onMounted(() => {
  // Config do toolbar parecido com o original, mas usando container custom
  // Inclui `color` como formato permitido porque vamos setar a cor do texto.
  quill = new Quill(editorRef.value, {
    theme: 'snow',
    placeholder: props.placeholder,
    modules: { toolbar: toolbarRef.value },
    formats: ['header', 'bold', 'italic', 'list', 'background', 'color']
  })

  // Botão background (🖍️)
  const bgBtn = toolbarRef.value?.querySelector('.ql-background')
  if (bgBtn) {
    bgBtn.innerHTML = '<span style="font-size:16px;">🖍️</span>'

    // salva a seleção no mousedown (antes de perder foco)
    bgBtn.addEventListener('mousedown', () => {
      savedRange = quill.getSelection() || savedRange
    })

    bgBtn.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      showBackgroundPicker(bgBtn)
    })
  }

  // selection-change
  quill.on('selection-change', (range) => {
    savedRange = range

    if (range && range.length > 0) {
      const st = getSelectedText(range)
      emit('selection-changed', {
        selectedText: st,
        range,
        hasSelection: true,
        hasHighlight: selectionHasHighlight(range)
      })
    } else {
      emit('selection-changed', {
        selectedText: '',
        range,
        hasSelection: false,
        hasHighlight: false
      })
    }
  })

  // text-change: emite (com debounce curto)
  quill.on('text-change', () => {
    if (textChangeTimeout) clearTimeout(textChangeTimeout)
    textChangeTimeout = setTimeout(() => {
      const fullText = quill.getText()
      const html = editorRef.value?.querySelector('.ql-editor')?.innerHTML || ''
      emit('content-changed', { fullText, html })
    }, 200)
  })

  // listeners no editor
  const editorEl = editorRef.value.querySelector('.ql-editor')
  editorEl.addEventListener('contextmenu', onContextMenu)
  editorEl.addEventListener('wheel', preventWheelLeak, { passive: false })

  // Ajusta highlights existentes (se houver)
  normalizeHighlightTextColors()

  emit('editor-ready', quill)
})

onBeforeUnmount(() => {
  removePicker()
  if (textChangeTimeout) clearTimeout(textChangeTimeout)

  try {
    const editorEl = editorRef.value?.querySelector('.ql-editor')
    if (editorEl) {
      editorEl.removeEventListener('contextmenu', onContextMenu)
      editorEl.removeEventListener('wheel', preventWheelLeak)
    }
  } catch {}
})

// ----------------------------
// Expose (para App.vue chamar)
// ----------------------------
defineExpose({
  formatBackground,
  clearHighlight,
  clearSelection,
  getFullText: () => (quill ? quill.getText().trim() : ''),
  getSelectedText: () => (hasValidSavedRange() ? getSelectedText(savedRange) : '')
})
</script>

<template>
  <div class="quill-wrapper">
    <div ref="toolbarRef" class="quill-toolbar">
      <select class="ql-header">
        <option value="1"></option>
        <option value="2"></option>
        <option value="3"></option>
        <option selected></option>
      </select>

      <button class="ql-bold" type="button"></button>
      <button class="ql-italic" type="button"></button>
      <button class="ql-list" value="ordered" type="button"></button>
      <button class="ql-list" value="bullet" type="button"></button>
      <button class="ql-background" type="button"></button>
    </div>

    <div ref="editorRef" class="quill-editor"></div>
  </div>
</template>

<style scoped>
.quill-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.quill-toolbar {
  border-radius: 10px 10px 0 0;
  overflow: hidden;
}

/* Mantém o editor ocupando todo o espaço do painel */
.quill-editor {
  flex: 1;
  min-height: 0;
  border-radius: 0 0 10px 10px;
  overflow: hidden;
}

/* Se você tiver CSS global forçando branco, isto pode não vencer um !important.
   Mas ajuda em setups normais. */
:deep(.ql-editor) {
  /* deixe seu tema controlar se quiser; aqui é um fallback “dark friendly” */
  color: var(--text-color, #e5e7eb);
}

/* garante que seleção/toolbar fiquem “apertadinhos” em layouts tight */
:deep(.ql-toolbar.ql-snow) {
  border: 1px solid var(--surface-border, #2a2a2a);
}
:deep(.ql-container.ql-snow) {
  border: 1px solid var(--surface-border, #2a2a2a);
  border-top: none;
}
</style>
