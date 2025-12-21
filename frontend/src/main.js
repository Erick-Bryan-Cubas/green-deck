import { createApp } from 'vue'
import App from './App.vue'

import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'

import 'primeicons/primeicons.css'
import 'primeflex/primeflex.css'

// Quill via npm (sem CDN)
import 'quill/dist/quill.snow.css'

const app = createApp(App)

app.use(PrimeVue, {
  theme: { preset: Aura },
  ripple: true
})

app.mount('#app')
