<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const connected = ref(false)
const loading = ref(true)
const models = ref([])
const host = ref('')

let timer = null

const title = computed(() => {
  if (loading.value) return 'Ollama: verificando...'
  if (!connected.value) return 'Ollama: desconectado'
  const m = models.value?.length ? ` (${models.value.length} modelos)` : ''
  return `Ollama: conectado${m}`
})

async function refresh() {
  loading.value = true
  try {
    const resp = await fetch('/api/ollama-status')
    if (!resp.ok) throw new Error('bad_response')
    const data = await resp.json()
    connected.value = !!data.connected
    models.value = Array.isArray(data.models) ? data.models : []
    host.value = data.host || ''
  } catch {
    connected.value = false
    models.value = []
    host.value = ''
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 8000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="ollama-status" :class="connected ? 'connected' : 'disconnected'" :title="title">
    <i v-if="loading" class="pi pi-spinner pi-spin" />
    <i v-else class="pi pi-microchip" />
  </div>
</template>

<style scoped>
.ollama-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.06);
  box-shadow: 0 10px 24px rgba(0,0,0,0.18);
}

.ollama-status.connected {
  box-shadow: 0 10px 24px rgba(16, 185, 129, 0.10);
  border-color: rgba(16, 185, 129, 0.30);
}

.ollama-status.disconnected {
  opacity: 0.72;
  border-color: rgba(239, 68, 68, 0.30);
}

.ollama-status i {
  font-size: 15px;
}
</style>
