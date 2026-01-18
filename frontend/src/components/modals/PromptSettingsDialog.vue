<!-- frontend/src/components/modals/PromptSettingsDialog.vue -->
<script setup>
import { ref, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import PromptEditor from '@/components/PromptEditor.vue'

const props = defineProps({
  visible: Boolean,
  cardType: {
    type: String,
    default: 'basic'
  },
  savedPrompts: {
    type: Object,
    default: null
  },
  hasCustomPrompts: Boolean
})

const emit = defineEmits([
  'update:visible',
  'save',
  'reset'
])

// Local state
const promptEditorRef = ref(null)
const pendingPrompts = ref(null)

// Reset pending prompts when dialog opens
watch(() => props.visible, (visible) => {
  if (visible) {
    pendingPrompts.value = props.savedPrompts ? { ...props.savedPrompts } : null
  }
})

// Track prompt changes from editor
function onPromptUpdate(prompts) {
  pendingPrompts.value = prompts
}

// Actions
function close() {
  emit('update:visible', false)
}

function save() {
  emit('save', pendingPrompts.value)
  close()
}

function reset() {
  emit('reset')
  close()
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    header="Prompts de Geração"
    modal
    class="modern-dialog"
    style="width: min(860px, 96vw);"
  >
    <div class="prompt-settings-info mb-3">
      <div class="flex align-items-center gap-2 mb-2">
        <i class="pi pi-info-circle text-primary" />
        <span class="font-semibold">Personalize os prompts de geração de flashcards</span>
      </div>
      <p class="text-color-secondary text-sm m-0">
        Os prompts salvos aqui serão usados automaticamente em todas as gerações futuras.
        <br />
        No modal de geração, você ainda pode fazer ajustes temporários que não afetam os salvos.
      </p>
    </div>

    <div v-if="hasCustomPrompts" class="saved-indicator mb-3">
      <Tag severity="success" class="pill">
        <i class="pi pi-check-circle mr-2" />
        Prompts personalizados ativos
      </Tag>
    </div>

    <PromptEditor
      ref="promptEditorRef"
      :cardType="cardType"
      :initialPrompts="savedPrompts"
      mode="settings"
      @update:customPrompts="onPromptUpdate"
    />

    <template #footer>
      <div class="flex justify-content-between w-full">
        <Button
          v-if="hasCustomPrompts"
          label="Restaurar Padrões"
          icon="pi pi-refresh"
          severity="warning"
          outlined
          @click="reset"
        />
        <div v-else></div>

        <div class="flex gap-2">
          <Button label="Cancelar" severity="secondary" outlined @click="close" />
          <Button
            label="Salvar Prompts"
            icon="pi pi-save"
            @click="save"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.prompt-settings-info {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.15);
}

.saved-indicator .pill {
  border-radius: 20px;
}
</style>
