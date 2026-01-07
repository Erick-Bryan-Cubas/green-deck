/**
 * Composable for dashboard filter state management
 */
import { ref, computed, watch } from 'vue'

// Singleton state for filters (shared across components)
const dateRange = ref([null, null])
const selectedDecks = ref([])
const selectedStatus = ref([])

export function useDashboardFilters() {
  /**
   * Check if any filter is active
   */
  const hasActiveFilters = computed(() => {
    return dateRange.value.some(d => d !== null) ||
           selectedDecks.value.length > 0 ||
           selectedStatus.value.length > 0
  })

  /**
   * Build query string from active filters
   * @returns {string} Query string for API calls
   */
  const queryString = computed(() => {
    const params = new URLSearchParams()

    if (dateRange.value[0]) {
      params.append('start_date', dateRange.value[0].toISOString().split('T')[0])
    }
    if (dateRange.value[1]) {
      params.append('end_date', dateRange.value[1].toISOString().split('T')[0])
    }
    if (selectedDecks.value.length > 0) {
      params.append('decks', selectedDecks.value.join(','))
    }
    if (selectedStatus.value.length > 0) {
      params.append('status', selectedStatus.value.join(','))
    }

    const qs = params.toString()
    return qs ? `?${qs}` : ''
  })

  /**
   * Clear all filters
   */
  function clearFilters() {
    dateRange.value = [null, null]
    selectedDecks.value = []
    selectedStatus.value = []
  }

  /**
   * Set date range filter
   * @param {Date|null} start - Start date
   * @param {Date|null} end - End date
   */
  function setDateRange(start, end) {
    dateRange.value = [start, end]
  }

  /**
   * Set decks filter
   * @param {string[]} decks - Array of deck names
   */
  function setDecks(decks) {
    selectedDecks.value = decks
  }

  /**
   * Set status filter
   * @param {string[]} status - Array of status keys
   */
  function setStatus(status) {
    selectedStatus.value = status
  }

  return {
    dateRange,
    selectedDecks,
    selectedStatus,
    hasActiveFilters,
    queryString,
    clearFilters,
    setDateRange,
    setDecks,
    setStatus
  }
}
