<script setup>

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Quill from 'quill'
import 'quill/dist/quill.snow.css'
import '../utils/quillHighlightFormat.js'
import { looksLikeMarkdown, markdownToHtml, autolinkUrls } from '../utils/markdownToHtml'

// ------------------------------------------------------------
// Temas de fundo do editor
// ------------------------------------------------------------
const EDITOR_THEMES = [
  { value: 'default',          label: 'Padrão',            bg: null,      fg: null,      ph: null },
  { value: 'kindle',           label: 'Branco',            bg: '#ffffff', fg: '#111827', ph: 'rgba(17,24,39,0.45)' },
  { value: 'sepia',            label: 'Sépia',             bg: '#f4ecd8', fg: '#5c4b37', ph: 'rgba(92,75,55,0.5)' },
  { value: 'dark',             label: 'Escuro',            bg: '#0f172a', fg: '#e2e8f0', ph: 'rgba(226,232,240,0.45)' },
  { value: 'dracula',          label: 'Dracula',           bg: '#282A36', fg: '#F8F8F2', ph: 'rgba(248,248,242,0.45)' },
  { value: 'nord',             label: 'Nord',              bg: '#2e3440', fg: '#d8dee9', ph: 'rgba(216,222,233,0.45)' },
  { value: 'solarized-dark',   label: 'Solarized Escuro',  bg: '#002b36', fg: '#839496', ph: 'rgba(131,148,150,0.5)' },
  { value: 'solarized-light',  label: 'Solarized Claro',   bg: '#fdf6e3', fg: '#657b83', ph: 'rgba(101,123,131,0.5)' },
  { value: 'gruvbox',          label: 'Gruvbox',           bg: '#282828', fg: '#ebdbb2', ph: 'rgba(235,219,178,0.45)' },
  { value: 'monokai',          label: 'Monokai',           bg: '#272822', fg: '#f8f8f2', ph: 'rgba(248,248,242,0.45)' },
]

const props = defineProps({
  placeholder: {
    type: String,
    default: 'Cole ou digite o texto aqui, selecione trechos e gere cartões...'
  },
  showLineNumbers: {
    type: Boolean,
    default: false
  },
  theme: {
    type: String,
    default: 'default'
  }
})

const emit = defineEmits([
  'selection-changed', // { selectedText, range, hasSelection, hasHighlight }
  'content-changed',   // { fullText, html }
  'editor-ready',      // quill instance
  'context-menu',      // { originalEvent, hasSelection, hasHighlight, selectedText, range }
  'theme-changed'      // themeValue (string)
])

const editorRef = ref(null)
const lineNumbersRef = ref(null)
const lineHeights = ref([])   // array de { height } para cada linha do editor
const editorTheme = ref(props.theme || 'default')

let quill = null
let textChangeTimeout = null
let resizeObserver = null

let savedRange = null

// ------------------------------------------------------------
// Line numbers — conta linhas VISUAIS (como VS Code).
// Divide a altura de conteúdo de cada bloco pelo line-height
// computado para saber quantas linhas cada bloco ocupa.
// ------------------------------------------------------------
function getLineHeightPx(el) {
  const computed = window.getComputedStyle(el)
  const lh = parseFloat(computed.lineHeight)
  if (!isNaN(lh) && lh > 0) return lh
  // Fallback: fontSize × 1.42 (padrão do Quill)
  const fontSize = parseFloat(computed.fontSize) || 13
  return fontSize * 1.42
}

