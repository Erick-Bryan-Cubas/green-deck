<!-- frontend/src/components/CardsPanelHead.vue -->
<!-- Cabeçalho do painel de cartões: título + pills de contagem/fonte,
     undo/redo, modo seleção, busca expansível, limpar e exportar. -->
<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import InputText from 'primevue/inputtext'

defineProps({
  hasCards: {
    type: Boolean,
    default: false
  },
  cardsTotalLabel: {
    type: String,
    default: '0'
  },
  selectedCount: {
    type: Number,
    default: 0
  },
  generationSource: {
    type: String,
    default: ''
  },
  generationCountLabel: {
    type: String,
    default: ''
  },
  sourceTitle: {
    type: String,
    default: ''
  },
  canUndo: {
    type: Boolean,
    default: false
  },
  canRedo: {
    type: Boolean,
    default: false
  },
  selectionMode: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['undo', 'redo', 'toggle-selection', 'clear-all', 'export'])

// v-model:search — o termo de busca pertence à página; a expansão é local
const search = defineModel('search', { type: String, default: '' })
const searchExpanded = ref(false)
</script>

<template>
  <div class="panel-head">
    <div class="panel-title">
      <i class="pi pi-clone mr-2" />
      Cartões
      <Tag :severity="hasCards ? 'success' : 'secondary'" class="pill ml-2 cards-total-pill">
        <i class="pi pi-inbox mr-1" />
        <span class="total-label">Total</span>
        <span class="total-sep">•</span>
        <span class="total-value">{{ cardsTotalLabel }}</span>
      </Tag>
      <Tag v-if="selectedCount > 0" severity="warning" class="pill ml-2">
        {{ selectedCount }} selecionados
      </Tag>
      <!-- Indicador da fonte da última geração -->
      <Transition name="fade">
        <Tag
          v-if="generationSource && hasCards"
          :severity="generationSource === 'selection' ? 'info' : generationSource === 'highlight' ? 'warning' : 'secondary'"
          class="pill ml-2 generation-source-tag"
          :title="sourceTitle"
        >
          <i
            :class="generationSource === 'selection' ? 'pi pi-mouse' : generationSource === 'highlight' ? 'pi pi-palette' : 'pi pi-file'"
            class="mr-1 source-icon"
          />
          <span class="source-label">
            {{ generationSource === 'selection' ? 'Seleção' : generationSource === 'highlight' ? 'Marcações' : 'Texto completo' }}
          </span>
          <span v-if="generationCountLabel" class="source-count">
            {{ generationCountLabel }}
          </span>
        </Tag>
      </Transition>
    </div>

    <div class="panel-actions">
      <!-- Undo/Redo -->
      <div class="undo-redo-group">
        <Button
          icon="pi pi-undo"
          severity="secondary"
          text
          rounded
          size="small"
          :disabled="!canUndo"
          aria-label="Desfazer"
          title="Desfazer (Ctrl+Z)"
          @click="emit('undo')"
        />
        <Button
          icon="pi pi-refresh"
          severity="secondary"
          text
          rounded
          size="small"
          :disabled="!canRedo"
          aria-label="Refazer"
          title="Refazer (Ctrl+Y)"
          @click="emit('redo')"
        />
      </div>

      <!-- Modo seleção -->
      <Button
        class="selection-toggle-btn"
        :icon="selectionMode ? 'pi pi-check-square' : 'pi pi-stop'"
        :severity="selectionMode ? 'primary' : 'secondary'"
        :outlined="selectionMode"
        text
        rounded
        size="small"
        :disabled="!hasCards"
        :aria-label="selectionMode ? 'Sair do modo seleção' : 'Modo seleção'"
        :title="selectionMode ? 'Sair do modo seleção' : 'Modo seleção'"
        @click="emit('toggle-selection')"
      />

      <!-- Busca expansível -->
      <div class="search-wrap" :class="{ 'expanded': searchExpanded }">
        <button
          class="search-toggle"
          type="button"
          aria-label="Buscar cartões"
          @click="searchExpanded = !searchExpanded"
        >
          <i class="pi pi-search" />
        </button>
        <InputText
          v-show="searchExpanded"
          v-model="search"
          class="search"
          placeholder="Buscar..."
          @blur="!search && (searchExpanded = false)"
        />
      </div>

      <!-- Limpar / Exportar -->
      <div class="export-group">
        <Button
          class="clear-all-btn"
          icon="pi pi-delete-left"
          :disabled="!hasCards"
          severity="danger"
          text
          rounded
          aria-label="Limpar todos os cartões"
          title="Limpar todos os cartões"
          @click="emit('clear-all')"
        />
        <Button
          class="export-btn"
          :disabled="!hasCards"
          icon="pi pi-send"
          outlined
          rounded
          aria-label="Exportar para o Anki"
          v-tooltip.top="'Exportar para o Anki'"
          @click="emit('export')"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel-head {
  padding: 10px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--panel-head-border);
  background: var(--panel-head-bg);
  min-width: 0;
}

