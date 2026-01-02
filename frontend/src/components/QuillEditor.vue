<script setup>

import { onBeforeUnmount, onMounted, ref } from 'vue'
import Quill from 'quill'
import 'quill/dist/quill.snow.css'

const props = defineProps({
  placeholder: {
    type: String,
    default: 'Cole ou digite o texto aqui, selecione trechos e gere cards...'
  },
  showLineNumbers: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'selection-changed', // { selectedText, range, hasSelection, hasHighlight }
  'content-changed',   // { fullText, html }
  'editor-ready',      // quill instance
  'context-menu'       // { originalEvent, hasSelection, hasHighlight, selectedText, range }
])

const editorRef = ref(null)
const lineNumbersRef = ref(null)
const lineCount = ref(1)

let quill = null
let textChangeTimeout = null

let savedRange = null

// ------------------------------------------------------------
// Line numbers
// ------------------------------------------------------------
function updateLineCount() {
  if (!quill) return
  const text = quill.getText()
  lineCount.value = Math.max(1, (text.match(/\n/g) || []).length + 1)
}

function syncLineNumbersScroll() {
  if (!lineNumbersRef.value || !quill) return
  const editorEl = quill.root
  if (editorEl) {
    lineNumbersRef.value.scrollTop = editorEl.scrollTop
  }
}

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
    // Cores claras (marca-texto)
    { color: '#fef08a', label: 'Amarelo' },
    { color: '#bbf7d0', label: 'Verde claro' },
    { color: '#bfdbfe', label: 'Azul claro' },
    { color: '#fbcfe8', label: 'Rosa' },
    { color: '#ddd6fe', label: 'Roxo claro' },
    { color: '#fed7aa', label: 'Laranja' },
    // Cores médias
    { color: '#fcd34d', label: 'Amarelo forte' },
    { color: '#4ade80', label: 'Verde' },
    { color: '#60a5fa', label: 'Azul' },
    { color: '#f472b6', label: 'Rosa forte' },
    { color: '#a78bfa', label: 'Roxo' },
    { color: '#fb923c', label: 'Laranja forte' },
    // Cores extras
    { color: '#f87171', label: 'Vermelho' },
    { color: '#22d3d8', label: 'Ciano' },
    { color: 'transparent', label: 'Remover' }
  ]

  const picker = document.createElement('div')
  picker.className = PICKER_CLASS
  picker.style.cssText = `
    position: fixed;
    background: #111827;
    border: 1px solid #374151;
    border-radius: 10px;
    padding: 10px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.55);
    z-index: 99999;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 6px;
    width: 230px;
  `

  const rect = buttonEl.getBoundingClientRect()
  // tamanho aproximado do picker (5 colunas, 3 linhas)
  const pickerW = 230
  const pickerH = 10 + (3 * 38) + (2 * 6) + 10
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
// Configuração da toolbar com todos os botões
const toolbarOptions = [
  // Grupo: Cabeçalhos
  [{ 'header': [1, 2, 3, false] }],
  
  // Grupo: Formatação de texto
  ['bold', 'italic', 'underline', 'strike'],
  
  // Grupo: Cores
  [{ 'color': [] }, { 'background': [] }],
  
  // Grupo: Listas e indentação
  [{ 'list': 'ordered' }, { 'list': 'bullet' }],
  [{ 'indent': '-1' }, { 'indent': '+1' }],
  
  // Grupo: Alinhamento
  [{ 'align': [] }],
  
  // Grupo: Blocos especiais
  ['blockquote', 'code-block', 'link'],
  
  // Grupo: Subscrito/Sobrescrito
  [{ 'script': 'sub' }, { 'script': 'super' }],
  
  // Grupo: Limpar formatação
  ['clean']
]

