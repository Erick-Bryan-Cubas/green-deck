/**
 * Composable for session management (localStorage persistence)
 */
import { computed, ref, watch } from 'vue'

const LS_SESSIONS_KEY = 'spaced-rep.sessions.v1'
const LS_ACTIVE_SESSION_KEY = 'spaced-rep.sessions.active.v1'
const MAX_SESSIONS = 30
const MAX_LOCALSTORAGE_CHARS = 4_000_000

/**
 * Generate a safe unique ID
 */
function safeId() {
  try {
    return crypto.randomUUID()
  } catch {
    return `sess_${Date.now()}_${Math.random().toString(16).slice(2)}`
  }
}

/**
 * Normalize plain text by cleaning up whitespace
 */
function normalizePlainText(t) {
  return String(t || '')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

/**
 * Generate session title from text content
 */
function sessionTitleFromText(text) {
  const t = String(text || '').trim()
  const firstLine = t
    .split('\n')
    .map((s) => s.trim())
    .find(Boolean)
  if (!firstLine) return 'Texto sem título'
  return firstLine.length > 60 ? firstLine.slice(0, 59) + '…' : firstLine
}

/**
 * Format session timestamp for display
 */
function formatSessionStamp(iso) {
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return ''
  }
}

export function useSessionManager(options = {}) {
  const { onNotify = () => {} } = options

  const sessions = ref([])
  const activeSessionId = ref(null)
  const isRestoringSession = ref(false)

  const savedSessionExists = computed(() => sessions.value.length > 0)

  /**
   * Load sessions from localStorage
   */
  function loadSessions() {
    try {
      const raw = localStorage.getItem(LS_SESSIONS_KEY)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []

      return parsed
        .map((s) => ({
          id: typeof s.id === 'string' ? s.id : safeId(),
          title: typeof s.title === 'string' ? s.title : 'Sessão',
          createdAt: typeof s.createdAt === 'string' ? s.createdAt : new Date().toISOString(),
          updatedAt: typeof s.updatedAt === 'string' ? s.updatedAt : new Date().toISOString(),
          plainText: typeof s.plainText === 'string' ? s.plainText : '',
          quillDelta: s.quillDelta ?? null,
          cards: Array.isArray(s.cards) ? s.cards : [],
          documentContext: typeof s.documentContext === 'string' ? s.documentContext : ''
        }))
        .slice(0, MAX_SESSIONS)
    } catch {
      return []
    }
  }

  /**
   * Persist sessions to localStorage
   */
  function persistSessions(list) {
    try {
      const capped = list.slice(0, MAX_SESSIONS)
      const raw = JSON.stringify(capped)
      if (raw.length > MAX_LOCALSTORAGE_CHARS) {
        onNotify('Conteúdo muito grande — não foi possível salvar a sessão no localStorage.', 'warn')
        return false
      }
      localStorage.setItem(LS_SESSIONS_KEY, raw)
      return true
    } catch {
      onNotify('Falha ao salvar sessão (storage indisponível).', 'warn')
      return false
    }
  }

  /**
   * Load active session ID from localStorage
   */
  function loadActiveSessionId() {
    try {
      return localStorage.getItem(LS_ACTIVE_SESSION_KEY) || null
    } catch {
      return null
    }
  }

  /**
   * Persist active session ID
   */
  function persistActiveSessionId(id) {
    try {
      if (!id) localStorage.removeItem(LS_ACTIVE_SESSION_KEY)
      else localStorage.setItem(LS_ACTIVE_SESSION_KEY, id)
    } catch {
      // Ignore storage errors
    }
  }

  /**
   * Get session by ID
   */
  function getSessionById(id) {
    return sessions.value.find((s) => s.id === id) || null
  }

  /**
   * Upsert (insert or update) a session
   */
  function upsertSession(session) {
    const now = new Date().toISOString()
    const next = { ...session, updatedAt: now }

    const idx = sessions.value.findIndex((s) => s.id === next.id)
    if (idx >= 0) {
      sessions.value.splice(idx, 1, next)
    } else {
      sessions.value.unshift(next)
    }

    sessions.value.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
    sessions.value = sessions.value.slice(0, MAX_SESSIONS)

    persistSessions(sessions.value)
  }

  /**
   * Delete a session by ID
   */
  function deleteSessionById(id) {
    sessions.value = sessions.value.filter((s) => s.id !== id)
    persistSessions(sessions.value)

    if (activeSessionId.value === id) {
      activeSessionId.value = sessions.value[0]?.id || null
      persistActiveSessionId(activeSessionId.value)
    }
  }

  /**
   * Clear all sessions
   */
  function clearAllSessions() {
    sessions.value = []
    activeSessionId.value = null
    persistActiveSessionId(null)
    try {
      localStorage.removeItem(LS_SESSIONS_KEY)
    } catch {
      // Ignore
    }
  }

  /**
   * Ensure there is an active session
   */
  function ensureActiveSession() {
    if (activeSessionId.value) return activeSessionId.value

    const id = safeId()
    activeSessionId.value = id
    persistActiveSessionId(id)

    upsertSession({
      id,
      title: 'Nova sessão',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      plainText: '',
      quillDelta: null,
      cards: [],
      documentContext: ''
    })

    return id
  }

  /**
   * Create a new session
   */
  function createNewSession() {
    const id = safeId()
    activeSessionId.value = id
    persistActiveSessionId(id)

    upsertSession({
      id,
      title: 'Nova sessão',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      plainText: '',
      quillDelta: null,
      cards: [],
      documentContext: ''
    })

    return id
  }

  /**
   * Initialize sessions on mount
   */
  function initializeSessions() {
    sessions.value = loadSessions()
    activeSessionId.value = loadActiveSessionId()

    // Validate active session exists
    if (activeSessionId.value && !getSessionById(activeSessionId.value)) {
      activeSessionId.value = sessions.value[0]?.id || null
      persistActiveSessionId(activeSessionId.value)
    }
  }

  return {
    // State
    sessions,
    activeSessionId,
    isRestoringSession,
    savedSessionExists,

    // Methods
    loadSessions,
    persistSessions,
    getSessionById,
    upsertSession,
    deleteSessionById,
    clearAllSessions,
    ensureActiveSession,
    createNewSession,
    initializeSessions,

    // Utilities
    safeId,
    normalizePlainText,
    sessionTitleFromText,
    formatSessionStamp
  }
}
