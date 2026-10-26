<template>
  <NotFound v-if="missing" />
  <div v-else class="flex min-w-0 flex-1 flex-col gap-4 px-5 py-6" data-testid="section-page">
    <p v-if="error" class="text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
    <p v-else-if="contacts && !contacts.length" class="text-ink-gray-7" data-testid="client-view-empty">No client contact yet.</p>
    <p v-else-if="!ready" class="text-ink-gray-7">Loading…</p>
    <template v-else>
      <div role="status" class="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-6 border border-outline-gray-2 bg-surface-blue-1 px-4 py-3 text-ink-blue-8" data-testid="client-view-banner">
        <span class="lucide-eye size-4 flex-none" aria-hidden="true" />
        <span class="min-w-0 flex-[1_1_320px]">
          <strong class="font-semibold">Viewing as {{ view.client_name }}, read-only.</strong>
          <span class="block text-sm text-ink-gray-8">You see only what both you and this client can open.</span>
        </span>
        <Dropdown v-if="entry && entry.options" :options="entry.options" align="end">
          <Button variant="outline" size="sm" icon-left="lucide-users" label="Switch contact" data-testid="client-view-contacts" />
        </Dropdown>
        <Button variant="ghost" size="sm" label="Close" :route="{ name: 'section', params: { project, section: 'home' } }" data-testid="client-view-close" />
      </div>

      <p v-if="!view.portal_open" class="text-ink-gray-8" data-testid="client-view-off">{{ view.client_name }} cannot open this project in the portal now.</p>
      <template v-else>
        <nav aria-label="Portal sections" class="flex flex-wrap border-b border-outline-gray-2" data-testid="client-view-tabs">
          <router-link v-for="t in tabs" :key="t.key" :to="{ query: t.key === 'home' ? {} : { tab: t.key } }"
            class="-mb-px flex h-10 items-center gap-1.5 border-b-2 px-3 text-base no-underline"
            :class="tab === t.key ? 'border-outline-blue-6 font-semibold text-ink-blue-8' : 'border-transparent text-ink-gray-8 hover:text-ink-gray-9'"
            :aria-current="tab === t.key ? 'page' : undefined" data-testid="portal-tab" :data-tab="t.key">{{ t.label }}</router-link>
        </nav>

        <section v-if="tab === 'files' && boardName" class="flex flex-col gap-3.5" data-testid="client-view-board">
          <div>
            <router-link :to="{ query: { tab: 'files', group: 'whiteboards' } }" class="text-xs text-ink-gray-7 no-underline hover:text-ink-gray-9">← Canvas</router-link>
            <div class="mt-1 flex flex-wrap items-baseline gap-2.5">
              <h1 class="m-0 text-3xl-semibold text-ink-gray-9">{{ boardTitle }}</h1>
              <Badge label="View only" />
            </div>
          </div>
          <div class="cw-card overflow-hidden">
            <!-- The React root lives on this element only; Vue never re-renders its children. -->
            <div ref="canvas" class="h-[calc(100vh-190px)] min-h-[420px]" data-testid="client-view-canvas" />
          </div>
        </section>
        <template v-else>
          <HomeView v-if="tab === 'home'" :data="view.data" :project="project" :tabs="tabs" :viewer-name="view.client_name" :board-link="previewBoardLink" />
          <DiscussionView v-else-if="tab === 'discuss'" :room="previewRoom" :rows="previewRows" :loaded="rowsLoaded" />
          <ApprovalsView v-else-if="tab === 'approvals'" :data="view.data" :groups="groupsOf('approvals')" :group="group" :discuss="tabs.some((t) => t.key === 'discuss')" />
          <FilesView v-else-if="tab === 'files'" :data="view.data" :project="project" :groups="groupsOf('files')" :group="group" :board-link="previewBoardLink" />
        </template>
        <!-- T31: the sheet in the preview reads only (no answer step, no call that writes); the host says so structurally. -->
        <ApprovalSheet v-if="sheetRequest" :key="sheetRequest" :request="sheetRequest" @close="closeSheet" />
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, useColorScheme } from 'frappe-ui'
import NotFound from '../pages/NotFound.vue'
import { call } from '../api.js'
import { ENGINES, loadScript } from '../loader.js'
import { MODE_KEY } from '../mode.js'
import { HOST_KEY, createHost } from '../chat/host.js'
import { normal } from '../words.js'
import ApprovalSheet from '../approvals/ApprovalSheet.vue'
import { clientViewEntry, groupOf, previewBoardLink, tabOf, visibleTabs } from '../portal/tabs.js'
import ApprovalsView from '../portal/views/Approvals.vue'
import DiscussionView from '../portal/views/Discussion.vue'
import FilesView from '../portal/views/Files.vue'
import HomeView from '../portal/views/Home.vue'

// Staff "View as client" (P3-05, D-136): one client contact's portal, exactly as the server answers it for that
// client (construction_core.portal_preview: every read is the client's own, limited to what the caller can open),
// drawn with the portal's own views in the client's own Simple or Advanced view (P3-01). Read-only: no composer, no
// mark-read, no typing, no live rooms, nothing written. The contact is a Project Member row (route item).
const PV = 'construction_core.portal_preview.'
const props = defineProps({ frame: Object, project: String, section: String })
const route = useRoute()
const router = useRouter()
const contact = computed(() => route.params.item || '')
const clientMode = ref('simple')
provide(MODE_KEY, clientMode) // the portal views ask useMode(): here it is the client's, not the viewer's
// The chat as this client reads it, read-only: no message box, no actions, no live updates (P3-64 host, preview).
const host = createHost({ viewer: 'preview', base: { project: () => props.project, contact: () => contact.value } })
provide(HOST_KEY, host)

