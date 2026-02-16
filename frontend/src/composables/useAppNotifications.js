import { computed, ref } from 'vue'

const LS_NOTIFICATIONS_KEY = 'green-deck.notifications.v1'
const MAX_NOTIFICATIONS = 150

function safeId() {
  try {
    return crypto.randomUUID()
  } catch {
    return `notif_${Date.now()}_${Math.random().toString(16).slice(2)}`
  }
}

function normalizeSeverity(severity) {
  if (severity === 'danger') return 'error'
  if (severity === 'warning') return 'warn'
  if (severity === 'secondary') return 'info'
  return ['success', 'info', 'warn', 'error'].includes(severity) ? severity : 'info'
}

function loadNotifications() {
  try {
    const raw = localStorage.getItem(LS_NOTIFICATIONS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []

    return parsed
      .map((item) => ({
        id: typeof item?.id === 'string' ? item.id : safeId(),
        message: String(item?.message || ''),
        severity: normalizeSeverity(item?.severity),
        source: String(item?.source || 'App'),
        timestamp: Number.isFinite(Number(item?.timestamp)) ? Number(item.timestamp) : Date.now(),
        read: Boolean(item?.read)
      }))
      .filter((item) => item.message)
      .slice(0, MAX_NOTIFICATIONS)
  } catch {
    return []
  }
}

function persistNotifications(list) {
  try {
    localStorage.setItem(LS_NOTIFICATIONS_KEY, JSON.stringify(list.slice(0, MAX_NOTIFICATIONS)))
  } catch {
  }
}

const notifications = ref(loadNotifications())

const unreadCount = computed(() => notifications.value.reduce((acc, item) => acc + (item.read ? 0 : 1), 0))

function addNotification(payload = {}) {
  const message = String(payload.message || payload.summary || '').trim()
  if (!message) return

  const next = {
    id: safeId(),
    message,
    severity: normalizeSeverity(payload.severity),
    source: String(payload.source || 'App'),
    timestamp: Date.now(),
    read: false
  }

  notifications.value = [next, ...notifications.value].slice(0, MAX_NOTIFICATIONS)
  persistNotifications(notifications.value)
}

function markNotificationRead(id) {
  let changed = false
  notifications.value = notifications.value.map((item) => {
    if (item.id !== id || item.read) return item
    changed = true
    return { ...item, read: true }
  })
  if (changed) persistNotifications(notifications.value)
}

function markAllAsRead() {
  if (!notifications.value.some((item) => !item.read)) return
  notifications.value = notifications.value.map((item) => ({ ...item, read: true }))
  persistNotifications(notifications.value)
}

function clearNotifications() {
  notifications.value = []
  persistNotifications(notifications.value)
}

export function useAppNotifications() {
  return {
    notifications,
    unreadCount,
    addNotification,
    markNotificationRead,
    markAllAsRead,
    clearNotifications
  }
}
