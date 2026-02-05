<!-- frontend/src/components/modals/QuestionGenerateModal.vue -->
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
import Textarea from 'primevue/textarea'
import InputText from 'primevue/inputtext'
import RadioButton from 'primevue/radiobutton'

const props = defineProps({
  visible: Boolean,
  selectedModel: String,
  currentModelInfo: Object,
  generating: Boolean,
  hasSelectedText: Boolean,
  selectedTextLength: {
    type: Number,
    default: 0
  },
  fullTextLength: {
    type: Number,
    default: 0
  },
  // Helper functions passed from parent
  getModelInfo: Function,
  getProviderSeverity: Function,
  getProviderLabel: Function
})

const emit = defineEmits([
  'update:visible',
  'generate',
  'parse'
])

// Internal state
const currentStep = ref('1')
const inputMode = ref('generate')  // 'generate' | 'paste'
const pastedText = ref('')
const textSource = ref('selection') // 'selection' | 'full'
const questionType = ref('mixed')
const quantityMode = ref('auto')
const localNumQuestions = ref(5)
const domain = ref('')

// Constants
const inputModeOptions = [
  { label: 'Gerar do Texto', value: 'generate', icon: 'pi pi-sparkles' },
  { label: 'Colar Questões', value: 'paste', icon: 'pi pi-file-edit' }
]

const questionTypeOptions = [
  { value: 'kprim', label: 'Kprim', description: '4 afirmativas V/F independentes' },
  { value: 'mc', label: 'Múltipla Escolha', description: 'Várias alternativas corretas' },
  { value: 'sc', label: 'Escolha Única', description: 'Uma alternativa correta' },
  { value: 'mixed', label: 'Misto (Recomendado)', description: 'IA decide o melhor tipo' }
]

const quantityModeOptions = [
  { label: 'Automático', value: 'auto', icon: 'pi pi-sparkles' },
  { label: 'Manual', value: 'manual', icon: 'pi pi-sliders-v' }
]

const presetOptions = [3, 5, 10, 15, 20]

// Computed
const isOllamaModel = computed(() => {
  if (!props.getModelInfo || !props.selectedModel) return false
  return props.getModelInfo(props.selectedModel)?.provider === 'ollama'
})

const modelInfo = computed(() => {
  if (!props.getModelInfo || !props.selectedModel) return null
  return props.getModelInfo(props.selectedModel)
})

const canProceedStep1 = computed(() => {
  if (inputMode.value === 'paste') {
    return pastedText.value.trim().length > 50
  }
  // Generate mode
  if (textSource.value === 'selection') {
    return props.hasSelectedText && props.selectedTextLength > 50
  }
  return props.fullTextLength > 50
})

const canProceedStep2 = computed(() => {
  return questionType.value !== null
})

// Watch for modal open/close
watch(() => props.visible, (visible) => {
  if (visible) {
    // Reset state
    currentStep.value = '1'
    inputMode.value = 'generate'
    pastedText.value = ''
    textSource.value = props.hasSelectedText ? 'selection' : 'full'
    questionType.value = 'mixed'
    quantityMode.value = 'auto'
    localNumQuestions.value = 5
    domain.value = ''
  }
})

// Methods
function close() {
  emit('update:visible', false)
}

function confirm() {
  if (inputMode.value === 'paste') {
    emit('parse', {
      text: pastedText.value,
      model: props.selectedModel
    })
  } else {
    emit('generate', {
      textSource: textSource.value,
      questionType: questionType.value,
      numQuestions: quantityMode.value === 'manual' ? localNumQuestions.value : null,
      domain: domain.value || null,
      model: props.selectedModel
    })
  }
}

