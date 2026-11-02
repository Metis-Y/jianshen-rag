<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api.js'

const router = useRouter()
const me = ref(null)

onMounted(async () => {
  try {
    me.value = await api.get('/auth/me')
  } catch (e) {
    // 错误信息已由拦截器 alert；token 失效时 App.vue 会清除并跳转登录页
  }
})

function logout() {
  localStorage.removeItem('token')
  router.replace('/login')
}
</script>

<template>
  <div class="page-center">
    <div class="card">
      <h2>欢迎，{{ (me && me.username) || '用户' }}</h2>
      <p class="hint" style="margin: 12px 0 24px">资料上传与问答功能开发中</p>
      <p v-if="me && me.goal" class="hint" style="margin-bottom: 8px">
        目标：{{ me.goal }}
      </p>
      <p v-if="me && me.allergies" class="hint" style="margin-bottom: 24px">
        忌口/过敏：{{ me.allergies }}
      </p>
      <button class="btn" @click="logout">退出登录</button>
    </div>
  </div>
</template>