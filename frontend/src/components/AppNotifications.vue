<script setup>
import { Toast as ToastItem, ToastContainer } from 'vue-toastflow'

const ICONS_BY_TYPE = {
  default: 'pi pi-bell',
  loading: 'pi pi-spin pi-spinner',
  success: 'pi pi-check-circle',
  error: 'pi pi-times-circle',
  warning: 'pi pi-exclamation-triangle',
  info: 'pi pi-info-circle'
}

function resolveIcon(type) {
  return ICONS_BY_TYPE[type] || ICONS_BY_TYPE.default
}
</script>

<template>
  <ToastContainer v-slot="slotProps">
    <ToastItem
      v-bind="slotProps"
      @dismiss="slotProps.dismiss"
    >
      <template #icon="{ toast }">
        <i
          :class="resolveIcon(toast.type)"
          class="app-toast-icon"
          aria-hidden="true"
        />
      </template>
    </ToastItem>
  </ToastContainer>
</template>

<style scoped>
.app-toast-icon {
  font-size: var(--tf-toast-icon-size);
  line-height: 1;
}
</style>
