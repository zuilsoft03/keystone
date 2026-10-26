<template>
  <section :aria-label="title" class="relative flex min-h-0 min-w-0 flex-1 flex-col bg-surface-base" :data-testid="`${tid}room`">
    <header v-if="!bare" class="flex min-h-14 items-center gap-2.5 border-b border-outline-gray-2 px-4 py-2 max-md:px-1.5">
      <slot name="back" />
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <h1 class="m-0 truncate text-lg font-semibold text-ink-gray-9" :data-testid="`${tid}room-title`">{{ title }}</h1>
          <Badge v-if="badge" size="sm" :theme="badgeTheme" :label="badge" />
        </div>
        <p v-if="line" class="m-0 truncate text-xs text-ink-gray-7">{{ line }}</p>
      </div>
      <Button v-if="room && !inThread" variant="ghost" size="sm" icon-left="lucide-images" :label="w('attachments.files_button')"
        :aria-expanded="showFiles ? 'true' : 'false'" :data-testid="`${tid}files-toggle`" @click="toggleFiles" />
      <slot name="actions" />
    </header>
    <div v-if="showFiles && room && !inThread" class="absolute right-3 top-14 z-20 max-h-[60vh] w-80 max-w-[calc(100%-24px)] overflow-y-auto rounded-6 border border-outline-gray-2 bg-surface-base p-3 shadow-lg"
      :data-testid="`${tid}files-panel`">
      <Gallery :thread="room" :fallback="loadedFiles" :portal="portal" :prefix="tid" />
    </div>
    <p v-if="error || state.error" class="mx-4 mt-2 text-ink-red-7" role="alert" :data-testid="`${tid}error`">{{ error || state.error }}</p>
    <!-- P3-68: what the reader's own action did, said once and politely (a message's counts are not live regions) -->
    <p class="sr-only" role="status" :data-testid="`${tid}status`">{{ status }}</p>
    <AgreedList v-if="agreed.length" :items="agreed" :portal="portal" :prefix="tid" @go="goto" />
    <p v-if="notice" class="mx-4 mt-2 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-8" role="status" :data-testid="`${own}draft-dropped`">{{ notice }}</p>
    <ol ref="list" class="m-0 flex min-h-0 flex-1 list-none flex-col gap-0.5 overflow-y-auto px-3 py-2" :aria-live="live ? 'polite' : 'off'" :data-testid="`${tid}messages`">
      <template v-if="rootMessage">
        <MessageItem :message="rootMessage" :portal="portal" :prefix="`${tid}root-`" still />
        <li role="separator" class="my-1.5 flex items-center gap-2.5 text-xs text-ink-gray-7" :data-testid="`${tid}root-divider`">
          <span class="font-medium">{{ repliesWord }}</span><span class="h-px flex-1 bg-surface-gray-3" />
        </li>
      </template>
      <li v-if="state.cursor" class="self-center">
        <Button size="sm" variant="ghost" :label="w('core.older')" :loading="state.older" :data-testid="`${own}older`" @click="timeline.older()" />
      </li>
      <li v-if="state.loading" class="p-3 text-sm text-ink-gray-7">{{ w('core.loading') }}</li>
      <li v-else-if="!state.messages.length && !pending.length && !rootMessage" class="p-3 text-sm text-ink-gray-7" :data-testid="`${own}empty`">{{ w('core.empty') }}</li>
      <template v-for="{ m, sep } in rows" :key="m.name">
        <li v-if="sep" role="separator" class="my-1.5 flex items-center gap-2.5 text-xs text-ink-gray-7" :data-testid="`${tid}day-separator`">
          <span class="h-px flex-1 bg-surface-gray-3" /><span class="rounded-full border border-outline-gray-2 bg-surface-base px-2.5 py-0.5 font-medium">{{ sep }}</span><span class="h-px flex-1 bg-surface-gray-3" />
        </li>
        <MessageItem :message="m" :portal="portal" :prefix="tid" :line="lineFor(m)" :team="teamFor(m)"
          :can-reply="replyable(m)" :can-team="teamable(m)" @action="act" @thread="(t, msg) => emit('open-thread', t, msg)" @team="(msg) => emit('team', msg)" />
      </template>
      <li v-if="state.newer" class="self-center">
        <Button size="sm" variant="ghost" :label="w('core.newer')" :loading="state.newering" :data-testid="`${own}newer`" @click="timeline.newerPage()" />
      </li>
      <li v-for="u in pending" :key="u.client_id" class="flex gap-2.5 rounded-5 px-2.5 py-2"
        :class="u.state === 'failed' ? 'bg-surface-red-1' : ''" :data-testid="`${own}unsent`" :data-state="u.state">
        <Avatar :label="me" size="xl" :theme="themeOf(user)" />
        <div class="min-w-0 flex-1">
          <strong class="text-base font-semibold text-ink-gray-9">{{ me }}</strong>
          <MessageText v-if="u.text" :text="u.text" :parts="localParts(u.mentions, u.refs)" :portal="portal" :prefix="`${own}unsent-`" />
          <ul v-if="u.files?.length" class="m-0 mt-1 flex list-none flex-wrap gap-1.5 p-0">
            <li v-for="(f, i) in u.files" :key="i" class="inline-flex max-w-full items-center gap-1.5 rounded-4 border border-outline-gray-2 px-2 py-1 text-xs text-ink-gray-8">
              <span class="lucide-paperclip size-3.5 flex-none" aria-hidden="true" /><span class="truncate">{{ f }}</span>
            </li>
          </ul>
          <p v-if="u.state === 'sending'" class="m-0 mt-1 text-xs text-ink-gray-7">{{ w('core.sending') }}</p>
          <div v-else role="alert" class="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-ink-red-8">
            <span>{{ outbox.reasons[u.client_id] || w('core.not_sent') }}</span>
            <Button size="sm" variant="outline" :label="w('core.retry')" :data-testid="`${own}retry`" @click="retry(u)" />
            <Button size="sm" variant="ghost" :label="w('core.delete')" :data-testid="`${own}discard`" @click="outbox.discard(room, u.client_id)" />
          </div>
        </div>
      </li>
    </ol>
    <div v-if="host.viewer === 'staff'" class="mx-4 min-h-5" aria-live="polite">
      <p v-if="typingName" class="m-0 flex items-center gap-2 text-sm italic text-ink-gray-7" :data-testid="`${own}typing`">
        {{ w('core.typing', { name: typingName }) }} <Badge class="not-italic" size="sm" theme="amber" :label="w('core.badge_team')" />
      </p>
    </div>
    <Composer v-if="canWrite" ref="composer" v-model="text" v-model:also="also" :placeholder="placeholder" :audience="audienceLine" :actions="actions"
      :accept="accepted" :tray="tray" :voice="voice" :poll="poll" :thread="state.thread" :portal="portal" :prefix="tid" :also-room="inThread" v-model:marks="marks"
      @send="send" @typing="typing" @sent="polled" />
    <slot name="footer" />
  </section>
