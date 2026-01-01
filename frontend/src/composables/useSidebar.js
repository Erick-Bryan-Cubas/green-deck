/**
 * Composable for sidebar navigation state and menu items
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

export function useSidebar(options = {}) {
  const router = useRouter()
  const { activePage = 'generator', onNotify = () => {} } = options

  const sidebarRef = ref(null)

  // Build menu items based on current page
  const sidebarMenuItems = computed(() => [
    {
      key: 'generator',
      label: 'Generator',
      icon: 'pi pi-bolt',
      iconColor: '#10B981',
      tooltip: 'Gerar flashcards',
      active: activePage === 'generator',
      command: () => router.push('/')
    },
    {
      key: 'browser',
      label: 'Browser',
      icon: 'pi pi-database',
      iconColor: '#3B82F6',
      tooltip: 'Navegar pelos cards salvos',
      active: activePage === 'browser',
      command: () => router.push('/browser')
    },
    {
      key: 'dashboard',
      label: 'Dashboard',
      icon: 'pi pi-chart-bar',
      iconColor: '#F59E0B',
      tooltip: 'Estatísticas de estudo',
      active: activePage === 'dashboard',
      command: () => router.push('/dashboard')
    },
    { separator: true },
    {
      key: 'logs',
      label: 'Logs',
      icon: 'pi pi-wave-pulse',
      iconColor: '#EF4444',
      tooltip: 'Ver registros do sistema',
      command: () => onNotify('logs')
    }
  ])

  const sidebarFooterActions = computed(() => [
    {
      icon: 'pi pi-question-circle',
      tooltip: 'Ajuda',
      command: () => onNotify('help', 'Documentação em breve!')
    },
    {
      icon: 'pi pi-moon',
      tooltip: 'Tema',
      command: () => onNotify('theme', 'Tema alternativo em breve!')
    }
  ])

  // Helper to check if sidebar is open
  const isSidebarOpen = computed(() => sidebarRef.value?.sidebarOpen ?? true)

  // Toggle sidebar from parent
  function toggleSidebar() {
    sidebarRef.value?.toggleSidebar?.()
  }

  return {
    sidebarRef,
    sidebarMenuItems,
    sidebarFooterActions,
    isSidebarOpen,
    toggleSidebar
  }
}