.panel-title {
  font-size: var(--fs-md);
  font-weight: 800;
  letter-spacing: -0.2px;
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  white-space: nowrap;
  flex-shrink: 1;
  overflow: hidden;
}

.panel-title > i:first-child {
  font-size: var(--icon-md);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: nowrap;
  min-width: 0;
  flex-shrink: 1;
}

.panel-actions :deep(.p-button.p-button-icon-only) {
  width: var(--control-sm);
  height: var(--control-sm);
  min-width: var(--control-sm);
}

.panel-actions :deep(.p-button.p-button-icon-only .p-button-icon) {
  font-size: var(--icon-sm);
}

.pill {
  border-radius: 999px;
  font-weight: 900;
  font-size: var(--fs-xs);
}

.undo-redo-group {
  display: flex;
  gap: 2px;
  align-items: center;
}

/* Busca expansível */
.search-wrap {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.search-toggle {
  width: var(--control-sm);
  height: var(--control-sm);
  border-radius: 10px;
  background: var(--chip-bg);
  border: 1px solid var(--chip-border);
  color: var(--chip-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.search-toggle:hover {
  background: var(--chip-hover-bg);
  border-color: var(--chip-hover-border);
  color: var(--chip-hover-text);
}

.search-wrap.expanded .search-toggle {
  background: var(--chip-active-bg);
  border-color: var(--chip-active-border);
  color: var(--chip-active-text);
}

.search {
  width: 0;
  opacity: 0;
  padding: 0;
  height: var(--control-sm);
  border-radius: 10px;
  background: var(--chip-bg);
  border: 1px solid var(--chip-border);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: var(--fs-sm);
}

.search-wrap.expanded .search {
  width: 200px;
  opacity: 1;
  padding: 0 12px;
}

.search:focus {
  background: var(--chip-hover-bg);
  border-color: var(--chip-active-border);
  box-shadow: var(--searchbar-input-focus-ring);
}

.search::placeholder {
  color: var(--searchbar-placeholder);
  font-weight: 500;
}

.export-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.export-btn {
  flex-shrink: 0;
}

/* Pill de total */
.cards-total-pill {
  flex-shrink: 0;
  font-size: 0.72rem;
  padding: 0.2rem 0.6rem;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(34, 197, 94, 0.05));
  border: 1px solid rgba(34, 197, 94, 0.35);
}

.cards-total-pill .total-label {
  font-weight: 700;
  opacity: 0.8;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  font-size: 0.6rem;
}

.cards-total-pill .total-sep {
  opacity: 0.6;
}

.cards-total-pill .total-value {
  font-weight: 900;
  font-size: 0.82rem;
}

/* Indicador de fonte de geração */
.generation-source-tag {
  font-size: 0.72rem;
  padding: 0.2rem 0.6rem;
  cursor: help;
  gap: 6px;
  display: inline-flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(148, 163, 184, 0.2);
  flex-shrink: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.generation-source-tag .source-icon {
  font-size: 0.75rem;
}

.generation-source-tag .source-label {
  font-weight: 800;
  letter-spacing: 0.2px;
}

.generation-source-tag .source-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
  position: relative;
  padding-left: 10px;
}

.generation-source-tag .source-count::before {
  content: '•';
  position: absolute;
  left: 2px;
  opacity: 0.6;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* =========================
   Container queries — colapso por prioridade
   (o container "cards-panel" é definido no painel pai)
========================= */
@container cards-panel (max-width: 600px) {
  .generation-source-tag {
    display: none !important;
  }
}

@container cards-panel (max-width: 480px) {
  .undo-redo-group {
    display: none;
  }
  .panel-title .pill:not(.cards-total-pill) {
    display: none;
  }
}

/* < 380px — esconde modo seleção e busca (sobram limpar + exportar) */
@container cards-panel (max-width: 380px) {
  .selection-toggle-btn,
  .search-wrap {
    display: none;
  }
}
</style>
