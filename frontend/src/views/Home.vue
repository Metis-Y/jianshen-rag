<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api.js'

const router = useRouter()
const me = ref(null)
const stats = ref(null)

onMounted(async () => {
  try {
    me.value = await api.get('/auth/me')
  } catch (e) {
    // 错误信息已由拦截器 alert；token 失效时 App.vue 会清除并跳转登录页
  }
  try {
    stats.value = await api.get('/stats')
  } catch (e) {
    // 错误信息已由拦截器 alert
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
      <p class="hint" style="margin: 12px 0 16px">
        上传训练资料、记录每日训练，然后向助手提问你的进展
      </p>
      <p v-if="me && me.goal" class="hint" style="margin-bottom: 4px">
        目标：{{ me.goal }}
      </p>
      <p
        v-if="me && me.allergies && me.allergies.length"
        class="hint"
        style="margin-bottom: 12px"
      >
        忌口/过敏：{{ me.allergies.join('、') }}
      </p>
      <div v-if="stats" class="stats-grid">
        <div class="stat">
          <span class="stat-num">{{ stats.docCount }}</span>
          <span class="stat-label">资料数</span>
        </div>
        <div class="stat">
          <span class="stat-num">{{ stats.logDays }}</span>
          <span class="stat-label">训练天数</span>
        </div>
        <div class="stat">
          <span class="stat-num">{{ stats.qaCount }}</span>
          <span class="stat-label">问答次数</span>
        </div>
        <div class="stat">
          <span class="stat-num">
            {{
              stats.positiveRate != null
                ? Math.round(stats.positiveRate * 100) + '%'
                : '—'
            }}
          </span>
          <span class="stat-label">好评率</span>
        </div>
        <div class="stat">
          <span class="stat-num">
            {{ stats.latestWeight != null ? stats.latestWeight + 'kg' : '—' }}
          </span>
          <span class="stat-label">最近体重</span>
        </div>
        <div class="stat">
          <span class="stat-num">{{ stats.weekVolume }}kg</span>
          <span class="stat-label">本周容量</span>
        </div>
      </div>
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}

.stat {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 6px;
  text-align: center;
}

.stat-num {
  display: block;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.stat-label {
  font-size: 12px;
  color: #6b7280;
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