</template>

<script setup>
import { computed, inject, nextTick, onUnmounted, provide, ref, watch } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import { boot } from '../boot.js'
import { themeOf } from '../frame.js'
import { useMode } from '../mode.js'
import { onEvent } from '../realtime.js'
import { readerNearBottom, scrollToNewest } from '../sections/drafts.js'
import { dayLabel, formatDate, singleFlight, withDaySeparators } from '../sections/util.js'
import AgreedList from './AgreedList.vue'
import Composer from './Composer.vue'
import MessageItem from './MessageItem.vue'
import MessageText from './MessageText.vue'
import { HOST_KEY, ROOM_KEY } from './host.js'
import { Timeline } from './live.js'
import { Outbox } from './outbox.js'
import Gallery from './parts/attachments/Gallery.vue'
import { TEAM_ROOM_ACCEPT, trayOf } from './parts/attachments/tray.js'
import { pollOf } from './parts/polls/draft.js'
import { voiceOf } from './parts/voice/draft.js'
import { composerActions, runAction } from './registry.js'
import { later } from './rooms.js'
import { build, localParts } from './tokens.js'
import { lineOf, teamThreadsAbout } from './threads.js'
import { wordsFor } from './words.js'

// One conversation's timeline and message box (P3-64, R-32 §14.1): a room, or a thread (`inThread`, its root drawn
// first). The messages oldest first with day chips, kept live by message (live.js), the reader's unsent messages with
// Retry and Delete (outbox.js), the team's typing line (staff only) and the box, a thread's with "Also send to room".
// In a room each message carries its reply line and, for staff on a client's message, "Discuss with team" and the
// "Team discussing" marker. The page names the conversation and its words; the host decides what the reader may do.
const props = defineProps({
  room: { type: String, default: '' }, // the conversation shown: a room, or a thread when inThread
  audience: { type: String, default: '' }, // its audience: 'Internal' or 'Client'
  title: { type: String, default: '' },
  badge: { type: String, default: '' },
  badgeTheme: { type: String, default: 'gray' },
  line: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  audienceLine: { type: String, default: '' },
  accept: { type: String, default: '' },
  portal: Boolean,
  prefix: { type: String, default: '' },
  threadRows: { type: Array, default: () => [] }, // the project's thread rows (discuss.api.threads)
  teamRoom: { type: String, default: '' }, // staff: the Team room, for the "Team discussing" marker
  inThread: Boolean,
  at: { type: String, default: '' }, // P3-74: open the room around this message (the inbox's row), not at its newest
  root: { type: String, default: '' }, // a thread's root message, drawn above its replies
  replies: { type: Number, default: 0 },
  live: { type: Boolean, default: true }, // only the list the reader is in is a live region
  bare: Boolean, // no header: the thread panel draws its own
  ask: { type: String, default: '' }, // P3-65: a client's "Ask about this file": the file's address, put into the box
})
const emit = defineEmits(['opened', 'open-thread', 'team', 'asked', 'files'])
const host = inject(HOST_KEY)
const w = wordsFor(useMode(), props.portal)
const tid = computed(() => (props.inThread ? `${props.prefix}thread-` : props.prefix)) // the room's own test ids
const own = computed(() => (props.inThread ? 'thread-' : ''))
const timeline = new Timeline(host)
timeline.onNewest = () => markRead()
const state = timeline.state
const outbox = new Outbox(host)
const user = boot.user || ''
const me = boot.full_name || user
const text = ref('')
const marks = ref([]) // P3-66: the people and items picked into the text (tokens.js); the send turns their labels into tokens
const also = ref(false) // "Also send to room": off by default, and again after each send
const error = ref('')
const notice = ref('')
const typingName = ref('')
// P3-65: the files the next message carries, the page's tray for this conversation (kept when the room unmounts)
const tray = computed(() => (props.room && !host.readOnly && host.upload ? trayOf(host, props.room) : null))
// P3-75 (design §15.4): the Team room also takes Revit families and SketchUp files, which the server allows staff in an
// Internal conversation only (client_files.STAFF_ROOM_TYPES); the page's own list wins when it names one.
const accepted = computed(() => props.accept || (host.viewer === 'staff' && props.audience === 'Internal' ? TEAM_ROOM_ACCEPT : ''))
// P3-67: the voice note the next message carries (parts/voice/draft.js), where the thread offers voice
const voice = computed(() => (props.room && !host.readOnly && host.upload && (state.thread?.capabilities || []).includes('voice') ? voiceOf(host, props.room) : null))
// P3-68: the poll the box is making, where the thread offers polls (staff, an open thread)
const poll = computed(() => (props.room && !host.readOnly && host.send && (state.thread?.capabilities || []).includes('polls') ? pollOf(host, props.room, props.audience) : null))
const showFiles = ref(false)
const rootMessage = ref(null)
const status = ref('')
const agreed = ref([]) // P3-68: the Agreed messages of a Client conversation, newest first
let statusTimer = null
const list = ref(null)
const composer = ref(null)
const markOnce = singleFlight()
const canWrite = computed(() => !host.readOnly && Boolean(host.send) && Boolean(props.room) && state.thread?.status !== 'Locked')
const actions = computed(() => composerActions(host, state.thread))
// A read-only view (the staff preview) has no unsent rows and never reads or writes a draft (audit F2).
const pending = computed(() => (props.room && !host.readOnly ? outbox.list(props.room).rows : []))
// The portal never guesses "today" for a client in another time zone (D-354): its chips show the date only.
const rows = computed(() => withDaySeparators(state.messages, new Date(), props.portal ? formatDate : dayLabel))
const repliesWord = computed(() => (props.replies === 1 ? w('core.replies_one') : w('core.replies', { count: props.replies })))
const staffInClient = computed(() => host.viewer === 'staff' && props.audience === 'Client')
let typingTimer = null
let lastTyping = 0
let follow = false // the next change of the list scrolls to the newest message (opened, or the reader's own send)
let holding = false // opening at a message: the list scrolls to it once, not to the newest

