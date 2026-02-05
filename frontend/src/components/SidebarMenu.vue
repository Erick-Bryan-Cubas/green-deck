<!-- frontend/src/components/SidebarMenu.vue -->
<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import { APP_VERSION, IS_BETA } from '@/config/version'

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
    default: APP_VERSION
  },
  showBetaBadge: {
    type: Boolean,
    default: IS_BETA
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

// Hover state for mini-popups
const hoveredItem = ref(null)
const hoverPosition = ref({ top: 0, left: 0 })
let hoverTimeout = null

function handleMouseEnter(event, item) {
  if (sidebarExpanded.value) return
  if (hoverTimeout) {
    clearTimeout(hoverTimeout)
    hoverTimeout = null
  }
  const rect = event.currentTarget.getBoundingClientRect()
  hoverPosition.value = {
    top: item.submenu ? rect.top : rect.top + rect.height / 2,
    left: rect.right + 12
  }
  hoveredItem.value = item
}

function handleMouseLeave() {
  // Delay closing to allow mouse to move to popup
  hoverTimeout = setTimeout(() => {
    hoveredItem.value = null
  }, 100)
}

function handlePopupMouseEnter() {
  if (hoverTimeout) {
    clearTimeout(hoverTimeout)
    hoverTimeout = null
  }
}

function handlePopupMouseLeave() {
  hoveredItem.value = null
}

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

      <!-- Brand logo when expanded -->
      <Transition name="fade">
        <svg
          v-if="sidebarExpanded"
          class="sidebar-brand-logo"
          width="322"
          height="60"
          viewBox="0 0 322 60"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          role="img"
          aria-label="Green Deck"
        >
          <title>Green Deck</title>
          <path class="brand-text" d="M32.5739 26.4375C32.4678 25.4697 32.2424 24.6146 31.8977 23.8722C31.5663 23.1165 31.1089 22.4801 30.5256 21.9631C29.9422 21.4328 29.233 21.0284 28.3977 20.75C27.5625 20.4716 26.5947 20.3324 25.4943 20.3324C23.4129 20.3324 21.464 20.8494 19.6477 21.8835C17.8447 22.9176 16.3068 24.4223 15.0341 26.3977C13.7614 28.3598 12.893 30.7595 12.429 33.5966C11.9517 36.4337 11.9517 38.8466 12.429 40.8352C12.9195 42.8239 13.8409 44.3419 15.1932 45.3892C16.5587 46.4233 18.3153 46.9403 20.4631 46.9403C22.4119 46.9403 24.1619 46.5956 25.7131 45.9062C27.2642 45.2036 28.5303 44.2159 29.5114 42.9432C30.5057 41.6705 31.142 40.1657 31.4205 38.429L33.1307 38.6875H22.6506L23.7244 32.2045H40.767L39.892 37.3352C39.322 40.9148 38.0691 43.9905 36.1335 46.5625C34.1979 49.1345 31.785 51.1098 28.8949 52.4886C26.018 53.8674 22.8627 54.5568 19.429 54.5568C15.6108 54.5568 12.3958 53.715 9.78409 52.0312C7.18561 50.3343 5.33617 47.928 4.2358 44.8125C3.14867 41.6837 2.95644 37.9716 3.65909 33.6761C4.20265 30.375 5.17045 27.4318 6.5625 24.8466C7.9678 22.2481 9.68466 20.0473 11.7131 18.2443C13.7415 16.4413 15.9886 15.0691 18.4545 14.1278C20.9337 13.1866 23.5123 12.7159 26.1903 12.7159C28.4972 12.7159 30.5852 13.054 32.4545 13.7301C34.3371 14.393 35.9479 15.3343 37.2869 16.554C38.6392 17.7737 39.66 19.2254 40.3494 20.9091C41.0521 22.5795 41.3769 24.4223 41.3239 26.4375H32.5739ZM43.4368 54L48.5277 23.4545H56.7408L55.8459 28.7841H56.1641C57.0391 26.8883 58.2124 25.4564 59.6839 24.4886C61.1688 23.5076 62.7663 23.017 64.4766 23.017C64.9008 23.017 65.3449 23.0436 65.8089 23.0966C66.2862 23.1364 66.7105 23.2027 67.0817 23.2955L65.8089 30.8324C65.4377 30.6998 64.9074 30.5937 64.218 30.5142C63.5419 30.4214 62.8989 30.375 62.2891 30.375C61.0561 30.375 59.9093 30.6468 58.8487 31.1903C57.7881 31.7206 56.8932 32.4631 56.1641 33.4176C55.4482 34.3722 54.9775 35.4725 54.7521 36.7188L51.9084 54H43.4368ZM78.7699 54.5966C75.6411 54.5966 73.0492 53.9602 70.9943 52.6875C68.9394 51.4015 67.4943 49.5852 66.6591 47.2386C65.8371 44.8788 65.6979 42.0881 66.2415 38.8665C66.7718 35.7244 67.839 32.9669 69.4432 30.5938C71.0606 28.2206 73.089 26.3712 75.5284 25.0455C77.9678 23.7197 80.6856 23.0568 83.6818 23.0568C85.697 23.0568 87.5199 23.3816 89.1506 24.0312C90.7945 24.6676 92.16 25.6354 93.2472 26.9347C94.3343 28.2206 95.0767 29.8314 95.4744 31.767C95.8854 33.7027 95.8788 35.9697 95.4545 38.5682L95.0767 40.8949H69.304L70.1193 35.6449H87.9375C88.1364 34.4252 88.0568 33.3447 87.6989 32.4034C87.3409 31.4621 86.7443 30.7263 85.9091 30.196C85.0739 29.6525 84.0464 29.3807 82.8267 29.3807C81.5805 29.3807 80.4138 29.6856 79.3267 30.2955C78.2396 30.9053 77.3248 31.7074 76.5824 32.7017C75.8532 33.6828 75.3826 34.75 75.1705 35.9034L74.2358 41.1136C73.9706 42.7178 74.0237 44.0502 74.3949 45.1108C74.7794 46.1714 75.4422 46.9669 76.3835 47.4972C77.3248 48.0142 78.518 48.2727 79.9631 48.2727C80.9044 48.2727 81.786 48.1402 82.608 47.875C83.4432 47.6098 84.1856 47.2188 84.8352 46.7017C85.4848 46.1714 86.0152 45.5152 86.4261 44.733L94.1619 45.25C93.446 47.1326 92.3589 48.7765 90.9006 50.1818C89.4422 51.5739 87.6856 52.661 85.6307 53.4432C83.589 54.2121 81.3021 54.5966 78.7699 54.5966ZM112.293 54.5966C109.165 54.5966 106.573 53.9602 104.518 52.6875C102.463 51.4015 101.018 49.5852 100.183 47.2386C99.3606 44.8788 99.2214 42.0881 99.7649 38.8665C100.295 35.7244 101.362 32.9669 102.967 30.5938C104.584 28.2206 106.612 26.3712 109.052 25.0455C111.491 23.7197 114.209 23.0568 117.205 23.0568C119.22 23.0568 121.043 23.3816 122.674 24.0312C124.318 24.6676 125.683 25.6354 126.771 26.9347C127.858 28.2206 128.6 29.8314 128.998 31.767C129.409 33.7027 129.402 35.9697 128.978 38.5682L128.6 40.8949H102.827L103.643 35.6449H121.461C121.66 34.4252 121.58 33.3447 121.222 32.4034C120.864 31.4621 120.268 30.7263 119.433 30.196C118.597 29.6525 117.57 29.3807 116.35 29.3807C115.104 29.3807 113.937 29.6856 112.85 30.2955C111.763 30.9053 110.848 31.7074 110.106 32.7017C109.377 33.6828 108.906 34.75 108.694 35.9034L107.759 41.1136C107.494 42.7178 107.547 44.0502 107.918 45.1108C108.303 46.1714 108.966 46.9669 109.907 47.4972C110.848 48.0142 112.041 48.2727 113.487 48.2727C114.428 48.2727 115.309 48.1402 116.131 47.875C116.967 47.6098 117.709 47.2188 118.359 46.7017C119.008 46.1714 119.539 45.5152 119.95 44.733L127.685 45.25C126.969 47.1326 125.882 48.7765 124.424 50.1818C122.966 51.5739 121.209 52.661 119.154 53.4432C117.112 54.2121 114.826 54.5966 112.293 54.5966ZM143.43 36.3409L140.487 54H132.036L137.126 23.4545H145.18L144.305 28.8438H144.643C145.611 27.054 146.977 25.642 148.74 24.608C150.517 23.5739 152.538 23.0568 154.805 23.0568C156.927 23.0568 158.696 23.5208 160.115 24.4489C161.547 25.3769 162.554 26.696 163.138 28.4062C163.734 30.1165 163.834 32.1648 163.436 34.5511L160.175 54H151.703L154.706 36.0625C155.011 34.1932 154.772 32.7348 153.99 31.6875C153.221 30.6269 151.982 30.0966 150.271 30.0966C149.131 30.0966 148.084 30.3419 147.129 30.8324C146.175 31.3229 145.373 32.0388 144.723 32.9801C144.087 33.9081 143.656 35.0284 143.43 36.3409Z" />
          <path class="brand-accent" d="M195.388 54H180.752L187.513 13.2727H201.871C205.967 13.2727 209.368 14.108 212.073 15.7784C214.79 17.4489 216.706 19.8419 217.82 22.9574C218.933 26.0597 219.132 29.7652 218.416 34.0739C217.727 38.2367 216.355 41.8097 214.3 44.7926C212.245 47.7623 209.613 50.0426 206.405 51.6335C203.197 53.2112 199.524 54 195.388 54ZM190.595 46.6222H195.885C198.444 46.6222 200.684 46.1449 202.607 45.1903C204.542 44.2358 206.127 42.7642 207.359 40.7756C208.606 38.7869 209.487 36.2415 210.004 33.1392C210.495 30.196 210.462 27.8097 209.905 25.9801C209.361 24.1373 208.307 22.7917 206.743 21.9432C205.179 21.0814 203.124 20.6506 200.578 20.6506H194.911L190.595 46.6222ZM235.176 54.5966C232.047 54.5966 229.455 53.9602 227.4 52.6875C225.345 51.4015 223.9 49.5852 223.065 47.2386C222.243 44.8788 222.104 42.0881 222.647 38.8665C223.177 35.7244 224.245 32.9669 225.849 30.5938C227.466 28.2206 229.495 26.3712 231.934 25.0455C234.373 23.7197 237.091 23.0568 240.087 23.0568C242.103 23.0568 243.926 23.3816 245.556 24.0312C247.2 24.6676 248.566 25.6354 249.653 26.9347C250.74 28.2206 251.482 29.8314 251.88 31.767C252.291 33.7027 252.284 35.9697 251.86 38.5682L251.482 40.8949H225.71L226.525 35.6449H244.343C244.542 34.4252 244.462 33.3447 244.105 32.4034C243.747 31.4621 243.15 30.7263 242.315 30.196C241.48 29.6525 240.452 29.3807 239.232 29.3807C237.986 29.3807 236.819 29.6856 235.732 30.2955C234.645 30.9053 233.73 31.7074 232.988 32.7017C232.259 33.6828 231.788 34.75 231.576 35.9034L230.641 41.1136C230.376 42.7178 230.429 44.0502 230.801 45.1108C231.185 46.1714 231.848 46.9669 232.789 47.4972C233.73 48.0142 234.924 48.2727 236.369 48.2727C237.31 48.2727 238.192 48.1402 239.014 47.875C239.849 47.6098 240.591 47.2188 241.241 46.7017C241.89 46.1714 242.421 45.5152 242.832 44.733L250.568 45.25C249.852 47.1326 248.765 48.7765 247.306 50.1818C245.848 51.5739 244.091 52.661 242.036 53.4432C239.995 54.2121 237.708 54.5966 235.176 54.5966ZM268.58 54.5966C265.438 54.5966 262.852 53.9337 260.824 52.608C258.809 51.2689 257.397 49.4129 256.588 47.0398C255.793 44.6667 255.654 41.9356 256.171 38.8466C256.674 35.7178 257.728 32.9735 259.332 30.6136C260.937 28.2405 262.972 26.3911 265.438 25.0653C267.917 23.7263 270.701 23.0568 273.79 23.0568C276.455 23.0568 278.708 23.5407 280.551 24.5085C282.394 25.4763 283.746 26.8352 284.608 28.5852C285.47 30.3352 285.761 32.3902 285.483 34.75H277.509C277.522 33.2386 277.131 32.0123 276.335 31.071C275.54 30.1297 274.373 29.6591 272.835 29.6591C271.51 29.6591 270.29 30.017 269.176 30.733C268.076 31.4356 267.141 32.4631 266.372 33.8153C265.617 35.1676 265.086 36.8049 264.781 38.7273C264.463 40.6761 264.457 42.3333 264.761 43.6989C265.066 45.0644 265.65 46.1051 266.511 46.821C267.373 47.5369 268.46 47.8949 269.773 47.8949C270.754 47.8949 271.662 47.696 272.497 47.2983C273.346 46.9006 274.088 46.3239 274.725 45.5682C275.361 44.7992 275.851 43.8778 276.196 42.804H284.19C283.647 45.1506 282.659 47.2055 281.227 48.9688C279.809 50.732 278.026 52.1108 275.878 53.1051C273.73 54.0994 271.297 54.5966 268.58 54.5966ZM296.853 45.2102L298.543 35.0483H299.776L311.529 23.4545H321.254L305.583 38.8068H303.555L296.853 45.2102ZM287.725 54L294.487 13.2727H302.958L296.197 54H287.725ZM306.816 54L300.055 40.696L306.677 34.7102L316.739 54H306.816Z" />
        </svg>
      </Transition>

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
            @mouseenter="(e) => handleMouseEnter(e, item)"
            @mouseleave="handleMouseLeave"
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
          @mouseenter="(e) => handleMouseEnter(e, item)"
          @mouseleave="handleMouseLeave"
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
          <Tag v-if="showBetaBadge" severity="warn" class="beta-badge">BETA</Tag>
        </div>
      </Transition>
    </div>
  </aside>

  <!-- Mini popup rendered outside sidebar to avoid overflow clipping -->
  <Teleport to="body">
    <Transition name="popup">
      <div
        v-if="hoveredItem && !sidebarExpanded"
        class="sidebar-popup-portal"
        :class="{ 'has-submenu': hoveredItem.submenu }"
        :style="{ top: hoverPosition.top + 'px', left: hoverPosition.left + 'px' }"
        @mouseenter="handlePopupMouseEnter"
        @mouseleave="handlePopupMouseLeave"
      >
        <!-- Header with label and badge -->
        <div class="popup-header">
          <span class="sidebar-popup-label">{{ hoveredItem.label }}</span>
          <Tag v-if="hoveredItem.badge" :severity="hoveredItem.badge > 0 ? 'success' : 'secondary'" class="sidebar-popup-badge">{{ hoveredItem.badge }}</Tag>
        </div>

        <!-- Submenu items if present -->
        <div v-if="hoveredItem.submenu" class="popup-submenu">
          <button
            v-for="(sub, subIdx) in hoveredItem.submenu"
            :key="subIdx"
            class="popup-submenu-item"
            :class="{ 'active': sub.active, 'disabled': sub.disabled }"
            @click="!sub.disabled && handleItemClick(sub)"
          >
            <span class="popup-submenu-label">{{ sub.label }}</span>
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
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
  background: linear-gradient(180deg, var(--sidebar-bg-start) 0%, var(--sidebar-bg-end) 100%);
  backdrop-filter: blur(24px);
  border: 1px solid var(--sidebar-border);
  border-radius: 24px;
  box-shadow: var(--sidebar-shadow);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: visible;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar.expanded {
  width: 300px;
}

.sidebar-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--sidebar-header-border);
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  background: var(--sidebar-header-bg);
  min-height: 56px;
  overflow: visible;
  gap: 10px;
  border-radius: 23px 23px 0 0;
}

