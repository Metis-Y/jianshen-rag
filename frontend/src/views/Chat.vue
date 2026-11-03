<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api.js'

const router = useRouter()

// ---- 状态 ----
const convs = ref([])
const activeConvId = ref(null)
const messages = ref([])          // [{id, role, content, citations, feedback, isError}]
const streaming = ref(false)
const streamingText = ref('')
const streamCitations = ref([])
const streamError = ref('')

// 视图切换计数：每次切会话/新对话 +1；流式气泡只属于发起时的那个视图，
// 切到别的会话后不显示，答完也不追加进无关会话
const viewSeq = ref(0)
const streamSeq = ref(-1)

const input = ref('')
const scope = ref([])             // 限定资料范围（docId 列表）
const scopeOptions = ref([])      // READY 文档选项
const docsTotal = ref(0)          // 用户全部文档数（含非 READY），用于空态引导

const chatBody = ref(null)

const noDocs = computed(() => docsTotal.value === 0)
const streamInView = computed(() => streaming.value && streamSeq.value === viewSeq.value)

function mapMessage(m) {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    citations: m.citations || [],
    feedback: m.feedback === true ? 'up' : m.feedback === false ? 'down' : null,
    isError: false
  }
}

// ---- 会话 ----
async function loadConversations() {
  try {
    const data = await api.get('/conversations', { params: { page: 1, size: 50 } })
    convs.value = (data && data.list) || []
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  }
}

async function loadMessages(convId) {
  try {
    const data = await api.get(`/conversations/${convId}/messages`)
    messages.value = ((data && data.list) || []).map(mapMessage)
    scrollToBottom()
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  }
}

function openConversation(conv) {
  activeConvId.value = conv.id
  viewSeq.value += 1
  loadMessages(conv.id)
}

function newChat() {
  activeConvId.value = null
  messages.value = []
  viewSeq.value += 1
}

async function removeConversation(conv) {
  try {
    await ElMessageBox.confirm('删除该会话及其全部消息？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch (e) {
    return
  }
  try {
    await api.delete(`/conversations/${conv.id}`)
    ElMessage.success('已删除')
    if (activeConvId.value === conv.id) {
      newChat()
    }
    await loadConversations()
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  }
}

// ---- 资料范围与空态 ----
async function loadScopeOptions() {
  try {
    const data = await api.get('/documents', { params: { page: 1, size: 200 } })
    docsTotal.value = (data && data.total) || 0
    const rows = ((data && data.list) || []).filter((r) => r.status === 'READY')
    scopeOptions.value = rows.map((r) => ({ value: r.docId, label: r.filename }))
    // 已选范围中的文档若已删除，自动清理（删除一致性）
    scope.value = scope.value.filter((id) => scopeOptions.value.some((o) => o.value === id))
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  }
}

// ---- SSE 流式问答（fetch 直连，绕过 axios 拦截器）----
function parseBlock(block) {
  let event = 'message'
  const dataLines = []
  for (const raw of block.split('\n')) {
    const line = raw.replace(/\r$/, '')
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }
  let data = null
  try {
    data = JSON.parse(dataLines.join('\n'))
  } catch (e) {
    data = null
  }
  return { event, data }
}

function handleSseEvent(event, data) {
  if (event === 'citations') {
    streamCitations.value = Array.isArray(data) ? data : []
  } else if (event === 'message') {
    if (data && data.delta) {
      streamingText.value += data.delta
    }
  } else if (event === 'error') {
    streamError.value = (data && data.message) || '请求失败'
  }
}

function streamFieldsReset() {
  streamingText.value = ''
  streamCitations.value = []
  streamError.value = ''
}

async function send() {
  if (streaming.value) return
  const question = input.value.trim()
  if (!question) {
    ElMessage.warning('请输入问题')
    return
  }

  input.value = ''
  messages.value.push({ role: 'user', content: question })
  streamFieldsReset()
  streaming.value = true
  streamSeq.value = viewSeq.value
  scrollToBottom()

  const body = { question }
  if (activeConvId.value) body.conversationId = activeConvId.value
  if (scope.value.length) body.documentIds = scope.value

  let resp
  try {
    resp = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify(body)
    })
  } catch (e) {
    ElMessage.error('网络错误，请重试')
    streaming.value = false
    streamSeq.value = -1
    return
  }

  if (!resp.ok) {
    let msg = `请求失败（${resp.status}）`
    try {
      const j = await resp.json()
      msg = j.message || msg
    } catch (e) {
      /* 非 JSON 响应体 */
    }
    ElMessage.error(msg)
    if (resp.status === 401) {
      localStorage.removeItem('token')
      router.replace('/login')
    }
    streaming.value = false
    streamSeq.value = -1
    return
  }

  let doneInfo = null
  try {
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        if (block.trim()) {
          const { event, data } = parseBlock(block)
          if (event === 'done') {
            doneInfo = data
          } else {
            handleSseEvent(event, data)
          }
        }
      }
    }
    if (buf.trim()) {
      const { event, data } = parseBlock(buf)
      if (event === 'done') {
        doneInfo = data
      } else {
        handleSseEvent(event, data)
      }
    }
  } catch (e) {
    streamError.value = '连接中断，请重试'
  } finally {
    const msg = {
      id: doneInfo ? doneInfo.messageId : null,
      role: 'assistant',
      content: streamingText.value || streamError.value || '（无回复内容）',
      citations: streamCitations.value,
      feedback: null,
      isError: !!streamError.value
    }
    const sameView = streamSeq.value === viewSeq.value
    if (doneInfo && doneInfo.conversationId) {
      if (sameView) {
        // 流式视图一直打开：就地追加并记录会话
        activeConvId.value = doneInfo.conversationId
        messages.value.push(msg)
      } else if (activeConvId.value === doneInfo.conversationId) {
        // 切走后又切回该会话：从历史重载补齐
        await loadMessages(doneInfo.conversationId)
      }
    } else if (sameView) {
      // 未落库（模型失败/未配置）也展示在当前会话
      messages.value.push(msg)
    }
    streamFieldsReset()
    streaming.value = false
    streamSeq.value = -1
    await loadConversations()
    scrollToBottom()
  }
}

