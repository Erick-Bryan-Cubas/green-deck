/**
 * Wrapper JS para funcoes Python (Brython).
 *
 * A logica real esta em /public/py/markdown_processor.py.
 * Este arquivo apenas delega para as funcoes Python expostas em window.
 * Se o Brython ainda nao carregou, retorna fallbacks seguros.
 */

export function autolinkUrls(html) {
  if (window.py_autolink_urls) return window.py_autolink_urls(html)
  return html
}

export function looksLikeMarkdown(text) {
  if (window.py_looks_like_markdown) return window.py_looks_like_markdown(text)
  return false
}

export function markdownToHtml(text) {
  if (window.py_markdown_to_html) return window.py_markdown_to_html(text)
  return text
}
