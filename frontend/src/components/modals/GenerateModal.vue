<!-- frontend/src/components/modals/GenerateModal.vue -->
<script setup>
import { ref, computed, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Stepper from 'primevue/stepper'
import StepList from 'primevue/steplist'
import StepPanels from 'primevue/steppanels'
import Step from 'primevue/step'
import StepPanel from 'primevue/steppanel'
import SelectButton from 'primevue/selectbutton'
import InputNumber from 'primevue/inputnumber'
import Slider from 'primevue/slider'
import PromptEditor from '@/components/PromptEditor.vue'

const props = defineProps({
  visible: Boolean,
  selectedModel: String,
  currentModelInfo: Object,
  generating: Boolean,
  cardType: String,
  numCardsEnabled: Boolean,
  numCardsSlider: {
    type: Number,
    default: 10
  },
  // Helper functions passed from parent
  getModelInfo: Function,
  getProviderSeverity: Function,
  getProviderLabel: Function
})

const emit = defineEmits([
  'update:visible',
  'update:numCardsSlider',
  'confirm',
  'customPromptsUpdate'
])

// Internal state
const generateStep = ref('1')
const quantityMode = ref('auto')
const customPrompts = ref(null)

// Constants
const quantityModeOptions = [
  { label: 'Automático', value: 'auto', icon: 'pi pi-sparkles' },
  { label: 'Manual', value: 'manual', icon: 'pi pi-sliders-v' }
]
const presetOptions = [5, 10, 15, 20, 30]

// Local num cards value
const localNumCards = ref(props.numCardsSlider)

// Sync local state with prop
watch(() => props.numCardsSlider, (val) => {
  localNumCards.value = val
})

// When modal opens, reset state
watch(() => props.visible, (visible) => {
  if (visible) {
    generateStep.value = '1'
    quantityMode.value = props.numCardsEnabled ? 'manual' : 'auto'
    localNumCards.value = props.numCardsSlider
    customPrompts.value = null
  }
})

// Computed
const isOllamaModel = computed(() => {
  if (!props.getModelInfo || !props.selectedModel) return false
  return props.getModelInfo(props.selectedModel)?.provider === 'ollama'
})

const modelInfo = computed(() => {
  if (!props.getModelInfo || !props.selectedModel) return null
  return props.getModelInfo(props.selectedModel)
})

// Methods
function onCustomPromptsUpdate(prompts) {
  customPrompts.value = prompts
  emit('customPromptsUpdate', prompts)
}

function close() {
  emit('update:visible', false)
}

function confirm() {
  emit('update:numCardsSlider', localNumCards.value)
  emit('confirm', {
    quantityMode: quantityMode.value,
    numCards: localNumCards.value,
    customPrompts: customPrompts.value
  })
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    modal
    appendTo="body"
    :draggable="false"
    :dismissableMask="true"
    class="modern-dialog"
    :style="{ width: 'min(640px, 96vw)' }"
  >
    <template #header>
      <div class="flex align-items-center justify-content-between w-full">
        <div class="flex align-items-center gap-2">
          <i class="pi pi-bolt text-primary" style="font-size: 1.25rem" />
          <span class="font-semibold text-lg">Configurar Geração</span>
        </div>
        <!-- GPU/CPU Badge no header -->
        <div v-if="currentModelInfo && isOllamaModel" class="flex align-items-center">
          <Tag :severity="currentModelInfo.using_gpu ? 'success' : 'warning'" class="pill">
            <i :class="currentModelInfo.using_gpu ? 'pi pi-bolt' : 'pi pi-desktop'" class="mr-1" />
            {{ currentModelInfo.using_gpu ? 'GPU' : 'CPU' }}
          </Tag>
        </div>
      </div>
    </template>

    <!-- Model Info Panel -->
    <div v-if="selectedModel" class="model-info-panel surface-ground border-round p-3 mb-3">
      <div class="flex align-items-center justify-content-between">
        <div class="flex align-items-center gap-2">
          <i class="pi pi-microchip text-primary" />
          <div>
            <div class="font-semibold">{{ selectedModel }}</div>
            <div class="text-sm text-color-secondary" v-if="modelInfo">
              <Tag :severity="getProviderSeverity(modelInfo.provider)" class="pill mr-2">
                {{ getProviderLabel(modelInfo.provider) }}
              </Tag>
            </div>
          </div>
        </div>

        <!-- GPU/VRAM Info (apenas Ollama) -->
        <div v-if="currentModelInfo && isOllamaModel" class="text-right">
          <div class="flex align-items-center gap-2 justify-content-end">
            <i :class="currentModelInfo.using_gpu ? 'pi pi-bolt text-green-500' : 'pi pi-desktop text-yellow-500'" />
            <span class="font-medium">
              {{ currentModelInfo.using_gpu ? 'GPU' : 'CPU' }}
            </span>
          </div>
          <div v-if="currentModelInfo.size_vram_mb > 0" class="text-sm text-color-secondary">
            VRAM: {{ currentModelInfo.size_vram_mb }} MB
          </div>
        </div>
      </div>

      <!-- ALERTA CPU -->
      <Message v-if="currentModelInfo && !currentModelInfo.using_gpu && isOllamaModel" severity="warn" :closable="false" class="mt-3 mb-0">
        <div class="flex align-items-center gap-2">
          <i class="pi pi-exclamation-triangle" />
          <span>Processamento via CPU pode ser significativamente mais lento.</span>
        </div>
      </Message>
    </div>

    <!-- Aviso se nenhum modelo selecionado -->
    <Message v-if="!selectedModel" severity="error" :closable="false" class="mb-3">
      <div class="flex align-items-center gap-2">
        <i class="pi pi-times-circle" />
        <span>Nenhum modelo selecionado. Configure um modelo em <strong>Configurações → Modelos</strong>.</span>
      </div>
    </Message>

    <Stepper v-model:value="generateStep" class="generate-stepper">
      <StepList>
        <Step value="1">Quantidade</Step>
        <Step value="2">Prompts</Step>
      </StepList>
      <StepPanels>
        <!-- STEP 1: Quantidade -->
        <StepPanel value="1">
          <div class="flex flex-column gap-4 p-3">
            <div class="text-center">
              <h4 class="m-0 mb-2">Quantos cards criar?</h4>
              <p class="text-color-secondary m-0 text-sm">
                Escolha o modo de definição
              </p>
            </div>

            <SelectButton
              v-model="quantityMode"
              :options="quantityModeOptions"
              optionLabel="label"
              optionValue="value"
              class="w-full justify-content-center"
            />

            <Transition name="slide-fade">
              <div v-if="quantityMode === 'manual'" class="flex flex-column gap-3">
                <div class="flex align-items-center justify-content-center gap-3">
                  <InputNumber
                    v-model="localNumCards"
                    :min="1"
                    :max="50"
                    showButtons
                    buttonLayout="horizontal"
                    :inputStyle="{ width: '4rem', textAlign: 'center', fontWeight: 'bold', fontSize: '1.25rem' }"
                  >
                    <template #decrementbuttonicon>
                      <i class="pi pi-minus" />
                    </template>
                    <template #incrementbuttonicon>
                      <i class="pi pi-plus" />
                    </template>
                  </InputNumber>
                  <span class="text-color-secondary font-medium">cards</span>
                </div>

                <Slider v-model="localNumCards" :min="1" :max="50" class="w-full" />

                <div class="flex justify-content-center gap-2 flex-wrap">
                  <Button
                    v-for="preset in presetOptions"
                    :key="preset"
                    :label="String(preset)"
                    :outlined="localNumCards !== preset"
                    :severity="localNumCards === preset ? undefined : 'secondary'"
                    size="small"
                    @click="localNumCards = preset"
                  />
                </div>
              </div>
            </Transition>

            <div v-if="quantityMode === 'auto'" class="surface-ground border-round p-3 text-center">
              <i class="pi pi-info-circle text-primary mr-2" />
              <span class="text-color-secondary text-sm">
                A IA calculará automaticamente baseado no texto
              </span>
            </div>
          </div>
        </StepPanel>

        <!-- STEP 2: Prompts -->
        <StepPanel value="2">
          <div class="flex flex-column gap-3 p-3">
            <div class="flex align-items-center justify-content-between mb-2">
              <span class="font-medium">Instruções de Geração</span>
              <Tag
                :severity="customPrompts ? 'warning' : 'secondary'"
                :value="customPrompts ? 'Customizado' : 'Padrão'"
                :icon="customPrompts ? 'pi pi-pencil' : 'pi pi-check'"
              />
            </div>
            <PromptEditor
              :cardType="cardType"
              @update:customPrompts="onCustomPromptsUpdate"
            />
          </div>
        </StepPanel>
      </StepPanels>
    </Stepper>

    <template #footer>
      <div class="flex justify-content-between w-full">
        <Button
          v-if="generateStep === '1'"
          label="Cancelar"
          severity="secondary"
          text
          @click="close"
        />
        <Button
          v-else
          label="Voltar"
          icon="pi pi-arrow-left"
          severity="secondary"
          text
          @click="generateStep = '1'"
        />

        <Button
          v-if="generateStep === '1'"
          label="Próximo"
          icon="pi pi-arrow-right"
          iconPos="right"
          @click="generateStep = '2'"
        />
        <Button
          v-else
          label="Gerar Cards"
          icon="pi pi-bolt"
          severity="success"
          :loading="generating"
          @click="confirm"
        />
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
/* Generate Stepper Styles */
:deep(.generate-stepper) {
  margin: -1rem;
}

:deep(.generate-stepper .p-stepper-list) {
  padding: 1rem;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(139, 92, 246, 0.04) 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

:deep(.generate-stepper .p-stepper-panels) {
  padding: 1rem;
}

/* Transition for slider */
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.25s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* Model info panel */
.model-info-panel {
  border: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
