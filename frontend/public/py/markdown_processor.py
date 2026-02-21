"""
Processador de Markdown para o Quill Editor.
Roda no browser via Brython — substitui markdownToHtml.js.

Usa as libs JS `marked` e `DOMPurify` expostas em window pelo main.js.
"""

from browser import window, document  # noqa: F401 — Brython built-ins
import re


# ---------------------------------------------------------------------------
# autolink_urls
# ---------------------------------------------------------------------------
def autolink_urls(html):
    """
    Converte URLs em texto plano (dentro de HTML) para links clicaveis.
    Trata URLs com angle brackets (&lt;URL&gt;) e URLs soltas.
    """
    if not html:
        return html

    # URLs com angle brackets: &lt; URL &gt; ou &lt; URL (sem fechar)
    def _fix_angle_bracket(m):
        url = m.group(1).strip()
        clean = re.sub(r'\s+', '', url)
        return f'<a href="{clean}">{clean}</a>'

    html = re.sub(
        r'&lt;\s*(https?://[^\s<>&]+(?:[^\s<>&])*?)\s*(?:&gt;|(?=[\s.<]))',
        _fix_angle_bracket,
        html,
    )

    # URLs soltas que nao estao dentro de href="" ou <a>
    def _linkify(m):
        raw = m.group(0)
        url = raw.rstrip('.,;:!?)"\'>')
        trailing = raw[len(url):]
        return f'<a href="{url}">{url}</a>{trailing}'

    html = re.sub(
        r'(?<!["\'>=/])https?://[^\s<>"\']+',
        _linkify,
        html,
    )

    return html


# ---------------------------------------------------------------------------
# looks_like_markdown
# ---------------------------------------------------------------------------
def looks_like_markdown(text):
    """
    Detecta se o texto contem sintaxe Markdown.
    Requer 2+ padroes para evitar falsos positivos em texto comum.
    """
    if not text or len(text) < 20:
        return False

    patterns = [
        r'#{1,6}\s+\S',                  # headers
        r'\*\*[^*]+\*\*',                # bold
        r'(?m)^\s*[-*+]\s+\S',           # unordered list
        r'(?m)^\s*\d+\.\s+',             # ordered list
        r'(?m)^```',                      # code fence
        r'(?m)^>\s+',                     # blockquote
        r'\[[^\]]+\]\([^)]+\)',           # links
    ]

    matches = 0
    for p in patterns:
        if re.search(p, text):
            matches += 1
            if matches >= 2:
                return True
    return False


# ---------------------------------------------------------------------------
# markdown_to_html
# ---------------------------------------------------------------------------
def markdown_to_html(text):
    """
    Converte Markdown para HTML sanitizado, compativel com Quill editor.
    Normaliza headers inline e tabelas antes de converter.
    """
    if not text:
        return ''

    marked = window.marked
    DOMPurify = window.DOMPurify

    # Normaliza headers inline: "texto ## Header" -> "texto\n\n## Header"
    normalized = re.sub(r'([^\n])(#{1,6}\s)', r'\1\n\n\2', text)

    # Normaliza listas inline: "texto. - item" -> "texto.\n\n- item"
    normalized = re.sub(r'([.!?:;]) +([-*+\u221e]) +', r'\1\n\n\2 ', normalized)

    # Separa sentencas coladas: "palavra. Maiuscula" -> "palavra.\n\nMaiuscula"
    # Exige 5+ letras minusculas antes do ponto (evita "Dr.", "Fig.", etc.)
    normalized = re.sub(
        r'([a-z\u00e1\u00e0\u00e2\u00e3\u00e9\u00e8\u00ea\u00ed\u00f3\u00f4'
        r'\u00f5\u00fa\u00e7]{5,}[.!?]) +([A-Z\u00c0-\u00da])',
        r'\1\n\n\2',
        normalized,
    )

    # Remove excesso de quebras
    normalized = re.sub(r'\n{4,}', '\n\n\n', normalized)

    # Converte Markdown para HTML usando marked.js
    html = marked.parse(normalized, {
        'gfm': True,
        'breaks': True,
        'async': False,
    })

    # Corrige URLs classificadas como headings (h1-h6)
    def _fix_url_heading(m):
        content = m.group(2).strip()
        # Remove tags HTML internas
        plain = re.sub(r'<[^>]+>', '', content).strip()
        # Decodifica entidades HTML
        plain = (
            plain
            .replace('&lt;', '<')
            .replace('&gt;', '>')
            .replace('&amp;', '&')
        )
        core = plain.strip('<> .\n\r\t')
        if re.match(r'https?://', core):
            clean_url = re.sub(r'\s+', '', core)
            return f'<p><a href="{clean_url}">{clean_url}</a></p>'
        return m.group(0)

    html = re.sub(
        r'<(h[1-6])[^>]*>([\s\S]*?)</\1>',
        _fix_url_heading,
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Auto-linkifica URLs em texto plano
    html = autolink_urls(html)

    # Tabelas -> code block (Quill nao suporta tables)
    def _table_to_code(m):
        temp = document.createElement('div')
        temp.innerHTML = m.group(0)
        rows = temp.querySelectorAll('tr')
        result = ''
        for i, row in enumerate(rows):
            cells = row.querySelectorAll('th, td')
            vals = [c.textContent.strip() for c in cells]
            result += '  |  '.join(vals) + '\n'
            if i == 0:
                result += '--+--'.join(['--------'] * len(vals)) + '\n'
        return '<pre><code>' + result + '</code></pre>'

    html = re.sub(r'<table[\s\S]*?</table>', _table_to_code, html, flags=re.IGNORECASE)

    # Sanitiza com DOMPurify
    html = DOMPurify.sanitize(html, {
        'ALLOWED_TAGS': [
            'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'del',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
            'a', 'hr', 'sub', 'sup', 'span',
        ],
        'ALLOWED_ATTR': ['href', 'target', 'rel', 'class'],
    })

    return html


# ---------------------------------------------------------------------------
# Exporta funcoes para JavaScript via window
# ---------------------------------------------------------------------------
window.py_autolink_urls = autolink_urls
window.py_looks_like_markdown = looks_like_markdown
window.py_markdown_to_html = markdown_to_html
