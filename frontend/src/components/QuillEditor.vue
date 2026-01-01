<script setup>

import { onBeforeUnmount, onMounted, ref } from 'vue'
import Quill from 'quill'
import 'quill/dist/quill.snow.css'

const props = defineProps({
  placeholder: {
    type: String,
    default: 'Cole ou digite o texto aqui, selecione trechos e gere cards...'
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

let savedRange = null

// ------------------------------------------------------------
// Contraste automático: dado um HEX, retorna #111.. ou #fff
// ------------------------------------------------------------
function hexToRgb(hex) {
  const h = (hex || '').replace('#', '').trim()
  if (h.length === 3) {
    const r = parseInt(h[0] + h[0], 16)
    const g = parseInt(h[1] + h[1], 16)
    const b = parseInt(h[2] + h[2], 16)
    return { r, g, b }
  }
  if (h.length === 6) {
    const r = parseInt(h.slice(0, 2), 16)
    const g = parseInt(h.slice(2, 4), 16)
    const b = parseInt(h.slice(4, 6), 16)
    return { r, g, b }
  }
  return null
}

function relativeLuminance({ r, g, b }) {
  // sRGB -> linear
  const srgb = [r, g, b].map((v) => v / 255)
  const lin = srgb.map((c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)))
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
}

function textColorForBackground(bgHex) {
  const rgb = hexToRgb(bgHex)
  if (!rgb) return '#111827'
  const L = relativeLuminance(rgb)
  // fundo claro -> texto escuro; fundo escuro -> texto claro
  return L > 0.52 ? '#111827' : '#ffffff'
}

// ------------------------------------------------------------
// Seleção / formatos
// ------------------------------------------------------------
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

  if (!bg || bg === 'transparent') {
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

// ------------------------------------------------------------
// Normaliza highlights antigos (background mas cor errada)
// ------------------------------------------------------------
function normalizeHighlightTextColors() {
  if (!quill) return

  const delta = quill.getContents()
  let idx = 0

  delta.ops.forEach((op) => {
    const ins = op.insert
    const len = typeof ins === 'string' ? ins.length : 1
    const bg = op.attributes?.background

    if (bg && typeof bg === 'string' && bg.startsWith('#')) {
      quill.formatText(idx, len, { color: textColorForBackground(bg) })
    }
    idx += len
  })
}

// ------------------------------------------------------------
// Picker custom (🖍️) - também clamp na tela
// ------------------------------------------------------------
const PICKER_CLASS = 'custom-color-picker'
let pickerCleanupFns = []

function removePicker() {
  const existing = document.querySelector(`.${PICKER_CLASS}`)
  if (existing) existing.remove()
  pickerCleanupFns.forEach((fn) => {
    try { fn() } catch {}
  })
  pickerCleanupFns = []
}

function clampPosition(x, y, w, h, margin = 8) {
  const maxX = window.innerWidth - w - margin
  const maxY = window.innerHeight - h - margin
  return {
    x: Math.max(margin, Math.min(x, maxX)),
    y: Math.max(margin, Math.min(y, maxY))
  }
}

function showBackgroundPicker(buttonEl) {
  savedRange = quill?.getSelection() || savedRange
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
    border-radius: 10px;
    padding: 8px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.55);
    z-index: 99999;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
    width: 156px;
  `

  const rect = buttonEl.getBoundingClientRect()
  // tamanho aproximado do picker (altura depende do grid, mas aqui é estável)
  const pickerW = 156
  const pickerH = 8 + (3 * 36) + (2 * 6) + 8
  const pos = clampPosition(rect.left, rect.bottom + 8, pickerW, pickerH)

  picker.style.left = `${pos.x}px`
  picker.style.top = `${pos.y}px`

  colors.forEach(({ color, label }) => {
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.title = label

    const txtColor = color === 'transparent' ? '#e5e7eb' : textColorForBackground(color)
    btn.style.cssText = `
      width: 44px;
      height: 36px;
      border-radius: 8px;
      border: 2px solid #374151;
      background-color: ${color === 'transparent' ? 'transparent' : color};
      cursor: pointer;
      transition: transform 0.12s ease, border-color 0.12s ease;
      position: relative;
      overflow: hidden;
      ${color === 'transparent'
        ? 'background-image: linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc), linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc); background-size: 8px 8px; background-position: 0 0, 4px 4px;'
        : ''
      }
    `

    // mini “A” pra mostrar contraste (ajuda UX)
    btn.innerHTML = `<span style="
        position:absolute; inset:0;
        display:grid; place-items:center;
        font-weight:900; font-size:12px;
        color:${txtColor};
        text-shadow:${txtColor === '#ffffff' ? '0 1px 2px rgba(0,0,0,0.45)' : 'none'};
      ">A</span>`

    btn.addEventListener('mousedown', (e) => {
      e.preventDefault()
      e.stopPropagation()
    })

    btn.addEventListener('mouseenter', () => {
      btn.style.transform = 'scale(1.06)'
      btn.style.borderColor = '#ffffff'
    })
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = 'scale(1)'
      btn.style.borderColor = '#374151'
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

  const onDocClick = (e) => {
    if (!picker.contains(e.target) && e.target !== buttonEl) removePicker()
  }
  document.addEventListener('click', onDocClick)
  pickerCleanupFns.push(() => document.removeEventListener('click', onDocClick))

  const onScroll = () => removePicker()
  const onResize = () => removePicker()
  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onResize)
  pickerCleanupFns.push(() => window.removeEventListener('scroll', onScroll, true))
  pickerCleanupFns.push(() => window.removeEventListener('resize', onResize))
}

// ------------------------------------------------------------
// Context menu: clamp para não vazar a tela
// (1) emitimos um MouseEvent “clampado”
// (2) fallback: após abrir, tenta ajustar .p-contextmenu visível
// ------------------------------------------------------------
function createClampedMouseEvent(e, estimatedW = 260, estimatedH = 320) {
  const pos = clampPosition(e.clientX, e.clientY, estimatedW, estimatedH, 8)
  const init = {
    bubbles: true,
    cancelable: true,
    view: window,
    clientX: pos.x,
    clientY: pos.y,
    screenX: e.screenX,
    screenY: e.screenY,
    button: e.button,
    buttons: e.buttons,
    ctrlKey: e.ctrlKey,
    shiftKey: e.shiftKey,
    altKey: e.altKey,
    metaKey: e.metaKey
  }
  return new MouseEvent(e.type, init)
}

function clampPrimeContextMenuIfVisible() {
  // tenta ajustar o menu do PrimeVue se ele estiver aberto
  requestAnimationFrame(() => {
    const menus = Array.from(document.querySelectorAll('.p-contextmenu'))
    if (!menus.length) return

    const visible = menus
      .filter((el) => {
        const st = window.getComputedStyle(el)
        return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity || '1') > 0
      })
      .sort((a, b) => (a.getBoundingClientRect().top - b.getBoundingClientRect().top))

    const el = visible[visible.length - 1]
    if (!el) return

    const r = el.getBoundingClientRect()
    const margin = 8
    let left = r.left
    let top = r.top

    if (r.right > window.innerWidth - margin) left -= (r.right - (window.innerWidth - margin))
    if (r.bottom > window.innerHeight - margin) top -= (r.bottom - (window.innerHeight - margin))
    if (left < margin) left = margin
    if (top < margin) top = margin

    el.style.left = `${Math.round(left)}px`
    el.style.top = `${Math.round(top)}px`
  })
}

