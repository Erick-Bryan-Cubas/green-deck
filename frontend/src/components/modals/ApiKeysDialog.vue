<!-- frontend/src/components/modals/ApiKeysDialog.vue -->
<script setup>
import { ref, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Checkbox from 'primevue/checkbox'

const props = defineProps({
  visible: Boolean,
  storedKeys: {
    type: Object,
    default: () => ({})
  },
  hasStoredKeys: Boolean
})

const emit = defineEmits([
  'update:visible',
  'save',
  'clear'
])

// Local state
const anthropicApiKey = ref('')
const openaiApiKey = ref('')
const perplexityApiKey = ref('')
const storeLocally = ref(true)
const anthropicApiKeyError = ref('')

// Initialize local state when dialog opens
watch(() => props.visible, (visible) => {
  if (visible) {
    anthropicApiKey.value = props.storedKeys.anthropicApiKey || ''
    openaiApiKey.value = props.storedKeys.openaiApiKey || ''
    perplexityApiKey.value = props.storedKeys.perplexityApiKey || ''
    anthropicApiKeyError.value = ''
  }
}, { immediate: true })

// Actions
function close() {
  emit('update:visible', false)
}

function saveKeys() {
  const aKey = anthropicApiKey.value.trim()
  const oKey = openaiApiKey.value.trim()
  const pKey = perplexityApiKey.value.trim()

  // Validate Anthropic key format
  if (aKey && !aKey.startsWith('sk-ant-')) {
    anthropicApiKeyError.value = 'Chave inválida: deve começar com sk-ant-'
    return
  }

  emit('save', {
    anthropicApiKey: aKey,
    openaiApiKey: oKey,
    perplexityApiKey: pKey,
    storeLocally: storeLocally.value
  })
  close()
}

function clearKeys() {
  emit('clear')
  anthropicApiKey.value = ''
  openaiApiKey.value = ''
  perplexityApiKey.value = ''
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    header="Configurar Chaves de API"
    modal
    class="modern-dialog"
    style="width: min(760px, 96vw);"
  >
    <div class="api-info surface-ground border-round p-3 mb-3">
      <div class="flex align-items-start gap-2">
        <i class="pi pi-info-circle text-primary mt-1" />
        <div>
          <span class="font-semibold">Chaves de API são opcionais</span>
          <p class="text-color-secondary text-sm m-0 mt-1">
            Se você possui modelos locais no Ollama, não é necessário configurar chaves de API.
            As chaves são armazenadas apenas no seu navegador e nunca são enviadas a servidores externos.
          </p>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="col-12">
        <label class="font-semibold">Chave Claude (Anthropic) <span class="opt">(Opcional)</span></label>
        <InputText v-model="anthropicApiKey" class="w-full" placeholder="sk-ant-api03-..." autocomplete="off" />
        <small class="text-color-secondary">Obtenha em console.anthropic.com/keys</small>
        <div v-if="anthropicApiKeyError" class="err">{{ anthropicApiKeyError }}</div>
      </div>

      <div class="col-12 mt-3">
        <label class="font-semibold">Chave OpenAI <span class="opt">(Opcional)</span></label>
        <InputText v-model="openaiApiKey" class="w-full" placeholder="sk-..." autocomplete="off" />
        <small class="text-color-secondary">Obtenha em platform.openai.com/api-keys</small>
      </div>

      <div class="col-12 mt-3">
        <label class="font-semibold">Chave Perplexity <span class="opt">(Opcional)</span></label>
        <InputText v-model="perplexityApiKey" class="w-full" placeholder="pplx-..." autocomplete="off" />
        <small class="text-color-secondary">Obtenha em perplexity.ai/settings/api</small>
      </div>

      <div class="col-12 mt-3 flex align-items-center gap-2">
        <Checkbox v-model="storeLocally" :binary="true" />
        <label>Lembrar chaves neste dispositivo</label>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-content-between w-full">
        <Button
          v-if="hasStoredKeys"
          label="Limpar Chaves"
          icon="pi pi-trash"
          severity="danger"
          outlined
          @click="clearKeys"
        />
        <div v-else></div>
        <div class="flex gap-2">
          <Button label="Cancelar" severity="secondary" outlined @click="close" />
          <Button label="Salvar" icon="pi pi-save" @click="saveKeys" />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.opt {
  font-weight: 400;
  font-size: 0.85rem;
  color: rgba(148, 163, 184, 0.7);
}

.err {
  color: #ef4444;
  font-size: 0.85rem;
  margin-top: 0.25rem;
}
</style>
