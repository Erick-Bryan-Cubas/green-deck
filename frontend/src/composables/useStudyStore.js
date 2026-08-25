/**
 * Cliente da API de estudo (/api/study).
 *
 * É a camada durável: PDFs, marcações, posição de leitura e sessões vivem no
 * DuckDB do backend. O localStorage continua sendo usado como cache local e
 * como rede de segurança — se o backend estiver fora, nada quebra, apenas a
 * persistência entre máquinas/limpezas de navegador deixa de existir.
 *
 * Regra de convergência: o lado local ganha quando os dois têm dados (foi o
 * último a ser escrito nesta máquina); o remoto só entra quando o local está
 * vazio — o caso de "abri em outro navegador / limpei os dados".
 */

const BASE = '/api/study'

// Depois de uma falha de rede, para de tentar por um tempo para não encher o
// console de erros enquanto o backend estiver fora do ar
const OFFLINE_COOLDOWN_MS = 20_000
let offlineUntil = 0

function isOffline() {
  return Date.now() < offlineUntil
}

function markOffline() {
  offlineUntil = Date.now() + OFFLINE_COOLDOWN_MS
}

function markOnline() {
  offlineUntil = 0
}

async function readJson(resp) {
  try {
    return await resp.json()
  } catch {
    return null
  }
}

async function request(path, options = {}, { silent = true } = {}) {
  if (isOffline()) return null
  try {
    const resp = await fetch(`${BASE}${path}`, options)
    const data = await readJson(resp)
    if (!resp.ok || data?.success === false) {
      const detail = data?.detail || data?.error || `HTTP ${resp.status}`
      if (!silent) throw new Error(typeof detail === 'string' ? detail : `HTTP ${resp.status}`)
      console.warn(`[study] ${path}: ${typeof detail === 'string' ? detail : resp.status}`)
      return null
    }
    markOnline()
    return data
  } catch (e) {
    markOffline()
    if (!silent) throw e
    console.warn(`[study] ${path} indisponível:`, e?.message || e)
    return null
  }
}

/**
 * Registra o PDF no backend (dedup por sha256) e devolve o documento com as
 * marcações já salvas para ele. Lança se não der — quem chama decide o que
 * fazer (seguir sem persistência remota).
 */
export async function uploadStudyDocument(file) {
  const form = new FormData()
  form.append('file', file, file.name)
  // Upload é a única chamada que não pode ser silenciosa: sem id não há
  // vínculo com a sessão nem persistência
  offlineUntil = 0
  const data = await request('/documents', { method: 'POST', body: form }, { silent: false })
  return data ? { document: data.document, highlights: data.highlights || [] } : null
}

export async function fetchStudyDocument(documentId) {
  if (!documentId) return null
  const data = await request(`/documents/${documentId}`)
  return data ? { document: data.document, highlights: data.highlights || [] } : null
}

/** Bytes do PDF original, para remontar o leitor ao restaurar uma sessão. */
export async function fetchStudyFileBytes(documentId) {
  if (!documentId || isOffline()) return null
  try {
    const resp = await fetch(`${BASE}/documents/${documentId}/file`)
    if (!resp.ok) {
      console.warn(`[study] arquivo ${documentId}: HTTP ${resp.status}`)
      return null
    }
    markOnline()
    return new Uint8Array(await resp.arrayBuffer())
  } catch (e) {
    markOffline()
    console.warn('[study] falha ao baixar o PDF:', e?.message || e)
    return null
  }
}

export async function listStudyDocuments(limit = 50) {
  const data = await request(`/documents?limit=${limit}`)
  return data?.documents || []
}

export async function saveStudyHighlights(documentId, highlights) {
  if (!documentId) return false
  const data = await request(`/documents/${documentId}/highlights`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ highlights: highlights || [] })
  })
  return !!data
}

export async function saveStudyReading(documentId, reading) {
  if (!documentId) return false
  const data = await request(`/documents/${documentId}/reading`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(reading || {})
  })
  return !!data
}

export async function deleteStudyDocument(documentId) {
  if (!documentId) return false
  return !!(await request(`/documents/${documentId}`, { method: 'DELETE' }))
}

// ============================================================
// Sessões
// ============================================================
export async function listStudySessions() {
  const data = await request('/sessions')
  return Array.isArray(data?.sessions) ? data.sessions : []
}

export async function saveStudySession(session) {
  if (!session?.id) return false
  const data = await request(`/sessions/${encodeURIComponent(session.id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session })
  })
  return !!data
}

export async function deleteStudySession(sessionId) {
  if (!sessionId) return false
  return !!(await request(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }))
}

export async function clearStudySessions() {
  return !!(await request('/sessions', { method: 'DELETE' }))
}

/**
 * Junta as sessões locais com as do banco por id, mantendo a versão de
 * updatedAt mais recente. Usado na inicialização.
 */
export function mergeSessions(localList, remoteList) {
  const local = Array.isArray(localList) ? localList : []
  const remote = Array.isArray(remoteList) ? remoteList : []
  const byId = new Map()
  for (const s of remote) {
    if (s?.id) byId.set(s.id, s)
  }
  for (const s of local) {
    if (!s?.id) continue
    const existing = byId.get(s.id)
    if (!existing) {
      byId.set(s.id, s)
      continue
    }
    const localStamp = new Date(s.updatedAt || 0).getTime()
    const remoteStamp = new Date(existing.updatedAt || 0).getTime()
    byId.set(s.id, localStamp >= remoteStamp ? s : existing)
  }
  return [...byId.values()].sort(
    (a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0)
  )
}
