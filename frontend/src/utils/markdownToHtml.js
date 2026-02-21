import { marked } from 'marked'
import DOMPurify from 'dompurify'

/**
 * Converte URLs em texto plano (dentro de HTML) para links clicáveis.
 * Trata URLs com angle brackets (&lt;URL&gt;) e URLs soltas.
 */
export function autolinkUrls(html) {
  if (!html) return html

  // Trata URLs com angle brackets: &lt; URL &gt; ou &lt; URL (sem fechar)
  html = html.replace(
    /&lt;\s*(https?:\/\/[^\s<>&]+(?:[^\s<>&])*?)\s*(?:&gt;|[.\s]|$)/gi,
    (match, url) => {
      const clean = url.trim().replace(/\s+/g, '')
      // Preserva pontuação final que não faz parte do &gt;
      const suffix = match.endsWith('&gt;') ? '' : match.slice(match.lastIndexOf(url) + url.length).replace(/&gt;/g, '')
      return `<a href="${clean}">${clean}</a>${suffix}`
    }
  )

  // Linkifica URLs soltas que não estão dentro de href="" ou <a>
  html = html.replace(
    /(?<!["'>=/])https?:\/\/[^\s<>"']+/g,
    (match) => {
      const url = match.replace(/[.,;:!?)"'>]+$/, '')
      const trailing = match.slice(url.length)
      return `<a href="${url}">${url}</a>${trailing}`
    }
  )

  return html
}

/**
 * Detecta se o texto contém sintaxe Markdown.
 * Requer 2+ padrões para evitar falsos positivos em texto comum.
 */
export function looksLikeMarkdown(text) {
  if (!text || text.length < 20) return false
  const patterns = [
    /#{1,6}\s+\S/,               // headers (inclusive inline)
    /\*\*[^*]+\*\*/,             // bold
    /^\s*[-*+]\s+\S/m,           // unordered list (com conteúdo após)
    /^\s*\d+\.\s+/m,             // ordered list
    /^```/m,                      // code fence
    /^>\s+/m,                     // blockquote
    /\[[^\]]+\]\([^)]+\)/,       // links
  ]
  let matches = 0
  for (const p of patterns) {
    if (p.test(text)) matches++
    if (matches >= 2) return true
  }
  return false
}

/**
 * Converte Markdown para HTML sanitizado, compatível com Quill editor.
 * Normaliza headers inline e tabelas antes de converter.
 */
export function markdownToHtml(text) {
  if (!text) return ''

  // Normaliza headers inline: "texto ## Header" → "texto\n\n## Header"
  let normalized = text.replace(/([^\n])(#{1,6}\s)/g, '$1\n\n$2')

  // Normaliza listas inline: "texto. - item" → "texto.\n\n- item"
  normalized = normalized.replace(/([.!?:;]) +([-*+\u221e]) +/g, '$1\n\n$2 ')

  // Separa sentencas coladas: "palavra. Maiuscula" → "palavra.\n\nMaiuscula"
  // Exige 5+ letras minusculas antes do ponto (evita "Dr.", "Fig.", etc.)
  normalized = normalized.replace(/([a-záàâãéèêíóôõúç]{5,}[.!?]) +([A-ZÀ-Ú])/g, '$1\n\n$2')

  // Remove excesso de quebras
  normalized = normalized.replace(/\n{4,}/g, '\n\n\n')

  let html = marked.parse(normalized, {
    gfm: true,
    breaks: true,
    async: false,
  })

  // Corrige URLs que foram classificadas como headings (h1-h6)
  html = html.replace(
    /<(h[1-6])[^>]*>([\s\S]*?)<\/\1>/gi,
    (match, tag, content) => {
      const plain = content.replace(/<[^>]+>/g, '').trim()
      const decoded = plain.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
      const core = decoded.replace(/^[<>\s.]+|[<>\s.]+$/g, '')
      if (/^https?:\/\//.test(core)) {
        const cleanUrl = core.replace(/\s+/g, '')
        return `<p><a href="${cleanUrl}">${cleanUrl}</a></p>`
      }
      return match
    }
  )

  // Auto-linkifica URLs em texto plano
  html = autolinkUrls(html)

  // Tabelas → code block (Quill não suporta tables)
  html = html.replace(/<table[\s\S]*?<\/table>/gi, (match) => {
    const temp = document.createElement('div')
    temp.innerHTML = match
    const rows = temp.querySelectorAll('tr')
    let result = ''
    rows.forEach((row, i) => {
      const cells = row.querySelectorAll('th, td')
      const vals = Array.from(cells).map(c => c.textContent.trim())
      result += vals.join('  |  ') + '\n'
      if (i === 0) result += vals.map(() => '--------').join('--+--') + '\n'
    })
    return '<pre><code>' + result + '</code></pre>'
  })

  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'del',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
      'a', 'hr', 'sub', 'sup', 'span'
    ],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
  })
}
