// frontend/src/main.js
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

import PrimeVue from 'primevue/config'
import Aura from '@primevue/themes/aura'
import { createToastflow } from 'vue-toastflow'

import './style.css'
import { initTheme } from '@/composables/useTheme'

import 'primeicons/primeicons.css'
import 'primeflex/primeflex.css'

initTheme()

createApp(App)
  .use(router)
  .use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: '.theme-dark' } }, ripple: true })
  .use(createToastflow())
  .mount('#app')
