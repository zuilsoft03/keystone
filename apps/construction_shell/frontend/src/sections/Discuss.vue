<template>
  <div class="relative flex min-h-0 flex-1 bg-surface-base max-md:flex-col" data-testid="section-page">
    <aside v-if="!isPhone || (!room && !missing && !inApprovals)" :aria-label="w('core.discussion')"
      class="flex w-full flex-col overflow-y-auto border-r border-outline-gray-2 bg-surface-base md:w-64 md:flex-none">
      <div class="px-4 pt-3">
        <h1 class="m-0 text-lg font-semibold text-ink-gray-9" data-testid="section-title">{{ w('core.discussion') }}</h1>
        <p class="m-0 truncate text-xs text-ink-gray-7">{{ frame?.project?.project_name || project }}</p>
      </div>
      <p v-if="roomsState.error" class="px-4 pt-2 text-ink-red-7" role="alert" data-testid="error">{{ roomsState.error }}</p>
      <RoomList :rooms="rooms" :current="inApprovals ? '' : room" :company="company" :loaded="roomsState.loaded" :link-of="linkOf" :summaries="summaries" />
      <router-link :to="tabRoute(project)" class="mx-2 flex min-h-12 items-center gap-2.5 rounded-5 px-2.5 py-2 no-underline"
        :class="inApprovals ? 'bg-surface-blue-1 text-ink-blue-9' : 'text-ink-gray-9 hover:bg-surface-gray-2'" :aria-current="inApprovals ? 'page' : undefined" data-testid="approvals-link">
        <span class="lucide-square-check size-[18px] flex-none" aria-hidden="true" />
        <span class="flex-1 truncate text-base font-semibold">{{ sw('tab_title') }}</span>
        <Badge v-if="openCount(approvals.counts)" variant="solid" theme="blue" size="sm" :label="String(openCount(approvals.counts))" data-testid="approvals-count" />
      </router-link>
      <div class="flex flex-col gap-2 px-2 pb-3">
        <MentionsFilter v-if="rows.length" v-model="mentionsOnly" :count="mentioned.length" />
        <ThreadList v-if="current" :threads="shownActive" :heading="w('core.active_threads')" :current="threadName" :link-of="threadLink" show-empty
          :empty-word="mentionsOnly ? w('core.no_mentioned') : ''" testid="active-threads" />
        <ThreadList :threads="shownFollowed" :heading="w('core.following')" :current="threadName" :link-of="threadLink" :room-of="roomNameOf" testid="followed-threads" />
      </div>
    </aside>
    <p v-if="actionError" class="absolute left-1/2 top-16 z-10 m-0 -translate-x-1/2 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="action-error">{{ actionError }}</p>
    <p v-if="missing" class="m-0 flex-1 p-5 text-ink-gray-7" role="alert" data-testid="not-found">{{ w('core.not_found') }}</p>
    <EvidencePage v-else-if="evidenceName" :key="evidenceName" :project="project" :request="evidenceName" />
    <RequestPage v-else-if="approvalName" :key="approvalName" :project="project" :request="approvalName" @changed="loadApprovals" />
    <ApprovalsTab v-else-if="inApprovals" :project="project" :data="approvals" :loading="approvalsLoading" :error="approvalsError" />
    <ChatRoom v-else-if="current && !(isPhone && (openThread || requestName))" :key="current.name" :room="current.name" :audience="current.audience"
      :at="atName" :title="titleOf(current)" :badge="w(current.audience === 'Internal' ? 'core.header_team' : 'core.header_client')"
      :badge-theme="current.audience === 'Internal' ? 'amber' : 'violet'" :line="lineOf(current)"
      :placeholder="w('core.write_to', { room: titleOf(current) })" :audience-line="audienceOf(current)"
      :thread-rows="rows" :team-room="teamRoom" :live="focusIn !== 'panel'"
      @focusin="focusIn = 'room'" @open-thread="openThreadOn" @team="discussWithTeam">
      <template #back>
        <router-link v-if="isPhone" :to="linkOf(null)" class="grid size-12 flex-none place-items-center rounded-4 text-ink-gray-8 hover:bg-surface-gray-2"
          :aria-label="w('core.back')" data-testid="room-back"><span class="lucide-chevron-left size-5" aria-hidden="true" /></router-link>
      </template>
    </ChatRoom>
    <RequestPanel v-if="requestName && current" :key="requestName" :request="requestName" :phone="isPhone" @close="closeRequest" />
    <ThreadPanel v-else-if="openThread" :key="openThread.name" :thread="openThread" :room-title="titleOf(current)" :phone="isPhone"
      :audience-line="openThread.audience === 'Internal' ? w('core.audience_thread_team') : w('core.audience_thread_client')"
      :live="focusIn === 'panel'" :thread-rows="rows" :team-room="teamRoom"
      @focus="focusIn = 'panel'" @close="closeThread" @team="discussWithTeam" />
    <p v-else-if="threadMissing && !missing" class="m-0 p-5 text-ink-gray-7 md:w-[360px] md:border-l md:border-outline-gray-2" role="alert" data-testid="thread-not-found">{{ w('core.not_found') }}</p>
  </div>
