<!-- frontend/src/App.vue -->
<script setup>
import { RouterView } from 'vue-router'
import AppNotifications from '@/components/AppNotifications.vue'
</script>

<template>
  <RouterView />
  <AppNotifications />
</template>
