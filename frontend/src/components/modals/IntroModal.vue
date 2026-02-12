<!-- frontend/src/components/modals/IntroModal.vue -->
<script setup>
import { ref, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'

const props = defineProps({
  visible: Boolean
})

const emit = defineEmits([
  'update:visible',
  'complete',
  'skip'
])

// Internal state
const introStep = ref(1)
const dontShowIntroAgain = ref(false)
const TOTAL_INTRO_STEPS = 3

// Reset state when modal opens
watch(() => props.visible, (visible) => {
  if (visible) {
    introStep.value = 1
    dontShowIntroAgain.value = false
  }
})

// Navigation
function nextIntroStep() {
  if (introStep.value < TOTAL_INTRO_STEPS) {
    introStep.value++
  } else {
    finishIntro()
  }
}

function prevIntroStep() {
  if (introStep.value > 1) {
    introStep.value--
  }
}

function skipIntro() {
  finishIntro(true)
}

function finishIntro(skipped = false) {
  emit('complete', {
    dontShowAgain: dontShowIntroAgain.value,
    skipped
  })
  emit('update:visible', false)
}
</script>

<template>
  <Dialog
    :visible="visible"
    @update:visible="emit('update:visible', $event)"
    :closable="false"
    modal
    class="intro-modal-dialog"
    :style="{ width: 'min(520px, 94vw)' }"
  >
    <template #header>
      <div class="flex justify-content-between align-items-center w-full">
        <span class="text-sm font-medium" style="color: rgba(148, 163, 184, 0.7)">{{ introStep }}/{{ TOTAL_INTRO_STEPS }}</span>
        <div class="flex gap-2 align-items-center">
          <span
            v-for="n in TOTAL_INTRO_STEPS"
            :key="n"
            class="inline-block border-round-sm transition-colors transition-duration-300"
            :style="{
              width: n === introStep ? '2rem' : '0.5rem',
              height: '0.35rem',
              background: n === introStep ? 'linear-gradient(90deg, #10b981, #34d399)' : 'rgba(148, 163, 184, 0.3)'
            }"
          />
        </div>
        <Button
          label="Pular"
          @click="skipIntro"
          text
          size="small"
          class="p-1 text-xs"
          style="color: rgba(148, 163, 184, 0.7)"
        />
      </div>
    </template>

    <!-- Step 1: Boas-vindas -->
    <div v-if="introStep === 1" class="text-center py-5">
      <div
        class="flex align-items-center justify-content-center mx-auto mb-4 border-round-xl"
        style="width: 5rem; height: 5rem; background: linear-gradient(135deg, #10b981, #059669); box-shadow: 0 8px 32px rgba(16, 185, 129, 0.3)"
      >
        <i class="pi pi-bolt text-white" style="font-size: 2.5rem" />
      </div>
      <h2 class="text-2xl font-bold mb-3 mt-0" style="color: #f1f5f9">Bem-vindo ao Green Deck!</h2>
      <p class="line-height-3 m-0 px-3" style="color: rgba(148, 163, 184, 0.9)">
        Transforme qualquer conteudo em flashcards inteligentes usando IA.<br />
        Estude de forma eficiente com repeticao espacada.
      </p>
    </div>

    <!-- Step 2: Como funciona -->
    <div v-else-if="introStep === 2" class="py-4">
      <h2 class="text-xl font-bold mb-5 text-center mt-0" style="color: #f1f5f9">Como usar</h2>
      <div class="flex flex-column gap-3 px-2">
        <div
          class="flex align-items-center gap-3 p-3 border-round-lg"
          style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(148, 163, 184, 0.1)"
        >
          <div
            class="flex align-items-center justify-content-center border-round-lg flex-shrink-0"
            style="width: 3rem; height: 3rem; background: linear-gradient(135deg, #10b981, #059669)"
          >
            <i class="pi pi-file-edit text-xl text-white" />
          </div>
          <div>
            <span class="font-medium" style="color: #f1f5f9">Cole ou digite seu conteudo</span>
            <p class="text-sm m-0 mt-1" style="color: rgba(148, 163, 184, 0.8)">Use o editor para adicionar textos, PDFs ou documentos</p>
          </div>
        </div>
        <div
          class="flex align-items-center gap-3 p-3 border-round-lg"
          style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(148, 163, 184, 0.1)"
        >
          <div
            class="flex align-items-center justify-content-center border-round-lg flex-shrink-0"
            style="width: 3rem; height: 3rem; background: linear-gradient(135deg, #10b981, #059669)"
          >
            <i class="pi pi-sparkles text-xl text-white" />
          </div>
          <div>
            <span class="font-medium" style="color: #f1f5f9">Gere flashcards com IA</span>
            <p class="text-sm m-0 mt-1" style="color: rgba(148, 163, 184, 0.8)">A IA analisa e cria cartões de alta qualidade</p>
          </div>
        </div>
        <div
          class="flex align-items-center gap-3 p-3 border-round-lg"
          style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(148, 163, 184, 0.1)"
        >
          <div
            class="flex align-items-center justify-content-center border-round-lg flex-shrink-0"
            style="width: 3rem; height: 3rem; background: linear-gradient(135deg, #10b981, #059669)"
          >
            <i class="pi pi-sync text-xl text-white" />
          </div>
          <div>
            <span class="font-medium" style="color: #f1f5f9">Estude ou exporte para Anki</span>
            <p class="text-sm m-0 mt-1" style="color: rgba(148, 163, 184, 0.8)">Use repeticao espacada ou exporte seus decks</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3: Comecar -->
    <div v-else-if="introStep === 3" class="text-center py-5">
      <div
        class="flex align-items-center justify-content-center mx-auto mb-4 border-round-xl"
        style="width: 5rem; height: 5rem; background: linear-gradient(135deg, #10b981, #059669); box-shadow: 0 8px 32px rgba(16, 185, 129, 0.3)"
      >
        <i class="pi pi-check text-white" style="font-size: 2.5rem" />
      </div>
      <h2 class="text-xl font-bold mb-3 mt-0" style="color: #f1f5f9">Tudo pronto!</h2>
      <p class="mb-5 px-3" style="color: rgba(148, 163, 184, 0.9)">
        A seguir, voce podera configurar os modelos de IA para geracao dos cartões.
      </p>
      <div
        class="flex align-items-center justify-content-center gap-2 p-3 border-round-lg mx-auto"
        style="max-width: 20rem; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(148, 163, 184, 0.1)"
      >
        <Checkbox v-model="dontShowIntroAgain" :binary="true" inputId="dontShowAgain" />
        <label for="dontShowAgain" class="cursor-pointer text-sm" style="color: rgba(148, 163, 184, 0.9)">
          Nao mostrar esta introducao novamente
        </label>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-content-between align-items-center w-full">
        <Button
          v-if="introStep > 1"
          label="Anterior"
          @click="prevIntroStep"
          text
          icon="pi pi-arrow-left"
          style="color: rgba(148, 163, 184, 0.8)"
        />
        <span v-else></span>
        <Button
          :label="introStep === TOTAL_INTRO_STEPS ? 'Comecar' : 'Proximo'"
          @click="nextIntroStep"
          :icon="introStep === TOTAL_INTRO_STEPS ? 'pi pi-check' : 'pi pi-arrow-right'"
          iconPos="right"
          class="px-4"
          :style="{
            background: 'linear-gradient(135deg, #10b981, #059669)',
            border: 'none',
            color: 'white'
          }"
        />
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
:deep(.intro-modal-dialog) {
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.98) 0%, rgba(10, 10, 14, 0.99) 100%);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 24px;
  box-shadow:
    0 25px 50px -12px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(255, 255, 255, 0.05) inset;
}

:deep(.intro-modal-dialog .p-dialog-header) {
  background: transparent;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
  padding: 1.25rem 1.5rem;
}

:deep(.intro-modal-dialog .p-dialog-content) {
  background: transparent;
  padding: 0 1.5rem;
}

:deep(.intro-modal-dialog .p-dialog-footer) {
  background: transparent;
  border-top: 1px solid rgba(148, 163, 184, 0.08);
  padding: 1.25rem 1.5rem;
}
</style>
