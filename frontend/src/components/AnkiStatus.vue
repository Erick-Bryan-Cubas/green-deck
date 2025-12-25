<!-- frontend/src/components/AnkiStatus.vue -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const connected = ref(false)
const version = ref(null)
const checking = ref(true)

const statusClass = computed(() => {
  if (checking.value) return 'checking'
  return connected.value ? 'connected' : 'disconnected'
})

const tooltip = computed(() => {
  if (checking.value) return 'Checking Anki...'
  return connected.value
    ? `Anki: Online (v${version.value || 'unknown'})`
    : 'Anki: Offline - Make sure Anki is running with AnkiConnect'
})

let interval = null

async function checkStatus() {
  try {
    const response = await fetch('/api/anki-status')
    const data = await response.json()
    connected.value = !!data.connected
    version.value = data.version
    checking.value = false
  } catch {
    connected.value = false
    checking.value = false
  }
}

onMounted(() => {
  checkStatus()
  interval = setInterval(checkStatus, 2000)
})

onBeforeUnmount(() => {
  if (interval) clearInterval(interval)
})
</script>

<template>
  <div class="anki-status" :class="statusClass" :title="tooltip" aria-label="Anki status">
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
  padding: 4px;
  border-radius: 10px;
}

.anki-svg {
  display: block;
  filter: drop-shadow(0 2px 10px rgba(0, 0, 0, 0.22));
}

/* estados */
.checking {
  --anki-accent: rgba(148, 163, 184, 0.95);
  opacity: 0.95;
}

.connected {
  --anki-accent: #22c55e; /* verde */
}

.disconnected {
  --anki-accent: #ef4444; /* vermelho */
  opacity: 0.92;
}

/* opcional: “risco” no offline */
.disconnected::after {
  content: '';
  position: absolute;
  width: 26px;
  height: 2px;
  background: rgba(239, 68, 68, 0.95);
  border-radius: 999px;
  transform: rotate(45deg);
}
</style>