const contacts = ref(null)
const view = ref(null)
const ready = ref(false)
const missing = ref(false)
const error = ref('')
const canvas = ref(null)
const boardTitle = ref('Canvas')
const entry = computed(() => clientViewEntry(props.project, contacts.value))

const sectionsOff = computed(() => view.value?.data?.sections_off)
// P3-79: the Approvals tab shows as the client's does (the switch and the section on). The sheet it opens is read-only here.
const approvalsOn = computed(() => Boolean(view.value?.data) && !(sectionsOff.value || []).includes('approvals'))
const tab = computed(() => tabOf(route.query.tab, sectionsOff.value, clientMode.value, approvalsOn.value))
const tabs = computed(() => visibleTabs(sectionsOff.value, clientMode.value, tab.value, approvalsOn.value))
const group = computed(() => groupOf(tab.value, route.query.group || route.query.tab, sectionsOff.value, clientMode.value, approvalsOn.value))
const sheetRequest = computed(() => (tab.value === 'approvals' && typeof route.query.request === 'string' ? route.query.request : ''))
const closeSheet = () => router.replace({ query: { tab: 'approvals' } })
const groupsOf = (key) => tabs.value.find((t) => t.key === key)?.groups || []
// As the portal: the client's one timeline, the Client room, with its threads, reply lines and ?thread= (audit F1),
// read as the client and bounded by the viewer's reads (portal_preview.preview_threads).
const previewRows = ref([])
const rowsLoaded = ref(false)
const previewRoom = computed(() => previewRows.value.find((t) => !t.in_room && t.audience === 'Client') || null)
const boardName = computed(() => (typeof route.query.board === 'string' ? route.query.board : ''))

let alive = true // an answer that arrives after the page closed changes nothing

function failed(e) {
  if (!alive) return
  if (e.type === 'DoesNotExistError') missing.value = true
  else error.value = e.message || 'Could not open the client view.'
}

onMounted(async () => {
  try {
    if (!contact.value) {
      contacts.value = await call(PV + 'contacts', { project: props.project })
      // Only if this page is still the one on screen: no late answer pulls the user back (or into another project).
      const here = route.params.project === props.project && route.params.section === 'client-view' && !route.params.item
      if (alive && here && contacts.value.length) {
        const first = clientViewEntry(props.project, contacts.value.slice(0, 1)).route
        router.replace({ ...first, query: route.query })
      }
      return
    }
    const args = { project: props.project, contact: contact.value }
    const [list, answer, mode] = await Promise.all([
      call(PV + 'contacts', { project: props.project }),
      call(PV + 'preview', args),
      call('construction_shell.preferences.client_mode', args),
    ])
    contacts.value = list
    view.value = answer
    clientMode.value = normal(mode)
    ready.value = true
  } catch (e) {
    failed(e)
  }
})

let rowsAsked = 0
watch([ready, tab], async () => {
  if (!ready.value || !view.value?.portal_open || tab.value !== 'discuss') return
  const ask = ++rowsAsked
  try {
    const rows = await host.read('threads', { project: props.project })
    if (ask === rowsAsked) previewRows.value = rows
  } catch (e) {
    if (ask === rowsAsked) failed(e)
  } finally {
    if (ask === rowsAsked) rowsLoaded.value = true
  }
})

// The board, view only, on the same engine as the portal's board page; no live room (the preview is not the client).
const { resolvedColorScheme } = useColorScheme()
let root = null
let excalidraw = null
watch(resolvedColorScheme, (theme) => excalidraw && excalidraw.updateScene({ appState: { theme } }))

function closeBoard() {
  if (root) root.unmount()
  root = null
  excalidraw = null
}

let boardAsked = 0
watch([ready, tab, boardName], async () => {
  closeBoard()
  const ask = ++boardAsked // only the latest board asked for is drawn; a slower or failed earlier answer is dropped
  if (!ready.value || !view.value?.portal_open || tab.value !== 'files' || !boardName.value) return
  try {
    const b = await call(PV + 'preview_board', { project: props.project, contact: contact.value, board: boardName.value })
    if (ask !== boardAsked) return
    boardTitle.value = b.title
    await loadScript(ENGINES.whiteboard)
    const lib = await window.ccWhiteboard.load()
    await nextTick()
    if (ask !== boardAsked || !canvas.value) return
    closeBoard()
    root = window.ReactDOM.createRoot(canvas.value)
    root.render(window.React.createElement(lib.Excalidraw, {
      initialData: { elements: b.scene.elements || [], appState: b.scene.appState || {}, files: b.scene.files || {} },
      viewModeEnabled: true, zenModeEnabled: true, excalidrawAPI: (a) => (excalidraw = a), theme: resolvedColorScheme.value,
    }))
  } catch (e) {
    if (ask === boardAsked) failed(e)
  }
})

onBeforeUnmount(() => {
  alive = false
  closeBoard()
})
</script>
