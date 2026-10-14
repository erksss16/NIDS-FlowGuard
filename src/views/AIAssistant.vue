<template>
  <div class="ai-assistant">
    <div v-if="dbConnected" class="assistant-shell">
      <section class="assistant-header">
        <div>
          <h3>AI 安全助手</h3>
          <span>可以询问检测数据，也可以进行普通对话</span>
        </div>
        <div class="assistant-status">
          <span></span>
          数据库已连接
        </div>
      </section>

      <section class="quick-panel">
        <button v-for="q in quickQuestions" :key="q" @click="askQuick(q)">{{ q }}</button>
      </section>

      <section class="chat-panel">
        <div ref="chatBody" class="chat-body">
          <div v-for="msg in messages" :key="msg.id" class="message-row" :class="msg.role">
            <div class="message-bubble">
              <p>{{ msg.text }}</p>
            </div>
          </div>
        </div>

        <form class="chat-input" @submit.prevent="sendMessage">
          <input v-model="draft" placeholder="例如：最近的告警是什么类型？" :disabled="loading" />
          <button type="submit" :disabled="loading || !draft.trim()">{{ loading ? '思考中' : '发送' }}</button>
        </form>
      </section>
    </div>

    <div v-else class="clean-state">
      <div class="clean-card">
        <h3>AI 安全助手</h3>
        <p>请先连接检测结果数据库。普通问题可直接回答，检测相关问题会基于当前数据分析。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, nextTick } from 'vue'

const dbConnected = inject('dbConnected')
const backendUrl = inject('backendUrl')

const quickQuestions = [
  '最近的告警是什么时候，是什么类型？',
  '攻击来源最多的 IP 是什么，是什么协议的？',
  '攻击是如何进行的？',
  '异常告警主要集中在哪些协议？',
  '哪些服务被攻击最多？',
]

const messages = ref([
  {
    id: 1,
    role: 'assistant',
    text: '你可以问我检测数据相关问题，也可以问普通问题。涉及告警、流量、攻击来源、协议服务时，我会先查询当前数据库再回答。',
  },
])
const draft = ref('')
const loading = ref(false)
const chatBody = ref(null)
let nextId = 2

async function scrollBottom() {
  await nextTick()
  if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight
}
function askQuick(question) {
  draft.value = question
  sendMessage()
}
async function sendMessage() {
  const text = draft.value.trim()
  if (!text || loading.value) return
  messages.value.push({ id: nextId++, role: 'user', text })
  draft.value = ''
  loading.value = true
  await scrollBottom()
  try {
    const res = await fetch(`${backendUrl.value}/api/assistant/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    messages.value.push({
      id: nextId++,
      role: 'assistant',
      text: data.answer,
    })
  } catch (e) {
    messages.value.push({
      id: nextId++,
      role: 'assistant',
      text: '助手暂时无法回答，请确认后端服务正在运行。',
    })
  } finally {
    loading.value = false
    await scrollBottom()
  }
}
</script>

<style scoped>
.assistant-shell { display: grid; grid-template-rows: auto auto 1fr; gap: 14px; min-height: calc(100vh - 112px); }
.assistant-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 18px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.assistant-header h3 { font-size: 16px; color: #292524; margin-bottom: 3px; }
.assistant-header span { font-size: 12px; color: #78716c; }
.assistant-status { display: inline-flex; align-items: center; gap: 7px; color: #16a34a; font-size: 12px; font-weight: 700; }
.assistant-status span { width: 8px; height: 8px; border-radius: 50%; background: #16a34a; }
.quick-panel { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.quick-panel button { height: 32px; padding: 0 12px; border: 1px solid #dbeafe; border-radius: 6px; background: #eff6ff; color: #2563eb; font-size: 12px; font-weight: 700; cursor: pointer; }
.quick-panel button:hover { background: #dbeafe; }
.chat-panel { display: grid; grid-template-rows: 1fr auto; min-height: 520px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; overflow: hidden; }
.chat-body { padding: 18px; overflow-y: auto; }
.message-row { display: flex; margin-bottom: 12px; }
.message-row.user { justify-content: flex-end; }
.message-bubble { max-width: min(760px, 82%); padding: 12px 14px; border-radius: 8px; background: #f8fafc; color: #292524; border: 1px solid #e2e8f0; }
.message-row.user .message-bubble { background: #2563eb; color: #fff; border-color: #2563eb; }
.message-bubble p { margin: 0; font-size: 14px; line-height: 1.7; white-space: pre-wrap; }
.chat-input { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 14px; border-top: 1px solid #f5f5f4; background: #fafafa; }
.chat-input input { height: 40px; border: 1px solid #e7e5e4; border-radius: 6px; padding: 0 12px; background: #fff; color: #292524; font-size: 14px; outline: none; }
.chat-input input:focus { border-color: #2563eb; }
.chat-input button { height: 40px; padding: 0 18px; border: 1px solid #2563eb; border-radius: 6px; background: #2563eb; color: #fff; font-size: 13px; font-weight: 700; cursor: pointer; }
.chat-input button:disabled { opacity: 0.65; cursor: not-allowed; }
.clean-state { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 120px); }
.clean-card { text-align: center; max-width: 460px; padding: 42px 30px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px; }
.clean-card h3 { font-size: 18px; color: #292524; margin-bottom: 8px; }
.clean-card p { color: #78716c; line-height: 1.7; font-size: 14px; }
@media (max-width: 760px) {
  .assistant-header { align-items: flex-start; flex-direction: column; gap: 10px; }
  .message-bubble { max-width: 92%; }
  .chat-input { grid-template-columns: 1fr; }
}
</style>
