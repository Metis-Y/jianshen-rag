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
    <div class="nav-left">
      <span class="nav-title">健身管家</span>
      <nav class="nav-links">
        <RouterLink to="/" :class="{ active: route.path === '/' }">首页</RouterLink>
        <RouterLink
          to="/documents"
          :class="{ active: route.path === '/documents' }"
        >
          资料
        </RouterLink>
        <RouterLink
          to="/records"
          :class="{ active: route.path === '/records' }"
        >
          记录
        </RouterLink>
      </nav>
    </div>
    <div class="nav-right">
      <span>{{ username }}</span>
      <el-button size="small" class="logout-btn" @click="logout">退出</el-button>
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

.nav-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.nav-title {
  font-size: 18px;
  font-weight: 600;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-links a {
  color: #9ca3af;
  text-decoration: none;
  font-size: 14px;
}

.nav-links a:hover {
  color: #fff;
}

.nav-links a.active {
  color: #fff;
  font-weight: 600;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-right .el-button.logout-btn {
  background: rgba(255, 255, 255, 0.15);
  border: none;
  color: #fff;
}

.nav-right .el-button.logout-btn:hover {
  background: rgba(255, 255, 255, 0.25);
  color: #fff;
}
</style>