const lineFor = (m) => (props.inThread ? null : lineOf(props.threadRows, props.room, m.name))
const teamFor = (m) => (staffInClient.value ? teamThreadsAbout(props.threadRows, props.teamRoom, m.name) : [])
const replyable = (m) => !props.inThread && canWrite.value && m.kind !== 'System' && !m.staff_only && !m.removed
// "Discuss with team": on a client's message, by the server's own per-message flag (staff reads only, audit F6).
const teamable = (m) => staffInClient.value && !host.readOnly && m.kind !== 'System' && !m.removed && m.from_client === true

// Never while the room is opened at an older message (P3-74): its newest messages are not on screen yet. Reaching them
// with "Show newer messages" marks it read (timeline.onNewest).
function markRead() {
  const room = props.room
  if (!room || !host.write || !timeline.atNewest()) return
  markOnce(room, () => host.write('mark_read', { thread: room }).then(() => later(host.project)).catch(() => {}))
}

async function send() {
  const room = props.room
  const body = text.value
  const box = tray.value
  const attachments = box ? box.ids() : []
  const note = voice.value?.payload() || null // P3-67: a voice note staged on the server, sent on its own
  if (voice.value?.busy) return // the take still runs, or the note is still on its way to the server
  if (note) {
    if (attachments.length || box?.busy) return // the server sends a voice note on its own; the box keeps the two apart
  } else if ((!body.trim() && !attachments.length) || box?.busy) return
  if (box?.blocked) return // a large file still being checked, or refused (P3-75): the message waits for the reader
  const files = note ? [w('voice.message')] : box ? box.names() : []
  const alsoRoom = props.inThread && also.value
  const tagged = build(body, marks.value)
  text.value = ''
  marks.value = []
  also.value = false
  error.value = ''
  box?.sent()
  voice.value?.sent()
  follow = true
  await scrollSoon()
  const name = await outbox.send(room, tagged.text, { also_room: alsoRoom, attachments, files, mentions: tagged.mentions, refs: tagged.refs, voice: note })
  if (name && room === props.room) {
    follow = true
    await (state.newer ? timeline.open(room) : timeline.refresh(name)) // opened at an older message: go to the newest
    markRead()
  }
}

