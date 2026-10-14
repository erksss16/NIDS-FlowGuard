<template>
  <div class="login-page">
    <div class="login-card">
      <div class="logo-section">
        <div class="logo-icon">
          <svg viewBox="0 0 48 48" fill="none">
            <rect x="10" y="10" width="28" height="28" rx="7" stroke="currentColor" stroke-width="2.5"/>
            <path d="M24 17v14M17 24h14" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
            <circle cx="24" cy="24" r="10" stroke="currentColor" stroke-width="2.5"/>
          </svg>
        </div>
        <h1 class="logo-title">NIDS</h1>
        <p class="logo-desc">网络流量入侵检测系统</p>
      </div>

      <form class="login-form" @submit.prevent="handleLogin(false)">
        <div class="input-group">
          <label class="input-label">用户名</label>
          <input v-model="username" type="text" class="input-field" placeholder="请输入用户名" autocomplete="username" />
        </div>
        <div class="input-group">
          <label class="input-label">密码</label>
          <input v-model="password" :type="showPwd ? 'text' : 'password'" class="input-field" placeholder="请输入密码" autocomplete="current-password" />
        </div>

        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

        <button type="submit" class="login-btn" :class="{ loading }">
          <span v-if="!loading">登 录</span>
          <span v-else class="loading-text"><span class="spinner"></span>验证中...</span>
        </button>
      </form>

      <p class="login-footer">信息安全竞赛作品</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const showPwd = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const backendUrl = 'http://localhost:8000'

async function handleLogin() {
  errorMsg.value = ''
  if (!username.value.trim()) { errorMsg.value = '请输入用户名'; return }
  if (!password.value.trim()) { errorMsg.value = '请输入密码'; return }

  loading.value = true
  try {
    const res = await fetch(`${backendUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value.trim(), password: password.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok && data.ok) {
      sessionStorage.setItem('nids_auth', 'true')
      sessionStorage.setItem('nids_user', JSON.stringify(data.user))
      router.push('/app/dashboard')
    } else {
      errorMsg.value = data.detail || '用户名或密码错误'
    }
  } catch {
    errorMsg.value = '后端服务未启动，请先运行 NIDS 后端'
  } finally {
    loading.value = false
  }
}

</script>

<style scoped>
.login-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #fafaf9; }
.login-card { width: 380px; max-width: 92vw; padding: 44px 36px 32px; background: #fff; border: 1px solid #e7e5e4; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.logo-section { text-align: center; margin-bottom: 32px; }
.logo-icon { width: 44px; height: 44px; margin: 0 auto 14px; color: #f97316; }
.logo-icon svg { width: 100%; height: 100%; }
.logo-title { font-size: 22px; font-weight: 700; letter-spacing: 0.06em; color: #292524; margin-bottom: 4px; }
.logo-desc { font-size: 13px; color: #78716c; }

.login-form { display: flex; flex-direction: column; gap: 16px; }
.input-label { display: block; font-size: 13px; font-weight: 500; color: #44403c; margin-bottom: 5px; }
.input-field { width: 100%; padding: 10px 14px; background: #fafaf9; border: 1px solid #e7e5e4; border-radius: 6px; color: #292524; font-size: 14px; font-family: inherit; outline: none; transition: border-color 0.2s; }
.input-field::placeholder { color: #a8a29e; }
.input-field:focus { border-color: #f97316; box-shadow: 0 0 0 3px rgba(249,115,22,0.1); }

.error-msg { font-size: 13px; color: #ef4444; background: rgba(239,68,68,0.06); padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(239,68,68,0.15); }

.login-btn { width: 100%; margin-top: 6px; padding: 11px; background: #f97316; color: #fff; border: none; border-radius: 6px; font-size: 14px; font-weight: 600; font-family: inherit; cursor: pointer; transition: background 0.2s; }
.login-btn:hover:not(.loading) { background: #ea580c; }
.login-btn.loading { background: #e7e5e4; color: #78716c; cursor: not-allowed; }
.loading-text { display: inline-flex; align-items: center; gap: 8px; }
.spinner { width: 14px; height: 14px; border: 2px solid #d6d3d1; border-top-color: #f97316; border-radius: 50%; animation: spin 0.6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.login-footer { text-align: center; margin-top: 24px; font-size: 12px; color: #a8a29e; }
</style>
