<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

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

let timer = null

async function checkStatus() {
  try {
    const res = await fetch('/api/anki-status')
    const data = await res.json()
    connected.value = !!data.connected
    version.value = data.version ?? null
    checking.value = false
  } catch {
    connected.value = false
    checking.value = false
  }
}

onMounted(async () => {
  await checkStatus()
  timer = setInterval(checkStatus, 2000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="anki-status" :class="statusClass" :title="tooltip">
    <i class="pi pi-database" style="font-size: 1.1rem" />
  </div>
</template>

<style scoped>
.anki-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.2rem;
  height: 2.2rem;
  border-radius: 999px;
  border: 1px solid var(--p-surface-400);
}
.connected {
  color: var(--p-green-400);
}
.disconnected {
  color: var(--p-red-400);
}
</style>
