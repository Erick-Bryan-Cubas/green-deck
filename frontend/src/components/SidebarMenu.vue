<!-- frontend/src/components/SidebarMenu.vue -->
<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'

defineProps({
  menuItems: {
    type: Array,
    required: true
  },
  footerActions: {
    type: Array,
    default: () => []
  },
  version: {
    type: String,
    default: 'v1.0.0'
  },
  logoSrc: {
    type: String,
    default: '/green.svg'
  }
})

const emit = defineEmits(['close'])

const sidebarOpen = ref(true)
const sidebarExpanded = ref(false)
const expandedMenus = ref(new Set())

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function toggleSidebarExpand() {
  sidebarExpanded.value = !sidebarExpanded.value
  if (!sidebarExpanded.value) {
    expandedMenus.value.clear()
  }
}

function toggleSubmenu(key) {
  if (!sidebarExpanded.value) return
  if (expandedMenus.value.has(key)) {
    expandedMenus.value.delete(key)
  } else {
    expandedMenus.value.add(key)
  }
}

function closeSidebar() {
  sidebarOpen.value = false
  emit('close')
}

function handleItemClick(item) {
  if (item.command) {
    item.command()
  }
}

// Expose state for parent components
defineExpose({
  sidebarOpen,
  sidebarExpanded,
  toggleSidebar,
  closeSidebar
})
</script>

<template>
  <aside v-if="sidebarOpen" class="sidebar" :class="{ 'expanded': sidebarExpanded }">
    <div class="sidebar-header">
      <img :src="logoSrc" alt="Logo" class="sidebar-logo" />
      <Button 
        :icon="sidebarExpanded ? 'pi pi-chevron-left' : 'pi pi-chevron-right'" 
        text 
        rounded 
        severity="secondary"
        @click="toggleSidebarExpand" 
        class="sidebar-toggle"
        v-tooltip.right="sidebarExpanded ? 'Recolher menu' : 'Expandir menu'"
      />
    </div>

    <nav class="sidebar-nav">
      <template v-for="(item, idx) in menuItems" :key="idx">
        <div v-if="item.separator" class="sidebar-separator"></div>
        
        <div v-else-if="item.submenu" class="sidebar-item has-submenu">
          <button 
            class="sidebar-link" 
            :class="{ 'expanded': expandedMenus.has(item.key), 'active': item.active }"
            @click="toggleSubmenu(item.key)"
            v-tooltip.right="!sidebarExpanded ? { value: item.tooltip || item.label, showDelay: 300 } : null"
          >
            <span class="sidebar-icon-wrap" :style="{ '--icon-color': item.iconColor }">
              <i :class="item.icon" class="sidebar-icon"></i>
            </span>
            <Transition name="fade">
              <span v-if="sidebarExpanded" class="sidebar-label">{{ item.label }}</span>
            </Transition>
            <Transition name="fade">
              <Tag v-if="sidebarExpanded && item.badge" :severity="item.badge > 0 ? 'success' : 'secondary'" class="sidebar-badge">{{ item.badge }}</Tag>
            </Transition>
            <Transition name="fade">
              <i v-if="sidebarExpanded" class="pi pi-chevron-down sidebar-chevron"></i>
            </Transition>
          </button>
          
          <Transition name="submenu">
            <div v-if="sidebarExpanded && expandedMenus.has(item.key)" class="sidebar-submenu">
              <template v-for="(sub, subIdx) in item.submenu" :key="subIdx">
                <div v-if="sub.separator" class="submenu-separator"></div>
                <button 
                  v-else
                  class="submenu-link" 
                  :class="{ 'disabled': sub.disabled, 'active': sub.active, 'danger': sub.danger }"
                  :disabled="sub.disabled"
                  @click="handleItemClick(sub)"
                >
                  <span class="submenu-icon-wrap" :style="{ '--icon-color': sub.iconColor }">
                    <i :class="sub.icon" class="submenu-icon"></i>
                  </span>
                  <div class="submenu-text">
                    <span class="submenu-label">{{ sub.label }}</span>
                    <span v-if="sub.sublabel" class="submenu-sublabel">{{ sub.sublabel }}</span>
                  </div>
                  <i v-if="sub.active" class="pi pi-check submenu-check"></i>
                </button>
              </template>
            </div>
          </Transition>
        </div>

        <button 
          v-else 
          class="sidebar-link" 
          :class="{ 'active': item.active }"
          @click="handleItemClick(item)"
          v-tooltip.right="!sidebarExpanded ? { value: item.tooltip || item.label, showDelay: 300 } : null"
        >
          <span class="sidebar-icon-wrap" :style="{ '--icon-color': item.iconColor }">
            <i :class="item.icon" class="sidebar-icon"></i>
          </span>
          <Transition name="fade">
            <span v-if="sidebarExpanded" class="sidebar-label">{{ item.label }}</span>
          </Transition>
          <Transition name="fade">
            <Tag v-if="sidebarExpanded && item.badge" :severity="item.badge > 0 ? 'success' : 'secondary'" class="sidebar-badge">{{ item.badge }}</Tag>
          </Transition>
        </button>
      </template>
    </nav>

    <div class="sidebar-footer">
      <div class="sidebar-footer-actions">
        <button
          v-for="(action, idx) in footerActions"
          :key="idx"
          class="sidebar-footer-btn"
          @click="action.command?.()"
          v-tooltip.top="action.tooltip"
        >
          <i :class="action.icon"></i>
        </button>
      </div>
      <Transition name="fade">
        <div v-if="sidebarExpanded" class="sidebar-version">
          <span>{{ version }}</span>
        </div>
      </Transition>
    </div>
  </aside>
