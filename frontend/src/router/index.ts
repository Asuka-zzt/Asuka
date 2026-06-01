import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'chat', component: () => import('@/views/ChatView.vue') },
  { path: '/agent', name: 'agent', component: () => import('@/views/AgentTestView.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
