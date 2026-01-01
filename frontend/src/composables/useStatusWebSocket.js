// frontend/src/composables/useStatusWebSocket.js
/**
 * WebSocket composable for real-time Anki/Ollama status updates.
 * Replaces polling with push-based notifications for better performance.
 */
import { ref, onMounted, onBeforeUnmount, readonly } from 'vue'

// Singleton state shared across all components
const ankiStatus = ref({
  connected: false,
  version: null,
  url: null,
  checking: true
})

const ollamaStatus = ref({
  connected: false,
  host: null,
  models: [],
  loading: true
})

let ws = null
let reconnectTimer = null
let pingTimer = null
let subscribers = 0

function getWebSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}/ws/status`
}

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return
  }

  try {
    ws = new WebSocket(getWebSocketUrl())

    ws.onopen = () => {
      console.debug('[WS] Connected to status WebSocket')
      // Start ping/pong for keepalive
      pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send('ping')
        }
      }, 30000) // Ping every 30 seconds
    }

    ws.onmessage = (event) => {
      if (event.data === 'pong') return

      try {
        const message = JSON.parse(event.data)
        if (message.type === 'status_update' && message.data) {
          const { anki, ollama } = message.data

          if (anki) {
            ankiStatus.value = {
              connected: !!anki.connected,
              version: anki.version || null,
              url: anki.url || null,
              checking: false
            }
          }

          if (ollama) {
            ollamaStatus.value = {
              connected: !!ollama.connected,
              host: ollama.host || null,
              models: Array.isArray(ollama.models) ? ollama.models : [],
              loading: false
            }
          }
        }
      } catch (e) {
        console.warn('[WS] Failed to parse message:', e)
      }
    }

    ws.onclose = (event) => {
      console.debug('[WS] Disconnected, will reconnect...')
      cleanup()
      // Reconnect after 3 seconds
      if (subscribers > 0) {
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    ws.onerror = (error) => {
      console.warn('[WS] Error:', error)
    }
  } catch (error) {
    console.error('[WS] Failed to create WebSocket:', error)
    // Fallback: try to reconnect
    if (subscribers > 0) {
      reconnectTimer = setTimeout(connect, 5000)
    }
  }
}

function cleanup() {
  if (pingTimer) {
    clearInterval(pingTimer)
    pingTimer = null
  }
}

function disconnect() {
  cleanup()
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
}

function forceRefresh() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('refresh')
  }
}

/**
 * Composable for Anki status with WebSocket
 */
export function useAnkiStatus() {
  onMounted(() => {
    subscribers++
    if (subscribers === 1) {
      connect()
    }
  })

  onBeforeUnmount(() => {
    subscribers--
    if (subscribers === 0) {
      disconnect()
    }
  })

  return {
    connected: readonly(ankiStatus),
    refresh: forceRefresh
  }
}

/**
 * Composable for Ollama status with WebSocket
 */
export function useOllamaStatus() {
  onMounted(() => {
    subscribers++
    if (subscribers === 1) {
      connect()
    }
  })

  onBeforeUnmount(() => {
    subscribers--
    if (subscribers === 0) {
      disconnect()
    }
  })

  return {
    status: readonly(ollamaStatus),
    refresh: forceRefresh
  }
}

/**
 * Composable for both statuses (recommended for layouts using both)
 */
export function useServicesStatus() {
  onMounted(() => {
    subscribers++
    if (subscribers === 1) {
      connect()
    }
  })

  onBeforeUnmount(() => {
    subscribers--
    if (subscribers === 0) {
      disconnect()
    }
  })

  return {
    anki: readonly(ankiStatus),
    ollama: readonly(ollamaStatus),
    refresh: forceRefresh,
    isConnected: () => ws && ws.readyState === WebSocket.OPEN
  }
}