</template>

<style scoped>
/* =========================
   Sidebar Menu - Modern Design
========================= */
.sidebar {
  position: fixed;
  left: 12px;
  top: 12px;
  bottom: 12px;
  width: 80px;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.95) 0%, rgba(17, 24, 39, 0.98) 100%);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 24px;
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(255, 255, 255, 0.05) inset;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar.expanded {
  width: 300px;
}

.sidebar-header {
  padding: 16px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(180deg, rgba(16, 185, 129, 0.1) 0%, transparent 100%);
  min-height: auto;
  overflow: visible;
  gap: 10px;
  border-radius: 23px 23px 0 0;
}

.sidebar.expanded .sidebar-header {
  padding: 18px 20px;
}

.sidebar-logo {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  filter: drop-shadow(0 2px 8px rgba(16, 185, 129, 0.3));
  transition: transform 0.3s ease;
}

.sidebar:hover .sidebar-logo {
  transform: scale(1.05);
}

.sidebar-toggle {
  width: 24px;
  height: 24px;
  min-width: 24px;
  flex-shrink: 0;
  transition: all 0.2s ease;
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
}

.sidebar.expanded .sidebar-toggle {
  width: 24px;
  height: 24px;
}

.sidebar-toggle:hover {
  background: transparent !important;
  transform: scale(1.15);
}

.sidebar-toggle :deep(.p-button-icon) {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.5);
  transition: color 0.2s ease;
}

.sidebar-toggle:hover :deep(.p-button-icon) {
  color: #10B981;
}

.sidebar.expanded .sidebar-toggle :deep(.p-button-icon) {
  font-size: 14px;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 8px;
  scrollbar-width: thin;
  scrollbar-color: rgba(16, 185, 129, 0.3) transparent;
}

.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: rgba(16, 185, 129, 0.3);
  border-radius: 4px;
}

.sidebar-nav::-webkit-scrollbar-thumb:hover {
  background: rgba(16, 185, 129, 0.5);
}

.sidebar-separator {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(148, 163, 184, 0.15) 50%, transparent 100%);
  margin: 12px 16px;
}

.sidebar-item {
  margin-bottom: 4px;
  overflow: visible;
}

.sidebar-link {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 6px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.85);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 14px;
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  position: relative;
  overflow: visible;
}

.sidebar.expanded .sidebar-link {
  justify-content: flex-start;
  padding: 10px 14px;
}

.sidebar-link::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%) scaleY(0);
  width: 4px;
  height: 24px;
  background: linear-gradient(180deg, #10B981 0%, #34D399 100%);
  border-radius: 0 4px 4px 0;
  transition: transform 0.2s ease;
}