async function retry(u) {
  const room = props.room
  const name = await outbox.retry(room, u.client_id)
  if (name && room === props.room) await timeline.refresh(name) // the stored message replaces the failed row
}

// A poll was sent from the builder: the list goes to it, as after any send of the reader's own.
async function polled(name) {
  follow = true
  await (state.newer ? timeline.open(props.room) : timeline.refresh(name))
  markRead()
}

// What a message and its parts may ask of the room (P3-68): put an action's answer into the list (the message or the thread's
// root), say what happened once, politely, or show why it failed.
function merge(message) {
  if (message && rootMessage.value && message.name === rootMessage.value.name) rootMessage.value = message
  else timeline.merge(message)
  if (message && message.removed) loadAgreed() // a removed message leaves the Agreed list
}

function say(text) {
  status.value = ''
  clearTimeout(statusTimer)
  nextTick(() => {
    status.value = text // cleared first, so the same words said twice are read twice
    statusTimer = setTimeout(() => (status.value = ''), 4000)
  })
}

function fail(text) {
  error.value = text || ''
}

provide(ROOM_KEY, { get thread() { return state.thread }, merge, say, fail })

// The Agreed list: only a Client conversation has one, and only a reader who can read it (the staff preview cannot).
async function loadAgreed() {
  const room = props.room
  if (!room || props.audience !== 'Client' || host.readOnly || host.viewer === 'preview') {
    agreed.value = []
    return
  }
  try {
    const answer = await host.read('agreed', { thread: room })
    if (room === props.room) agreed.value = answer?.messages || []
  } catch {
    if (room === props.room) agreed.value = []
  }
}

