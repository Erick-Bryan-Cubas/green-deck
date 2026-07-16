<!-- frontend/src/components/SelectionBar.vue -->
<!-- Barra flutuante de ações em massa exibida quando há cartões selecionados. -->
<script setup>
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'

defineProps({
  selectedCount: {
    type: Number,
    required: true
  },
  totalCount: {
    type: Number,
    required: true
  },
  allSelected: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['toggle-select-all', 'export', 'delete', 'cancel'])
</script>

<template>
  <div class="selection-bar">
    <div class="selection-info">
      <Checkbox
        :model-value="allSelected"
        binary
        aria-label="Selecionar todos os cartões"
        @update:model-value="emit('toggle-select-all', $event)"
      />
      <span class="selection-count">{{ selectedCount }} de {{ totalCount }}</span>
    </div>
    <div class="selection-actions">
      <Button
        icon="pi pi-send"
        label="Exportar"
        severity="primary"
        size="small"
        @click="emit('export')"
      />
      <Button
        icon="pi pi-trash"
        label="Excluir"
        severity="danger"
        size="small"
        @click="emit('delete')"
      />
      <Button
        icon="pi pi-times"
        severity="secondary"
        text
        rounded
        size="small"
        aria-label="Cancelar seleção"
        title="Cancelar seleção"
        @click="emit('cancel')"
      />
    </div>
  </div>
</template>

<style scoped>
.selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--selection-bg);
  border: 1px solid var(--selection-border);
  border-radius: 12px;
  margin: 0 12px 12px 12px;
  backdrop-filter: blur(8px);
}

.selection-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.selection-count {
  font-weight: 700;
  font-size: var(--fs-md);
  color: var(--selection-text);
}

.selection-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
