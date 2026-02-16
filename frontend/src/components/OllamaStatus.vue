<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useOllamaStatus } from '@/composables/useStatusWebSocket'

const { status: ollamaState } = useOllamaStatus()

const connected = computed(() => ollamaState.value.connected)
const loading = computed(() => ollamaState.value.loading)
const models = computed(() => ollamaState.value.models)
const statusClass = computed(() => {
  if (loading.value) return 'checking'
  return connected.value ? 'connected' : 'disconnected'
})
const transitionClass = ref('')
let transitionTimer = null

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

const title = computed(() => {
  if (loading.value) return 'Ollama: verificando...'
  if (!connected.value) return 'Ollama: desconectado'
  const m = models.value?.length ? ` (${models.value.length} modelos)` : ''
  return `Ollama: conectado${m}`
})

onBeforeUnmount(() => {
  if (transitionTimer) {
    clearTimeout(transitionTimer)
    transitionTimer = null
  }
})
</script>

<template>
  <div class="ollama-status" :class="[statusClass, transitionClass]" :title="title">
    <span class="state-flash" aria-hidden="true"></span>
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
  position: relative;
  overflow: visible;
  transition:
    border-color 280ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 280ms cubic-bezier(0.22, 1, 0.36, 1),
    transform 280ms cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 320ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform, box-shadow, opacity;
}

.ollama-status.checking {
  opacity: 0.95;
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
  transition: transform 280ms cubic-bezier(0.22, 1, 0.36, 1);
}

.state-flash {
  position: absolute;
  inset: -3px;
  border-radius: 12px;
  border: 1px solid transparent;
  opacity: 0;
  pointer-events: none;
}

.transition-online {
  animation: status-online 560ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.transition-online i {
  animation: icon-online 560ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.transition-online .state-flash {
  animation: status-ring-online 560ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.transition-offline {
  animation: status-offline 460ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.transition-offline i {
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
  .ollama-status {
    transition: none;
  }

  .transition-online,
  .transition-offline {
    animation: none;
  }
}
</style>