// ---- 反馈 ----
async function feedback(msg, positive) {
  if (!msg.id) return
  // 再点已高亮的选项 → 取消；点另一项 → 切换
  const clear = (positive && msg.feedback === 'up') || (!positive && msg.feedback === 'down')
  try {
    await api.post(`/messages/${msg.id}/feedback`, { positive: clear ? null : positive })
    msg.feedback = clear ? null : positive ? 'up' : 'down'
    ElMessage.success(clear ? '已取消反馈' : '感谢反馈')
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  }
}

// ---- 滚动 ----
function scrollToBottom() {
  nextTick(() => {
    if (chatBody.value) {
      chatBody.value.scrollTop = chatBody.value.scrollHeight
    }
  })
}

watch(streamingText, scrollToBottom)

onMounted(async () => {
  await Promise.all([loadConversations(), loadScopeOptions()])
})
</script>

<template>
  <div class="chat-page">
    <div class="chat-layout">
      <!-- 左侧：历史会话（可滚动） + 底部固定新对话入口 -->
      <aside class="conv-side">
        <div class="conv-header">历史对话</div>
        <div class="conv-list">
          <div v-if="!convs.length" class="conv-empty">暂无历史会话</div>
          <div
            v-for="conv in convs"
            :key="conv.id"
            class="conv-item"
            :class="{ active: conv.id === activeConvId }"
            @click="openConversation(conv)"
          >
            <span class="conv-title">{{ conv.title }}</span>
            <el-button
              link
              type="danger"
              size="small"
              class="conv-del"
              @click.stop="removeConversation(conv)"
            >
              删除
            </el-button>
          </div>
        </div>
        <el-button type="primary" class="new-chat-btn" @click="newChat">
          开启新对话
        </el-button>
      </aside>

      <!-- 右侧：对话主体 -->
      <main class="chat-main">
        <div ref="chatBody" class="chat-body">
          <div v-if="!messages.length && !streamInView" class="chat-welcome">
            <h2>向健身助手提问</h2>
            <p class="hint">
              资料类问题会引用你上传的文档；关于“进步 / 趋势 / 体重”的问题，
              会基于你的真实训练与体征记录回答
            </p>
          </div>

          <el-alert
            v-if="noDocs"
            class="kb-empty"
            type="info"
            :closable="false"
            show-icon
            title="个人知识库是空的"
          >
            <template #default>
              <span>当前将基于公共知识库回答；上传自己的训练计划或营养资料后，回答会更贴合你的记录。</span>
              <el-button link type="primary" @click="router.push('/documents')">
                去资料页
              </el-button>
            </template>
          </el-alert>

          <div v-for="(msg, i) in messages" :key="i" class="msg-row" :class="msg.role">
            <div class="bubble" :class="{ 'error-bubble': msg.isError }">
              <div v-if="msg.role === 'user'" class="bubble-text">{{ msg.content }}</div>
              <div v-else class="bubble-text bubble-pre">{{ msg.content }}</div>
              <div v-if="msg.role === 'assistant' && msg.citations && msg.citations.length" class="citations">
                <span class="cite-label">引用来源</span>
                <el-tag
                  v-for="c in msg.citations"
                  :key="c.idx"
                  size="small"
                  type="info"
                  class="cite-tag"
                >
                  [{{ c.idx }}]《{{ c.docTitle }}》{{ c.source ? ' · ' + c.source : '' }}
                </el-tag>
              </div>
              <div v-if="msg.role === 'assistant' && msg.id" class="feedback-row">
                <el-button
                  link
                  size="small"
                  :type="msg.feedback === 'up' ? 'primary' : ''"
                  @click="feedback(msg, true)"
                >
                  有帮助
                </el-button>
                <el-button
                  link
                  size="small"
                  :type="msg.feedback === 'down' ? 'danger' : ''"
                  @click="feedback(msg, false)"
                >
                  没帮助
                </el-button>
              </div>
            </div>
          </div>

          <!-- 流式输出中的 assistant 气泡：只在发起提问的会话视图显示 -->
          <div v-if="streamInView && (streamingText || streamCitations.length)" class="msg-row assistant">
            <div class="bubble">
              <div class="bubble-text bubble-pre">
                {{ streamingText || '思考中…' }}<span class="cursor">▍</span>
              </div>
              <div v-if="streamCitations.length" class="citations">
                <span class="cite-label">引用来源</span>
                <el-tag
                  v-for="c in streamCitations"
                  :key="c.idx"
                  size="small"
                  type="info"
                  class="cite-tag"
                >
                  [{{ c.idx }}]《{{ c.docTitle }}》{{ c.source ? ' · ' + c.source : '' }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部输入区 -->
        <div class="chat-input">
          <div class="input-toolbar">
            <el-select
              v-model="scope"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              clearable
              :disabled="streaming || !scopeOptions.length"
              placeholder="限定资料范围（可选）"
              class="scope-select"
            >
              <el-option
                v-for="opt in scopeOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
            <span v-if="scope.length" class="scope-hint">
              仅基于所选 {{ scope.length }} 份资料回答
            </span>
          </div>
          <div class="input-row">
            <el-input
              v-model="input"
              type="textarea"
              :rows="2"
              resize="none"
              placeholder="输入你的问题，如：深蹲日怎么安排？我最近一周训练进步了吗？"
              :disabled="streaming"
              @keydown.enter.exact.prevent="send"
              @focus="loadScopeOptions"
            />
            <el-button
              type="primary"
              class="send-btn"
              :disabled="streaming"
              @click="send"
            >
              {{ streaming ? '回答中…' : '发送' }}
            </el-button>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  padding: 24px;
  display: flex;
  justify-content: center;
}

