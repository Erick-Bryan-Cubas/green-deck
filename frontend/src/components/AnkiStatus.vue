<!-- frontend/src/components/AnkiStatus.vue -->
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAnkiStatus } from '@/composables/useStatusWebSocket'

const { connected: ankiState } = useAnkiStatus()
const transitionClass = ref('')
let transitionTimer = null

const statusClass = computed(() => {
  if (ankiState.value.checking) return 'checking'
  return ankiState.value.connected ? 'connected' : 'disconnected'
})

watch(statusClass, (nextStatus, prevStatus) => {
  if (!prevStatus || nextStatus === prevStatus) return

  if (transitionTimer) {
    clearTimeout(transitionTimer)
    transitionTimer = null
  }

  if (nextStatus === 'connected') {
    transitionClass.value = 'transition-online'
    transitionTimer = setTimeout(() => {
      transitionClass.value = ''
      transitionTimer = null
    }, 560)
    return
  }

  if (nextStatus === 'disconnected') {
    transitionClass.value = 'transition-offline'
    transitionTimer = setTimeout(() => {
      transitionClass.value = ''
      transitionTimer = null
    }, 460)
    return
  }

  transitionClass.value = ''
})

const tooltip = computed(() => {
  if (ankiState.value.checking) return 'Checking Anki...'
  return ankiState.value.connected
    ? `Anki: Online (v${ankiState.value.version || 'unknown'})`
    : 'Anki: Offline - Make sure Anki is running with AnkiConnect'
})

onBeforeUnmount(() => {
  if (transitionTimer) {
    clearTimeout(transitionTimer)
    transitionTimer = null
  }
})
</script>

<template>
  <div class="anki-status" :class="[statusClass, transitionClass]" :title="tooltip" aria-label="Anki status">
    <span class="state-flash" aria-hidden="true"></span>
    <!-- SVG inline (como você mandou), com cores controladas por CSS vars -->
    <svg class="anki-svg" viewBox="0 0 222 222" width="22" height="22" aria-hidden="true">
      <defs>
        <!-- máscara pra manter as estrelas “dentro do cartão” -->
        <mask id="ankiCardMask" maskUnits="userSpaceOnUse" x="0" y="0" width="222" height="222">
          <path
            d="M159.095 7H63.1867C45.4105 7 31 21.2812 31 38.898V182.289C31 199.906 45.4105 214.188 63.1867 214.188H159.095C176.871 214.188 191.281 199.906 191.281 182.289V38.898C191.281 21.2812 176.871 7 159.095 7Z"
            fill="white"
          />
        </mask>
      </defs>

      <!-- “cartão” interno -->
      <path
        d="M159.095 7H63.1867C45.4105 7 31 21.2812 31 38.898V182.289C31 199.906 45.4105 214.188 63.1867 214.188H159.095C176.871 214.188 191.281 199.906 191.281 182.289V38.898C191.281 21.2812 176.871 7 159.095 7Z"
        fill="var(--anki-bg)"
      />

      <!-- estrelas (clipadas pelo cartão) -->
      <g mask="url(#ankiCardMask)">
        <path
          d="M132.111 183.136C127.333 187.678 108.321 173.784 101.762 174.676C95.2028 175.567 80.6677 194.021 74.8324 190.921C68.9972 187.822 76.4558 165.609 73.5734 159.702C70.691 153.796 48.4901 145.798 49.6615 139.341C50.8328 132.883 74.4542 133.049 79.2319 128.507C84.0096 123.965 84.8239 100.569 91.3831 99.6771C97.9422 98.7856 105.082 121.101 110.918 124.2C116.753 127.3 139.457 120.837 142.339 126.744C145.222 132.651 126.013 146.276 124.842 152.734C123.671 159.192 136.888 178.594 132.111 183.136Z"
          fill="var(--anki-accent)"
          stroke="var(--anki-accent)"
          stroke-width="1.2"
        />

        <path
          d="M168.599 63.4275C168.167 66.9153 155.53 67.5238 153.112 70.0937C150.693 72.6635 150.961 85.1986 147.48 85.8689C144 86.5393 139.511 74.8171 136.297 73.3318C133.084 71.8465 121.137 75.9723 119.418 72.8988C117.699 69.8253 127.562 61.9721 127.994 58.4843C128.426 54.9965 120.775 45.0113 123.193 42.4414C125.612 39.8716 136.196 46.7402 139.677 46.0699C143.157 45.3996 150.375 35.1026 153.589 36.5879C156.802 38.0731 153.481 50.1714 155.2 53.2449C156.919 56.3184 169.031 59.9397 168.599 63.4275Z"
          fill="var(--anki-accent)"
          stroke="var(--anki-accent)"
          stroke-width="1.1"
        />
      </g>

      <!-- contorno do cartão -->
      <path
        d="M160.24 5H61.7598C45.8762 5 33 18.2528 33 34.6009V184.399C33 200.747 45.8762 214 61.7598 214H160.24C176.124 214 189 200.747 189 184.399V34.6009C189 18.2528 176.124 5 160.24 5Z"
        fill="none"
        stroke="var(--anki-accent)"
        stroke-width="6"
      />
    </svg>
  </div>
