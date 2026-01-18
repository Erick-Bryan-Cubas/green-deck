<!-- frontend/src/components/modals/EditCardDialog.vue -->
<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Select from 'primevue/select'
import ContextMenu from 'primevue/contextmenu'
import LazyQuillEditor from '@/components/LazyQuillEditor.vue'
import { rewriteCard } from '@/services/api.js'

const props = defineProps({
  visible: Boolean,
  card: Object,
  cardIndex: {
    type: Number,
    default: -1
  },
  availableDeckNames: {
    type: Array,
    default: () => []
  },
  selectedModel: String
})

const emit = defineEmits([
  'update:visible',
  'save',
  'delete',
  'duplicate',
  'fetchDecks'
])

// Internal state
const editDraft = ref({ front: '', back: '', deck: 'General' })
const editFrontRef = ref(null)
const editBackRef = ref(null)
const editFrontReady = ref(false)
const editBackReady = ref(false)
const pendingEditContent = ref(null)
const isRewriting = ref(false)
const editContextMenuRef = ref(null)
const editSelectedText = ref('')

// Helper function
function getCardType(front) {
  const q = String(front || '').trim()
  return q.includes('{{c1::') ? 'cloze' : 'basic'
}

// Watch for card changes
watch(() => props.card, (newCard) => {
  if (newCard) {
    editDraft.value = {
      front: String(newCard.front ?? ''),
      back: String(newCard.back ?? ''),
      deck: String(newCard.deck ?? 'General')
    }
    pendingEditContent.value = {
      front: editDraft.value.front,
      back: editDraft.value.back
    }
  }
}, { immediate: true })

// When modal opens, load content into editors
watch(() => props.visible, (visible) => {
  if (visible && props.card) {
    nextTick(() => {
      if (editFrontReady.value && editFrontRef.value) {
        editFrontRef.value.setContent(editDraft.value.front)
      }
      if (editBackReady.value && editBackRef.value) {
        editBackRef.value.setContent(editDraft.value.back)
      }
    })
  }
})

// Editor ready handlers
function onEditFrontReady() {
  editFrontReady.value = true
  if (pendingEditContent.value?.front !== undefined) {
    nextTick(() => {
      editFrontRef.value?.setContent(pendingEditContent.value.front)
    })
  }
}

function onEditBackReady() {
  editBackReady.value = true
  if (pendingEditContent.value?.back !== undefined) {
    nextTick(() => {
      editBackRef.value?.setContent(pendingEditContent.value.back)
    })
  }
}

// Actions
function saveCard() {
  const frontHtml = editFrontRef.value?.getHtml() || editDraft.value.front
  const backHtml = editBackRef.value?.getHtml() || editDraft.value.back

  emit('save', {
    index: props.cardIndex,
    front: frontHtml,
    back: backHtml,
    deck: editDraft.value.deck || 'General'
  })
  emit('update:visible', false)
}

function deleteCard() {
  emit('delete', props.cardIndex)
  emit('update:visible', false)
}

function duplicateCard() {
  emit('duplicate', props.cardIndex)
}

async function handleRewriteCard(action) {
  if (props.cardIndex < 0) return
  if (isRewriting.value) return

  isRewriting.value = true
  try {
    const result = await rewriteCard(
      {
        front: editDraft.value.front,
        back: editDraft.value.back,
      },
      action,
      props.selectedModel
    )

    if (result.success) {
      editDraft.value.front = result.front
      editDraft.value.back = result.back
      editFrontRef.value?.setContent(result.front)
      editBackRef.value?.setContent(result.back)
    }
  } catch (error) {
    console.error('Rewrite error:', error)
  } finally {
    isRewriting.value = false
  }
}