function updateLineNumbers() {
  if (!quill || !quill.root) {
    lineHeights.value = [{ height: 0 }]
    return
  }

  const editor = quill.root
  const children = editor.children
  const entries = []

  for (let i = 0; i < children.length; i++) {
    const child = children[i]
    const lineHeightPx = getLineHeightPx(child)

    // Altura do conteúdo sem padding/border (importante para <pre>, <blockquote>)
    const rect = child.getBoundingClientRect()
    const style = window.getComputedStyle(child)
    const pt = parseFloat(style.paddingTop) || 0
    const pb = parseFloat(style.paddingBottom) || 0
    const bt = parseFloat(style.borderTopWidth) || 0
    const bb = parseFloat(style.borderBottomWidth) || 0
    const contentHeight = rect.height - pt - pb - bt - bb

    const visualLineCount = Math.max(1, Math.round(contentHeight / lineHeightPx))

    // Espaço extra entre blocos (margin collapse, etc.)
    let blockHeight
    if (i < children.length - 1) {
      blockHeight = children[i + 1].offsetTop - child.offsetTop
    } else {
      blockHeight = rect.height
    }
    const extraSpace = blockHeight - rect.height

    // Uma entrada por linha visual
    for (let line = 0; line < visualLineCount; line++) {
      let h = lineHeightPx
      if (line === 0) h += pt + bt
      if (line === visualLineCount - 1) h += pb + bb + extraSpace
      entries.push({ height: h })
    }
  }

  if (entries.length === 0) entries.push({ height: 0 })
  lineHeights.value = entries
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
  return !!fmt.highlight
}

function hasValidSavedRange() {
  return !!(savedRange && typeof savedRange.index === 'number' && savedRange.length > 0)
}

function applyFormatsToSavedRange(formats) {
  if (!quill) return
  if (!hasValidSavedRange()) return

  quill.setSelection(savedRange)
  quill.format('highlight', formats.highlight ?? false)
}

function formatBackground(bg) {
  if (!quill) return
  if (!hasValidSavedRange()) return

  if (!bg || bg === 'transparent') {
    applyFormatsToSavedRange({ highlight: false })
    return
  }

  applyFormatsToSavedRange({ highlight: bg })
}

function clearHighlight() {
  if (!quill) return
  if (!hasValidSavedRange()) return
  applyFormatsToSavedRange({ highlight: false })
}

function clearSelection() {
  if (!quill) return
  quill.setSelection(null)
}

