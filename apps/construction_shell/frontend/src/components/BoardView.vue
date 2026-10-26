<template>
  <div class="flex min-h-0 flex-1 flex-col gap-3.5 px-6 py-5" data-testid="board-view">
    <div class="flex flex-wrap items-end gap-3">
      <div class="min-w-0 flex-[1_1_320px]">
        <div class="text-xs text-ink-gray-7"><router-link :to="{ name: 'section', params: { project, section: 'whiteboards' } }" class="text-ink-gray-7 no-underline hover:text-ink-gray-9">← Canvas</router-link></div>
        <div class="mt-1 flex flex-wrap items-baseline gap-2.5">
          <h1 class="m-0 text-3xl-semibold text-ink-gray-9" data-testid="board-title-heading">{{ board?.title || 'Board' }}</h1>
          <span v-if="status" class="text-sm text-ink-gray-7" data-testid="board-status">{{ status }}</span>
          <span v-if="savedLine" class="text-sm text-ink-gray-7" data-testid="board-saved">{{ savedLine }}</span>
          <Badge v-if="board?.client_visible" theme="blue" label="Shared with client" />
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button v-if="target" variant="solid" theme="blue" size="md" icon-left="lucide-send" :label="w('markup.post', { title: postTitle })" :loading="posting" :disabled="!board"
          data-testid="post-board" @click="postBack" />
        <Button v-if="board?.can_edit" variant="solid" theme="blue" size="md" label="Save version" :disabled="!unsaved || saving"
          data-testid="save-version" @click="save" />
        <Button variant="outline" size="md" label="Versions" data-testid="board-versions" @click="toggleVersions" />
        <Button variant="outline" size="md" icon-left="lucide-message-circle" label="Team discussion" @click="discuss('Internal')" />
        <Button v-if="board?.client_visible" variant="outline" size="md" icon-left="lucide-message-circle" label="Client conversation" @click="discuss('Client')" />
      </div>
    </div>
    <p v-if="error" class="text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
    <div class="flex min-h-0 flex-1 flex-wrap gap-3">
      <div class="cw-card flex min-w-0 flex-[999_1_520px] flex-col overflow-hidden">
        <!-- The React root lives on this element only; Vue never re-renders its children. -->
        <div ref="canvas" class="min-h-[70vh] flex-1" data-testid="board-canvas" />
      </div>
      <aside v-if="versions" class="cw-card flex-[1_1_260px] overflow-y-auto p-3" data-testid="versions">
        <h2 class="cw-label mb-1.5 text-ink-gray-7">Versions</h2>
        <div v-for="v in versions" :key="v.version" class="flex items-center gap-2 rounded-4 px-2 py-1.5 text-sm hover:bg-surface-gray-1">
          <span class="w-8 font-semibold text-ink-gray-9">v{{ v.version }}</span>
          <span class="min-w-0 flex-1 truncate text-ink-gray-8">{{ v.saved_by }}</span>
          <Button size="xs" label="Restore" @click="restore(v.version)" />
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, useColorScheme } from 'frappe-ui'
import { call } from '../api.js'
import { createHost } from '../chat/host.js'
import { trayOf } from '../chat/parts/attachments/tray.js'
import { flatBlob, settle } from '../chat/parts/markup/board.js'
import { roomName } from '../chat/rooms.js'
import { threadTitle } from '../chat/threads.js'
import { wordsFor } from '../chat/words.js'
import { ENGINES, loadScript } from '../loader.js'
import { useMode } from '../mode.js'
import { onEvent, subscribeDoc } from '../realtime.js'
import { boot } from '../boot.js'

// A project whiteboard on the same engine and API as the Desk Board page (P1-15): autosave 2.5 s after the last
// change; a save names the version it started from, so a colleague's newer save is never overwritten. Every save is a
// version on the server (whiteboard.api.save), so "Save version" saves now instead of waiting (D-146).
const WB = 'construction_core.whiteboard.api.'
const props = defineProps({ name: { type: String, required: true }, project: String })

