<!-- frontend/src/components/modals/CustomInstructionDialog.vue -->
<script setup>
import { ref, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'

const props = defineProps({
  visible: Boolean,
  initialInstruction: {
    type: String,
    default: ''
  }
})

const emit = defineEmits([
  'update:visible',
  'confirm'
])

// Local state
const instruction = ref('')

// Reset instruction when dialog opens
watch(() => props.visible, (visible) => {
  if (visible) {
    instruction.value = props.initialInstruction || ''
  }
})

function close() {
  emit('update:visible', false)
}

function confirm() {
  emit('confirm', instruction.value.trim())
  instruction.value = ''
  close()
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    header="Instrução Customizada"
    modal
    appendTo="body"
    class="modern-dialog"
    style="width: min(640px, 96vw);"
  >
    <div class="mb-3">
      <label class="font-semibold">Instrução para o LLM (opcional)</label>
      <Textarea
        v-model="instruction"
        autoResize
        class="w-full mt-2"
        rows="4"
        placeholder="Ex: Foque em conceitos técnicos, use linguagem formal..."
      />
      <small class="text-color-secondary mt-2 block">
        Deixe em branco para usar o contexto padrão do documento.
      </small>
    </div>

    <template #footer>
      <Button label="Cancelar" severity="secondary" outlined @click="close" />
      <Button label="Gerar" icon="pi pi-bolt" @click="confirm" />
    </template>
  </Dialog>
</template>