.chat-layout {
  width: 100%;
  max-width: 1080px;
  display: flex;
  gap: 16px;
  height: calc(100vh - 80px);
}

/* 左侧会话列表 */
.conv-side {
  width: 240px;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
}

.conv-header {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  padding: 4px 8px 8px;
  flex-shrink: 0;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.conv-empty {
  color: #9ca3af;
  font-size: 13px;
  text-align: center;
  margin-top: 24px;
}

.conv-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #374151;
}

.conv-item:hover {
  background: #f3f4f6;
}

.conv-item.active {
  background: #eff6ff;
  color: #1d4ed8;
}

.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-del {
  visibility: hidden;
}

.conv-item:hover .conv-del {
  visibility: visible;
}

/* 底部固定的新对话入口 */
.new-chat-btn {
  width: 100%;
  margin-top: 12px;
  margin-left: 0;
  flex-shrink: 0;
}

/* 右侧对话主体 */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.chat-welcome {
  text-align: center;
  color: #6b7280;
  margin-top: 60px;
}

.chat-welcome h2 {
  color: #1f2937;
  font-size: 20px;
  margin-bottom: 8px;
}

.kb-empty {
  margin-bottom: 16px;
}

.msg-row {
  display: flex;
  margin-bottom: 14px;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-row.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
}

.msg-row.user .bubble {
  background: #409eff;
  color: #fff;
}

.msg-row.assistant .bubble {
  background: #f3f4f6;
  color: #1f2937;
}

.error-bubble {
  background: #fef2f2 !important;
  color: #b91c1c !important;
}

.bubble-pre {
  white-space: pre-wrap;
  word-break: break-word;
}

.cursor {
  animation: blink 1s step-start infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.citations {
  margin-top: 8px;
  border-top: 1px dashed #d1d5db;
  padding-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cite-label {
  font-size: 12px;
  color: #6b7280;
  align-self: center;
}

.cite-tag {
  cursor: default;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.feedback-row {
  margin-top: 6px;
  display: flex;
  gap: 4px;
}

/* 底部输入区 */
.chat-input {
  border-top: 1px solid #e5e7eb;
  padding: 12px 16px;
  background: #fafafa;
}

.input-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.scope-select {
  width: 260px;
}

.scope-hint {
  font-size: 12px;
  color: #6b7280;
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.send-btn {
  height: 54px;
  width: 96px;
}

.hint {
  font-size: 13px;
  color: #9ca3af;
}
</style>