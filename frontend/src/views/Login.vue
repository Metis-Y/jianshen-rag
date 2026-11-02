<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api.js'

const router = useRouter()

const mode = ref('login') // 'login' | 'register'
const username = ref('')
const password = ref('')
const loading = ref(false)

function switchMode(next) {
  mode.value = next
  password.value = ''
}

async function submit() {
  if (!username.value.trim() || !password.value) {
    alert('用户名和密码不能为空')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'register') {
      await api.post('/auth/register', {
        username: username.value.trim(),
        password: password.value
      })
      alert('注册成功，请登录')
      // 切回登录模式，保留用户名，请用户重新输入密码登录
      switchMode('login')
    } else {
      const data = await api.post('/auth/login', {
        username: username.value.trim(),
        password: password.value
      })
      localStorage.setItem('token', data.token)
      router.replace('/')
    }
  } catch (e) {
    // 失败信息已由拦截器 alert
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page-center">
    <div class="card">
      <h2>{{ mode === 'login' ? '登录' : '注册' }}</h2>
      <p class="hint" style="margin-bottom: 20px">
        健身管家 · {{ mode === 'login' ? '欢迎回来' : '创建新账号' }}
      </p>

      <div class="tabs">
        <button
          type="button"
          class="tab"
          :class="{ active: mode === 'login' }"
          @click="switchMode('login')"
        >
          登录
        </button>
        <button
          type="button"
          class="tab"
          :class="{ active: mode === 'register' }"
          @click="switchMode('register')"
        >
          注册
        </button>
      </div>

      <form @submit.prevent="submit">
        <div class="field">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="username"
            class="input"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
          />
        </div>
        <div class="field">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            class="input"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
          />
        </div>
        <button class="btn" type="submit" :disabled="loading">
          {{ loading ? '提交中…' : mode === 'login' ? '登录' : '注册' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  margin-bottom: 20px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  overflow: hidden;
}

.tab {
  flex: 1;
  height: 38px;
  border: none;
  background: #f3f4f6;
  cursor: pointer;
  font-size: 14px;
  color: #4b5563;
}

.tab.active {
  background: #1f2937;
  color: #fff;
}
</style>