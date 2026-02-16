<script setup>
import { computed } from 'vue'
import { useOllamaStatus } from '@/composables/useStatusWebSocket'

const { status: ollamaState } = useOllamaStatus()

const connected = computed(() => ollamaState.value.connected)
const loading = computed(() => ollamaState.value.loading)
const models = computed(() => ollamaState.value.models)

const title = computed(() => {
  if (loading.value) return 'Ollama: verificando...'
  if (!connected.value) return 'Ollama: desconectado'
  const m = models.value?.length ? ` (${models.value.length} modelos)` : ''
  return `Ollama: conectado${m}`
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
  width: 30px;
  height: 30px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.06);
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.2);
}

.ollama-status.connected {
  border-color: rgba(16, 185, 129, 0.35);
}

.ollama-status.disconnected {
  opacity: 0.72;
  border-color: rgba(239, 68, 68, 0.35);
}

.ollama-status i {
  font-size: 14px;
}
</style>