.sidebar.expanded .sidebar-header {
  padding: 12px 14px;
}

.sidebar-logo {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  filter: drop-shadow(0 2px 8px var(--sidebar-logo-shadow));
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
  color: var(--sidebar-text-muted);
  transition: color 0.2s ease;
}

.sidebar-toggle:hover :deep(.p-button-icon) {
  color: var(--color-success);
}

.sidebar.expanded .sidebar-toggle :deep(.p-button-icon) {
  font-size: 14px;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: visible;
  padding: 12px 8px;
  scrollbar-width: thin;
  scrollbar-color: var(--sidebar-scrollbar) transparent;
}

.sidebar.expanded .sidebar-nav {
  overflow-x: hidden;
}

.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: var(--sidebar-scrollbar);
  border-radius: 4px;
}

.sidebar-nav::-webkit-scrollbar-thumb:hover {
  background: var(--sidebar-scrollbar-hover);
}

.sidebar-separator {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, var(--sidebar-separator) 50%, transparent 100%);
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
  color: var(--sidebar-text);
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
  background: linear-gradient(180deg, var(--sidebar-accent) 0%, var(--sidebar-accent-strong) 100%);
  border-radius: 0 4px 4px 0;
  transition: transform 0.2s ease;
}

.sidebar-link:hover {
  background: var(--sidebar-hover-bg);
  color: var(--app-text);
}

