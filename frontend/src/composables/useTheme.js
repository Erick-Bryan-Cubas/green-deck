import { computed, ref } from 'vue'

const STORAGE_KEY = 'green-deck.theme'
const DEFAULT_THEME = 'dark'

const theme = ref(DEFAULT_THEME)
let initialized = false

function getInitialTheme() {
  if (typeof window === 'undefined') return DEFAULT_THEME
  const saved = window.localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return DEFAULT_THEME
}

function applyTheme(nextTheme) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.classList.toggle('theme-dark', nextTheme === 'dark')
  root.classList.toggle('theme-light', nextTheme === 'light')
  root.style.colorScheme = nextTheme
}

export function initTheme() {
  if (initialized) return
  const initial = getInitialTheme()
  theme.value = initial
  applyTheme(initial)
  initialized = true
}

export function useTheme() {
  if (!initialized) initTheme()

  const isDark = computed(() => theme.value === 'dark')

  function setTheme(nextTheme) {
    if (nextTheme !== 'light' && nextTheme !== 'dark') return
    theme.value = nextTheme
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, nextTheme)
    }
    applyTheme(nextTheme)
  }

  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  return {
    theme,
    isDark,
    setTheme,
    toggleTheme
  }
}