onMounted(() => {
  quill = new Quill(editorRef.value, {
    theme: 'snow',
    placeholder: props.placeholder,
    modules: { 
      toolbar: toolbarOptions
    },
    formats: [
      'header', 'bold', 'italic', 'underline', 'strike',
      'list', 'indent', 'align',
      'background', 'color',
      'blockquote', 'code-block', 'code',
      'link', 'script'
    ]
  })

  // Adiciona botão customizado de marca-texto na toolbar
  const toolbar = quill.getModule('toolbar')
  if (toolbar?.container) {
    // Cria um grupo separado para o botão de marca-texto
    const highlightGroup = document.createElement('span')
    highlightGroup.className = 'ql-formats ql-highlight-group'

    const highlightBtn = document.createElement('button')
    highlightBtn.type = 'button'
    highlightBtn.className = 'ql-highlight-custom'
    highlightBtn.title = 'Marca-texto'
    highlightBtn.innerHTML = '<i class="pi pi-pencil" style="font-size: 14px;"></i>'

    highlightBtn.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      showBackgroundPicker(highlightBtn)
    })

    highlightGroup.appendChild(highlightBtn)

    // Insere após o grupo de cores existente
    const colorsGroup = toolbar.container.querySelector('.ql-color')?.closest('.ql-formats')
    if (colorsGroup) {
      colorsGroup.after(highlightGroup)
    } else {
      toolbar.container.appendChild(highlightGroup)
    }
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

    // Update line count immediately for responsive UI
    updateLineCount()

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
  editorEl.addEventListener('scroll', syncLineNumbersScroll)

  normalizeHighlightTextColors()
  updateLineCount()
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
      editorEl.removeEventListener('scroll', syncLineNumbersScroll)
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
  focus: () => quill?.focus(),
  /**
   * Get all highlighted (background-colored) content from the editor
   * Merges consecutive highlights of the same color into single groups
   * @returns {object} { texts: string[], combined: string, count: number }
   */
  getHighlightedContent: () => {
    if (!quill) return { texts: [], combined: '', count: 0 }

    const delta = quill.getContents()
    if (!delta || !delta.ops) return { texts: [], combined: '', count: 0 }

    const highlightGroups = [] // Each group = one user selection
    let currentGroup = null
    let currentColor = null

    delta.ops.forEach((op) => {
      const ins = op.insert
      const bg = op.attributes?.background

      if (bg && typeof bg === 'string' && bg.startsWith('#') && typeof ins === 'string') {
        if (currentColor === bg && currentGroup !== null) {
          // Continue same highlight group
          currentGroup.parts.push(ins)
        } else {
          // Start new group (different color)
          if (currentGroup && currentGroup.parts.length > 0) {
            highlightGroups.push(currentGroup)
          }
          currentGroup = { color: bg, parts: [ins] }
          currentColor = bg
        }
      } else {
        // Check if just whitespace between same-color highlights
        const isWhitespaceOnly = typeof ins === 'string' && /^[\s\n]+$/.test(ins)
        if (isWhitespaceOnly && currentGroup) {
          currentGroup.parts.push(ins) // Include whitespace in group
        } else {
          // End current group (non-whitespace breaks chain)
          if (currentGroup && currentGroup.parts.length > 0) {
            highlightGroups.push(currentGroup)
          }
          currentGroup = null
          currentColor = null
        }
      }
    })

    // Don't forget last group
    if (currentGroup && currentGroup.parts.length > 0) {
      highlightGroups.push(currentGroup)
    }

    const texts = highlightGroups.map(g => g.parts.join('').trim()).filter(t => t)

    return {
      texts,
      combined: texts.join('\n\n'),
      count: texts.length
    }
  },
  /**
   * Check if the editor has any highlighted content
   * @returns {boolean}
   */
  hasHighlightedContent: () => {
    if (!quill) return false
    
    const delta = quill.getContents()
    if (!delta || !delta.ops) return false

    return delta.ops.some((op) => {
      const bg = op.attributes?.background
      return bg && typeof bg === 'string' && bg.startsWith('#')
    })
  }
})

</script>

<template>
  <div class="qe-wrap" :class="{ 'with-line-numbers': showLineNumbers }">
    <!-- O Quill cria a toolbar automaticamente baseado em toolbarOptions -->
    <div ref="editorRef" class="qe-editor"></div>
    <!-- Line numbers posicionados absolutamente ao lado do conteúdo -->
    <div
      v-if="showLineNumbers"
      ref="lineNumbersRef"
      class="qe-line-numbers"
    >
      <div v-for="n in lineCount" :key="n" class="qe-line-number">{{ n }}</div>
    </div>
  </div>