// "Show in conversation": the message is brought into view, the list opened around it first when it is not loaded.
async function goto(name) {
  if (!state.messages.some((m) => m.name === name)) {
    holding = true
    await timeline.open(props.room, { at: name })
    await nextTick()
    holding = false
  }
  keepAt(name)
}

async function act(action, message) {
  try {
    await runAction(host, action, message)
    await timeline.refresh(message.name)
    if (action.id === 'agree') loadAgreed()
  } catch (e) {
    error.value = e.message
  }
}

// At most one typing signal every two seconds (the server also limits it); staff typing never reaches a client.
function typing() {
  const now = Date.now()
  if (!host.write || now - lastTyping < 2000 || !props.room) return
  lastTyping = now
  host.write('typing', { thread: props.room }).catch(() => {})
}

async function scrollSoon() {
  await nextTick()
  scrollToNewest(list.value)
}

async function loadRoot(name) {
  rootMessage.value = null
  if (!name) return
  try {
    const m = await host.read('message', { name })
    if (name === props.root) rootMessage.value = m
  } catch { /* a root the reader cannot read is not drawn (SEC-22) */ }
}

const offs = host.viewer === 'preview' ? [] : [
  onEvent('cc_discuss_typing', (d) => {
    if (d.thread !== props.room) return
    typingName.value = d.name
    clearTimeout(typingTimer)
    typingTimer = setTimeout(() => (typingName.value = ''), 4000)
  }),
  onEvent('cc_discuss_seen', (d) => d.thread === props.room && !state.newer && timeline.latest()), // never marks read again
  onEvent('cc_discuss_pin', (d) => d.thread === props.room && timeline.refresh(d.message)),
  // P3-68: the Agreed list follows an Agreed mark, an edit and a removal (the message itself is re-read by the timeline)
  onEvent('cc_discuss_changed', (d) => (d.thread === props.room || d.room === props.room) && ['agreed', 'edit', 'removed'].includes(d.part) && loadAgreed()),
]
timeline.listen({ onMessage: (d) => d.thread === props.room && d.author !== user && markRead() })

