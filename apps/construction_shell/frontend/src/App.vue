<template>
  <div class="flex h-full flex-col" data-testid="shell-app">
    <TopBar />
    <div class="flex min-h-0 flex-1">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, watch } from 'vue'
import TopBar from './components/TopBar.vue'
import { useMode } from './mode.js'
import { attach as attachBell, load as loadBell } from './notifications.js'
import { onEvent } from './realtime.js'
import { loadProjects, setCounts } from './store.js'

// Section counts and notices arrive in the user's own room (DR-8): one handler each for the whole app, removed with
// it. The bell also reloads when the window comes back (the socket gives up after its last reconnect attempt) and when
// the view changes, since its words are the view's (P3-06).
const mode = useMode()
const reloadBell = () => loadBell(mode.value)
const onVisible = () => document.visibilityState === 'visible' && reloadBell()
let off = null
let offBell = null
onMounted(() => {
  loadProjects()
  off = onEvent('cc_workspace_counts', ({ project, counts }) => setCounts(project, counts))
  reloadBell()
  offBell = attachBell(onEvent, reloadBell)
  window.addEventListener('focus', reloadBell)
  document.addEventListener('visibilitychange', onVisible)
})
watch(mode, reloadBell)
onUnmounted(() => {
  off && off()
  offBell && offBell()
  window.removeEventListener('focus', reloadBell)
  document.removeEventListener('visibilitychange', onVisible)
})
</script>
