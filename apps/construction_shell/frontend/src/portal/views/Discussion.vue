<template>
  <div class="cw-card relative flex h-[calc(100vh-180px)] min-h-[480px] overflow-hidden max-md:-mx-5 max-md:-my-6 max-md:h-[calc(100dvh-108px)] max-md:min-h-0 max-md:rounded-none max-md:border-0"
    data-testid="portal-discussion">
    <ChatRoom v-if="room && !(isPhone && openThread)" ref="roomView" :key="room.name" :room="room.name" audience="Client" :title="title" :line="w('core.portal_line')"
      :placeholder="firm ? w('core.write_to', { room: firm }) : w('core.write_team')" :audience-line="w('core.audience_portal')"
      :accept="accept" portal prefix="portal-" :thread-rows="rows" :live="focusIn !== 'panel'" :ask="ask"
      @focusin="focusIn = 'room'" @open-thread="openThreadOn" @asked="emit('asked')" @files="showActive = false">
      <template #actions>
        <Button v-if="active.length" variant="ghost" size="sm" icon-left="lucide-messages-square" :label="`${w('core.active_threads')} · ${active.length}`"
          :aria-expanded="showActive ? 'true' : 'false'" data-testid="portal-active-toggle" @click="toggleActive" />
      </template>
    </ChatRoom>
    <div v-if="showActive && !openThread" class="absolute right-3 top-14 z-10 w-72 rounded-6 border border-outline-gray-2 bg-surface-base p-2 shadow-lg">
      <MentionsFilter v-if="rows.length" v-model="mentionsOnly" :count="mentioned.length" portal prefix="portal-" class="mb-1" />
      <ThreadList :threads="shownActive" :heading="w('core.active_threads')" :link-of="threadLink" portal show-empty
        :empty-word="mentionsOnly ? w('core.no_mentioned') : ''" testid="portal-active-threads" />
    </div>
    <ThreadPanel v-if="openThread" :key="openThread.name" :thread="openThread" :room-title="title" :phone="isPhone" portal prefix="portal-"
      :audience-line="w('core.audience_portal')" :accept="accept" :live="focusIn === 'panel'" :thread-rows="rows"
      @focus="focusIn = 'panel'" @close="closeThread" />
    <p v-else-if="threadMissing" class="m-0 p-5 text-ink-gray-7 md:w-[360px] md:border-l md:border-outline-gray-2" role="alert" data-testid="portal-thread-not-found">{{ w('core.not_found') }}</p>
    <p v-if="actionError" class="absolute left-1/2 top-16 z-10 m-0 -translate-x-1/2 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="portal-action-error">{{ actionError }}</p>
    <p v-if="!room && loaded" class="p-5 text-ink-gray-7" data-testid="portal-no-room">{{ w('core.empty') }}</p>
    <p v-else-if="!room" class="p-5 text-ink-gray-7">{{ w('core.loading') }}</p>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import { useMode } from '../../mode.js'
import { isPhone } from '../state.js'
import ChatRoom from '../../chat/ChatRoom.vue'
import MentionsFilter from '../../chat/MentionsFilter.vue'
import ThreadList from '../../chat/ThreadList.vue'
import ThreadPanel from '../../chat/ThreadPanel.vue'
import { HOST_KEY } from '../../chat/host.js'
import { loadRooms } from '../../chat/rooms.js'
import { activeThreads, lineOf, mentionedThreads } from '../../chat/threads.js'
import { focusReplyLine } from '../../chat/focus.js'
import { wordsFor } from '../../chat/words.js'

// The portal's Discussion (P3-64, R-32; canvas "Discussion hub" frame 3): the client's one timeline, the Client room,
// named after the firm, with its threads (?thread=) beside it on a wide screen and as their own screen on a phone. A
// client opens a thread on a message and may also send a reply to the room (QR-2, D-415). Clients never see the Team
// room, staff notes or "Discuss with team". The page provides the chat host (the client's own, or the staff preview's,
// which is read-only and draws no threads) and names the room.
const props = defineProps({
  room: { type: Object, default: null }, // { name, title }
  rows: { type: Array, default: () => [] }, // the project's thread rows the reader reads
  loaded: Boolean,
  accept: { type: String, default: '' },
  ask: { type: String, default: '' }, // P3-65: "Ask about this file": the file the Files tab named, for the box
})
const emit = defineEmits(['asked'])
const route = useRoute()
const router = useRouter()
const host = inject(HOST_KEY)
const w = wordsFor(useMode(), true)
const NEUTRAL = 'Conversation' // the server's word when the firm has no name yet (D-370)
const focusIn = ref('room')
const showActive = ref(false)
const threadMissing = ref(false)
const actionError = ref('') // "Reply in thread" refused
const firm = computed(() => (props.room?.title && props.room.title !== NEUTRAL ? props.room.title : ''))
const title = computed(() => (firm.value ? w('core.portal_title', { firm: firm.value }) : w('core.discussion')))
const threadName = computed(() => (typeof route.query.thread === 'string' ? route.query.thread : ''))
const openThread = computed(() => props.rows.find((t) => t.name === threadName.value && t.in_room === props.room?.name) || null)
const active = computed(() => activeThreads(props.rows, props.room?.name))
// P3-66: the Mentions filter, on the threads that mention the client (an unread mention)
const mentionsOnly = ref(false)
const mentioned = computed(() => mentionedThreads(active.value))
const shownActive = computed(() => (mentionsOnly.value ? mentioned.value : active.value))
const threadLink = (t) => ({ query: { tab: 'discuss', thread: t.name } })
const roomView = ref(null)
// Active threads and Files in this conversation open at the same place: one closes the other (P3-65).
function toggleActive() {
  showActive.value = !showActive.value
  if (showActive.value) roomView.value?.closeFiles()
}

async function openThreadOn(row, message) {
  actionError.value = ''
  if (row) return router.push(threadLink(row))
  let refused = null
  try {
    await host.write('open_thread', { message: message.name })
  } catch (e) {
    refused = e // made meanwhile: the reload below finds it; else the answer is shown
  }
  await loadRooms(host.project)
  const made = lineOf(props.rows, props.room?.name, message.name)
  if (made) router.push(threadLink(made))
  else actionError.value = refused?.message || w('core.not_found')
}

async function closeThread(thread) {
  focusIn.value = 'room'
  await router.push({ query: { tab: 'discuss' } })
  await nextTick()
  focusReplyLine(thread.root)
}

// An old link (the mention email, Project.vue ?thread=): a thread of the client's room opens beside it; one the client
// may not read, or of another room, answers "not found" (§14.4).
let asked = ''
watch([threadName, () => props.rows, () => props.loaded], async () => {
  showActive.value = false
  const name = threadName.value
  threadMissing.value = false
  if (!name || !props.loaded || !props.room || openThread.value) return
  if (asked !== name && host.viewer !== 'preview') { // the preview reads its rows once and writes nothing
    asked = name
    await loadRooms(host.project) // a thread made since the rows were read
    if (openThread.value || name !== threadName.value) return
  }
  threadMissing.value = name !== props.room.name
}, { immediate: true })
watch(openThread, (t) => (focusIn.value = t ? 'panel' : 'room'))
</script>
