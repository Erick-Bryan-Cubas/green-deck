<!-- frontend/src/components/modals/TopicConfirmDialog.vue -->
<script setup>
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'

defineProps({
  visible: Boolean
})

const emit = defineEmits([
  'update:visible',
  'confirm',
  'cancel'
])

function confirm() {
  emit('confirm')
  emit('update:visible', false)
}

function cancel() {
  emit('cancel')
  emit('update:visible', false)
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    header="Marcar Tópicos Automaticamente?"
    modal
    class="modern-dialog"
    style="width: min(480px, 95vw);"
  >
    <div class="topic-confirm-content">
      <div class="confirm-icon">
        <i class="pi pi-palette" style="font-size: 2.5rem; color: var(--p-primary-500);"></i>
      </div>
      <p class="confirm-text">
        Deseja que o modelo identifique e marque automaticamente os diferentes tópicos no texto com cores?
      </p>
      <p class="confirm-subtext">
        <i class="pi pi-info-circle"></i>
        Serão identificados: definições, exemplos, conceitos, fórmulas, procedimentos e comparações.
      </p>
    </div>
    <template #footer>
      <div class="topic-confirm-footer">
        <Button
          label="Não, obrigado"
          icon="pi pi-times"
          severity="secondary"
          text
          @click="cancel"
        />
        <Button
          label="Sim, marcar tópicos"
          icon="pi pi-palette"
          @click="confirm"
        />
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.topic-confirm-content {
  text-align: center;
  padding: 1rem 0;
}

.confirm-icon {
  margin-bottom: 1.5rem;
}

.confirm-text {
  font-size: 1rem;
  color: rgba(255, 255, 255, 0.9);
  margin-bottom: 1rem;
  line-height: 1.5;
}

.confirm-subtext {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: rgba(148, 163, 184, 0.8);
  background: rgba(15, 23, 42, 0.5);
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin: 0;
}

.confirm-subtext i {
  color: var(--p-primary-color);
}

.topic-confirm-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  width: 100%;
}
</style>