.sidebar-link:hover {
  background: rgba(99, 102, 241, 0.12);
  color: #fff;
}

.sidebar-link:hover::before {
  transform: translateY(-50%) scaleY(1);
}

.sidebar-link.expanded,
.sidebar-link.active {
  background: rgba(99, 102, 241, 0.18);
  color: #fff;
}

.sidebar-link.expanded::before,
.sidebar-link.active::before {
  transform: translateY(-50%) scaleY(1);
  background: linear-gradient(180deg, #6366F1 0%, #8B5CF6 100%);
}

.sidebar-icon-wrap {
  width: 46px;
  height: 46px;
  min-width: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.sidebar.expanded .sidebar-icon-wrap {
  width: 38px;
  height: 38px;
  min-width: 38px;
  border-radius: 10px;
}

.sidebar-link:hover .sidebar-icon-wrap {
  background: color-mix(in srgb, var(--icon-color, #6366F1) 18%, transparent);
  transform: scale(1.08);
}

.sidebar-icon {
  font-size: 17px;
  color: var(--icon-color, rgba(255, 255, 255, 0.8));
  transition: color 0.2s ease;
}

.sidebar-link:hover .sidebar-icon {
  color: var(--icon-color, #fff);
}

.sidebar-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 800;
  flex-shrink: 0;
}

.sidebar-chevron {
  font-size: 11px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  opacity: 0.6;
  flex-shrink: 0;
}

.sidebar-link.expanded .sidebar-chevron {
  transform: rotate(180deg);
  opacity: 1;
}

.sidebar-submenu {
  padding: 6px 0 6px 20px;
  margin-top: 4px;
  overflow: hidden;
  border-left: 2px solid rgba(99, 102, 241, 0.2);
  margin-left: 28px;
}

.submenu-separator {
  height: 1px;
  background: rgba(148, 163, 184, 0.08);
  margin: 8px 12px;
}

.submenu-link {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.75);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  text-align: left;
  margin-bottom: 2px;
  position: relative;
}

.submenu-link:hover:not(.disabled) {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  transform: translateX(4px);
}

.submenu-link.active {
  background: rgba(16, 185, 129, 0.15);
  color: #10B981;
}

.submenu-link.danger:hover:not(.disabled) {
  background: rgba(239, 68, 68, 0.12);
  color: #EF4444;
}

.submenu-link.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.submenu-icon-wrap {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.submenu-link:hover:not(.disabled) .submenu-icon-wrap {
  background: color-mix(in srgb, var(--icon-color, #6366F1) 20%, transparent);
}

.submenu-icon {
  font-size: 13px;
  color: var(--icon-color, rgba(255, 255, 255, 0.7));
  transition: color 0.2s ease;
}

.submenu-link:hover:not(.disabled) .submenu-icon {
  color: var(--icon-color, #fff);
}

.submenu-link.active .submenu-icon {
  color: #10B981;
}

.submenu-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.submenu-label {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.submenu-sublabel {
  font-size: 11px;
  opacity: 0.55;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.submenu-check {
  font-size: 12px;
  color: #10B981;
  flex-shrink: 0;
}

.submenu-enter-active {
  animation: submenu-expand 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.submenu-leave-active {
  animation: submenu-collapse 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes submenu-expand {
  from {
    opacity: 0;
    max-height: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    max-height: 800px;
    transform: translateY(0);
  }
}

@keyframes submenu-collapse {
  from {
    opacity: 1;
    max-height: 800px;
  }
  to {
    opacity: 0;
    max-height: 0;
  }
}

/* Fade transition for labels */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Sidebar Footer */
.sidebar-footer {
  padding: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.08);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border-radius: 0 0 23px 23px;
}

.sidebar.expanded .sidebar-footer {
  justify-content: space-between;
  padding: 12px 14px;
}

.sidebar-footer-actions {
  display: flex;
  gap: 6px;
}

.sidebar-footer-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
}

.sidebar-footer-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #10B981;
  transform: scale(1.1);
}

.sidebar-version {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
  font-weight: 500;
  padding-right: 4px;
}
</style>