// Excalidraw follows the Light/Dark choice (D-126), also when it changes with the board open. The saved scene keeps
// no theme (whiteboard_loader.serialise), so one viewer's choice never reaches another.
const { resolvedColorScheme } = useColorScheme()
watch(resolvedColorScheme, (theme) => api && api.updateScene({ appState: { theme } }))
const router = useRouter()
const route = useRoute()
const w = wordsFor(useMode())
// P3-70: "Mark up on a Canvas" opens the board with ?post=<conversation>; "Post to <conversation>" sends its picture back there.
// A board opened from Canvas has no such address, so it has no button; nor has one whose address names a conversation that is
// not one of this board's project's that this person can open (aim: the threads read lists only those).
const host = createHost({ viewer: 'staff', base: { project: () => props.project } })
const post = computed(() => (typeof route.query.post === 'string' ? route.query.post : ''))
const target = ref(null)
const postTitle = computed(() => (target.value?.in_room ? threadTitle(target.value, w) : roomName(target.value, { viewer: 'staff', w })))
const posting = ref(false)
const canvas = ref(null)
const board = ref(null)
// What is happening now: unsaved changes, a save on its way, a colleague's save, a restore. Nothing once the board is
// saved: the design's line below says which version and who saved it (D-185).
const status = ref('')
const error = ref('')
const versions = ref(null)
const unsaved = ref(false)
const saving = ref(false)
// The design's line under the title (D-170): "Version N · saved by <name> · <time> ago", from the board's own saves.
// The server gives the saver's name and the seconds since the save (site time), so no clock zone is involved.
const saved = ref(null)
const now = ref(Date.now())
let ticker = null
const savedLine = computed(() => (saved.value
  ? `Version ${saved.value.version} · saved by ${saved.value.by} · ${ago(now.value - saved.value.at)}`
  : ''))

function ago(ms) {
  const minutes = Math.floor(Math.max(0, ms) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  return `${days} ${days === 1 ? 'day' : 'days'} ago`
}

function setSaved(v, by, ageSeconds) {
  saved.value = by ? { version: v, by, at: Date.now() - (ageSeconds || 0) * 1000 } : null
}
let lib = null
let api = null
let root = null
let version = 0
let edits = 0 // counts changes, so a save knows whether the board changed while it was in flight
let timer = null
let snapTimer = null
let gone = false // the board was left: Excalidraw is unmounted, so its API no longer holds the drawing
let leaving = null // the drawing as it was when the board was left
let lastSceneVersion = null
let savedJson = null
let settledAt = 0
const cleanups = []

function render(b) {
  board.value = b
  setSaved(b.version, b.saved_by_name, b.saved_age)
  version = b.version
  status.value = ''
  root = root || window.ReactDOM.createRoot(canvas.value)
  root.render(window.React.createElement(lib.Excalidraw, {
    key: b.name,
    initialData: { elements: b.scene.elements || [], appState: b.scene.appState || {}, files: b.scene.files || {} },
    viewModeEnabled: !b.can_edit,
    theme: resolvedColorScheme.value,
    excalidrawAPI: (a) => (api = a),
    onChange: changed,
    UIOptions: { canvasActions: { loadScene: false, saveToActiveFile: false } },
  }))
  lastSceneVersion = null
  savedJson = null
  settledAt = Date.now() + 1500 // Excalidraw re-measures text once fonts load; that is not an edit
}

function changed(elements, appState, files) {
  const v = lib.getSceneVersion(elements)
  if (lastSceneVersion === null || Date.now() < settledAt) {
    if (lastSceneVersion === null && post.value) api?.scrollToContent(undefined, { fitToContent: true }) // the picture opens whole
    lastSceneVersion = v
    savedJson = window.ccWhiteboard.serialise(elements, appState, files)
    return
  }
  if (v === lastSceneVersion) return
  lastSceneVersion = v
  clearTimeout(snapTimer) // the board is not idle: its picture waits for the next save
  edits += 1
  unsaved.value = true
  status.value = 'unsaved changes'
  clearTimeout(timer)
  timer = setTimeout(save, 2500)
}

async function save() {
  clearTimeout(timer)
  if (!api || !unsaved.value || saving.value) return
  saving.value = true
  status.value = 'saving…'
  const at = edits
  let again = false
  try {
    // After the board is left, only the drawing taken as it closed is sent: an unmounted Excalidraw reads as empty.
    const scene = gone ? leaving : window.ccWhiteboard.serialise(api.getSceneElements(), api.getAppState(), api.getFiles())
    if (scene === savedJson) {
      unsaved.value = false
      status.value = ''
      return
    }
    const r = await call(WB + 'save', { name: props.name, scene, base_version: version }, { post: true })
    if (r.conflict) {
      error.value = 'A colleague saved this board; showing their version.'
      replace(r.scene, r.version)
      setSaved(r.version, r.saved_by_name, r.saved_age)
    } else {
      version = r.version
      savedJson = scene
      setSaved(r.version, boot.full_name || boot.user, 0)
      // An edit made while this save was in flight is not in it: it stays unsaved and is saved next.
      unsaved.value = edits !== at || (gone && scene !== leaving)
      status.value = unsaved.value ? 'unsaved changes' : ''
      again = unsaved.value
      if (!again && !gone) snapTimer = setTimeout(() => snapshot(r.version), SNAPSHOT_IDLE)
    }
  } catch (e) {
    error.value = e.message || 'Could not save the board.'
  } finally {
    saving.value = false
  }
  if (again && gone) save() // left mid-save: send the last drawing now
  else if (again) timer = setTimeout(save, 2500)
}

// P3-75 (design §15.2): once a save has gone through and the board is idle, its picture (PNG, at most 512 px, always
// light) is sent with the version it shows, for the board's preview in cards and lists. The server takes it only for
// the newest version; a picture that fails never touches the board or its saves.
const SNAPSHOT_IDLE = 1500
// The board as a light PNG, its long side at most `max` px: the preview (512) and the picture posted to a conversation (2048).
const pngOf = (max) => flatBlob(lib, api, { mimeType: 'image/png', maxWidthOrHeight: max })

async function snapshot(v) {
  if (!api || gone || unsaved.value || saving.value || v !== version || !board.value?.can_edit) return
  try {
    const blob = await pngOf(512)
    const image = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = () => reject(reader.error)
      reader.readAsDataURL(blob)
    })
    if (v === version && !unsaved.value) await call(WB + 'snapshot', { name: props.name, version: v, image }, { post: true })
  } catch {
    // the preview keeps its placeholder; the board itself is saved
  }
}

