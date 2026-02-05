/**
 * Export helpers (UI-agnostic)
 */

/**
 * Download plain text content as a file.
 * @param {string} content
 * @param {string} filename
 * @param {string} mimeType
 */
export function downloadTextFile(content, filename, mimeType = 'text/plain') {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, 100)
}

/**
 * Build markdown for a list of cards grouped by deck.
 * @param {Array} cards
 * @param {Date} [date]
 * @returns {{ markdown: string, filename: string }}
 */
export function buildCardsMarkdown(cards, date = new Date()) {
  let markdown = `# Flashcards - ${date.toLocaleDateString()}\n\n`
  const deckGroups = {}

  cards.forEach((card) => {
    const d = card.deck || 'General'
    if (!deckGroups[d]) deckGroups[d] = []
    deckGroups[d].push(card)
  })

  for (const [deckName, arr] of Object.entries(deckGroups)) {
    markdown += `## ${deckName}\n\n`
    arr.forEach((card, idx) => {
      markdown += `### Card ${idx + 1}\n\n`
      markdown += `**Question:** ${card.front}\n\n`
      markdown += `---\n\n`
      markdown += `**Answer:** ${card.back}\n\n`
    })
  }

  const filename = `flashcards-${date.toISOString().slice(0, 10)}.md`
  return { markdown, filename }
}

/**
 * Export cards as markdown (with optional notifier).
 * @param {Array} cards
 * @param {(message: string, severity?: string) => void} [notify]
 * @returns {boolean}
 */
export function exportCardsAsMarkdown(cards, notify) {
  if (!Array.isArray(cards) || cards.length === 0) {
    if (notify) notify('No cards to export', 'info')
    return false
  }

  const { markdown, filename } = buildCardsMarkdown(cards)
  downloadTextFile(markdown, filename, 'text/markdown')
  if (notify) notify(`${cards.length} cards exportados em markdown`, 'success')
  return true
}
