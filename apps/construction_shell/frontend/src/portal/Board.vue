<template>
  <main class="mx-auto flex w-full max-w-[1120px] flex-1 flex-col gap-3.5 px-5 py-6" data-testid="portal-board">
    <div>
      <div class="text-xs text-ink-gray-7">
        <router-link :to="{ name: 'portal-project', params: { project }, query: { tab: 'files', group: 'whiteboards' } }" class="text-ink-gray-7 no-underline hover:text-ink-gray-9">← Shared files</router-link>
      </div>
      <div class="mt-1 flex flex-wrap items-baseline gap-2.5">
        <h1 class="m-0 text-3xl-semibold text-ink-gray-9" data-testid="portal-board-title">{{ title }}</h1>
        <Badge label="View only" />
      </div>
    </div>
    <p v-if="error" class="text-ink-red-7" role="alert">{{ error }}</p>
    <!-- An explicit height: Excalidraw fills its parent at 100%, which a min-height alone does not give. -->
    <div class="cw-card overflow-hidden">
      <div ref="canvas" class="h-[calc(100vh-190px)] min-h-[420px]" data-testid="portal-board-canvas" />
    </div>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, useColorScheme } from 'frappe-ui'
import { call } from '../api.js'
import { ENGINES, loadScript } from '../loader.js'
import { onEvent } from '../realtime.js'

// A client-visible board, read-only, on the same engine and API as the staff board (P1-15). Saves arrive in the
// client's own user room (D-100).
const route = useRoute()
const project = computed(() => route.params.project)
const canvas = ref(null)
const title = ref('Canvas')
const error = ref('')
let root = null
let api = null

// Excalidraw follows the Light/Dark choice (D-126), also when it changes with the board open. The saved scene keeps
// no theme (whiteboard_loader.serialise), so one viewer's choice never reaches another.
const { resolvedColorScheme } = useColorScheme()
watch(resolvedColorScheme, (theme) => api && api.updateScene({ appState: { theme } }))

async function show() {
  const b = await call('construction_core.whiteboard.api.load', { name: route.params.board })
  title.value = b.title
  const scene = { elements: b.scene.elements || [], appState: b.scene.appState || {}, files: b.scene.files || {} }
  if (api) {
    api.updateScene({ elements: scene.elements, appState: scene.appState })
    if (b.scene.files) api.addFiles(Object.values(b.scene.files))
    return
  }
  const lib = await window.ccWhiteboard.load()
  root = window.ReactDOM.createRoot(canvas.value)
  root.render(window.React.createElement(lib.Excalidraw, {
    initialData: scene, viewModeEnabled: true, zenModeEnabled: true, excalidrawAPI: (a) => (api = a),
    theme: resolvedColorScheme.value,
  }))
}

const off = onEvent('cc_whiteboard_saved', (d) => d.name === route.params.board && show().catch(() => {}))

onMounted(async () => {
  try {
    await loadScript(ENGINES.whiteboard)
    await show()
  } catch (e) {
    error.value = e.message || 'Could not open the board.'
  }
})

onBeforeUnmount(() => {
  off()
  if (root) root.unmount()
})
</script>