.sidebar-link:hover::before {
  transform: translateY(-50%) scaleY(1);
}

.sidebar-link.expanded,
.sidebar-link.active {
  background: var(--sidebar-active-bg);
  color: var(--app-text);
}

.sidebar-link.expanded::before,
.sidebar-link.active::before {
  transform: translateY(-50%) scaleY(1);
  background: linear-gradient(180deg, var(--color-primary) 0%, var(--sidebar-accent-strong) 100%);
}

.sidebar-icon-wrap {
  width: 46px;
  height: 46px;
  min-width: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--sidebar-icon-bg);
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
  background: color-mix(in srgb, var(--icon-color, var(--color-primary)) 18%, transparent);
  transform: scale(1.08);
}

.sidebar-icon {
  font-size: 17px;
  color: var(--icon-color, var(--sidebar-text));
  transition: color 0.2s ease;
}

.sidebar-link:hover .sidebar-icon {
  color: var(--icon-color, var(--app-text));
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
  border-left: 2px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
  margin-left: 28px;
}

.submenu-separator {
  height: 1px;
  background: color-mix(in srgb, var(--sidebar-separator) 70%, transparent);
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
  color: color-mix(in srgb, var(--sidebar-text) 85%, transparent);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  text-align: left;
  margin-bottom: 2px;
  position: relative;
}

