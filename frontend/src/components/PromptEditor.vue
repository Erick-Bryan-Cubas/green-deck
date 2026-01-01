<template>
  <div class="prompt-editor">
    <!-- Toggle para ativar/desativar prompts customizados -->
    <div class="flex align-items-center gap-2 mb-3">
      <Checkbox v-model="useCustomPrompts" :binary="true" inputId="useCustom" />
      <label for="useCustom" class="cursor-pointer">
        <i class="pi pi-pencil mr-1" />
        Usar prompts personalizados
      </label>
      <Button 
        v-if="useCustomPrompts && hasChanges"
        icon="pi pi-refresh" 
        severity="secondary" 
        text 
        size="small"
        v-tooltip.top="'Restaurar padrões'"
        @click="resetToDefaults"
      />
    </div>

    <!-- Accordion com as seções de prompts -->
    <Accordion v-if="useCustomPrompts" :multiple="true" :activeIndex="activeIndices">
      <!-- System Prompt -->
      <AccordionTab>
        <template #header>
          <div class="flex align-items-center gap-2">
            <i class="pi pi-cog" />
            <span>System Prompt</span>
            <Tag v-if="isSystemModified" severity="warning" value="modificado" class="ml-2" />
          </div>
        </template>
        <div class="prompt-section">
          <small class="text-color-secondary block mb-2">
            Define o comportamento base do modelo. Varia conforme o tipo de card selecionado.
          </small>
          <Textarea 
            v-model="customSystemPrompt" 
            autoResize 
            class="w-full font-mono text-sm"
            rows="4"
            :placeholder="defaultPrompts?.system?.basic || 'Carregando...'"
          />
        </div>
      </AccordionTab>

      <!-- Guidelines -->
      <AccordionTab>
        <template #header>
          <div class="flex align-items-center gap-2">
            <i class="pi pi-list-check" />
            <span>Diretrizes de Qualidade</span>
            <Tag v-if="isGuidelinesModified" severity="warning" value="modificado" class="ml-2" />
          </div>
        </template>
        <div class="prompt-section">
          <small class="text-color-secondary block mb-2">
            Regras de qualidade para criação dos flashcards (SuperMemo + Justin Sung).
          </small>
          <Textarea 
            v-model="customGuidelines" 
            autoResize 
            class="w-full font-mono text-sm"
            rows="8"
            :placeholder="defaultPrompts?.guidelines?.default || 'Carregando...'"
          />
        </div>
      </AccordionTab>

      <!-- Prompt de Geração (avançado) -->
      <AccordionTab>
        <template #header>
          <div class="flex align-items-center gap-2">
            <i class="pi pi-code" />
            <span>Template de Geração</span>
            <Tag severity="secondary" value="avançado" class="ml-2" />
            <Tag v-if="isGenerationModified" severity="warning" value="modificado" class="ml-2" />
          </div>
        </template>
        <div class="prompt-section">
          <small class="text-color-secondary block mb-2">
            Template principal de geração. Variáveis disponíveis: 
            <code>${"${src}"}</code>, <code>${"${ctx_block}"}</code>, <code>${"${guidelines}"}</code>, 
            <code>${"${target_min}"}</code>, <code>${"${target_max}"}</code>, 
            <code>${"${type_instruction}"}</code>, <code>${"${format_block}"}</code>, <code>${"${checklist_block}"}</code>
          </small>
          <Textarea 
            v-model="customGenerationPrompt" 
            autoResize 
            class="w-full font-mono text-sm"
            rows="12"
            :placeholder="defaultPrompts?.generation?.default || 'Carregando...'"
          />
        </div>
      </AccordionTab>
    </Accordion>

    <!-- Preview do que será usado -->
    <div v-if="useCustomPrompts" class="mt-3 p-3 surface-ground border-round">
      <div class="flex align-items-center gap-2 mb-2">
        <i class="pi pi-info-circle text-primary" />
        <span class="font-semibold text-sm">O que será usado:</span>
      </div>
      <ul class="text-sm text-color-secondary m-0 pl-4">
        <li>System: {{ isSystemModified ? 'Customizado' : 'Padrão' }}</li>
        <li>Diretrizes: {{ isGuidelinesModified ? 'Customizadas' : 'Padrão' }}</li>
        <li>Template: {{ isGenerationModified ? 'Customizado' : 'Padrão' }}</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import Checkbox from 'primevue/checkbox'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import Accordion from 'primevue/accordion'
