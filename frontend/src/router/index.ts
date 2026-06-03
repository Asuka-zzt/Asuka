import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'chat', component: () => import('@/views/ChatView.vue') },
  { path: '/learn', name: 'learn', component: () => import('@/views/LanguageLearningView.vue') },
  { path: '/agent', name: 'agent', component: () => import('@/views/AgentTestView.vue') },
  { path: '/wiki', name: 'wiki', component: () => import('@/views/CodebaseWikiView.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