function replace(scene, v) {
  version = v
  unsaved.value = false
  lastSceneVersion = null
  settledAt = Date.now() + 1500
  api.updateScene({ elements: scene.elements || [], appState: scene.appState || {} })
  if (scene.files) api.addFiles(Object.values(scene.files))
  status.value = ''
}

async function aim(project) {
  if (!post.value) return
  try {
    target.value = (await host.read('threads', { project })).find((t) => t.name === post.value) || null
  } catch {
    target.value = null
  }
}

// P3-70 (design §3.11): the board as one flat picture goes to the conversation's tray, as a new file; the person adds a note
// and sends it there. A save already running is waited for, and what is still unsaved is saved again, before the picture is
// made, so the board and the picture are never apart. The first save that fails or conflicts stops the post (its error is shown).
async function postBack() {
  if (!api) return
  posting.value = true
  error.value = ''
  try {
    await settle({ saving, unsaved, save })
    if (error.value) return
    const file = new File([await pngOf(2048)], `${board.value.title}.png`, { type: 'image/png' })
    trayOf(host, target.value.name).add([file], { shrink: false })
    router.push({ name: 'section', params: { project: board.value.project, section: 'discuss', item: target.value.name } })
  } catch (e) {
    error.value = e.message || w('markup.post_failed')
  } finally {
    posting.value = false
  }
}

async function onRemoteSave(d) {
  if (d.name !== props.name || d.version <= version || d.by === boot.user) return
  if (unsaved.value) {
    status.value = `a colleague saved version ${d.version}; your next save will show it`
    return
  }
  const b = await call(WB + 'load', { name: props.name })
  replace(b.scene, b.version)
  setSaved(b.version, b.saved_by_name, b.saved_age)
}

async function toggleVersions() {
  versions.value = versions.value ? null : await call(WB + 'versions', { name: props.name })
}

async function restore(v) {
  try {
    const r = await call(WB + 'restore', { name: props.name, version: v }, { post: true })
    const b = await call(WB + 'load', { name: props.name })
    replace(b.scene, b.version)
    setSaved(b.version, b.saved_by_name, b.saved_age)
    status.value = `restored as version ${r.version}`
    versions.value = null
  } catch (e) {
    error.value = e.message
  }
}

async function discuss(audience) {
  try {
    const thread = await call(WB + 'thread', { name: props.name, audience }, { post: true })
    router.push({ name: 'section', params: { project: props.project, section: 'discuss', item: thread } })
  } catch (e) {
    error.value = e.message
  }
}

onMounted(async () => {
  ticker = setInterval(() => (now.value = Date.now()), 30000) // "N min ago" moves on while the board is open
  cleanups.push(subscribeDoc('Whiteboard', props.name), onEvent('cc_whiteboard_saved', onRemoteSave))
  try {
    await loadScript(ENGINES.whiteboard)
    const [l, b] = await Promise.all([window.ccWhiteboard.load(), call(WB + 'load', { name: props.name })])
    lib = l
    render(b)
    aim(b.project) // the board's own project, whatever the address says
  } catch (e) {
    error.value = e.message || 'Could not open the board.'
  }
})

onBeforeUnmount(() => {
  clearInterval(ticker)
  clearTimeout(timer)
  clearTimeout(snapTimer)
  if (unsaved.value && api) leaving = window.ccWhiteboard.serialise(api.getSceneElements(), api.getAppState(), api.getFiles())
  gone = true
  if (unsaved.value) save() // keep the last change; the save names its base version, so it never overwrites a newer one
  cleanups.forEach((off) => off())
  if (root) root.unmount()
})
</script>