.submenu-link:hover:not(.disabled) {
  background: color-mix(in srgb, var(--sidebar-icon-bg) 90%, transparent);
  color: var(--app-text);
  transform: translateX(4px);
}

.submenu-link.active {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.submenu-link.danger:hover:not(.disabled) {
  background: color-mix(in srgb, var(--color-danger) 16%, transparent);
  color: var(--color-danger);
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
  background: color-mix(in srgb, var(--sidebar-icon-bg) 80%, transparent);
  border-radius: 8px;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.submenu-link:hover:not(.disabled) .submenu-icon-wrap {
  background: color-mix(in srgb, var(--icon-color, var(--color-primary)) 20%, transparent);
}

.submenu-icon {
  font-size: 13px;
  color: var(--icon-color, color-mix(in srgb, var(--sidebar-text) 80%, transparent));
  transition: color 0.2s ease;
}

.submenu-link:hover:not(.disabled) .submenu-icon {
  color: var(--icon-color, var(--app-text));
}

.submenu-link.active .submenu-icon {
  color: var(--color-success);
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
  color: var(--color-success);
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
  border-top: 1px solid color-mix(in srgb, var(--sidebar-separator) 60%, transparent);
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
  color: var(--sidebar-text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
}

.sidebar-footer-btn:hover {
  background: color-mix(in srgb, var(--sidebar-icon-bg) 90%, transparent);
  color: var(--color-success);
  transform: scale(1.1);
}

.sidebar-version {
  font-size: 11px;
  color: color-mix(in srgb, var(--sidebar-text-muted) 80%, transparent);
  font-weight: 500;
  padding-right: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.beta-badge {
  font-size: 9px;
  padding: 2px 6px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

/* Sidebar Brand Logo (expanded state) */
.sidebar-brand-logo {
  height: 24px;
  width: auto;
  flex: 1;
  display: block;
  max-width: 100%;
  max-height: 24px;
  filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.15));
}

.sidebar-brand-logo .brand-text {
  fill: var(--sidebar-brand-text);
}

.sidebar-brand-logo .brand-accent {
  fill: var(--sidebar-brand-accent);
}

</style>

<!-- Global styles for teleported popup -->
<style>
.sidebar-popup-portal {
  position: fixed;
  transform: translateY(-50%);
  background: linear-gradient(135deg, var(--sidebar-popup-bg-start) 0%, var(--sidebar-popup-bg-end) 100%);
  border: 1px solid var(--sidebar-popup-border);
  border-radius: 12px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  box-shadow: var(--sidebar-popup-shadow);
  z-index: 9999;
  pointer-events: none;
}

/* With submenu: vertical layout */
.sidebar-popup-portal.has-submenu {
  flex-direction: column;
  align-items: stretch;
  padding: 0;
  min-width: 160px;
  pointer-events: auto;
  transform: none;
}

.sidebar-popup-portal .popup-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sidebar-popup-portal.has-submenu .popup-header {
  padding: 12px 14px 8px;
  border-bottom: 1px solid color-mix(in srgb, var(--sidebar-popup-border) 60%, transparent);
}

.sidebar-popup-portal::before {
  content: '';
  position: absolute;
  left: -6px;
  top: 24px;
  border: 6px solid transparent;
  border-right-color: var(--sidebar-popup-border);
}

.sidebar-popup-portal::after {
  content: '';
  position: absolute;
  left: -5px;
  top: 24px;
  border: 5px solid transparent;
  border-right-color: var(--sidebar-popup-arrow);
}

/* Adjust arrow position for simple popups */
.sidebar-popup-portal:not(.has-submenu)::before,
.sidebar-popup-portal:not(.has-submenu)::after {
  top: 50%;
  transform: translateY(-50%);
}

.sidebar-popup-portal .sidebar-popup-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--sidebar-popup-text);
}

.sidebar-popup-portal .sidebar-popup-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 700;
}

/* Submenu styles */
.sidebar-popup-portal .popup-submenu {
  display: flex;
  flex-direction: column;
  padding: 6px;
}

.sidebar-popup-portal .popup-submenu-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: var(--sidebar-popup-muted);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 13px;
  font-weight: 500;
  text-align: left;
}

.sidebar-popup-portal .popup-submenu-item:hover:not(.disabled) {
  background: var(--sidebar-popup-hover);
  color: var(--sidebar-popup-text);
}

.sidebar-popup-portal .popup-submenu-item.active {
  background: var(--sidebar-popup-active);
  color: var(--color-success);
}

.sidebar-popup-portal .popup-submenu-item.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.sidebar-popup-portal .popup-submenu-label {
  flex: 1;
}

/* Popup transition */
.popup-enter-active,
.popup-leave-active {
  transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.popup-enter-from,
.popup-leave-to {
  opacity: 0;
  transform: translateY(-50%) translateX(-8px);
}

.popup-enter-to,
.popup-leave-from {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
}
</style>
