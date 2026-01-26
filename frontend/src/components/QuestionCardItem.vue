<!-- frontend/src/components/QuestionCardItem.vue -->
<script setup>
import { ref, computed } from 'vue'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import Button from 'primevue/button'
import QuizInteractive from './QuizInteractive.vue'

const props = defineProps({
  question: {
    type: Object,
    required: true
  },
  index: {
    type: Number,
    default: 0
  },
  selected: {
    type: Boolean,
    default: false
  },
  selectionMode: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['select', 'edit', 'delete', 'preview'])

// State
const isExpanded = ref(false)

// Computed
const qtypeLabel = computed(() => {
  switch (props.question.qtype) {
    case 0: return 'KPRIM'
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

const previewText = computed(() => {
  const q = props.question.question || ''
  const max = 150
  return q.length > max ? q.slice(0, max - 1) + '…' : q
})

const optionsPreview = computed(() => {
  const options = props.question.options || []
  return options.slice(0, 4).map((opt, i) => ({
    text: opt.text.length > 60 ? opt.text.slice(0, 60) + '…' : opt.text,
    isCorrect: opt.isCorrect,
    index: i + 1
  }))
})

// Methods
function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

function handleClick() {
  if (props.selectionMode) {
    emit('select', props.index)
  } else {
    toggleExpand()
  }
}

function handleEdit(e) {
  e.stopPropagation()
  emit('edit', props.index)
}

function handleDelete(e) {
  e.stopPropagation()
  emit('delete', props.index)
}

function handlePreview(e) {
  e.stopPropagation()
  emit('preview', props.index)
}
</script>

<template>
  <div
    class="question-card-item"
    :class="{ 'card-selected': selected, 'card-expanded': isExpanded }"
  >
    <Card class="question-card" @click="handleClick">
      <template #title>
        <div class="card-head">
          <div class="card-left">
            <span class="card-index">Q{{ index + 1 }}</span>
            <Tag :severity="qtypeSeverity" class="pill card-type-tag">
              {{ qtypeLabel }}
            </Tag>
            <span v-if="question.deck" class="deck-pill">
              <i class="pi pi-tag mr-1" />
              {{ question.deck }}
            </span>
          </div>
          <div class="card-right">
            <Button
              icon="pi pi-eye"
              severity="secondary"
              text
              rounded
              size="small"
              @click="handlePreview"
              v-tooltip.top="'Preview'"
            />
            <Button
              icon="pi pi-pencil"
              severity="secondary"
              text
              rounded
              size="small"
              @click="handleEdit"
              v-tooltip.top="'Editar'"
            />
            <Button
              icon="pi pi-trash"
              severity="danger"
              text
              rounded
              size="small"
              @click="handleDelete"
              v-tooltip.top="'Excluir'"
            />
            <Button
              :icon="isExpanded ? 'pi pi-chevron-up' : 'pi pi-chevron-down'"
              severity="secondary"
              text
              rounded
              size="small"
              @click.stop="toggleExpand"
            />
          </div>
        </div>
      </template>

      <template #content>
        <!-- Collapsed View -->
        <div v-if="!isExpanded" class="preview-content">
          <div class="preview-question">
            {{ previewText }}
          </div>
          <div class="preview-options">
            <div
              v-for="opt in optionsPreview"
              :key="opt.index"
              class="preview-option"
              :class="{ correct: opt.isCorrect }"
            >
              <span class="option-marker">{{ opt.index }}.</span>
              <span class="option-text">{{ opt.text }}</span>
              <i v-if="opt.isCorrect" class="pi pi-check text-green-500" />
            </div>
          </div>
        </div>

        <!-- Expanded View: Interactive Quiz -->
        <div v-else class="expanded-content">
          <QuizInteractive
            :question="question"
            :compact="false"
            :showActions="true"
          />
        </div>
      </template>
    </Card>
  </div>
</template>

<style scoped>
.question-card-item {
  margin-bottom: 10px;
}

.question-card {
  cursor: pointer;
  transition: all 0.2s ease;
}

.question-card:hover {
  transform: translateY(-1px);
}

.question-card-item.card-selected .question-card {
  border: 2px solid rgba(99, 102, 241, 0.7);
  background: rgba(99, 102, 241, 0.08);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.question-card-item.card-expanded .question-card {
  cursor: default;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.card-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-right {
  display: flex;
  align-items: center;
  gap: 2px;
}

.card-index {
  font-weight: 700;
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.7);
}

.card-type-tag {
  font-weight: 700;
  font-size: 0.7rem;
}

.deck-pill {
  display: flex;
  align-items: center;
  font-size: 0.75rem;
  color: rgba(148, 163, 184, 0.8);
  background: rgba(148, 163, 184, 0.1);
  padding: 2px 8px;
  border-radius: 999px;
}

.preview-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.preview-question {
  font-size: 0.9rem;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.9);
}

.preview-options {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preview-option {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.7);
}

.preview-option.correct {
  background: rgba(34, 197, 94, 0.1);
  color: rgba(34, 197, 94, 0.9);
}

.option-marker {
  font-weight: 600;
  color: rgba(148, 163, 184, 0.6);
  min-width: 18px;
}

.option-text {
  flex: 1;
}

.expanded-content {
  padding: 8px 0;
}

/* Deep styles for the card */
:deep(.p-card) {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 14px;
}

:deep(.p-card-body) {
  padding: 14px 16px;
}

:deep(.p-card-title) {
  font-size: 1rem;
  margin-bottom: 0;
}

:deep(.p-card-content) {
  padding: 12px 0 0 0;
}
</style>