</template>

<style scoped>
.qe-wrap {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
}

.qe-editor {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Line numbers - posicionados absolutamente ao lado do conteúdo */
.qe-line-numbers {
  position: absolute;
  left: 0;
  top: 42px; /* Altura da toolbar */
  bottom: 0;
  width: 44px;
  padding-top: 12px;
  padding-right: 6px;
  background: var(--surface-ground, #1e293b);
  border-right: 1px solid rgba(148, 163, 184, 0.15);
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  border-left: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 0 0 0 14px;
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Consolas, monospace;
  font-size: 0.75em;
  color: var(--text-color-secondary, #64748b);
  user-select: none;
  overflow-y: hidden;
  overflow-x: hidden;
  z-index: 1;
}

.qe-line-number {
  line-height: 1.42;
  height: 1.42em;
  padding-right: 4px;
}

/* Quando line numbers estão ativos, adiciona padding ao container e placeholder */
.with-line-numbers :deep(.ql-container.ql-snow) {
  padding-left: 44px;
}

.with-line-numbers :deep(.ql-editor.ql-blank::before) {
  left: 59px; /* 44px (line numbers) + 15px (default left) */
}

/* Toolbar gerada automaticamente pelo Quill */
:deep(.ql-toolbar.ql-snow) {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.03);
  border-radius: 14px 14px 0 0;
  padding: 8px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* Grupos de botões com separador visual */
:deep(.ql-toolbar.ql-snow .ql-formats) {
  display: inline-flex;
  align-items: center;
  margin-right: 8px;
  padding-right: 8px;
  border-right: 1px solid rgba(148, 163, 184, 0.2);
}

:deep(.ql-toolbar.ql-snow .ql-formats:last-child) {
  border-right: none;
  margin-right: 0;
  padding-right: 0;
}

/* Estilo dos botões na toolbar */
:deep(.ql-toolbar.ql-snow button) {
  width: 28px;
  height: 28px;
  padding: 4px;
  border-radius: 6px;
  transition: background-color 0.15s, transform 0.1s;
}

:deep(.ql-toolbar.ql-snow button:hover) {
  background-color: rgba(148, 163, 184, 0.15);
  transform: scale(1.05);
}

:deep(.ql-toolbar.ql-snow button.ql-active) {
  background-color: rgba(59, 130, 246, 0.25);
}

/* Botão customizado de marca-texto */
:deep(.ql-toolbar.ql-snow .ql-highlight-custom) {
  width: 28px;
  height: 28px;
  padding: 4px;
  border: none;
  border-radius: 6px;
  background: linear-gradient(135deg, #fef08a 0%, #fcd34d 100%);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.1s, box-shadow 0.15s;
}

:deep(.ql-toolbar.ql-snow .ql-highlight-custom:hover) {
  transform: scale(1.08);
  box-shadow: 0 2px 8px rgba(252, 211, 77, 0.4);
}

:deep(.ql-toolbar.ql-snow .ql-highlight-custom i) {
  color: #78350f;
}

:deep(.ql-toolbar.ql-snow .ql-highlight-group) {
  border-right: 1px solid rgba(148, 163, 184, 0.2);
}

/* Estilo dos selects na toolbar */
:deep(.ql-toolbar.ql-snow .ql-picker) {
  height: 28px;
}

:deep(.ql-toolbar.ql-snow .ql-picker-label) {
  border-radius: 6px;
  padding: 2px 8px;
  transition: background-color 0.15s;
}

:deep(.ql-toolbar.ql-snow .ql-picker-label:hover) {
  background-color: rgba(148, 163, 184, 0.15);
}

/* Dropdown de cores */
:deep(.ql-toolbar.ql-snow .ql-picker.ql-color .ql-picker-options),
:deep(.ql-toolbar.ql-snow .ql-picker.ql-background .ql-picker-options) {
  background: #1f2937;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

:deep(.ql-toolbar.ql-snow .ql-picker.ql-color .ql-picker-item),
:deep(.ql-toolbar.ql-snow .ql-picker.ql-background .ql-picker-item) {
  border-radius: 4px;
  transition: transform 0.1s;
}

:deep(.ql-toolbar.ql-snow .ql-picker.ql-color .ql-picker-item:hover),
:deep(.ql-toolbar.ql-snow .ql-picker.ql-background .ql-picker-item:hover) {
  transform: scale(1.15);
}

/* Dropdown de alinhamento e header */
:deep(.ql-toolbar.ql-snow .ql-picker-options) {
  background: #1f2937;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 8px;
  padding: 4px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

:deep(.ql-toolbar.ql-snow .ql-picker-item) {
  color: #e5e7eb;
  padding: 4px 8px;
  border-radius: 4px;
}

:deep(.ql-toolbar.ql-snow .ql-picker-item:hover) {
  background-color: rgba(59, 130, 246, 0.2);
}

/* Ícones SVG no tema escuro */
:deep(.ql-toolbar.ql-snow .ql-stroke) {
  stroke: #9ca3af;
}

:deep(.ql-toolbar.ql-snow .ql-fill) {
  fill: #9ca3af;
}

:deep(.ql-toolbar.ql-snow button:hover .ql-stroke),
:deep(.ql-toolbar.ql-snow button.ql-active .ql-stroke) {
  stroke: #3b82f6;
}

:deep(.ql-toolbar.ql-snow button:hover .ql-fill),
:deep(.ql-toolbar.ql-snow button.ql-active .ql-fill) {
  fill: #3b82f6;
}

:deep(.ql-toolbar.ql-snow .ql-picker-label .ql-stroke) {
  stroke: #9ca3af;
}

/* Container do editor com borda arredondada */
:deep(.ql-container.ql-snow) {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-top: none;
  border-radius: 0 0 14px 14px;
}

/* melhora o look do editor em dark UI */
:deep(.ql-editor) {
  color: var(--text-color, #e5e7eb);
}
/* Estilos para blockquote (citação) */
:deep(.ql-editor blockquote) {
  border-left: 4px solid #3b82f6;
  background-color: rgba(59, 130, 246, 0.1);
  margin: 12px 0;
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  color: #cbd5e1;
  font-style: italic;
}

/* Estilos para code-block */
:deep(.ql-editor pre.ql-syntax) {
  background-color: #0d1117;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
  font-size: 0.9em;
  color: #e6edf3;
  overflow-x: auto;
}

/* Estilos para código inline */
:deep(.ql-editor code) {
  background-color: rgba(110, 118, 129, 0.3);
  border-radius: 4px;
  padding: 2px 6px;
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
  font-size: 0.9em;
  color: #f0abfc;
}

/* Estilos para links */
:deep(.ql-editor a) {
  color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 2px;
  transition: color 0.15s;
}

:deep(.ql-editor a:hover) {
  color: #93c5fd;
}

/* Estilos para subscrito e sobrescrito */
:deep(.ql-editor sub) {
  font-size: 0.75em;
  vertical-align: sub;
}

:deep(.ql-editor sup) {
  font-size: 0.75em;
  vertical-align: super;
}

/* Estilos para listas ordenadas e com marcadores */
:deep(.ql-editor ol),
:deep(.ql-editor ul) {
  padding-left: 1.5em;
  margin: 8px 0;
}

:deep(.ql-editor li) {
  margin: 4px 0;
}

/* Estilos para indentação */
:deep(.ql-editor .ql-indent-1) { padding-left: 2em; }
:deep(.ql-editor .ql-indent-2) { padding-left: 4em; }
:deep(.ql-editor .ql-indent-3) { padding-left: 6em; }
:deep(.ql-editor .ql-indent-4) { padding-left: 8em; }
:deep(.ql-editor .ql-indent-5) { padding-left: 10em; }

/* Estilos para alinhamento */
:deep(.ql-editor .ql-align-center) { text-align: center; }
:deep(.ql-editor .ql-align-right) { text-align: right; }
:deep(.ql-editor .ql-align-justify) { text-align: justify; }
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