// ------------------------------------------------------------
// Migra highlights antigos (background → highlight)
// ------------------------------------------------------------
function migrateOldHighlights() {
  if (!quill) return

  const delta = quill.getContents()
  let idx = 0

  delta.ops.forEach((op) => {
    const ins = op.insert
    const len = typeof ins === 'string' ? ins.length : 1
    const bg = op.attributes?.background

    if (bg && typeof bg === 'string' && bg.startsWith('#')) {
      quill.formatText(idx, len, { background: false, color: false, highlight: bg }, 'api')
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
    background: var(--quill-picker-bg, #1e293b);
    border: 1px solid var(--quill-picker-border, rgba(148, 163, 184, 0.18));
    border-radius: 12px;
    padding: 10px;
    box-shadow: var(--quill-picker-shadow, 0 10px 30px rgba(0, 0, 0, 0.45));
    z-index: 99999;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 6px;
    width: 210px;
  `

  const rect = buttonEl.getBoundingClientRect()
  // tamanho aproximado do picker (5 colunas, 3 linhas)
  const pickerW = 210
  const pickerH = 10 + (3 * 34) + (2 * 6) + 10
  const pos = clampPosition(rect.left, rect.bottom + 8, pickerW, pickerH)

  picker.style.left = `${pos.x}px`
  picker.style.top = `${pos.y}px`

  colors.forEach(({ color, label }) => {
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.title = label

    const isRemove = color === 'transparent'
    const txtColor = isRemove ? '#e5e7eb' : textColorForBackground(color)
    btn.style.cssText = `
      width: 100%;
      aspect-ratio: 1;
      border-radius: 8px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      background-color: ${isRemove ? 'transparent' : color};
      cursor: pointer;
      transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
      position: relative;
      overflow: hidden;
      ${isRemove
        ? 'background-image: linear-gradient(45deg, rgba(148,163,184,0.15) 25%, transparent 25%, transparent 75%, rgba(148,163,184,0.15) 75%), linear-gradient(45deg, rgba(148,163,184,0.15) 25%, transparent 25%, transparent 75%, rgba(148,163,184,0.15) 75%); background-size: 8px 8px; background-position: 0 0, 4px 4px;'
        : ''
      }
    `

    // mini “A” pra mostrar contraste (ajuda UX)
    const iconContent = isRemove
      ? '<svg width=”14” height=”14” viewBox=”0 0 14 14” fill=”none” stroke=”rgba(248,113,113,0.8)” stroke-width=”2” stroke-linecap=”round”><line x1=”2” y1=”2” x2=”12” y2=”12”/><line x1=”12” y1=”2” x2=”2” y2=”12”/></svg>'
      : `<span style=”font-weight:800;font-size:11px;color:${txtColor};text-shadow:${txtColor === '#ffffff' ? '0 1px 2px rgba(0,0,0,0.5)' : 'none'};”>A</span>`
    btn.innerHTML = `<span style=”position:absolute;inset:0;display:grid;place-items:center;”>${iconContent}</span>`

    btn.addEventListener('mousedown', (e) => {
      e.preventDefault()
      e.stopPropagation()
    })

    btn.addEventListener('mouseenter', () => {
      btn.style.transform = 'scale(1.12)'
      btn.style.borderColor = 'rgba(255, 255, 255, 0.5)'
      btn.style.boxShadow = `0 2px 8px ${isRemove ? 'rgba(248,113,113,0.3)' : color + '66'}`
    })
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = 'scale(1)'
      btn.style.borderColor = 'rgba(148, 163, 184, 0.15)'
      btn.style.boxShadow = 'none'
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
// Theme picker (cor de fundo do editor)
// ------------------------------------------------------------
const THEME_PICKER_CLASS = 'custom-theme-picker'
let themePickerCleanupFns = []

function removeThemePicker() {
  const existing = document.querySelector(`.${THEME_PICKER_CLASS}`)
  if (existing) existing.remove()
  themePickerCleanupFns.forEach((fn) => {
    try { fn() } catch {}
  })
  themePickerCleanupFns = []
}

function applyEditorTheme(themeValue) {
  editorTheme.value = themeValue
  if (!quill) return

  const container = editorRef.value  // editorRef.value É o .ql-container (Quill transforma o div)
  const editor = quill?.root         // quill.root é o .ql-editor
  const toolbar = container?.previousElementSibling // .ql-toolbar é irmão anterior
  if (!container || !editor) return

  const theme = EDITOR_THEMES.find((t) => t.value === themeValue)

  const lineNrEl = lineNumbersRef.value

  if (!theme || !theme.bg) {
    // "Padrão" — remove overrides
    container.style.removeProperty('background-color')
    editor.style.removeProperty('color')
    editor.style.removeProperty('--editor-theme-placeholder')
    if (toolbar) {
      toolbar.style.removeProperty('background-color')
      toolbar.style.removeProperty('color')
    }
    if (lineNrEl) {
      lineNrEl.style.removeProperty('--editor-theme-linenr-bg')
      lineNrEl.style.removeProperty('--editor-theme-linenr-text')
      lineNrEl.style.removeProperty('--editor-theme-linenr-border')
    }
  } else {
    container.style.setProperty('background-color', theme.bg)
    editor.style.setProperty('color', theme.fg)
    if (theme.ph) {
      editor.style.setProperty('--editor-theme-placeholder', theme.ph)
    }
    if (toolbar) {
      toolbar.style.setProperty('background-color', theme.bg)
      toolbar.style.setProperty('color', theme.fg)
    }
    // Line numbers gutter — derivar cores do tema
    if (lineNrEl) {
      lineNrEl.style.setProperty('--editor-theme-linenr-bg', `color-mix(in srgb, ${theme.bg} 92%, ${theme.fg})`)
      lineNrEl.style.setProperty('--editor-theme-linenr-text', `color-mix(in srgb, ${theme.fg} 40%, transparent)`)
      lineNrEl.style.setProperty('--editor-theme-linenr-border', `color-mix(in srgb, ${theme.fg} 10%, transparent)`)
    }
  }

  emit('theme-changed', themeValue)
}

function showThemePicker(buttonEl) {
  const existing = document.querySelector(`.${THEME_PICKER_CLASS}`)
  if (existing) {
    removeThemePicker()
    return
  }

  // Fechar color picker se aberto
  removePicker()

  const picker = document.createElement('div')
  picker.className = THEME_PICKER_CLASS
  picker.style.cssText = `
    position: fixed;
    background: var(--quill-picker-bg, #111827);
    border: 1px solid var(--quill-picker-border, #374151);
    border-radius: 12px;
    padding: 10px;
    box-shadow: var(--quill-picker-shadow, 0 10px 30px rgba(0, 0, 0, 0.55));
    z-index: 99999;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    width: 300px;
  `

  const rect = buttonEl.getBoundingClientRect()
  const pickerW = 300
  const pickerH = 10 + (4 * 72) + (3 * 8) + 10
  const pos = clampPosition(rect.left, rect.bottom + 8, pickerW, pickerH)
  picker.style.left = `${pos.x}px`
  picker.style.top = `${pos.y}px`

  EDITOR_THEMES.forEach((theme) => {
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.title = theme.label

    const isActive = editorTheme.value === theme.value
    const swatchBg = theme.bg || 'var(--p-content-background, #1e293b)'
    const swatchFg = theme.fg || 'var(--text-color, #e5e7eb)'

    btn.style.cssText = `
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 6px;
      border-radius: 8px;
      border: 2px solid ${isActive ? '#6366f1' : '#374151'};
      background: transparent;
      cursor: pointer;
      transition: transform 0.12s ease, border-color 0.12s ease;
      ${isActive ? 'box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.35);' : ''}
    `

    const swatch = document.createElement('div')
    swatch.style.cssText = `
      width: 100%;
      height: 36px;
      border-radius: 6px;
      background-color: ${swatchBg};
      display: grid;
      place-items: center;
      font-weight: 700;
      font-size: 14px;
      color: ${swatchFg};
      border: 1px solid rgba(148, 163, 184, 0.15);
    `
    swatch.textContent = 'Aa'

    const label = document.createElement('span')
    label.style.cssText = `
      font-size: 10px;
      color: rgba(229, 231, 235, 0.7);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 80px;
    `
    label.textContent = theme.label

    btn.appendChild(swatch)
    btn.appendChild(label)

    btn.addEventListener('mousedown', (e) => {
      e.preventDefault()
      e.stopPropagation()
    })

    btn.addEventListener('mouseenter', () => {
      btn.style.transform = 'scale(1.04)'
      btn.style.borderColor = '#6366f1'
    })
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = 'scale(1)'
      btn.style.borderColor = isActive ? '#6366f1' : '#374151'
    })

    btn.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      applyEditorTheme(theme.value)
      removeThemePicker()
    })

    picker.appendChild(btn)
  })

  document.body.appendChild(picker)

  const onDocClick = (e) => {
    if (!picker.contains(e.target) && e.target !== buttonEl) removeThemePicker()
  }
  document.addEventListener('click', onDocClick)
  themePickerCleanupFns.push(() => document.removeEventListener('click', onDocClick))

  const onScroll = () => removeThemePicker()
  const onResize = () => removeThemePicker()
  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onResize)
  themePickerCleanupFns.push(() => window.removeEventListener('scroll', onScroll, true))
  themePickerCleanupFns.push(() => window.removeEventListener('resize', onResize))
}

// Watch para sincronizar com prop theme (ex: Zen Mode troca tema)
watch(() => props.theme, (newTheme) => {
  if (newTheme !== editorTheme.value) {
    applyEditorTheme(newTheme)
  }
})

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
      'background', 'color', 'highlight',
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

    // Cria botão de seletor de tema de fundo
    const themeGroup = document.createElement('span')
    themeGroup.className = 'ql-formats ql-theme-group'

    const themeBtn = document.createElement('button')
    themeBtn.type = 'button'
    themeBtn.className = 'ql-theme-picker'
    themeBtn.title = 'Tema do editor'
    themeBtn.innerHTML = '<i class="pi pi-palette" style="font-size: 14px;"></i>'

    themeBtn.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      showThemePicker(themeBtn)
    })

    themeGroup.appendChild(themeBtn)

    // Insere após o grupo do marca-texto
    const hlGroup = toolbar.container.querySelector('.ql-highlight-group')
    if (hlGroup) {
      hlGroup.after(themeGroup)
    } else {
      toolbar.container.appendChild(themeGroup)
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
    updateLineNumbers()

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

  migrateOldHighlights()
  updateLineNumbers()

  // ResizeObserver: atualiza números de linha quando o editor muda de largura
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateLineNumbers()
    })
    resizeObserver.observe(quill.root)
  }

  // Aplica tema inicial se definido via prop
  if (props.theme && props.theme !== 'default') {
    applyEditorTheme(props.theme)
  }

  emit('editor-ready', quill)
})

onBeforeUnmount(() => {
  removePicker()
  removeThemePicker()
  if (textChangeTimeout) clearTimeout(textChangeTimeout)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }

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
  setTheme: (value) => applyEditorTheme(value),
  getTheme: () => editorTheme.value,
  getFullText: () => (quill ? quill.getText().trim() : ''),
  // Retorna o texto exato do editor sem trim (para posicionamento preciso)
  getRawText: () => {
    if (!quill) return ''
    // Quill adiciona um \n no final, removemos apenas esse
    const text = quill.getText()
    return text.endsWith('\n') ? text.slice(0, -1) : text
  },
  getSelectedText: () => (hasValidSavedRange() ? getSelectedText(savedRange) : ''),
  getDelta: () => (quill ? quill.getContents() : null),
  setDelta: (delta) => {
    if (!quill) return
    if (!delta) {
      quill.setText('')
      return
    }
    quill.setContents(delta, 'api')
    migrateOldHighlights()
  },
  setContent: (text) => {
    if (!quill) return
    if (!text) {
      quill.setText('')
      return
    }

    if (typeof text === 'string') {
      // Remove marcadores de PAGE_BREAK do backend e substitui por separador visual
      let processedText = text.replace(/<!-- PAGE_BREAK -->/g, '<hr>')

      // Se o texto contém tags HTML reais (não apenas comentários), usa dangerouslyPasteHTML
      const hasRealHtmlTags = /<(?!--)[a-z][\s\S]*?>/i.test(processedText)

      if (hasRealHtmlTags) {
        // Escapa '<' soltos que não são tags HTML reais (ex: "< https://...")
        // Sem isso, dangerouslyPasteHTML interpreta como tag inválida e engole o conteúdo
        processedText = processedText.replace(/<(?![/a-zA-Z!])/g, '&lt;')

        // Corrige URLs classificadas como headings pelo Docling
        processedText = processedText.replace(
          /<(h[1-6])[^>]*>([\s\S]*?)<\/\1>/gi,
          (match, tag, content) => {
            const plain = content.replace(/<[^>]+>/g, '').trim()
            const decoded = plain.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ')
            const core = decoded.replace(/^[<>\s.]+|[<>\s.]+$/g, '')
            if (/^https?:\/\//.test(core)) {
              const cleanUrl = core.replace(/\s+/g, '')
              return `<p><a href="${cleanUrl}">${cleanUrl}</a></p>`
            }
            return match
          }
        )
        // Auto-linkifica URLs em texto plano
        processedText = autolinkUrls(processedText)
        quill.clipboard.dangerouslyPasteHTML(processedText, 'api')
      } else if (looksLikeMarkdown(processedText)) {
        // Markdown (ex: texto do Docling) — converter para HTML rico
        const htmlContent = markdownToHtml(processedText)
        quill.clipboard.dangerouslyPasteHTML(htmlContent, 'api')
      } else {
        // Texto plano — converte quebras de linha para parágrafos HTML
        const htmlContent = processedText
          .split('\n')
          .map(line => line.trim() === '' ? '<p><br></p>' : `<p>${line}</p>`)
          .join('')
        quill.clipboard.dangerouslyPasteHTML(htmlContent, 'api')
      }
    } else {
      quill.setText(String(text), 'api')
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
      const bg = op.attributes?.highlight

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
      const hl = op.attributes?.highlight
      return hl && typeof hl === 'string' && hl.startsWith('#')
    })
  },

  /**
   * Apply topic-based highlights to specific text ranges
   * @param {Array} segments - Array of {start, end, color} objects
   */
  applyTopicHighlights: (segments) => {
    console.log('[QuillEditor] applyTopicHighlights called with:', segments?.length, 'segments')
    if (!quill) {
      console.warn('[QuillEditor] applyTopicHighlights - quill not initialized')
      return
    }
    if (!Array.isArray(segments)) {
      console.warn('[QuillEditor] applyTopicHighlights - segments is not an array')
      return
    }

    // Quill adiciona \n implícito no final, então o comprimento real do texto é getLength() - 1
    const quillLength = quill.getLength()
    const textLength = quillLength - 1
    console.log('[QuillEditor] Quill length:', quillLength, '| Real text length:', textLength)

    // Sort segments from end to start to preserve positions
    const sorted = [...segments].sort((a, b) => b.start - a.start)

    let appliedCount = 0
    for (const seg of sorted) {
      const start = seg.start
      // Limitar end ao tamanho real do texto
      const end = Math.min(seg.end, textLength)
      const length = end - start
      const color = seg.color || '#e5e7eb'

      console.log('[QuillEditor] Processing segment:', { start, end, length, color, textLength })

      if (length > 0 && start >= 0 && end <= textLength) {
        try {
          quill.formatText(start, length, {
            highlight: color
          })
          appliedCount++
          console.log('[QuillEditor] Format applied:', { start, length, color })
        } catch (e) {
          console.error('[QuillEditor] Error applying format:', e)
        }
      } else {
        console.warn('[QuillEditor] Skipping segment - out of bounds:', { start, end, length, textLength })
      }
    }
    console.log('[QuillEditor] applyTopicHighlights completed:', appliedCount, 'of', segments.length, 'applied')
  },

  /**
   * Clear all topic highlights from the editor
   * Removes background and color formatting from entire document
   */
  clearTopicHighlights: () => {
    if (!quill) return
    const length = quill.getLength()
    quill.formatText(0, length, { highlight: false, background: false, color: false })
  },

  /**
   * Scroll to a specific position in the editor and select it
   * @param {number} start - Start character index
   * @param {number} length - Length of selection
   */
  scrollToPosition: (start, length) => {
    if (!quill) return

    // Set selection to highlight the text
    quill.setSelection(start, length)

    // Get bounds and scroll to make visible
    const bounds = quill.getBounds(start, length)
    if (bounds) {
      const container = editorRef.value?.querySelector('.ql-container')
      if (container) {
        // Scroll to center the selection vertically
        const targetScroll = bounds.top - (container.clientHeight / 3)
        container.scrollTo({
          top: Math.max(0, targetScroll),
          behavior: 'smooth'
        })
      }
    }
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
      <div
        v-for="(line, idx) in lineHeights"
        :key="idx"
        class="qe-line-number"
        :style="line.height ? { height: line.height + 'px' } : {}"
      >{{ idx + 1 }}</div>
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
  background: var(--editor-theme-linenr-bg, rgba(255, 255, 255, 0.04));
  border-right: 1px solid var(--editor-theme-linenr-border, rgba(148, 163, 184, 0.10));
  border-bottom: none;
  border-left: none;
  border-radius: 0 0 0 14px;
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Consolas, monospace;
  font-size: 0.75em;
  color: var(--editor-theme-linenr-text, rgba(148, 163, 184, 0.40));
  user-select: none;
  overflow-y: hidden;
  overflow-x: hidden;
  z-index: 1;
  transition: background 0.25s ease, color 0.25s ease, border-color 0.25s ease;
}

.qe-line-number {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding-right: 4px;
  box-sizing: border-box;
  overflow: hidden;
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
  background: var(--quill-toolbar-bg, rgba(255, 255, 255, 0.03));
  backdrop-filter: blur(8px);
  border-radius: 14px 14px 0 0;
  padding: 8px 12px;
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
  box-shadow: inset 0 -1px 0 rgba(148, 163, 184, 0.08);
}

:deep(.ql-toolbar.ql-snow::-webkit-scrollbar) {
  height: 3px;
}
:deep(.ql-toolbar.ql-snow::-webkit-scrollbar-thumb) {
  background: rgba(148, 163, 184, 0.3);
  border-radius: 3px;
}
:deep(.ql-toolbar.ql-snow::-webkit-scrollbar-track) {
  background: transparent;
}

/* Grupos de botões com separador gradiente */
:deep(.ql-toolbar.ql-snow .ql-formats) {
  display: inline-flex;
  align-items: center;
  margin-right: 8px;
  padding-right: 8px;
  border-right: none;
  background-image: linear-gradient(to bottom, transparent 15%, var(--quill-toolbar-sep) 50%, transparent 85%);
  background-size: 1px 100%;
  background-repeat: no-repeat;
  background-position: right center;
  flex-shrink: 0;
}

:deep(.ql-toolbar.ql-snow .ql-formats:last-child) {
  background-image: none;
  margin-right: 0;
  padding-right: 0;
}

/* Estilo dos botões na toolbar */
:deep(.ql-toolbar.ql-snow button) {
  width: 28px;
  height: 28px;
  padding: 4px;
  border-radius: 6px;
  transition: background-color 0.15s, transform 0.1s, box-shadow 0.15s;
}

:deep(.ql-toolbar.ql-snow button:hover) {
  background-color: var(--quill-toolbar-hover);
  transform: scale(1.05);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15);
}

:deep(.ql-toolbar.ql-snow button.ql-active) {
  background-color: var(--quill-accent-soft);
  box-shadow: 0 0 0 1.5px var(--quill-accent), inset 0 0 0 1px rgba(255, 255, 255, 0.08);
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
  box-shadow: 0 2px 8px color-mix(in srgb, var(--color-warning) 40%, transparent);
}

:deep(.ql-toolbar.ql-snow .ql-highlight-custom i) {
  color: var(--quill-inlinecode-text);
}

:deep(.ql-toolbar.ql-snow .ql-highlight-group) {
  border-right: 1px solid var(--quill-toolbar-sep);
}

/* Botão de seletor de tema */
:deep(.ql-toolbar.ql-snow .ql-theme-picker) {
  width: 28px;
  height: 28px;
  padding: 4px;
  border: none;
  border-radius: 6px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.1s, box-shadow 0.15s;
}

:deep(.ql-toolbar.ql-snow .ql-theme-picker:hover) {
  transform: scale(1.08);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4);
}

:deep(.ql-toolbar.ql-snow .ql-theme-picker i) {
  color: #ffffff;
}

:deep(.ql-toolbar.ql-snow .ql-theme-group) {
  border-right: 1px solid var(--quill-toolbar-sep);
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
  background-color: var(--quill-toolbar-hover);
}

/* Dropdown de cores */
:deep(.ql-toolbar.ql-snow .ql-picker.ql-color .ql-picker-options),
:deep(.ql-toolbar.ql-snow .ql-picker.ql-background .ql-picker-options) {
  background: var(--quill-dropdown-bg);
  border: 1px solid var(--quill-dropdown-border);
  border-radius: 8px;
  padding: 8px;
  box-shadow: var(--gen-modal-shadow);
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
  background: var(--quill-dropdown-bg);
  border: 1px solid var(--quill-dropdown-border);
  border-radius: 8px;
  padding: 4px;
  box-shadow: var(--gen-modal-shadow);
}

:deep(.ql-toolbar.ql-snow .ql-picker-item) {
  color: var(--quill-dropdown-text);
  padding: 4px 8px;
  border-radius: 4px;
}

:deep(.ql-toolbar.ql-snow .ql-picker-item:hover) {
  background-color: var(--quill-dropdown-hover);
}

/* Ícones SVG no tema escuro */
:deep(.ql-toolbar.ql-snow .ql-stroke) {
  stroke: var(--quill-icon);
}

:deep(.ql-toolbar.ql-snow .ql-fill) {
  fill: var(--quill-icon);
}

:deep(.ql-toolbar.ql-snow button:hover .ql-stroke),
:deep(.ql-toolbar.ql-snow button.ql-active .ql-stroke) {
  stroke: var(--quill-accent);
}

:deep(.ql-toolbar.ql-snow button:hover .ql-fill),
:deep(.ql-toolbar.ql-snow button.ql-active .ql-fill) {
  fill: var(--quill-accent);
}

:deep(.ql-toolbar.ql-snow .ql-picker-label .ql-stroke) {
  stroke: var(--quill-icon);
}

/* Container do editor com borda arredondada */
:deep(.ql-container.ql-snow) {
  border: 1px solid var(--quill-container-border);
  border-top: none;
  border-radius: 0 0 14px 14px;
  transition: border-color 0.2s;
}

/* Scrollbar do conteúdo do editor */
:deep(.ql-editor::-webkit-scrollbar) {
  width: 6px;
}
:deep(.ql-editor::-webkit-scrollbar-thumb) {
  background: rgba(148, 163, 184, 0.25);
  border-radius: 3px;
}
:deep(.ql-editor::-webkit-scrollbar-thumb:hover) {
  background: rgba(148, 163, 184, 0.4);
}
:deep(.ql-editor::-webkit-scrollbar-track) {
  background: transparent;
}

/* Seleção de texto com cor accent */
:deep(.ql-editor ::selection) {
  background: var(--quill-accent-soft);
}

/* melhora o look do editor em dark UI */
:deep(.ql-editor) {
  color: var(--text-color, #e5e7eb);
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.25) transparent;
}
/* Estilos para blockquote (citação) */
:deep(.ql-editor blockquote) {
  border-left: 4px solid var(--quill-blockquote-border);
  background-color: var(--quill-blockquote-bg);
  margin: 12px 0;
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  color: var(--quill-blockquote-text);
  font-style: italic;
}

/* Estilos para code-block */
:deep(.ql-editor pre.ql-syntax) {
  background-color: var(--quill-codeblock-bg);
  border: 1px solid var(--quill-codeblock-border);
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
  font-size: 0.9em;
  color: var(--quill-codeblock-text);
  overflow-x: auto;
}

/* Estilos para código inline */
:deep(.ql-editor code) {
  background-color: var(--quill-inlinecode-bg);
  border-radius: 4px;
  padding: 2px 6px;
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
  font-size: 0.9em;
  color: var(--quill-inlinecode-text);
}

/* Estilos para links */
:deep(.ql-editor a) {
  color: var(--quill-link);
  text-decoration: underline;
  text-underline-offset: 2px;
  transition: color 0.15s;
}

:deep(.ql-editor a:hover) {
  color: var(--quill-link-hover);
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
/* Highlight format: semi-transparent background + dashed underline */
:deep(.ql-editor .ql-highlight) {
  background-color: color-mix(in srgb, var(--hl-color) 25%, transparent);
  border-bottom: 2px dashed var(--hl-color);
  border-radius: 2px;
  padding-bottom: 1px;
}

/* Placeholder do Quill — usa tema do editor se ativo, senão fallback para tema global */
:deep(.ql-editor.ql-blank::before) {
  color: var(--editor-theme-placeholder, var(--quill-placeholder)) !important;
  opacity: 1 !important;
}

/* Opcional: deixa o placeholder mais “suave” e consistente */
:deep(.ql-editor.ql-blank::before) {
  font-style: italic;
}

</style>