function formatWordCount(chars) {
  const words = Math.round(chars / 5)
  return `~${words} palavras`
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
    :style="{ width: 'min(720px, 96vw)' }"
  >
    <template #header>
      <div class="flex align-items-center justify-content-between w-full">
        <div class="flex align-items-center gap-2">
          <i class="pi pi-question-circle text-primary" style="font-size: 1.25rem" />
          <span class="font-semibold text-lg">Gerar Questões</span>
          <Tag severity="info" class="pill">AllInOne</Tag>
        </div>
        <!-- GPU/CPU Badge -->
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
      </div>

      <Message v-if="currentModelInfo && !currentModelInfo.using_gpu && isOllamaModel" severity="warn" :closable="false" class="mt-3 mb-0">
        <div class="flex align-items-center gap-2">
          <i class="pi pi-exclamation-triangle" />
          <span>Processamento via CPU pode ser mais lento.</span>
        </div>
      </Message>
    </div>

    <!-- No model warning -->
    <Message v-if="!selectedModel" severity="error" :closable="false" class="mb-3">
      <div class="flex align-items-center gap-2">
        <i class="pi pi-times-circle" />
        <span>Nenhum modelo selecionado. Configure em <strong>Configurações</strong>.</span>
      </div>
    </Message>

    <Stepper v-model:value="currentStep" class="question-stepper">
      <StepList>
        <Step value="1">Fonte</Step>
        <Step value="2">Tipo</Step>
        <Step value="3">Opções</Step>
      </StepList>

      <StepPanels>
        <!-- STEP 1: Input Source -->
        <StepPanel value="1">
          <div class="flex flex-column gap-4 p-3">
            <div class="text-center">
              <h4 class="m-0 mb-2">Como deseja criar as questões?</h4>
            </div>

            <SelectButton
              v-model="inputMode"
              :options="inputModeOptions"
              optionLabel="label"
              optionValue="value"
              class="w-full justify-content-center"
            />

            <!-- Paste Mode -->
            <div v-if="inputMode === 'paste'" class="paste-section">
              <label class="block mb-2 font-medium">
                Cole suas questões (qualquer formato):
              </label>
              <Textarea
                v-model="pastedText"
                rows="8"
                class="w-full"
                placeholder="Cole aqui questões de PDFs, documentos, etc. A IA interpretará automaticamente..."
                autoResize
              />
              <small class="text-color-secondary">
                {{ pastedText.length }} caracteres
                <span v-if="pastedText.length < 50" class="text-yellow-500">
                  (mínimo 50 caracteres)
                </span>
              </small>
            </div>

            <!-- Generate Mode -->
            <div v-else class="generate-section">
              <label class="block mb-3 font-medium">Texto fonte:</label>

              <div class="flex flex-column gap-3">
                <div
                  class="source-option"
                  :class="{ selected: textSource === 'selection', disabled: !hasSelectedText }"
                  @click="hasSelectedText && (textSource = 'selection')"
                >
                  <RadioButton
                    v-model="textSource"
                    value="selection"
                    :disabled="!hasSelectedText"
                  />
                  <div class="source-info">
                    <span class="source-label">Texto selecionado</span>
                    <span v-if="hasSelectedText" class="source-meta">
                      {{ formatWordCount(selectedTextLength) }}
                    </span>
                    <span v-else class="source-meta text-yellow-500">
                      Nenhum texto selecionado
                    </span>
                  </div>
                </div>

                <div
                  class="source-option"
                  :class="{ selected: textSource === 'full', disabled: fullTextLength < 50 }"
                  @click="fullTextLength >= 50 && (textSource = 'full')"
                >
                  <RadioButton
                    v-model="textSource"
                    value="full"
                    :disabled="fullTextLength < 50"
                  />
                  <div class="source-info">
                    <span class="source-label">Texto completo</span>
                    <span v-if="fullTextLength >= 50" class="source-meta">
                      {{ formatWordCount(fullTextLength) }}
                    </span>
                    <span v-else class="source-meta text-yellow-500">
                      Texto insuficiente
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </StepPanel>

        <!-- STEP 2: Question Type -->
        <StepPanel value="2">
          <div class="flex flex-column gap-4 p-3">
            <div class="text-center">
              <h4 class="m-0 mb-2">Tipo de questão</h4>
              <p class="text-color-secondary m-0 text-sm">
                Escolha o formato das questões geradas
              </p>
            </div>

            <div class="type-options">
              <div
                v-for="opt in questionTypeOptions"
                :key="opt.value"
                class="type-option"
                :class="{ selected: questionType === opt.value }"
                @click="questionType = opt.value"
              >
                <RadioButton v-model="questionType" :value="opt.value" />
                <div class="type-info">
                  <span class="type-label">{{ opt.label }}</span>
                  <span class="type-desc">{{ opt.description }}</span>
                </div>
              </div>
            </div>
          </div>
        </StepPanel>

        <!-- STEP 3: Options -->
        <StepPanel value="3">
          <div class="flex flex-column gap-4 p-3">
            <div class="text-center">
              <h4 class="m-0 mb-2">Configurações</h4>
            </div>

            <!-- Quantity (only for generate mode) -->
            <div v-if="inputMode === 'generate'" class="quantity-section">
              <label class="block mb-2 font-medium">Quantidade de questões:</label>

              <SelectButton
                v-model="quantityMode"
                :options="quantityModeOptions"
                optionLabel="label"
                optionValue="value"
                class="w-full justify-content-center mb-3"
              />

              <Transition name="slide-fade">
                <div v-if="quantityMode === 'manual'" class="flex flex-column gap-3">
                  <div class="flex align-items-center justify-content-center gap-3">
                    <InputNumber
                      v-model="localNumQuestions"
                      :min="1"
                      :max="30"
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
                    <span class="text-color-secondary font-medium">questões</span>
                  </div>

                  <Slider v-model="localNumQuestions" :min="1" :max="30" class="w-full" />

                  <div class="flex justify-content-center gap-2 flex-wrap">
                    <Button
                      v-for="preset in presetOptions"
                      :key="preset"
                      :label="String(preset)"
                      :outlined="localNumQuestions !== preset"
                      :severity="localNumQuestions === preset ? undefined : 'secondary'"
                      size="small"
                      @click="localNumQuestions = preset"
                    />
                  </div>
                </div>
              </Transition>

              <div v-if="quantityMode === 'auto'" class="surface-ground border-round p-3 text-center">
                <i class="pi pi-info-circle text-primary mr-2" />
                <span class="text-color-secondary text-sm">
                  A IA calculará baseado no tamanho do texto
                </span>
              </div>
            </div>

            <!-- Domain -->
            <div class="domain-section">
              <label class="block mb-2 font-medium">
                Domínio/Categoria
                <span class="text-color-secondary font-normal">(opcional)</span>
              </label>
              <InputText
                v-model="domain"
                class="w-full"
                placeholder="Ex: Medicina, Direito, Concursos..."
              />
              <small class="text-color-secondary">
                Define o campo Domain das questões no Anki
              </small>
            </div>
          </div>
        </StepPanel>
      </StepPanels>
    </Stepper>

    <template #footer>
      <div class="flex justify-content-between w-full">
        <!-- Left button -->
        <Button
          v-if="currentStep === '1'"
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
          @click="currentStep = String(Number(currentStep) - 1)"
        />

        <!-- Right button -->
        <Button
          v-if="currentStep === '1'"
          label="Próximo"
          icon="pi pi-arrow-right"
          iconPos="right"
          :disabled="!canProceedStep1"
          @click="currentStep = '2'"
        />
        <Button
          v-else-if="currentStep === '2'"
          label="Próximo"
          icon="pi pi-arrow-right"
          iconPos="right"
          :disabled="!canProceedStep2"
          @click="currentStep = '3'"
        />
        <Button
          v-else
          :label="inputMode === 'paste' ? 'Interpretar Questões' : 'Gerar Questões'"
          icon="pi pi-sparkles"
          severity="success"
          :loading="generating"
          :disabled="!selectedModel"
          @click="confirm"
        />
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
/* Stepper Styles */
:deep(.question-stepper) {
  margin: -1rem;
}

:deep(.question-stepper .p-stepper-list) {
  padding: 1rem;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(139, 92, 246, 0.04) 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

:deep(.question-stepper .p-stepper-panels) {
  padding: 1rem;
}

/* Source Options */
.source-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: all 0.2s ease;
}

.source-option:hover:not(.disabled) {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.3);
}

.source-option.selected {
  background: rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.5);
}

.source-option.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.source-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.source-label {
  font-weight: 500;
}

.source-meta {
  font-size: 0.8rem;
  color: rgba(148, 163, 184, 0.7);
}

/* Type Options */
.type-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.type-option {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: all 0.2s ease;
}

.type-option:hover {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.3);
}

.type-option.selected {
  background: rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.5);
}

.type-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.type-label {
  font-weight: 600;
}

.type-desc {
  font-size: 0.8rem;
  color: rgba(148, 163, 184, 0.7);
}

/* Sections */
.paste-section,
.generate-section,
.quantity-section,
.domain-section {
  width: 100%;
}

/* Model info panel */
.model-info-panel {
  border: 1px solid rgba(255, 255, 255, 0.06);
}

/* Transitions */
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.25s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
