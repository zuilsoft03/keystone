<template>
  <NotFound v-if="missing" />
  <main v-else class="mx-auto flex w-full max-w-[1120px] flex-1 flex-col gap-4 px-5 py-6" data-testid="portal-project">
    <p v-if="error" class="text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
    <p v-if="!data && !error" class="text-ink-gray-7">Loading…</p>
    <template v-else-if="data">
      <p v-if="data.closed?.closed" class="m-0 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="portal-closed">This project is closed. You can read what was shared with you{{ data.closed.clients_until ? ` until ${data.closed.clients_until.slice(0, 10)}` : '' }}; nothing new can be added.</p>
      <HomeView v-if="tab === 'home'" :data="data" :project="project" :tabs="tabs" />
      <RequestsView v-else-if="tab === 'discuss' && requestName" :key="requestName" :request="requestName" :room="room?.name || ''" />
      <DiscussionView v-else-if="tab === 'discuss'" :room="room" :rows="threadRows" :loaded="roomsLoaded" :accept="acceptOf(data.upload)"
        :ask="ask" @asked="ask = ''" />
      <ApprovalsView v-else-if="tab === 'approvals'" :data="data" :groups="groupsOf('approvals')" :group="group" :discuss="tabs.some((t) => t.key === 'discuss')" />
      <FilesView v-else-if="tab === 'files'" :data="data" :project="project" :groups="groupsOf('files')" :group="group"
        :can-send="canSend" :accept="acceptOf(data.upload)" :sending="sending" :holds="holds" :can-ask="canAsk" @send-file="(file) => sendFile(file)" @ask="askAbout" />
    </template>
    <!-- P3-79: a request's sheet over the Approvals tab, from the address the request email and the cards carry. -->
    <ApprovalSheet v-if="sheetRequest" :key="sheetRequest" :request="sheetRequest" :option="asked('option')" :step="asked('step')"
      :can-message="tabs.some((t) => t.key === 'discuss')" @close="closeSheet" @message="messageTeam" />
  </main>
</template>

