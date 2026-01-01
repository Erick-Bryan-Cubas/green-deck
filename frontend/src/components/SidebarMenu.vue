<!-- frontend/src/components/SidebarMenu.vue -->
<script setup>
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'

const props = defineProps({
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
  closeSidebar()
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
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  width: 56px;
  background: var(--surface-ground, #1a1a2e);
  border-right: 1px solid var(--surface-border, rgba(255, 255, 255, 0.08));
  display: flex;
  flex-direction: column;
  z-index: 1000;
  transition: width 0.22s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.sidebar.expanded {
  width: 240px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 10px;
  border-bottom: 1px solid var(--surface-border, rgba(255, 255, 255, 0.06));
  min-height: 56px;
}

.sidebar-logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
  flex-shrink: 0;
}

.sidebar-toggle {
  opacity: 0.7;
  transition: opacity 0.15s;
}

.sidebar-toggle:hover {
  opacity: 1;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 0;
}

.sidebar-separator {
  height: 1px;
  background: var(--surface-border, rgba(255, 255, 255, 0.06));
  margin: 8px 12px;
}

.sidebar-item {
  position: relative;
}

.sidebar-link {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  background: transparent;
  border: none;
  color: var(--text-color-secondary, #94a3b8);
  font-size: 0.92rem;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}

.sidebar-link:hover {
  background: var(--surface-hover, rgba(255, 255, 255, 0.04));
  color: var(--text-color, #fff);
}

.sidebar-link.active {
  background: var(--primary-color, #10b981);
  color: #fff;
}

.sidebar-link.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 24px;
  background: var(--primary-color, #10b981);
  border-radius: 0 3px 3px 0;
}

.sidebar-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.sidebar-icon {
  font-size: 1.1rem;
  color: var(--icon-color, currentColor);
}

.sidebar-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-badge {
  font-size: 0.7rem;
  padding: 2px 6px;
}

.sidebar-chevron {
  font-size: 0.75rem;
  opacity: 0.6;
  transition: transform 0.2s;
}

.sidebar-link.expanded .sidebar-chevron {
  transform: rotate(180deg);
}

.sidebar-submenu {
  padding: 4px 0 4px 20px;
  background: rgba(0, 0, 0, 0.15);
}

.submenu-separator {
  height: 1px;
  background: var(--surface-border, rgba(255, 255, 255, 0.04));
  margin: 4px 12px;
}

.submenu-link {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  color: var(--text-color-secondary, #94a3b8);
  font-size: 0.85rem;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s;
  border-radius: 6px;
  margin: 2px 0;
}

.submenu-link:hover:not(.disabled) {
  background: var(--surface-hover, rgba(255, 255, 255, 0.06));
  color: var(--text-color, #fff);
}

.submenu-link.active {
  background: var(--primary-color, #10b981);
  color: #fff;
}

.submenu-link.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.submenu-link.danger:hover {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.submenu-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.submenu-icon {
  font-size: 0.9rem;
  color: var(--icon-color, currentColor);
}

.submenu-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.submenu-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.submenu-sublabel {
  font-size: 0.75rem;
  opacity: 0.6;
}

.submenu-check {
  font-size: 0.8rem;
  color: var(--primary-color, #10b981);
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--surface-border, rgba(255, 255, 255, 0.06));
}

.sidebar-footer-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.sidebar-footer-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  color: var(--text-color-secondary, #94a3b8);
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s;
}

.sidebar-footer-btn:hover {
  background: var(--surface-hover, rgba(255, 255, 255, 0.06));
  color: var(--text-color, #fff);
}

.sidebar-version {
  text-align: center;
  margin-top: 8px;
  font-size: 0.75rem;
  color: var(--text-color-secondary, #64748b);
  opacity: 0.6;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.submenu-enter-active,
.submenu-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.submenu-enter-from,
.submenu-leave-to {
  opacity: 0;
  max-height: 0;
}

.submenu-enter-to,
.submenu-leave-from {
  max-height: 300px;
}
</style>