// Context menu
const editContextMenuModel = computed(() => [
  {
    label: 'Gerar card Basic',
    icon: 'pi pi-plus',
    disabled: !editSelectedText.value,
    command: () => emit('generateFromSelection', { text: editSelectedText.value, type: 'basic' })
  },
  {
    label: 'Gerar card Cloze',
    icon: 'pi pi-plus',
    disabled: !editSelectedText.value,
    command: () => emit('generateFromSelection', { text: editSelectedText.value, type: 'cloze' })
  }
])
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    modal
    appendTo="body"
    :draggable="false"
    :dismissableMask="true"
    class="modern-dialog edit-card-dialog"
    style="width: min(900px, 96vw);"
  >
    <template #header>
      <div class="edit-dialog-header">
        <div class="edit-header-left">
          <span class="edit-card-number">#{{ cardIndex + 1 }}</span>
          <Tag
            :severity="getCardType(editDraft.front) === 'cloze' ? 'warning' : 'info'"
            class="edit-type-tag"
          >
            <i :class="getCardType(editDraft.front) === 'cloze' ? 'pi pi-pencil' : 'pi pi-file'" class="mr-1" />
            {{ getCardType(editDraft.front) === 'cloze' ? 'Cloze' : 'Básico' }}
          </Tag>
        </div>
        <div class="edit-header-right">
          <i class="pi pi-tag mr-2 text-color-secondary" />
          <Select
            v-model="editDraft.deck"
            :options="availableDeckNames.map((x) => ({ label: x, value: x }))"
            optionLabel="label"
            optionValue="value"
            class="deck-select-compact"
            filter
            placeholder="Deck"
          />
          <Button
            icon="pi pi-refresh"
            severity="secondary"
            text
            rounded
            @click="emit('fetchDecks')"
            title="Atualizar decks"
            class="ml-2"
          />
        </div>
      </div>
    </template>

    <ContextMenu ref="editContextMenuRef" :model="editContextMenuModel" appendTo="body" />

    <div class="edit-card-content">
      <div class="edit-field">
        <div class="edit-field-header">
          <i class="pi pi-comment" />
          <span>Frente</span>
        </div>
        <div class="edit-card-quill">
          <LazyQuillEditor
            ref="editFrontRef"
            placeholder="Frente do card..."
            @content-changed="editDraft.front = $event.html"
            @editor-ready="onEditFrontReady"
          />
        </div>
      </div>

      <div class="edit-field">
        <div class="edit-field-header">
          <i class="pi pi-comments" />
          <span>Verso</span>
        </div>
        <div class="edit-card-quill">
          <LazyQuillEditor
            ref="editBackRef"
            placeholder="Verso do card..."
            @content-changed="editDraft.back = $event.html"
            @editor-ready="onEditBackReady"
          />
        </div>
      </div>
    </div>

    <!-- AI Rewrite Section -->
    <div class="edit-ai-section">
      <div class="edit-ai-header">
        <i class="pi pi-sparkles" />
        <span>Reescrever com IA</span>
      </div>
      <div class="edit-ai-buttons">
        <Button
          label="Mais denso"
          icon="pi pi-plus"
          severity="secondary"
          outlined
          size="small"
          :loading="isRewriting"
          :disabled="isRewriting"
          @click="handleRewriteCard('densify')"
          title="Adiciona mais lacunas cloze ao card"
        />
        <Button
          label="Dividir cloze"
          icon="pi pi-clone"
          severity="secondary"
          outlined
          size="small"
          :loading="isRewriting"
          :disabled="isRewriting"
          @click="handleRewriteCard('split_cloze')"
          title="Divide o conteudo em varias lacunas"
        />
        <Button
          label="Simplificar"
          icon="pi pi-minus"
          severity="secondary"
          outlined
          size="small"
          :loading="isRewriting"
          :disabled="isRewriting"
          @click="handleRewriteCard('simplify')"
          title="Reduz complexidade do card"
        />
      </div>
    </div>

    <template #footer>
      <div class="edit-footer">
        <div class="edit-footer-left">
          <Button label="Excluir" icon="pi pi-trash" severity="danger" text @click="deleteCard" />
        </div>
        <div class="edit-footer-right">
          <Button label="Duplicar" icon="pi pi-copy" severity="secondary" outlined @click="duplicateCard" />
          <Button label="Cancelar" icon="pi pi-times" severity="secondary" text @click="emit('update:visible', false)" />
          <Button label="Salvar" icon="pi pi-check" severity="success" @click="saveCard" />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
/* Edit Card Dialog - Enhanced */
:deep(.edit-card-dialog) {
  --edit-accent: rgba(99, 102, 241, 0.9);
}

.edit-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 16px;
  flex-wrap: wrap;
}

.edit-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.edit-card-number {
  font-size: 1.25rem;
  font-weight: 900;
  color: var(--edit-accent);
}

.edit-type-tag {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  font-weight: 700;
}

.edit-header-right {
  display: flex;
  align-items: center;
}

.deck-select-compact {
  width: 180px;
}

.edit-card-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 768px) {
  .edit-card-content {
    grid-template-columns: 1fr;
  }
  .edit-dialog-header {
    flex-direction: column;
    align-items: flex-start;
  }
}

.edit-field {
  display: flex;
  flex-direction: column;
}

.edit-field-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 800;
  font-size: 14px;
  margin-bottom: 10px;
  color: rgba(255, 255, 255, 0.85);
}

.edit-field-header i {
  color: var(--edit-accent);
  font-size: 15px;
}

/* Edit Card QuillEditor */
.edit-card-quill {
  min-height: 180px;
  height: auto;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(0, 0, 0, 0.15);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.edit-card-quill:focus-within {
  border-color: var(--edit-accent);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.edit-card-quill :deep(.ql-toolbar) {
  border: none;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.03);
  padding: 6px 8px;
  flex-shrink: 0;
}

.edit-card-quill :deep(.ql-container) {
  border: none;
  min-height: 120px;
  flex: 1;
  font-size: 14px;
  display: flex;
  flex-direction: column;
}

.edit-card-quill :deep(.ql-editor) {
  min-height: 120px;
  height: auto;
  flex: 1;
  padding: 12px 14px;
  overflow-y: auto;
}

.edit-card-quill :deep(.ql-editor.ql-blank::before) {
  font-style: normal;
  color: rgba(148, 163, 184, 0.5);
}

/* AI Rewrite Section */
.edit-ai-section {
  margin-top: 20px;
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(99, 102, 241, 0.06);
  border: 1px solid rgba(99, 102, 241, 0.15);
}

.edit-ai-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 13px;
  margin-bottom: 12px;
  color: rgba(255, 255, 255, 0.7);
}

.edit-ai-header i {
  color: #fbbf24;
  font-size: 14px;
}

.edit-ai-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Edit Footer */
.edit-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.edit-footer-left {
  display: flex;
}

.edit-footer-right {
  display: flex;
  gap: 8px;
}
</style>
