<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const connected = ref(false)
const version = ref(null)
const checking = ref(true)

const statusClass = computed(() => (connected.value ? 'connected' : 'disconnected'))
const tooltip = computed(() => {
  if (checking.value) return 'Checking Anki...'
  return connected.value
    ? `Anki: Online (v${version.value || 'unknown'})`
    : 'Anki: Offline\nMake sure Anki is running with AnkiConnect'
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
  <div class="anki-status" :class="statusClass" :title="tooltip">
    <svg v-if="connected" class="anki-icon" width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>

    <svg v-else class="anki-icon" width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      <path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      <line x1="4" y1="4" x2="20" y2="20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
  </div>
</template>

<style scoped>
.anki-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border-radius: 10px;
}
.connected { color: #22c55e; }
.disconnected { color: #ef4444; opacity: 0.9; }
</style>
