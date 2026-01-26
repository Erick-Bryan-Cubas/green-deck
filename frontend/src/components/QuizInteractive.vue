<!-- frontend/src/components/QuizInteractive.vue -->
<script setup>
import { ref, computed } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Checkbox from 'primevue/checkbox'
import RadioButton from 'primevue/radiobutton'
import ToggleButton from 'primevue/togglebutton'

const props = defineProps({
  question: {
    type: Object,
    required: true
  },
  compact: {
    type: Boolean,
    default: false
  },
  showActions: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['answered'])

// State
const selectedOptions = ref([])
const isAnswered = ref(false)

// Computed
const qtypeLabel = computed(() => {
  switch (props.question.qtype) {
    case 0: return 'Kprim'
    case 1: return 'MC'
    case 2: return 'SC'
    default: return 'Q'
  }
})

const qtypeSeverity = computed(() => {
  switch (props.question.qtype) {
    case 0: return 'info'
    case 1: return 'success'
    case 2: return 'warning'
    default: return 'secondary'
  }
})

const qtypeDescription = computed(() => {
  switch (props.question.qtype) {
    case 0: return 'Marque V ou F para cada afirmativa'
    case 1: return 'Marque todas as corretas'
    case 2: return 'Escolha uma alternativa'
    default: return ''
  }
})

const correctCount = computed(() => {
  if (!isAnswered.value) return 0
  const options = props.question.options || []
  let correct = 0

  if (props.question.qtype === 0) {
    // Kprim: verificar V/F
    for (let i = 0; i < options.length; i++) {
      const userSaidTrue = selectedOptions.value.includes(i)
      const isActuallyCorrect = options[i]?.isCorrect
      if (userSaidTrue === isActuallyCorrect) correct++
    }
  } else {
    // MC/SC: verificar seleções
    for (let i = 0; i < options.length; i++) {
      const userSelected = selectedOptions.value.includes(i)
      const isActuallyCorrect = options[i]?.isCorrect
      if (userSelected === isActuallyCorrect) correct++
    }
  }

  return correct
})

const totalOptions = computed(() => (props.question.options || []).length)

const isFullyCorrect = computed(() => correctCount.value === totalOptions.value)

const feedbackClass = computed(() => {
  if (!isAnswered.value) return ''
  return isFullyCorrect.value ? 'feedback-correct' : 'feedback-incorrect'
})

const feedbackIcon = computed(() => {
  return isFullyCorrect.value ? 'pi pi-check-circle' : 'pi pi-times-circle'
})

const feedbackMessage = computed(() => {
  if (isFullyCorrect.value) {
    return `Correto! ${correctCount.value}/${totalOptions.value} acertos`
  }
  return `${correctCount.value}/${totalOptions.value} acertos`
})

// Methods
function toggleOption(idx) {
  if (isAnswered.value) return

  if (props.question.qtype === 2) {
    // SC: apenas uma seleção
    selectedOptions.value = [idx]
  } else {
    // Kprim ou MC: toggle
    const i = selectedOptions.value.indexOf(idx)
    if (i >= 0) {
      selectedOptions.value.splice(i, 1)
    } else {
      selectedOptions.value.push(idx)
    }
  }
}

function selectSingle(idx) {
  if (isAnswered.value) return
  selectedOptions.value = [idx]
}

function checkAnswer() {
  isAnswered.value = true
  emit('answered', {
    correct: isFullyCorrect.value,
    correctCount: correctCount.value,
    total: totalOptions.value,
    selected: [...selectedOptions.value]
  })
}

function reset() {
  selectedOptions.value = []
  isAnswered.value = false
}

function getOptionClass(idx) {
  const opt = props.question.options[idx]
  const classes = ['quiz-option']

  if (selectedOptions.value.includes(idx)) {
    classes.push('selected')
  }

  if (isAnswered.value) {
    if (opt?.isCorrect) {
      classes.push('correct')
    }
    if (selectedOptions.value.includes(idx) && !opt?.isCorrect) {
      classes.push('incorrect')
    }
    if (!selectedOptions.value.includes(idx) && opt?.isCorrect) {
      classes.push('missed')
    }
  }

  return classes.join(' ')
}

// Expose methods for parent
defineExpose({ reset, checkAnswer })
</script>

<template>
  <div class="quiz-interactive" :class="{ 'quiz-answered': isAnswered, 'quiz-compact': compact }">
    <!-- Question Header -->
    <div class="quiz-header">
      <div class="quiz-header-left">
        <Tag :severity="qtypeSeverity" class="qtype-tag">{{ qtypeLabel }}</Tag>
        <span v-if="question.domain" class="quiz-domain">{{ question.domain }}</span>
      </div>
      <span v-if="!compact" class="quiz-hint">{{ qtypeDescription }}</span>
    </div>

    <!-- Question Text -->
    <div class="quiz-question">
      {{ question.question }}
    </div>

    <!-- Options -->
    <div class="quiz-options">
      <div
        v-for="(opt, idx) in question.options"
        :key="idx"
        :class="getOptionClass(idx)"
        @click="toggleOption(idx)"
      >
        <div class="option-indicator">
          <!-- Kprim: V/F toggle buttons -->
          <template v-if="question.qtype === 0">
            <div class="kprim-toggle">
              <span
                class="kprim-btn"
                :class="{ active: selectedOptions.includes(idx), disabled: isAnswered }"
              >
                {{ selectedOptions.includes(idx) ? 'V' : 'F' }}
              </span>
            </div>
          </template>

          <!-- MC: Checkbox -->
          <template v-else-if="question.qtype === 1">
            <Checkbox
              :binary="true"
              :modelValue="selectedOptions.includes(idx)"
              :disabled="isAnswered"
              @click.stop="toggleOption(idx)"
            />
          </template>

          <!-- SC: Radio -->
          <template v-else>
            <RadioButton
              :modelValue="selectedOptions.length === 1 ? selectedOptions[0] : null"
              :value="idx"
              :disabled="isAnswered"
              @click.stop="selectSingle(idx)"
            />
          </template>
        </div>

        <div class="option-text">{{ opt.text }}</div>

        <div v-if="isAnswered" class="option-result">
          <i v-if="opt.isCorrect" class="pi pi-check text-green-500" />
          <i v-else class="pi pi-times text-red-400" />
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div v-if="showActions" class="quiz-actions">
      <Button
        v-if="!isAnswered"
        label="Verificar Resposta"
        icon="pi pi-check"
        @click="checkAnswer"
        :disabled="question.qtype !== 0 && selectedOptions.length === 0"
        size="small"
      />
      <Button
        v-else
        label="Tentar Novamente"
        icon="pi pi-refresh"
        severity="secondary"
        @click="reset"
        size="small"
      />
    </div>

    <!-- Feedback (shown after answer) -->
    <Transition name="slide-fade">
      <div v-if="isAnswered" class="quiz-feedback" :class="feedbackClass">
        <div class="feedback-result">
          <i :class="feedbackIcon" />
          <span>{{ feedbackMessage }}</span>
        </div>

        <div v-if="question.comment" class="feedback-comment">
          <strong>Explicação:</strong> {{ question.comment }}
        </div>

        <div v-if="question.sources" class="feedback-source">
          <i class="pi pi-link" />
          <span>{{ question.sources }}</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.quiz-interactive {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quiz-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.quiz-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.qtype-tag {
  font-weight: 700;
  font-size: 0.75rem;
}

.quiz-domain {
  font-size: 0.8rem;
  color: rgba(148, 163, 184, 0.8);
}

.quiz-hint {
  font-size: 0.75rem;
  color: rgba(148, 163, 184, 0.6);
  font-style: italic;
}

.quiz-question {
  font-size: 1rem;
  font-weight: 500;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.95);
}

.quiz-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quiz-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: all 0.2s ease;
}

