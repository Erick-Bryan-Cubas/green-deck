// frontend/src/main.js
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import Aura from '@primevue/themes/aura'

import 'primeicons/primeicons.css'
import 'primeflex/primeflex.css'

createApp(App)
  .use(router)
  .use(PrimeVue, { theme: { preset: Aura }, ripple: true })
  .use(ToastService)
  .mount('#app')
