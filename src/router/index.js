import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import MainLayout from '../views/MainLayout.vue'
import Dashboard from '../views/Dashboard.vue'
import TrafficMonitor from '../views/TrafficMonitor.vue'
import TrafficLogs from '../views/TrafficLogs.vue'
import AlertCenter from '../views/AlertCenter.vue'
import Statistics from '../views/Statistics.vue'
import ModelPerformance from '../views/ModelPerformance.vue'
import AIAssistant from '../views/AIAssistant.vue'

const routes = [
  { path: '/', name: 'Login', component: Login },
  {
    path: '/app',
    component: MainLayout,
    children: [
      { path: 'dashboard', name: 'Dashboard', component: Dashboard },
      { path: 'traffic', name: 'TrafficMonitor', component: TrafficMonitor },
      { path: 'traffic-logs', name: 'TrafficLogs', component: TrafficLogs },
      { path: 'alerts', name: 'AlertCenter', component: AlertCenter },
      { path: 'statistics', name: 'Statistics', component: Statistics },
      { path: 'model', name: 'ModelPerformance', component: ModelPerformance },
      { path: 'assistant', name: 'AIAssistant', component: AIAssistant },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const loggedIn = sessionStorage.getItem('nids_auth')

  // Already logged in → redirect from login page to dashboard
  if (to.name === 'Login' && loggedIn) {
    next({ name: 'Dashboard' })
    return
  }

  // Protected routes: must be logged in
  if (to.path.startsWith('/app') && !loggedIn) {
    next({ name: 'Login' })
    return
  }

  next()
})

export default router