.quiz-option:hover:not(.quiz-answered .quiz-option) {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.3);
}

.quiz-option.selected {
  background: rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.4);
}

.quiz-option.correct {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.4);
}

.quiz-option.incorrect {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.4);
}

.quiz-option.missed {
  background: rgba(251, 191, 36, 0.08);
  border-color: rgba(251, 191, 36, 0.3);
}

.quiz-answered .quiz-option {
  cursor: default;
}

.option-indicator {
  flex-shrink: 0;
}

.option-text {
  flex: 1;
  font-size: 0.9rem;
  line-height: 1.4;
}

.option-result {
  flex-shrink: 0;
  font-size: 1.1rem;
}

.kprim-toggle {
  display: flex;
  align-items: center;
}

.kprim-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 0.8rem;
  background: rgba(148, 163, 184, 0.15);
  color: rgba(148, 163, 184, 0.8);
  transition: all 0.2s ease;
}

.kprim-btn.active {
  background: rgba(34, 197, 94, 0.25);
  color: #22c55e;
}

.kprim-btn.disabled {
  cursor: default;
}

.quiz-actions {
  display: flex;
  justify-content: center;
  padding-top: 8px;
}

.quiz-feedback {
  padding: 14px;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.quiz-feedback.feedback-correct {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.quiz-feedback.feedback-incorrect {
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.feedback-result {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 0.95rem;
}

.feedback-correct .feedback-result {
  color: #22c55e;
}

.feedback-incorrect .feedback-result {
  color: #fbbf24;
}

.feedback-result i {
  font-size: 1.2rem;
}

.feedback-comment {
  font-size: 0.85rem;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.85);
}

.feedback-source {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 0.8rem;
  color: rgba(148, 163, 184, 0.7);
  font-style: italic;
}

.feedback-source i {
  margin-top: 2px;
}

/* Compact mode */
.quiz-compact .quiz-question {
  font-size: 0.9rem;
}

.quiz-compact .quiz-option {
  padding: 8px 10px;
}

.quiz-compact .option-text {
  font-size: 0.85rem;
}

/* Transitions */
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.3s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
