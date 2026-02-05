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
  'update:cardType',
  'confirm',
  'customPromptsUpdate'
])

// Internal state
const generateStep = ref('1')
const quantityMode = ref('auto')
const customPrompts = ref(null)

// Local card type value
const localCardType = ref(props.cardType || 'basic')

// Constants
const quantityModeOptions = [
  { label: 'Automático', value: 'auto', icon: 'pi pi-sparkles' },
  { label: 'Manual', value: 'manual', icon: 'pi pi-sliders-v' }
]
const presetOptions = [5, 10, 15, 20, 30]

// Card type options with icons
const cardTypeOptions = [
  {
    label: 'Básicos',
    value: 'basic',
    description: 'Cartões com frente e verso simples',
    icon: 'pi pi-file'
  },
  {
    label: 'Cloze',
    value: 'cloze',
    description: 'Cartões com lacunas para preencher',
    icon: 'pi pi-pencil'
  },
  {
    label: 'Básicos + Cloze',
    value: 'both',
    description: 'Gerar ambos os tipos de cartão',
    icon: 'pi pi-th-large'
  }
]

// Local num cards value
const localNumCards = ref(props.numCardsSlider)

// Sync local state with props
watch(() => props.numCardsSlider, (val) => {
  localNumCards.value = val
})

watch(() => props.cardType, (val) => {
  localCardType.value = val || 'basic'
})

// When modal opens, reset state
watch(() => props.visible, (visible) => {
  if (visible) {
    generateStep.value = '1'
    quantityMode.value = props.numCardsEnabled ? 'manual' : 'auto'
    localNumCards.value = props.numCardsSlider
    localCardType.value = props.cardType || 'basic'
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
  emit('update:cardType', localCardType.value)
  emit('confirm', {
    quantityMode: quantityMode.value,
    numCards: localNumCards.value,
    cardType: localCardType.value,
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
        <!-- STEP 1: Tipo e Quantidade -->
        <StepPanel value="1">
          <div class="flex flex-column gap-4 p-3">
            <!-- Seleção de Tipo de Cartão -->
            <div class="text-center">
              <h4 class="m-0 mb-2">Tipo de Cartão</h4>
              <p class="text-color-secondary m-0 text-sm">
                Selecione o formato dos cards
              </p>
            </div>

            <div class="card-type-selector">
              <div
                v-for="option in cardTypeOptions"
                :key="option.value"
                class="card-type-option"
                :class="{ 'selected': localCardType === option.value }"
                @click="localCardType = option.value"
              >
                <div class="card-type-icon">
                  <i :class="option.icon" />
                </div>
                <div class="card-type-content">
                  <span class="card-type-label">{{ option.label }}</span>
                  <span class="card-type-desc">{{ option.description }}</span>
                </div>
                <div class="card-type-check" v-if="localCardType === option.value">
                  <i class="pi pi-check" />
                </div>
              </div>
            </div>

            <!-- Separador -->
            <div class="separator"></div>

            <!-- Seleção de Quantidade -->
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

/* Separator */
.separator {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(148, 163, 184, 0.15) 50%, transparent 100%);
  margin: 0.5rem 0;
}

/* Card Type Selector */
.card-type-selector {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.card-type-option {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(15, 23, 42, 0.5);
  cursor: pointer;
  transition: all 0.25s ease;
}

.card-type-option:hover {
  border-color: rgba(99, 102, 241, 0.3);
  background: rgba(99, 102, 241, 0.08);
}

.card-type-option.selected {
  border-color: rgba(99, 102, 241, 0.5);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.card-type-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(99, 102, 241, 0.08);
  color: #6366f1;
  font-size: 1.25rem;
  transition: all 0.25s ease;
}

.card-type-option.selected .card-type-icon {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}

.card-type-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.card-type-label {
  font-weight: 600;
  font-size: 0.95rem;
  color: rgba(255, 255, 255, 0.9);
}

.card-type-desc {
  font-size: 0.8rem;
  color: rgba(148, 163, 184, 0.8);
}

.card-type-check {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
  font-size: 0.7rem;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
}
</style>
