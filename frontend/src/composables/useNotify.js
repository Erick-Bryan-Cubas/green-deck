/**
 * Composable for notification/toast management
 */
import { ref } from 'vue'
import { useToast } from 'primevue/usetoast'

export function useNotify() {
  const toast = useToast()
  const logs = ref([])

  /**
   * Show a notification toast
   * @param {string} message - The message to display
   * @param {string} severity - Toast severity: 'success' | 'info' | 'warn' | 'error'
   * @param {number} life - Duration in milliseconds
   */
  function notify(message, severity = 'info', life = 3000) {
    toast.add({ severity, summary: message, life })
  }

  /**
   * Add an entry to the logs
   * @param {string} message - Log message
   * @param {string} type - Log type: 'info' | 'warn' | 'error' | 'success'
   */
  function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString()
    logs.value.push({ timestamp, message, type })
  }

  /**
   * Clear all logs
   */
  function clearLogs() {
    logs.value = []
    addLog('Logs cleared', 'info')
  }

  /**
   * Show success notification
   */
  function success(message, life = 3000) {
    notify(message, 'success', life)
  }

  /**
   * Show warning notification
   */
  function warn(message, life = 4000) {
    notify(message, 'warn', life)
  }

  /**
   * Show error notification
   */
  function error(message, life = 5000) {
    notify(message, 'error', life)
  }

  /**
   * Show info notification
   */
  function info(message, life = 3000) {
    notify(message, 'info', life)
  }

  return {
    logs,
    notify,
    addLog,
    clearLogs,
    success,
    warn,
    error,
    info
  }
}
