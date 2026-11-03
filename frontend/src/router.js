import { createRouter, createWebHistory } from 'vue-router'
import Login from './views/Login.vue'
import Home from './views/Home.vue'
import Documents from './views/Documents.vue'
import Records from './views/Records.vue'
import Chat from './views/Chat.vue'

const routes = [
  { path: '/', name: 'home', component: Home },
  { path: '/chat', name: 'chat', component: Chat },
  { path: '/documents', name: 'documents', component: Documents },
  { path: '/records', name: 'records', component: Records },
  { path: '/login', name: 'login', component: Login }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 未登录访问受保护页面 -> 跳转 /login；已登录访问 /login -> 回首页
router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.path !== '/login' && !token) {
    return { path: '/login' }
  }
  if (to.path === '/login' && token) {
    return { path: '/' }
  }
  return true
})

export default router