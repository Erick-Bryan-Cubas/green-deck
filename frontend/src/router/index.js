// frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'generator',
      component: () => import('../pages/GeneratorPage.vue')
    },
    {
      path: '/browser',
      name: 'browser',
      component: () => import('../pages/BrowserPage.vue')
    },
    // fallback
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ],
  scrollBehavior() {
    return { top: 0 }
  }
})
