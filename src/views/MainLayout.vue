<template>
  <div class="main-layout">
    <nav class="sidenav">
      <div class="nav-header" @click="router.push('/app/dashboard')">
        <div class="nav-logo">
          <svg viewBox="0 0 48 48" fill="none">
            <rect
              x="10"
              y="10"
              width="28"
              height="28"
              rx="7"
              stroke="currentColor"
              stroke-width="2.5"
            />
            <path
              d="M24 17v14M17 24h14"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
            />
            <circle
              cx="24"
              cy="24"
              r="10"
              stroke="currentColor"
              stroke-width="2.5"
            />
          </svg>
        </div>
        <div class="nav-brand">
          <span class="nav-title">NIDS</span>
          <span class="nav-subtitle">入侵检测系统</span>
        </div>
      </div>

      <div class="nav-links">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="active"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            v-html="item.icon"
          ></svg>
          <span>{{ item.label }}</span>
        </router-link>
      </div>

      <div class="nav-footer">
        <button class="logout-btn" @click="handleLogout">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          <span>退出登录</span>
        </button>
      </div>
    </nav>

    <div class="content-area">
      <header class="topbar">
        <div class="topbar-left">
          <h2 class="topbar-title">{{ pageTitle }}</h2>
        </div>
        <div class="topbar-right">
          <button
            class="import-btn"
            @click="handleDBConnect"
            :disabled="connecting"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            {{ dbConnected ? "已连接" : connecting ? "连接中" : "连接数据库" }}
          </button>
          <span v-if="dbConnected" class="live-badge">实时同步中</span>
        </div>
      </header>

      <div class="content-body">
        <router-view v-slot="{ Component }">
          <transition name="content-fade" mode="out-in">
            <component :is="Component" :key="$route.path" />
          </transition>
        </router-view>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, provide, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";

const router = useRouter();
const route = useRoute();

const backendUrl = ref("http://localhost:8000");
provide("backendUrl", backendUrl);

const dbConnected = ref(false);
provide("dbConnected", dbConnected);
const connecting = ref(false);

const navItems = [
  {
    path: "/app/dashboard",
    label: "总览",
    icon: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  },
  {
    path: "/app/traffic",
    label: "实时流量",
    icon: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  },
  {
    path: "/app/traffic-logs",
    label: "完整日志",
    icon: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
  },
  {
    path: "/app/alerts",
    label: "告警中心",
    icon: '<path d="M12 2 2 22h20L12 2Z"/><path d="M12 9v5"/><path d="M12 18h.01"/>',
  },
  {
    path: "/app/statistics",
    label: "统计分析",
    icon: '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>',
  },
  {
    path: "/app/model",
    label: "模型性能",
    icon: '<circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 6v6M5.6 5.6l4.2 4.2m4.4 4.4l4.2 4.2M1 12h6m6 0h6M5.6 18.4l4.2-4.2m4.4-4.4l4.2-4.2"/>',
  },
  {
    path: "/app/assistant",
    label: "AI 助手",
    icon: '<path d="M12 3a7 7 0 0 0-7 7v3a4 4 0 0 0 4 4h1l2 3 2-3h1a4 4 0 0 0 4-4v-3a7 7 0 0 0-7-7Z"/><path d="M9 10h.01M15 10h.01M9.5 14a4 4 0 0 0 5 0"/>',
  },
].filter((item) => item.path !== "/app/model");

const pageTitle = computed(() => {
  const map = {
    "/app/dashboard": "总览",
    "/app/traffic": "实时流量",
    "/app/traffic-logs": "完整流量日志",
    "/app/alerts": "告警中心",
    "/app/statistics": "统计分析",
    "/app/model": "模型性能",
    "/app/assistant": "AI 安全助手",
  };
  return map[route.path] || "";
});

async function handleDBConnect() {
  connecting.value = true;
  try {
    const res = await fetch(`${backendUrl.value}/api/health`);
    const data = await res.json();
    dbConnected.value = Boolean(data.connected);
  } catch {
    dbConnected.value = false;
  } finally {
    connecting.value = false;
  }
}

function handleLogout() {
  sessionStorage.removeItem("nids_auth");
  router.push("/");
}

onMounted(handleDBConnect);
</script>

<style scoped>
.main-layout {
  display: flex;
  min-height: 100vh;
  background: #fafaf9;
}
.sidenav {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: 200px;
  background: #fff;
  border-right: 1px solid #e7e5e4;
  display: flex;
  flex-direction: column;
  z-index: 100;
}
.nav-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 14px;
  cursor: pointer;
  border-bottom: 1px solid #f5f5f4;
}
.nav-logo {
  width: 28px;
  height: 28px;
  color: #f97316;
  flex-shrink: 0;
}
.nav-logo svg {
  width: 100%;
  height: 100%;
}
.nav-brand {
  display: flex;
  flex-direction: column;
}
.nav-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #292524;
}
.nav-subtitle {
  font-size: 10px;
  color: #a8a29e;
}
.nav-links {
  flex: 1;
  padding: 8px 6px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 11px;
  border-radius: 6px;
  color: #78716c;
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  transition:
    background 0.15s,
    color 0.15s;
}
.nav-item svg {
  width: 17px;
  height: 17px;
  flex-shrink: 0;
}
.nav-item:hover {
  background: #f5f5f4;
  color: #292524;
}
.nav-item.active {
  background: rgba(249, 115, 22, 0.08);
  color: #f97316;
}
.nav-footer {
  padding: 8px 6px;
  border-top: 1px solid #f5f5f4;
}
.logout-btn {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 8px 11px;
  border-radius: 6px;
  background: none;
  border: none;
  color: #a8a29e;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
}
.logout-btn svg {
  width: 15px;
  height: 15px;
}
.logout-btn:hover {
  background: rgba(239, 68, 68, 0.06);
  color: #ef4444;
}
.content-area {
  margin-left: 200px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 28px;
  background: #fff;
  border-bottom: 1px solid #e7e5e4;
  position: sticky;
  top: 0;
  z-index: 50;
}
.topbar-title {
  font-size: 18px;
  font-weight: 700;
  color: #292524;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.import-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: 6px;
  background: #f97316;
  color: #fff;
  border: none;
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;
}
.import-btn svg {
  width: 15px;
  height: 15px;
}
.import-btn:hover {
  background: #ea580c;
}
.import-btn:disabled {
  opacity: 0.65;
  cursor: wait;
}
.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 10px;
  background: rgba(22, 163, 74, 0.08);
  color: #16a34a;
  font-size: 11px;
  font-weight: 600;
}
.content-body {
  flex: 1;
  padding: 22px 28px;
}
.content-fade-enter-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.content-fade-leave-active {
  transition:
    opacity 0.12s ease,
    transform 0.12s ease;
}
.content-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.content-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
@media (max-width: 768px) {
  .content-body {
    padding: 16px 12px;
  }
  .topbar {
    padding: 12px 16px;
  }
}
</style>
