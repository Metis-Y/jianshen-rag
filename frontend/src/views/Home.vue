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

function goDocuments() {
  router.push('/documents')
}

function goChat() {
  router.push('/chat')
}

function goRecords() {
  router.push('/records')
}

function logout() {
  localStorage.removeItem('token')
  router.replace('/login')
}
</script>

<template>
  <div class="page-center">
    <el-card class="home-card">
      <h2>欢迎，{{ (me && me.username) || '用户' }}</h2>
      <p class="hint" style="margin: 12px 0 24px">
        上传训练资料、记录每日训练，然后向助手提问你的进展
      </p>
      <p v-if="me && me.goal" class="hint" style="margin-bottom: 8px">
        目标：{{ me.goal }}
      </p>
      <p v-if="me && me.allergies" class="hint" style="margin-bottom: 24px">
        忌口/过敏：{{ me.allergies }}
      </p>
      <div class="actions">
        <el-button type="primary" @click="goChat">问答助手</el-button>
        <el-button @click="goDocuments">资料管理</el-button>
        <el-button @click="goRecords">训练记录</el-button>
        <el-button @click="logout">退出登录</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.home-card {
  width: 100%;
  max-width: 400px;
}

.home-card :deep(.el-card__body) {
  padding: 32px;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.actions .el-button {
  width: 100%;
  margin-left: 0;
}
</style>