</template>

<style scoped>
.anki-status {
  /* defaults */
  --anki-bg: rgba(255, 255, 255, 0.06);
  --anki-accent: rgba(148, 163, 184, 0.95);

  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: var(--anki-bg);
  border-radius: 10px;
  box-shadow: 0 0 0 0 rgba(0, 0, 0, 0);
  overflow: visible;
  transition:
    border-color 280ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 280ms cubic-bezier(0.22, 1, 0.36, 1),
    transform 280ms cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 320ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform, box-shadow, opacity;
}

.anki-svg {
  width: 18px;
  height: 18px;
  display: block;
  filter: drop-shadow(0 1px 6px rgba(0, 0, 0, 0.2));
  transition:
    transform 280ms cubic-bezier(0.22, 1, 0.36, 1),
    filter 320ms cubic-bezier(0.22, 1, 0.36, 1);
}

.state-flash {
  position: absolute;
  inset: -3px;
  border-radius: 12px;
  border: 1px solid transparent;
  opacity: 0;
  pointer-events: none;
}

/* estados */
.checking {
  --anki-accent: rgba(148, 163, 184, 0.95);
  opacity: 0.95;
}

.connected {
  --anki-accent: #22c55e; /* verde */
  border-color: rgba(16, 185, 129, 0.35);
}

.disconnected {
  --anki-accent: rgba(148, 163, 184, 0.88);
  opacity: 0.72;
  border-color: rgba(239, 68, 68, 0.35);
}

.transition-online {
  animation: status-online 560ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.transition-online .anki-svg {
  animation: icon-online 560ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.transition-online .state-flash {
  animation: status-ring-online 560ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.transition-offline {
  animation: status-offline 460ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.transition-offline .anki-svg {
  animation: icon-offline 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.transition-offline .state-flash {
  animation: status-ring-offline 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes status-online {
  0% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0);
  }
  35% {
    transform: scale(1.03);
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.14);
  }
  62% {
    transform: scale(1.045);
    box-shadow: 0 0 0 5px rgba(34, 197, 94, 0.18);
  }
  82% {
    transform: scale(1.012);
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.08);
  }
  100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0);
  }
}

@keyframes status-offline {
  0% {
    opacity: 0.86;
    transform: translateY(-1px) scale(1.015);
    box-shadow: 0 0 0 2px rgba(148, 163, 184, 0.12);
  }
  45% {
    opacity: 0.78;
    transform: translateY(0) scale(1.005);
  }
  100% {
    opacity: 0.72;
    transform: translateY(0) scale(1);
    box-shadow: 0 0 0 0 rgba(148, 163, 184, 0);
  }
}

@keyframes icon-online {
  0% {
    transform: scale(1);
  }
  38% {
    transform: scale(1.07);
  }
  68% {
    transform: scale(1.035);
  }
  100% {
    transform: scale(1);
  }
}

@keyframes icon-offline {
  0% {
    transform: scale(1);
  }
  40% {
    transform: scale(0.95);
  }
  100% {
    transform: scale(0.94);
  }
}

@keyframes status-ring-online {
  0% {
    opacity: 0;
    transform: scale(0.96);
    border-color: rgba(34, 197, 94, 0);
  }
  34% {
    opacity: 0.52;
    border-color: rgba(34, 197, 94, 0.42);
  }
  58% {
    opacity: 0.34;
    border-color: rgba(34, 197, 94, 0.26);
  }
  100% {
    opacity: 0;
    transform: scale(1.11);
    border-color: rgba(34, 197, 94, 0);
  }
}

@keyframes status-ring-offline {
  0% {
    opacity: 0;
    transform: scale(0.98);
    border-color: rgba(148, 163, 184, 0);
  }
  40% {
    opacity: 0.32;
    border-color: rgba(148, 163, 184, 0.28);
  }
  64% {
    opacity: 0.18;
    border-color: rgba(148, 163, 184, 0.18);
  }
  100% {
    opacity: 0;
    transform: scale(1.06);
    border-color: rgba(148, 163, 184, 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .anki-status {
    transition: none;
  }

  .transition-online,
  .transition-offline {
    animation: none;
  }
}
</style>