function onContextMenu(e) {
  e.preventDefault()
  removePicker()

  if (!quill) return

  const range = quill.getSelection()
  savedRange = range

  const hasSel = !!(range && range.length > 0)
  const selText = hasSel ? getSelectedText(range) : ''
  const hl = hasSel ? selectionHasHighlight(range) : false

  const clampedEvent = createClampedMouseEvent(e)

  emit('context-menu', {
    originalEvent: clampedEvent,
    hasSelection: hasSel,
    hasHighlight: hl,
    selectedText: selText,
    range
  })

  // fallback: reposiciona menu se Prime não clampou corretamente
  clampPrimeContextMenuIfVisible()
}

// ------------------------------------------------------------
// Wheel leak: impede scroll “vazar” para a página
// ------------------------------------------------------------
function preventWheelLeak(e) {
  const el = e.currentTarget
  const contentHeight = el.scrollHeight
  const visibleHeight = el.clientHeight
  const scrollTop = el.scrollTop

  const isAtTop = scrollTop === 0
  const isAtBottom = scrollTop + visibleHeight >= contentHeight - 1

  if ((isAtTop && e.deltaY < 0) || (isAtBottom && e.deltaY > 0)) return

  e.preventDefault()
  el.scrollTop += e.deltaY
}

// ------------------------------------------------------------
// Lifecycle
// ------------------------------------------------------------
onMounted(() => {
  quill = new Quill(editorRef.value, {
    theme: 'snow',
    placeholder: props.placeholder,
    modules: { toolbar: toolbarRef.value },
    formats: ['header', 'bold', 'italic', 'list', 'background', 'color']
  })

  const bgBtn = toolbarRef.value?.querySelector('.ql-background')
  if (bgBtn) {
    bgBtn.innerHTML = '<span style="font-size:16px;">🖍️</span>'
    bgBtn.addEventListener('mousedown', () => {
      savedRange = quill.getSelection() || savedRange
    })
    bgBtn.addEventListener('click', (ev) => {
      ev.preventDefault()
      ev.stopPropagation()
      showBackgroundPicker(bgBtn)
    })
  }

  quill.on('selection-change', (range) => {
    savedRange = range

    if (range && range.length > 0) {
      emit('selection-changed', {
        selectedText: getSelectedText(range),
        range,
        hasSelection: true,
        hasHighlight: selectionHasHighlight(range)
      })
    } else {
      emit('selection-changed', { selectedText: '', range, hasSelection: false, hasHighlight: false })
    }
  })

  quill.on('text-change', (delta, oldDelta, source) => {
    if (textChangeTimeout) clearTimeout(textChangeTimeout)

    // "texto mudou" somente se houve insert/delete
    const isTextMutation = Array.isArray(delta?.ops)
      ? delta.ops.some(op => op.insert != null || op.delete != null)
      : false

    textChangeTimeout = setTimeout(() => {
      const fullText = quill.getText()
      const html = editorRef.value?.querySelector('.ql-editor')?.innerHTML || ''
      const contents = quill.getContents()

      emit('content-changed', {
        fullText,
        html,
        delta: contents,
        source,
        isTextMutation
      })
    }, 200)
  })

  const editorEl = editorRef.value.querySelector('.ql-editor')
  editorEl.addEventListener('contextmenu', onContextMenu)
  editorEl.addEventListener('wheel', preventWheelLeak, { passive: false })

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

defineExpose({
  formatBackground,
  clearHighlight,
  clearSelection,
  getFullText: () => (quill ? quill.getText().trim() : ''),
  getSelectedText: () => (hasValidSavedRange() ? getSelectedText(savedRange) : ''),
  getDelta: () => (quill ? quill.getContents() : null),
  setDelta: (delta) => {
    if (!quill) return
    if (!delta) {
      quill.setText('')
      return
    }
    quill.setContents(delta, 'api')
    normalizeHighlightTextColors()
  },
  setContent: (text) => {
    if (!quill) return
    if (!text) {
      quill.setText('')
      return
    }
    // Se for HTML, usa clipboard para preservar formatação
    if (typeof text === 'string' && text.includes('<')) {
      quill.clipboard.dangerouslyPasteHTML(text, 'api')
    } else {
      // Texto simples
      quill.setText(text, 'api')
    }
  },
  getHtml: () => (quill ? quill.root.innerHTML : ''),
  getText: () => (quill ? quill.getText().trim() : ''),
  focus: () => quill?.focus()
})

</script>

<template>
  <div class="qe-wrap">
    <div ref="toolbarRef" class="qe-toolbar">
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

    <div ref="editorRef" class="qe-editor"></div>
  </div>
</template>

<style scoped>
.qe-wrap {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.qe-toolbar {
  border-radius: 14px 14px 0 0;
  overflow: hidden;
}

.qe-editor {
  flex: 1;
  min-height: 0;
  border-radius: 0 0 14px 14px;
  overflow: hidden;
}

/* bordas mais “clean” */
:deep(.ql-toolbar.ql-snow) {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.03);
}
:deep(.ql-container.ql-snow) {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-top: none;
}

/* melhora o look do editor em dark UI */
:deep(.ql-editor) {
  color: var(--text-color, #e5e7eb);
}

/* Placeholder do Quill (tema escuro) */
:deep(.ql-editor.ql-blank::before) {
  color: var(--text-color-secondary, rgba(229, 231, 235, 0.65)) !important;
  opacity: 1 !important;
}

/* Opcional: deixa o placeholder mais “suave” e consistente */
:deep(.ql-editor.ql-blank::before) {
  font-style: italic;
}

</style>