</template>

<script setup>
import { computed, nextTick, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge } from 'frappe-ui'
import { call } from '../api.js'
import ApprovalsTab from '../approvals/staff/ApprovalsTab.vue'
import EvidencePage from '../approvals/staff/EvidencePage.vue'
import RequestPage from '../approvals/staff/RequestPage.vue'
import { openCount, tabRoute } from '../approvals/staff/request.js'
import { staffWords } from '../approvals/words.js'
import { useMode } from '../mode.js'
import { isPhone } from '../portal/state.js'
import ChatRoom from '../chat/ChatRoom.vue'
import MentionsFilter from '../chat/MentionsFilter.vue'
import RoomList from '../chat/RoomList.vue'
import ThreadList from '../chat/ThreadList.vue'
import ThreadPanel from '../chat/ThreadPanel.vue'
import RequestPanel from '../chat/parts/file_requests/RequestPanel.vue'
import { HOST_KEY, createHost } from '../chat/host.js'
import { loadRooms, roomName, roomRows, roomsOf, watchRooms } from '../chat/rooms.js'
import { activeThreads, followedThreads, lineOf as threadOf, mentionedThreads } from '../chat/threads.js'
import { focusReplyLine } from '../chat/focus.js'
import { Inbox } from '../chat/inbox/store.js'
import { plain } from '../chat/tokens.js'
import { setInboxUnread } from '../store.js'
import { wordsFor } from '../chat/words.js'

