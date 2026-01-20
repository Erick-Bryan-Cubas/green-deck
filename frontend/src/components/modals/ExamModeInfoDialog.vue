<template>
  <Dialog
    :visible="visible"
    modal
    header="Modo Simulado/Prova"
    :style="{ width: '36rem' }"
    @update:visible="$emit('update:visible', $event)"
  >
    <div class="space-y-4">
      <section>
        <h3 class="text-lg font-semibold mb-2 flex items-center gap-2">
          <i class="pi pi-book text-primary" />
          O que é o Modo Simulado?
        </h3>
        <p class="text-surface-700 dark:text-surface-300">
          Um modo especializado para textos extraídos de provas e simulados que contêm
          questões de múltipla escolha com alternativas corretas e incorretas.
        </p>
      </section>

      <section>
        <h3 class="text-lg font-semibold mb-2 flex items-center gap-2">
          <i class="pi pi-lightbulb text-yellow-500" />
          Como funciona?
        </h3>
        <ul class="list-disc list-inside space-y-2 text-surface-700 dark:text-surface-300">
          <li>
            <strong>Aproveita alternativas incorretas:</strong> Alternativas erradas revelam
            conceitos comumente confundidos
          </li>
          <li>
            <strong>Gera cards contrastivos:</strong> Cria perguntas do tipo
            "Por que X está correto e Y está incorreto?"
          </li>
          <li>
            <strong>Usa explicações:</strong> Incorpora explicações das questões para
            enriquecer os cards
          </li>
          <li>
            <strong>Foco conceitual:</strong> Extrai conceitos subjacentes ao invés de
            apenas repetir alternativas
          </li>
        </ul>
      </section>

      <section>
        <h3 class="text-lg font-semibold mb-2 flex items-center gap-2">
          <i class="pi pi-file text-blue-500" />
          Formato esperado do texto
        </h3>
        <div class="bg-surface-100 dark:bg-surface-800 p-3 rounded-md font-mono text-sm">
          <div class="text-surface-600 dark:text-surface-400">## Questão 1</div>
          <div class="text-surface-600 dark:text-surface-400">Enunciado da questão...</div>
          <div class="text-surface-600 dark:text-surface-400 mt-2">**Alternativas:**</div>
          <div class="text-surface-600 dark:text-surface-400">A) Alternativa A</div>
          <div class="text-surface-600 dark:text-surface-400">B) Alternativa B</div>
          <div class="text-green-600 dark:text-green-400">C) Alternativa C ✅</div>
          <div class="text-surface-600 dark:text-surface-400">D) Alternativa D</div>
          <div class="text-surface-600 dark:text-surface-400 mt-2">**Explicação:**</div>
          <div class="text-surface-600 dark:text-surface-400">Explicação...</div>
        </div>
      </section>

      <Message severity="info" :closable="false">
        <p class="text-sm">
          <strong>Dica:</strong> O modo funciona melhor quando o texto mantém a estrutura
          de questões, alternativas e explicações. Textos sem essa estrutura funcionarão
          normalmente no modo padrão.
        </p>
      </Message>
    </div>

    <template #footer>
      <Button label="Entendi" icon="pi pi-check" @click="$emit('update:visible', false)" />
    </template>
  </Dialog>
</template>

<script setup>
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Message from 'primevue/message'

defineProps({
  visible: {
    type: Boolean,
    required: true
  }
})

defineEmits(['update:visible'])
</script>