<script setup>
import { computed, onUnmounted, provide, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NotFound from '../pages/NotFound.vue'
import { call, upload } from '../api.js'
import { useMode } from '../mode.js'
import { onEvent } from '../realtime.js'
import { HOST_KEY, createHost } from '../chat/host.js'
import { chatWord } from '../chat/words.js'
import { roomRows, roomsOf, watchRooms } from '../chat/rooms.js'
import ApprovalSheet from '../approvals/ApprovalSheet.vue'
import { waitingRows } from '../approvals/terms.js'
import { clearPortal, portal } from './state.js'
import { acceptOf, groupOf, limitFor, limitText, tabOf, visibleTabs } from './tabs.js'
import ApprovalsView from './views/Approvals.vue'
import DiscussionView from './views/Discussion.vue'
import FilesView from './views/Files.vue'
import HomeView from './views/Home.vue'
import RequestsView from './views/Requests.vue'

// One client project in the portal, on the live design's four tabs (D-124, version 1791648865-5845; D-127). Every read
// is construction_core.portal_api or discuss.api, which check each call again; nothing here adds data. P3-64: the
// Discussion tab is the client's room (chat/), through the client's chat host made here.
const route = useRoute()
const project = computed(() => route.params.project)
// P3-71: a file request opened from its card (?tab=discuss&request=<name>) replaces the conversation with its own page.
const requestName = computed(() => (typeof route.query.request === 'string' ? route.query.request : ''))
const data = ref(null)
const missing = ref(false)
const error = ref('')
const sending = ref(false)
// P3-07: a client sends a file in Files while the project takes files (Files on); a conversation's files go through the
// chat's own upload (P3-65). The server decides every check again (construction_core.portal_api.send_file); the size
// check here only saves a long upload.
const canSend = computed(() => Boolean(data.value?.upload) && !(data.value?.sections_off || []).includes('files'))
// The client's own Simple or Advanced view (D-154, D-163); P3-05's preview supplies the client's mode instead.
const mode = useMode()
// P3-79 (design §3.12): the Approvals tab's own group shows in either mode while the project's switch and section are on
// (the payload's sections_off holds "approvals" otherwise).
const approvalsOn = computed(() => Boolean(data.value) && !(data.value.sections_off || []).includes('approvals'))
const tab = computed(() => tabOf(route.query.tab, data.value?.sections_off, mode.value, approvalsOn.value))
const tabs = computed(() => visibleTabs(data.value?.sections_off, mode.value, tab.value, approvalsOn.value))
// An old link named a section as the tab (?tab=rfi): it opens that group on its new tab.
const group = computed(() => groupOf(tab.value, route.query.group || route.query.tab, data.value?.sections_off, mode.value, approvalsOn.value))
const groupsOf = (key) => tabs.value.find((t) => t.key === key)?.groups || []
// The request whose sheet is open: ?tab=approvals&request=<name> (the request email's address), with a Decision's picked
// option and the step the card opened it on.
const sheetRequest = computed(() => (tab.value === 'approvals' && typeof route.query.request === 'string' ? route.query.request : ''))
const asked = (key) => (typeof route.query[key] === 'string' ? route.query[key] : '')
// The client's chat (P3-64): their own reads and sends; files go through the host's upload and the send (P3-65).
const host = createHost({ viewer: 'client', base: { project: () => project.value, approvals: () => approvalsOn.value } })
provide(HOST_KEY, host)
// The client's one timeline is the project's Client room (§14.1); an old ?thread= link opens that thread beside it.
const roomsLoaded = computed(() => roomsOf(project.value).loaded)
const threadRows = computed(() => roomsOf(project.value).rows)
const room = computed(() => roomRows(project.value).find((t) => t.audience === 'Client') || null)
// "Ask about this file" (§3.2, L-9): the Client room opens with the file in its message box. The file is named by the
// address the Files tab shows, never an id; it is kept here, not in the address bar.
const router = useRouter()
const closeSheet = () => router.replace({ query: { tab: 'approvals' } })
const messageTeam = () => router.push({ query: { tab: 'discuss' } })
const ask = ref('')
const canAsk = computed(() => canSend.value && tabs.value.some((t) => t.key === 'discuss'))
function askAbout(url) {
  ask.value = url
  router.push({ query: { tab: 'discuss' } })
}

// The bar (PortalApp) shows this project's name and visible tabs.
watchEffect(() => {
  Object.assign(portal, {
    project: project.value,
    title: data.value?.project.project_name || project.value,
    tabs: data.value ? tabs.value : [],
    tab: tab.value,
    waiting: waitingRows(data.value).length, // the Approvals tab's badge: one source with the Home card and the tab (N11)
  })
})
onUnmounted(clearPortal)

async function load() {
  try {
    data.value = await call('construction_core.portal_api.project_data', { project: project.value })
    error.value = ''
  } catch (e) {
    if (e.type === 'DoesNotExistError') missing.value = true
    else error.value = e.message
  }
}

// A file from Files (P3-07). The server decides every check again (portal_api.send_file); the size check here only
// saves a long upload.
async function sendFile(file) {
  if (!file || sending.value) return
  sending.value = true
  try {
    const answer = await upload('construction_core.portal_api.send_file', { project: project.value }, checked(file))
    error.value = ''
    await load()
    if (answer?.checking) await loadHolds() // a large file is held and scanned after the request: "Checking…" (P3-75)
  } catch (e) {
    // An answer that is not the server's own (a gateway timeout) carries no message: never fail silently (P3-07 audit).
    error.value = e.message || 'The file may not have been sent. Check Files and try again.'
  } finally {
    sending.value = false
  }
}

function checked(file) {
  const max = limitFor(data.value?.upload, file.name)
  if (max && file.size > max) throw new Error(chatWord('attachments.too_large', { mode: mode.value, portal: true, values: { size: limitText(max) } }))
  return file
}

// P3-75 (D-417): the client's own large sends being scanned, or refused with a reason. They are asked for on the Files
// tab, and again every few seconds while one is being checked; one that passed is a File now, so the list is read again.
const holds = ref([])
let holdTimer = null
async function loadHolds() {
  clearTimeout(holdTimer)
  if (!canSend.value || tab.value !== 'files') return
  const name = project.value
  try {
    const rows = await call('construction_core.portal_api.checking', { project: name })
    if (name !== project.value) return
    const before = holds.value.filter((r) => r.checking).map((r) => r.file_name)
    holds.value = rows
    if (before.some((n) => !rows.some((r) => r.file_name === n && r.checking))) await load() // checked: a File, or refused
    if (rows.some((r) => r.checking)) holdTimer = setTimeout(loadHolds, 3000)
  } catch {
    holdTimer = setTimeout(loadHolds, 8000) // the next ask tries again; the list itself is unchanged
  }
}
watch([project, tab, canSend], loadHolds)

// Clients join no document room (D-100): their messages arrive in their own user room. Home's latest messages come
// from project_data, read again after a short wait so a burst of messages costs one read; the room keeps itself.
let reload = null
const again = () => {
  clearTimeout(reload)
  reload = setTimeout(load, 800)
}
const off = onEvent('cc_discuss_message', again)
// P3-78: a request changed (sent, answered, replaced, voided): the tab, the Home card and the badge read again
const offApproval = onEvent('cc_approval_changed', again)
let stopRooms = () => {}
onUnmounted(() => {
  off()
  offApproval()
  stopRooms()
  clearTimeout(reload)
  clearTimeout(holdTimer)
})

watch(project, (name) => {
  load()
  stopRooms()
  stopRooms = watchRooms(name, host)
}, { immediate: true })
</script>