import AccordionTab from 'primevue/accordiontab'
import Tag from 'primevue/tag'
import { getDefaultPrompts } from '@/services/api.js'

const props = defineProps({
  cardType: {
    type: String,
    default: 'basic'
  }
})

const emit = defineEmits(['update:customPrompts'])

// Estado
const useCustomPrompts = ref(false)
const defaultPrompts = ref(null)
const isLoading = ref(false)
const activeIndices = ref([])

// Prompts customizados
const customSystemPrompt = ref('')
const customGuidelines = ref('')
const customGenerationPrompt = ref('')

// Computed: verifica se algo foi modificado
const isSystemModified = computed(() => {
  if (!defaultPrompts.value?.system) return false
  const defaultVal = defaultPrompts.value.system[props.cardType] || defaultPrompts.value.system.basic
  return customSystemPrompt.value.trim() !== '' && customSystemPrompt.value.trim() !== defaultVal.trim()
})

const isGuidelinesModified = computed(() => {
  if (!defaultPrompts.value?.guidelines?.default) return false
  return customGuidelines.value.trim() !== '' && customGuidelines.value.trim() !== defaultPrompts.value.guidelines.default.trim()
})

const isGenerationModified = computed(() => {
  if (!defaultPrompts.value?.generation?.default) return false
  return customGenerationPrompt.value.trim() !== '' && customGenerationPrompt.value.trim() !== defaultPrompts.value.generation.default.trim()
})

const hasChanges = computed(() => {
  return isSystemModified.value || isGuidelinesModified.value || isGenerationModified.value
})

// Carrega prompts padrão do servidor
async function loadDefaultPrompts() {
  if (defaultPrompts.value) return // Já carregado
  
  isLoading.value = true
  try {
    defaultPrompts.value = await getDefaultPrompts()
  } catch (error) {
    console.error('Erro ao carregar prompts padrão:', error)
  } finally {
    isLoading.value = false
  }
}

// Reseta para os padrões
function resetToDefaults() {
  customSystemPrompt.value = ''
  customGuidelines.value = ''
  customGenerationPrompt.value = ''
}

// Emite os prompts customizados quando mudam
watch([useCustomPrompts, customSystemPrompt, customGuidelines, customGenerationPrompt], () => {
  if (!useCustomPrompts.value) {
    emit('update:customPrompts', null)
    return
  }
  
  const prompts = {}
  
  if (customSystemPrompt.value.trim()) {
    prompts.systemPrompt = customSystemPrompt.value.trim()
  }
  if (customGuidelines.value.trim()) {
    prompts.guidelines = customGuidelines.value.trim()
  }
  if (customGenerationPrompt.value.trim()) {
    prompts.generationPrompt = customGenerationPrompt.value.trim()
  }
  
  // Só emite se houver algo customizado
  if (Object.keys(prompts).length > 0) {
    emit('update:customPrompts', prompts)
  } else {
    emit('update:customPrompts', null)
  }
}, { deep: true })

// Carrega prompts quando ativar customização
watch(useCustomPrompts, (val) => {
  if (val) {
    loadDefaultPrompts()
  }
})

onMounted(() => {
  // Pré-carrega os prompts padrão
  loadDefaultPrompts()
})
</script>

<style scoped>
.prompt-editor {
  padding: 0.5rem 0;
}

.prompt-section {
  padding: 0.5rem 0;
}

.font-mono {
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
}

:deep(.p-accordion-header-link) {
  padding: 0.75rem 1rem;
}

:deep(.p-accordion-content) {
  padding: 0.75rem 1rem;
}

:deep(.p-textarea) {
  line-height: 1.5;
}

code {
  background: var(--surface-100);
  padding: 0.1rem 0.3rem;
  border-radius: 4px;
  font-size: 0.85em;
}
</style>