// The staff Discussion (P3-64, R-32; canvas "Discussion hub" frames 1 and 2, approved at 1792344418-fe7d, D-432): the
// project's rooms, Team and the client company's, each one timeline, with its threads beside it (?thread=) on a wide
// screen and as their own screen on a phone. No thread tabs and no notes for the team alone (D-413, D-419): "Discuss
// with team" opens the client message's thread in the Team room, never beside the Client timeline. The route's item is
// the room; an old link to a thread opens its room with the thread (api.resolve); a room or thread of another project
// answers "not found" like a missing one.
const props = defineProps({ frame: Object, project: String, section: String })
const route = useRoute()
const router = useRouter()
const w = wordsFor(useMode())
const sw = staffWords(useMode())
const host = createHost({ viewer: 'staff', base: { project: () => props.project } })
provide(HOST_KEY, host)
const company = ref('')
const missing = ref(false)
const threadMissing = ref(false)
const focusIn = ref('room') // only the list the reader is in is a live region
const actionError = ref('') // "Reply in thread" or "Discuss with team" refused
const roomsState = computed(() => roomsOf(props.project))
const rows = computed(() => roomsState.value.rows)
const rooms = computed(() => roomRows(props.project))
const item = computed(() => (typeof route.params.item === 'string' ? route.params.item : ''))
const current = computed(() => rooms.value.find((r) => r.name === item.value) || null)
const room = computed(() => current.value?.name || '')
const threadName = computed(() => (typeof route.query.thread === 'string' ? route.query.thread : ''))
const atName = computed(() => (typeof route.query.at === 'string' ? route.query.at : '')) // the inbox opens the room at a message (P3-74)
const requestName = computed(() => (typeof route.query.request === 'string' ? route.query.request : '')) // P3-71: a file request beside the room
// P3-80: the Approvals tab beside the rooms (?approvals=1), a request page (?approval=) and its evidence record (&evidence=1).
const approvalName = computed(() => (typeof route.query.approval === 'string' ? route.query.approval : ''))
const evidenceName = computed(() => (approvalName.value && route.query.evidence ? approvalName.value : ''))
const inApprovals = computed(() => Boolean(route.query.approvals || approvalName.value))
const approvals = ref({ rows: [], counts: {}, approvers: [] })
const approvalsLoading = ref(false)
const approvalsError = ref('')
async function loadApprovals() {
  const project = props.project
  approvalsLoading.value = true
  approvalsError.value = ''
  try {
    const out = await call('construction_core.approvals.staff.requests', { project })
    if (project === props.project) approvals.value = out
  } catch (e) {
    approvalsError.value = e.message || ''
  } finally {
    approvalsLoading.value = false
  }
}
// P3-74 (§14.6): the same rows as the Discussion inbox head the room list: each room's newest line and Needs a reply.
let inbox = null
const summaries = ref({})
const openThread = computed(() => rows.value.find((t) => t.name === threadName.value && t.in_room === room.value) || null)
const teamRoom = computed(() => rooms.value.find((r) => r.audience === 'Internal')?.name || '')
const active = computed(() => activeThreads(rows.value, room.value))
const followed = computed(() => followedThreads(rows.value))
// P3-66: the Mentions filter keeps the threads that mention the reader (an unread mention, as the thread row says it)
const mentionsOnly = ref(false)
const mentioned = computed(() => mentionedThreads(rows.value))
const shownActive = computed(() => (mentionsOnly.value ? mentionedThreads(active.value) : active.value))
const shownFollowed = computed(() => (mentionsOnly.value ? mentionedThreads(followed.value) : followed.value))

const linkOf = (r) => ({ name: 'section', params: { project: props.project, section: 'discuss', ...(r ? { item: r.name } : {}) } })
const threadLink = (t) => ({ ...linkOf({ name: t.in_room }), query: { thread: t.name } })
const titleOf = (r) => roomName(r, { viewer: 'staff', company: company.value, w })
const roomNameOf = (t) => titleOf(rooms.value.find((r) => r.name === t.in_room))
const lineOf = (r) => (r.audience === 'Internal' ? w('core.line_team')
  : company.value ? w('core.line_client', { company: company.value }) : w('core.line_client_plain'))
const audienceOf = (r) => (r.audience === 'Internal' ? w('core.audience_team')
  : company.value ? w('core.audience_client', { company: company.value }) : w('core.audience_client_plain'))

// The room the screen opens with no item: one with unread messages, else the Client room, else the first.
function defaultRoom(list) {
  return list.find((r) => r.unread) || list.find((r) => r.audience === 'Client') || list[0] || null
}

// An item that is no room of this project is an old link to a thread: open its room, with the thread for the panel.
async function settleRoom() {
  missing.value = false
  if (!roomsState.value.loaded) return
  if (!item.value) {
    const first = defaultRoom(rooms.value)
    if (first && !isPhone.value) router.replace({ ...linkOf(first), query: route.query })
    return
  }
  if (current.value) return
  const where = await resolve(item.value)
  if (!where) return
  router.replace({ ...linkOf({ name: where.room }), query: where.room !== where.thread ? { ...route.query, thread: where.thread } : route.query })
}

