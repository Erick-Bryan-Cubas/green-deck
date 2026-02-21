import Quill from 'quill'
import { StyleAttributor, Scope } from 'parchment'

/**
 * Custom Quill format: semi-transparent highlight with dashed underline.
 *
 * Instead of Quill's built-in `background` (which sets an opaque inline
 * `background-color`), this attributor writes a CSS custom property
 * `--hl-color` and adds the class `ql-highlight` to the span, giving
 * full CSS control over rendering (transparency, border, etc.).
 *
 * Delta key: `highlight` (e.g. `{ highlight: '#fef08a' }`)
 */
class HighlightAttributor extends StyleAttributor {
  add(node, value) {
    if (!value || value === 'transparent' || value === false) {
      this.remove(node)
      return true
    }
    node.style.setProperty('--hl-color', value)
    node.classList.add('ql-highlight')
    return true
  }

  remove(node) {
    node.style.removeProperty('--hl-color')
    node.classList.remove('ql-highlight')
  }

  value(node) {
    return node.style.getPropertyValue('--hl-color').trim() || ''
  }
}

const HighlightStyle = new HighlightAttributor('highlight', '--hl-color', {
  scope: Scope.INLINE
})

Quill.register(HighlightStyle, true)

export { HighlightStyle }
