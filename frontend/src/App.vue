<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from './api.js'

const route = useRoute()
const router = useRouter()
const username = ref('')

// 拉取当前用户：顶部导航显示用户名；token 失效时清除并回登录页
async function refreshUser() {
  if (!localStorage.getItem('token')) {
    username.value = ''
    return
  }
  try {
    const me = await api.get('/auth/me')
    username.value = (me && me.username) || ''
  } catch (e) {
    // 错误信息已由拦截器 alert；token 无效时清掉并回登录页
    localStorage.removeItem('token')
    username.value = ''
    if (route.path !== '/login') {
      router.replace('/login')
    }
  }
}

function logout() {
  localStorage.removeItem('token')
  username.value = ''
  router.replace('/login')
}

onMounted(refreshUser)
watch(() => route.path, refreshUser)
</script>

<template>
  <header v-if="username" class="nav">
    <span class="nav-title">健身管家</span>
    <div class="nav-right">
      <span>{{ username }}</span>
      <button class="btn btn-small" @click="logout">退出</button>
    </div>
  </header>
  <router-view />
</template>

<style scoped>
.nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 24px;
  background: #1f2937;
  color: #fff;
}

.nav-title {
  font-size: 18px;
  font-weight: 600;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.btn.btn-small {
  width: auto;
  height: 32px;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.15);
}

.btn.btn-small:hover {
  background: rgba(255, 255, 255, 0.25);
}
</style>