// ?thread= names a thread of this room; a thread of the project's other room opens there (never side by side, §14.1).
let notFound = '' // a thread already answered "not found": a rows reload does not ask again
async function settleThread() {
  const name = threadName.value
  threadMissing.value = Boolean(name) && name === notFound
  if (!name || threadMissing.value || !roomsState.value.loaded || !current.value || openThread.value) return
  const known = rows.value.find((t) => t.name === name)
  if (known?.in_room) return router.replace({ ...linkOf({ name: known.in_room }), query: { ...route.query, thread: name } })
  const where = await resolve(name, true)
  if (!where || name !== threadName.value) return
  await loadRooms(props.project) // a thread made since the rows were read
  const found = rows.value.find((t) => t.name === name)
  if (found?.in_room) return found.in_room === room.value ? null : router.replace(threadLink(found))
  notFound = name
  threadMissing.value = true
}

// api.resolve, answered as "not found" when it is missing, unreadable, or of another project.
async function resolve(name, forThread = false) {
  try {
    const where = await host.read('resolve', { thread: name })
    if (rooms.value.some((r) => r.name === where.room)) return where
  } catch { /* the same answer as a thread of another project */ }
  if (forThread) {
    notFound = name
    threadMissing.value = true
  } else missing.value = true
  return null
}

// "Reply in thread": the message's thread in this room, opened on first use.
async function openThreadOn(row, message) {
  actionError.value = ''
  if (row) return router.push(threadLink(row))
  let refused = null
  try {
    await host.write('open_thread', { message: message.name, audience: current.value.audience, title: plain(message.text, w) })
  } catch (e) {
    refused = e // a thread made meanwhile by someone else: the reload below finds it; else the answer is shown
  }
  await loadRooms(props.project)
  const made = threadOf(rows.value, room.value, message.name)
  if (made) router.push(threadLink(made))
  else actionError.value = refused?.message || w('core.not_found')
}

// "Discuss with team" (§14.1): the one Team-room thread about the client's message, opened in the Team room.
async function discussWithTeam(message) {
  actionError.value = ''
  try {
    const made = await host.write('discuss_with_team', { message: message.name })
    await loadRooms(props.project)
    router.push({ ...linkOf({ name: made.room }), query: { thread: made.thread } })
  } catch (e) {
    actionError.value = e.message || w('core.not_found')
  }
}

// Close or Back: the room again, with the focus on the root's reply line (or the room's box when there is none).
async function closeThread(thread) {
  focusIn.value = 'room'
  await router.push({ ...linkOf(current.value), query: {} })
  await nextTick()
  focusReplyLine(thread.root)
}

// P3-71: Close or Back on a file request: the room as it was, with the focus on the card the request was opened from.
async function closeRequest(request) {
  const { request: _closed, ...rest } = route.query
  await router.push({ ...linkOf(current.value), query: rest })
  await nextTick()
  document.querySelector(`[data-request="${request}"] [data-testid$="request-open"], [data-request="${request}"] [data-testid$="request-send"]`)?.focus()
}

// What the staff call the client's room: the company of its contacts (Client Profile), else "Client".
async function loadCompany(project) {
  try {
    const people = await call('construction_core.onboarding.invites.client_details', { project })
    if (project === props.project) company.value = people.map((p) => p.company_name).find(Boolean) || ''
  } catch {
    company.value = ''
  }
}

let stop = () => {}
watch(() => props.project, (project) => {
  stop()
  stop = watchRooms(project, host)
  loadCompany(project)
  approvals.value = { rows: [], counts: {}, approvers: [] }
  loadApprovals()
  inbox?.close()
  summaries.value = {}
  inbox = new Inbox(host, { project })
  inbox.onLoad = (state) => {
    setInboxUnread(state.totals.by_project) // the top bar's count for this project
    if (project === props.project) summaries.value = Object.fromEntries(state.rooms.map((r) => [r.room, r]))
  }
  inbox.load()
  inbox.listen()
}, { immediate: true })
watch([item, () => roomsState.value.loaded, () => rooms.value.length], settleRoom, { immediate: true })
watch([threadName, room, () => roomsState.value.rows], settleThread, { immediate: true })
watch(openThread, (t) => (focusIn.value = t ? 'panel' : 'room'))
onUnmounted(() => {
  stop()
  inbox?.close()
})
</script>
