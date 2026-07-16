/**
 * useSidebar — fonte única do menu lateral, compartilhada por todas as páginas.
 *
 * Estrutura do menu (idêntica em todas as páginas):
 *   1. Navegação: Gerador / Browser / Dashboard (com estado ativo)
 *   2. Itens específicos da página (topItems) — ex.: Sessões e Cartões no Gerador
 *   3. Configurações: Modelo IA, Prompts, Chaves de API
 *      — handlers locais quando a página fornece; senão deep-link para
 *        o Gerador via /?settings=model|prompts|keys
 *   4. Logs (quando a página fornece onOpenLogs)
 *   Rodapé: Documentação + alternador de tema
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import { colorTokens, sidebarIconColors } from '@/config/theme'

export function useSidebar(options = {}) {
  const {
    activePage = '',        // 'generator' | 'browser' | 'dashboard'
    topItems = () => [],    // itens específicos da página (função ou array)
    onOpenLogs = null,      // quando presente, exibe o item Logs
    logsHasError = () => false,
    settings = {}           // { onModel, onPrompts, onKeys, promptsBadge }
  } = options

  const router = useRouter()
  const { isDark, toggleTheme } = useTheme()

  // Deep-link: abre a configuração correspondente no Gerador
  function goToSettings(which) {
    router.push({ path: '/', query: { settings: which } })
  }

  function resolveTopItems() {
    const items = typeof topItems === 'function' ? topItems() : topItems
    return Array.isArray(items) ? items : []
  }

  const sidebarMenuItems = computed(() => {
    const pageItems = resolveTopItems()

    return [
      // --- Navegação principal ---
      {
        key: 'generator',
        label: 'Gerador',
        icon: 'pi pi-bolt',
        iconColor: sidebarIconColors.generator,
        tooltip: 'Gerar flashcards',
        active: activePage === 'generator',
        command: () => { if (activePage !== 'generator') router.push('/') }
      },
      {
        key: 'browser',
        label: 'Browser',
        icon: 'pi pi-database',
        iconColor: sidebarIconColors.browser,
        tooltip: 'Navegar pelos cartões salvos',
        active: activePage === 'browser',
        command: () => { if (activePage !== 'browser') router.push('/browser') }
      },
      {
        key: 'dashboard',
        label: 'Dashboard',
        icon: 'pi pi-chart-bar',
        iconColor: sidebarIconColors.dashboard,
        tooltip: 'Estatísticas de estudo',
        active: activePage === 'dashboard',
        command: () => { if (activePage !== 'dashboard') router.push('/dashboard') }
      },

      // --- Itens específicos da página ---
      ...(pageItems.length ? [{ separator: true }, ...pageItems] : []),

      { separator: true },

      // --- Configurações (disponível em todas as páginas) ---
      {
        key: 'config',
        label: 'Configurações',
        icon: 'pi pi-cog',
        iconColor: sidebarIconColors.settings,
        tooltip: 'Ajustes e preferências',
        submenu: [
          {
            label: 'Escolher Modelo IA',
            icon: 'pi pi-microchip-ai',
            iconColor: colorTokens.success,
            command: settings.onModel || (() => goToSettings('model'))
          },
          {
            label: 'Prompts de Geração',
            icon: 'pi pi-file-edit',
            iconColor: colorTokens.primary,
            badge: settings.promptsBadge ? settings.promptsBadge() : null,
            command: settings.onPrompts || (() => goToSettings('prompts'))
          },
          {
            label: 'Chaves de API',
            icon: 'pi pi-key',
            iconColor: colorTokens.warning,
            command: settings.onKeys || (() => goToSettings('keys'))
          }
        ]
      },

      // --- Logs (quando a página tem superfície de logs) ---
      ...(onOpenLogs
        ? [{
            key: 'logs',
            label: 'Logs',
            icon: 'pi pi-wave-pulse',
            status: logsHasError() ? 'error' : 'ok',
            iconColor: logsHasError() ? colorTokens.danger : colorTokens.neutral,
            tooltip: 'Ver registros do sistema',
            command: onOpenLogs
          }]
        : [])
    ]
  })

  const sidebarFooterActions = computed(() => [
    {
      icon: 'pi pi-question-circle',
      tooltip: 'Documentação',
      command: () => router.push('/docs')
    },
    {
      icon: isDark.value ? 'pi pi-sun' : 'pi pi-moon',
      tooltip: isDark.value ? 'Ativar modo claro' : 'Ativar modo escuro',
      command: toggleTheme
    }
  ])

  return {
    sidebarMenuItems,
    sidebarFooterActions
  }
}
