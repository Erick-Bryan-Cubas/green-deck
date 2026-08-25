<!-- frontend/src/components/EditorPanelHead.vue -->
<!-- Cabeçalho do painel do editor: título + status de salvamento, Modo Zen,
     undo/redo, busca, navegação de highlights, estatísticas e menu "⋯". -->
<script setup>
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import InputSwitch from 'primevue/inputswitch'

defineProps({
  saveStatus: {
    type: String,
    default: 'idle'
  },
  saveStatusSeverity: {
    type: String,
    default: 'secondary'
  },
  saveStatusIcon: {
    type: String,
    default: ''
  },
  saveStatusText: {
    type: String,
    default: ''
  },
  immersiveReader: {
    type: Boolean,
    default: false
  },
  searchActive: {
    type: Boolean,
    default: false
  },
  hasHighlights: {
    type: Boolean,
    default: false
  },
  highlightLabel: {
    type: String,
    default: ''
  },
  textStats: {
    type: Object,
    default: () => ({ words: 0, readingTimeLabel: '' })
  },
  pdfAvailable: {
    type: Boolean,
    default: false
  },
  viewMode: {
    type: String,
    default: 'editor' // 'editor' | 'pdf'
  }
})

const emit = defineEmits([
  'set-reader',
  'undo',
  'redo',
  'toggle-search',
  'prev-highlight',
  'next-highlight',
  'more',
  'set-view-mode'
])
</script>

<template>
  <!-- No modo PDF o leitor traz a própria barra de ferramentas: o cabeçalho
       fica compacto para não roubar altura útil de leitura -->
  <div class="panel-head" :class="{ 'is-compact': viewMode === 'pdf' }">
    <div class="panel-title">
      <i :class="viewMode === 'pdf' ? 'pi pi-file-pdf mr-2' : 'pi pi-pencil mr-2'" />
      {{ viewMode === 'pdf' ? 'Estudo PDF' : 'Editor' }}

      <!-- Indicador de salvamento -->
      <Transition name="fade">
        <Tag
          v-if="viewMode !== 'pdf' && saveStatus !== 'idle'"
          :severity="saveStatusSeverity"
          class="pill save-status ml-2"
        >
          <i :class="saveStatusIcon" class="mr-1" /> {{ saveStatusText }}
        </Tag>
      </Transition>
    </div>

    <div class="panel-actions">
      <!-- Alternância Editor / PDF (quando há um PDF em estudo) -->
      <div
        v-if="pdfAvailable"
        class="view-mode-toggle"
        role="group"
        aria-label="Modo de visualização"
      >
        <button
          type="button"
          class="view-mode-btn"
          :class="{ 'is-active': viewMode === 'editor' }"
          title="Editor de texto"
          @click="emit('set-view-mode', 'editor')"
        >
          <i class="pi pi-pencil" />
          <span>Editor</span>
        </button>
        <button
          type="button"
          class="view-mode-btn"
          :class="{ 'is-active': viewMode === 'pdf' }"
          title="Estudar pelo PDF"
          @click="emit('set-view-mode', 'pdf')"
        >
          <i class="pi pi-file-pdf" />
          <span>PDF</span>
        </button>
      </div>

      <!-- Modo Zen -->
      <div v-if="viewMode !== 'pdf'" class="editor-zen-group">
        <div class="editor-switch" title="Ativar Modo Zen">
          <span class="editor-switch-label">
            <i class="pi pi-bullseye" />
            Modo Zen
          </span>
          <InputSwitch
            class="zen-switch"
            :model-value="immersiveReader"
            :title="immersiveReader ? 'Sair do Modo Zen (Esc)' : 'Ativar Modo Zen'"
            @update:model-value="emit('set-reader', $event)"
          />
        </div>
      </div>

      <!-- Undo/Redo do Editor -->
      <div v-if="viewMode !== 'pdf'" class="editor-undo-redo">
        <Button
          icon="pi pi-undo"
          severity="secondary"
          text
          rounded
          size="small"
          aria-label="Desfazer edição"
          title="Desfazer edição (Ctrl+Z)"
          @click="emit('undo')"
        />
        <Button
          icon="pi pi-redo"
          severity="secondary"
          text
          rounded
          size="small"
          aria-label="Refazer edição"
          title="Refazer edição (Ctrl+Y)"
          @click="emit('redo')"
        />
      </div>

      <!-- Busca no texto -->
      <Button
        v-if="viewMode !== 'pdf'"
        icon="pi pi-search"
        severity="secondary"
        :outlined="searchActive"
        text
        rounded
        size="small"
        aria-label="Buscar no texto"
        title="Buscar no texto (Ctrl+F)"
        @click="emit('toggle-search')"
      />

      <!-- Navegação de Highlights -->
      <div v-if="viewMode !== 'pdf' && hasHighlights" class="highlight-nav">
        <Button
          icon="pi pi-chevron-left"
          severity="secondary"
          text
          rounded
          size="small"
          aria-label="Highlight anterior"
          title="Highlight anterior"
          @click="emit('prev-highlight')"
        />
        <Tag severity="warning" class="pill highlight-counter">
          <i class="pi pi-palette mr-1" /> {{ highlightLabel }}
        </Tag>
        <Button
          icon="pi pi-chevron-right"
          severity="secondary"
          text
          rounded
          size="small"
          aria-label="Próximo highlight"
          title="Próximo highlight"
          @click="emit('next-highlight')"
        />
      </div>

      <!-- Estatísticas de texto -->
      <div v-if="viewMode !== 'pdf'" class="text-stats">
        <Tag severity="secondary" class="pill stats-pill">
          <i class="pi pi-align-left mr-1" /> {{ textStats.words }} palavras
        </Tag>
        <Tag severity="secondary" class="pill stats-pill">
          <i class="pi pi-clock mr-1" /> {{ textStats.readingTimeLabel }}
        </Tag>
      </div>

      <!-- Mais opções (nº de linhas, exportar texto) -->
      <Button
        v-if="viewMode !== 'pdf'"
        icon="pi pi-ellipsis-v"
        severity="secondary"
        text
        rounded
        size="small"
        aria-label="Mais opções do editor"
        title="Mais opções"
        @click="emit('more', $event)"
      />
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