// A conversation opens at its newest message, or at `at` (P3-74), with its own draft; the old one's messages and box
// never show under it.
watch(() => [props.room, props.at], async ([room, at], old) => {
  if (old && old[0] === room && !at) return // the page dropped ?at= (a thread opened or closed): keep the place
  typingName.value = ''
  error.value = ''
  also.value = false
  showFiles.value = false
  follow = !at
  holding = Boolean(at)
  const d = host.readOnly ? { text: '', dropped: false } : outbox.draft(room, props.audience)
  text.value = d.text
  marks.value = d.marks || []
  notice.value = d.dropped ? w('core.note_dropped') : ''
  agreed.value = []
  await timeline.open(room, { at })
  if (room !== props.room || at !== props.at) return
  loadAgreed()
  if (holding) {
    await nextTick()
    holding = false
    keepAt(at)
  }
  if (state.error) return
  markRead()
  emit('opened', state.thread)
  await nextTick()
  composer.value?.focus({ opening: true })
}, { immediate: true })
watch(() => props.root, loadRoot, { immediate: true })
// "Ask about this file" (§3.2, L-9): the file the client read in Files goes into the box, linked, never copied.
watch(() => [props.ask, props.room, canWrite.value], async ([url, room, can]) => {
  if (!url || !room || !can || !host.act) return
  emit('asked')
  try {
    const answer = await host.act('attachments', 'attach', { thread: room, url })
    if (room === props.room) tray.value?.link(answer)
  } catch (e) {
    error.value = e.message || ''
  }
}, { immediate: true })
watch(text, (now) => props.room && !host.readOnly && outbox.keep(props.room, now))
watch(marks, (picked) => props.room && !host.readOnly && outbox.pick(props.room, picked, text.value))
// P3-67: a hold that is let go (no lock, no cancel) sends the note at once, as soon as the server has it
watch(() => voice.value?.state.sendNow, (now) => now && send(), { immediate: true })
// A new message scrolls the list only when the reader is near the end, or after their own send.
watch(() => [state.messages, pending.value.length], async () => {
  if (holding) return
  const go = follow || readerNearBottom(list.value)
  follow = false
  await nextTick()
  if (go) scrollToNewest(list.value)
})
function scrollToMessage(name) {
  const row = name && [...(list.value?.querySelectorAll('[data-name]') || [])].find((el) => el.dataset.name === name)
  if (row) row.scrollIntoView({ block: 'center' })
}

// Opening at a message (P3-74): the list is drawn before its part views have loaded (async), and a card that arrives
// afterwards (a photo of 320 px, P3-65) moves the message out of view. So the message is brought back each time the
// rows change size, until they settle (KEEP_AT ms) or the reader scrolls on their own.
const KEEP_AT = 2500
let stopKeeping = () => {}
function keepAt(name) {
  stopKeeping()
  scrollToMessage(name)
  const el = list.value
  if (!el || typeof ResizeObserver !== 'function') return
  const sizes = new ResizeObserver(() => scrollToMessage(name))
  for (const row of el.children) sizes.observe(row)
  const stop = () => {
    sizes.disconnect()
    clearTimeout(timer)
    for (const type of ['wheel', 'touchstart', 'keydown']) el.removeEventListener(type, stop)
    stopKeeping = () => {}
  }
  const timer = setTimeout(stop, KEEP_AT)
  for (const type of ['wheel', 'touchstart', 'keydown']) el.addEventListener(type, stop, { passive: true })
  stopKeeping = stop
}

// Files in this conversation opens over the room's header; the page closes its own popover there (`files`).
function toggleFiles() {
  showFiles.value = !showFiles.value
  if (showFiles.value) emit('files')
}

// The files of the messages on screen: what Files in this conversation shows to a view that cannot read the gallery.
const loadedFiles = computed(() => state.messages.flatMap((m) => m.parts?.attachments || []).filter((c) => c && c.url))

onUnmounted(() => {
  stopKeeping()
  clearTimeout(statusTimer)
  offs.forEach((off) => off())
  timeline.close()
  clearTimeout(typingTimer)
})
defineExpose({ state, rootMessage, focusBox: () => composer.value?.focus({ opening: true }), closeFiles: () => (showFiles.value = false) })
</script>