.panel-head.is-compact {
  padding: 5px 14px;
}

.panel-head.is-compact .panel-title {
  font-size: var(--fs-sm, 13px);
  font-weight: 700;
  color: var(--app-text-muted, var(--text-color-secondary));
}

.panel-title {
  font-size: var(--fs-md);
  font-weight: 800;
  letter-spacing: -0.2px;
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  flex-shrink: 0;
  white-space: nowrap;
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

.save-status {
  font-size: var(--fs-2xs);
  animation: fadeInStatus 0.3s ease;
}

@keyframes fadeInStatus {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.editor-zen-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Alternância Editor / PDF */
.view-mode-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: 999px;
  background: var(--surface-100);
  border: 1px solid var(--surface-200);
}

.view-mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-color-secondary);
  font-size: var(--fs-2xs);
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}

.view-mode-btn i {
  font-size: var(--icon-sm);
}

.view-mode-btn:hover:not(.is-active) {
  color: var(--text-color);
}

.view-mode-btn.is-active {
  background: var(--surface-0);
  color: var(--text-color);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.14);
}

.view-mode-btn.is-active .pi-file-pdf {
  color: var(--red-400);
}

.editor-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.45), rgba(15, 23, 42, 0.65));
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.08);
  backdrop-filter: blur(8px);
  transition: border-color 0.2s ease;
}

.editor-switch:hover {
  border-color: rgba(99, 102, 241, 0.4);
}

.editor-switch-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 0.75rem;
  color: rgba(226, 232, 240, 0.9);
  letter-spacing: 0.01em;
}

.editor-switch-label i {
  font-size: 0.9rem;
}

.zen-switch:deep(.p-inputswitch-slider) {
  background: rgba(71, 85, 105, 0.55);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.35);
}

.zen-switch:deep(.p-inputswitch.p-highlight .p-inputswitch-slider) {
  background: linear-gradient(135deg, #a855f7, #6366f1);
  box-shadow:
    0 0 0 1px rgba(168, 85, 247, 0.45),
    0 0 14px rgba(168, 85, 247, 0.35);
}

.editor-undo-redo {
  display: flex;
  gap: 2px;
  align-items: center;
}

.highlight-nav {
  display: flex;
  gap: 4px;
  align-items: center;
}

.highlight-counter {
  font-variant-numeric: tabular-nums;
  min-width: 60px;
  justify-content: center;
}

.text-stats {
  display: flex;
  gap: 6px;
  align-items: center;
}

.stats-pill {
  font-variant-numeric: tabular-nums;
  font-size: var(--fs-2xs);
  opacity: 0.85;
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
   (o container "editor-panel" é definido no painel pai)
========================= */
@container editor-panel (max-width: 800px) {
  .text-stats {
    display: none;
  }
}

@container editor-panel (max-width: 650px) {
  .view-mode-btn span {
    display: none;
  }
  .editor-switch-label {
    font-size: 0;
    gap: 0;
  }
  .editor-switch-label i {
    font-size: 0.9rem;
  }
  .editor-switch {
    padding: 4px 6px;
    gap: 6px;
  }
  .editor-zen-group {
    gap: 4px;
  }
  .panel-actions {
    gap: 8px;
  }
}

@container editor-panel (max-width: 500px) {
  .editor-zen-group {
    display: none;
  }
}
</style>
