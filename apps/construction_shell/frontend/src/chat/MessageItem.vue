<template>
  <li ref="item" tabindex="-1" class="group relative flex gap-2.5 rounded-5 px-2.5 py-2 focus:outline-none max-md:flex-wrap"
    :class="message.staff_only ? 'bg-surface-amber-1' : ''" :data-testid="`${prefix}message`" :data-name="message.name">
    <Avatar v-if="!eventLine" :image="message.author.image || undefined" :label="message.author.name" size="xl" :theme="themeOf(message.author.user)" />
    <div class="min-w-0 flex-1">
      <div v-if="!eventLine" class="flex flex-wrap items-baseline gap-1.5">
        <strong class="text-base font-semibold text-ink-gray-9">{{ message.author.name }}</strong>
        <Badge v-if="message.mine" size="sm" theme="blue" :label="w('core.you')" />
        <Badge v-if="message.staff_only" size="sm" theme="amber" :label="w('core.staff_note')" data-testid="staff-only-tag" />
        <Badge v-if="message.pinned" size="sm" theme="amber" :label="w('core.pinned')" data-testid="pinned-tag" />
        <Badge v-if="message.agreed && !message.removed" size="sm" theme="green" :label="w('core.agreed')" :data-testid="`${prefix}agreed-tag`" />
        <span class="ml-auto flex items-baseline gap-1.5 text-xs text-ink-gray-7">
          <span v-if="message.edited && !message.removed" :data-testid="`${prefix}edited`">{{ w('core.edited') }}</span>
          <time :datetime="message.creation" :title="message.when">{{ time }}</time>
        </span>
      </div>
      <p v-if="message.removed" class="text-p-base mt-0.5 italic text-ink-gray-7" data-testid="removed">{{ w('core.removed') }}</p>
      <div v-else-if="editing">
        <Composer ref="editor" v-model="editText" v-model:marks="editMarks" :actions="editActions" :thread="room?.thread" :portal="portal" :prefix="`${prefix}edit-`"
          editing :saveable="canSave" :busy="saving" :placeholder="w('core.edit_label')" @send="save" @cancel="stopEditing" />
        <p v-if="editError" class="m-0 mt-1 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}edit-error`">{{ editError }}</p>
      </div>
      <template v-else>
        <MessageText v-if="body" :text="body" :parts="message.parts" :portal="portal" :prefix="prefix" />
        <p v-if="kindLine" class="mt-0.5 text-sm text-ink-gray-7" data-testid="kind-fallback">{{ kindLine }}</p>
        <component :is="PART_VIEWS[key]" v-for="key in shown" :key="key" :items="itemsOf(key)" :message="message" :portal="portal" :prefix="prefix"
          v-bind="eventLine && key === 'pointer' ? { time } : null" />
        <!-- P3-66: a message whose text tags an item but carries no refs part still draws the neutral card, never the token -->
        <component :is="PART_VIEWS.refs" v-if="orphanRefs" :items="[]" :message="message" :portal="portal" :prefix="prefix" />
        <p v-for="key in parts.unknown" :key="key" class="mt-1 text-sm text-ink-gray-7" data-testid="unknown-part">{{ w('core.unknown_part') }}</p>
      </template>
      <button v-if="line" type="button" class="mt-1.5 inline-flex items-center gap-1.5 rounded-4 px-1.5 py-0.5 text-sm text-ink-gray-7 hover:bg-surface-gray-2"
        :aria-label="reply.aria" :data-reply-for="message.name" data-testid="reply-line" @click="emit('thread', line, message)">
        <span class="lucide-messages-square size-4 text-ink-blue-8" aria-hidden="true" />
        <strong class="font-semibold text-ink-blue-8">{{ reply.text.split(' · ')[0] }}</strong>
        <span v-if="reply.text.includes(' · ')">· {{ reply.text.split(' · ').slice(1).join(' · ') }}</span>
        <Badge v-if="reply.fresh" size="sm" variant="solid" theme="blue" :label="w('core.replies_new', { count: reply.fresh })" />
      </button>
      <button v-if="team.length" type="button" class="ml-1 mt-1.5 inline-flex items-center gap-1.5 rounded-4 bg-surface-amber-1 px-2 py-0.5 text-xs font-medium text-ink-amber-8 hover:bg-surface-amber-2"
        data-testid="team-discussing" @click="emit('thread', team[0], message)">
        <span class="lucide-users size-3.5" aria-hidden="true" />{{ w('core.team_discussing', { count: teamCount }) }}
      </button>
      <div v-if="message.seen_by?.length" class="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-gray-7" data-testid="seen-by">
        <span>{{ w('core.seen_by') }}</span>
        <Avatar v-for="s in message.seen_by" :key="s.user" :image="s.image || undefined" :label="s.name" size="sm" :theme="themeOf(s.user)" :title="s.name" />
        <Badge size="sm" theme="amber" :label="w('core.badge_team')" />
      </div>
    </div>
    <MessageTools v-if="!still && !eventLine && (actions.length || reactions.length || canReply || canTeam)" :actions="actions" :reactions="reactions" :can-reply="canReply" :can-team="canTeam"
      :message="message" :portal="portal" :prefix="prefix" @thread="emit('thread', line, message)" @team="emit('team', message)" @action="onAction" @react="react" />
    <RemoveDialog v-if="removing" v-model:open="removing" :message="message" :portal="portal" :prefix="prefix" @done="item?.focus()" />
    <HistoryDialog v-if="showing" v-model:open="showing" :message="message" :portal="portal" :prefix="prefix" />
  </li>
</template>

<script setup>
import { computed, inject, nextTick, ref } from 'vue'
import { Avatar, Badge } from 'frappe-ui'
import { themeOf } from '../frame.js'
import Composer from './Composer.vue'
import MessageText from './MessageText.vue'
import MessageTools from './MessageTools.vue'
import { useMode } from '../mode.js'
import { clockTime, stampTime } from '../sections/util.js'
import { HOST_KEY, ROOM_KEY } from './host.js'
import { changed, editDraft, editPayload } from './parts/edit/edit.js'
import HistoryDialog from './parts/edit/HistoryDialog.vue'
import RemoveDialog from './parts/edit/RemoveDialog.vue'
import { eventsOnly } from './parts/events/view.js'
import { choices, offered, said } from './parts/reactions/summary.js'
import { withoutPictures } from './parts/polls/view.js'
import { KINDS, PART_VIEWS, composerActions, messageActions, partsOf, reactionsOffered } from './registry.js'
import { replyLine } from './threads.js'
import { refPositions } from './tokens.js'
import { wordsFor } from './words.js'

// One message's frame (design §13.2 F2): the core draws author, "You", the staff-only mark (old notes, staff only),
// pinned, Agreed, "edited", time and the removed line, checked before any part is drawn; each part draws its own items.
// Text is drawn with {{ }} only. A part key the screen does not know gets a neutral line; a kind it does not know, its text
// and the kind's fallback line. P3-68: the toolbar (MessageTools) offers React and More; Edit opens the box in place of the
// text, Remove asks first, History lists the earlier texts. The answers go to the room, which merges them (no re-read: the
// counts are recounted by a job after the commit).
const props = defineProps({
  message: { type: Object, required: true },
  portal: Boolean,
  prefix: { type: String, default: '' },
  line: { type: Object, default: null }, // the thread off this message in its room (its reply line)
  team: { type: Array, default: () => [] }, // the Team threads about this client message (staff only)
  canReply: Boolean, // "Reply in thread": a message of a room timeline the reader may write in
  canTeam: Boolean, // "Discuss with team": staff, on a client's message
  still: Boolean, // a thread's root above its replies: drawn with no toolbar
})
const emit = defineEmits(['action', 'thread', 'team'])
const host = inject(HOST_KEY)
const room = inject(ROOM_KEY, null)
const w = wordsFor(useMode(), props.portal)
const item = ref(null)
const editor = ref(null)
const editing = ref(false)
const editText = ref('')
const editMarks = ref([])
const editError = ref('')
const saving = ref(false)
const removing = ref(false)
const showing = ref(false)
let draft = { text: '', marks: [] }
const parts = computed(() => partsOf(props.message))
const actions = computed(() => (props.still ? [] : messageActions(host, props.message)))
const reactions = computed(() => (!props.still && reactionsOffered(host, room?.thread, props.message) ? choices(props.message.parts?.reactions, offered(host), w) : []))
const editActions = computed(() => composerActions(host, room?.thread).filter((a) => a.part === 'mentions' || a.part === 'refs'))
const canSave = computed(() => changed(draft, editText.value, editMarks.value))
// The parts to draw: a poll message's photos are its options' pictures, so the attachments part shows only the others.
const shown = computed(() => parts.value.known.filter((k) => k !== 'attachments' || itemsOf(k)?.length))
// The portal never guesses "today" for a client in another time zone (D-354): it shows the date with the time.
const time = computed(() => (props.portal ? stampTime(props.message.creation) : clockTime(props.message.creation)))
// P3-69 (canvas "Events in a thread"): a System message of design events only is its lines alone, the time at the right of
// each: no avatar, name or toolbar. A room mirror or a root card is still drawn as a message.
const eventLine = computed(() => eventsOnly(props.message))
// A System card's stored text is the neutral word: its pointer part draws it, so the word is not shown twice. A file
// sent without a caption carries its name as text: the card shows it (portal/tabs.js messageText, P3-07).
const body = computed(() => {
  const m = props.message
  if (m.kind === 'System' && (parts.value.known.includes('pointer') || parts.value.known.includes('approval'))) return '' // P3-78: the approval card has no pointer part
  const files = m.parts?.attachments || []
  // P3-65: a message of files the reader cannot open (every card dropped) is named by its kind, never a blank bubble
  if (!m.text && m.kind === 'Files' && !files.length) return w('kind.Files')
  // P3-67: the same for a voice note whose card the reader cannot open (an unreadable file): named by its kind
  if (!m.text && m.kind === 'Voice' && !m.parts?.voice) return w('kind.Voice')
  // P3-68: and for a poll whose card is gone
  if (!m.text && m.kind === 'Poll' && !m.parts?.polls) return w('kind.Poll')
  return files.length === 1 && files[0].file_name === m.text ? '' : m.text
})
// P3-66: tokens in the text with no refs part to draw them
const orphanRefs = computed(() => !parts.value.known.includes('refs') && refPositions(body.value).length > 0)
const kindLine = computed(() => (KINDS.includes(props.message.kind) ? '' : w('kind.fallback')))
const reply = computed(() => replyLine(props.line, w, props.portal ? stampTime : clockTime))
const teamCount = computed(() => props.team.reduce((n, t) => n + (Number(t.replies) || 0), 0))

function itemsOf(key) {
  return key === 'attachments' ? withoutPictures(props.message) : props.message.parts[key]
}

// An action with a screen of its own opens it here; any other goes to the room (it runs the call and re-reads).
function onAction(action) {
  if (action.open === 'edit') startEditing()
  else if (action.open === 'remove') removing.value = true
  else if (action.open === 'history') showing.value = true
  else emit('action', action, props.message)
}

function startEditing() {
  draft = editDraft(props.message, w)
  editText.value = draft.text
  editMarks.value = draft.marks
  editError.value = ''
  editing.value = true
  nextTick(() => editor.value?.focus({ force: true })) // forced: the menu the reader used has the focus now
}

function stopEditing() {
  editing.value = false
  nextTick(() => item.value?.focus())
}

async function save() {
  if (saving.value || !canSave.value) return
  saving.value = true
  editError.value = ''
  try {
    const { text, parts: kept } = editPayload(editText.value, editMarks.value)
    room?.merge(await host.edit({ message: props.message.name, text, parts: kept }))
    room?.say(w('core.said_edited'))
    stopEditing()
  } catch (e) {
    editError.value = e.message || ''
  } finally {
    saving.value = false
  }
}

async function react(choice) {
  try {
    room?.merge(await host.act('reactions', 'react', { message: props.message.name, reaction: choice.id, on: choice.on ? 0 : 1 }))
    room?.say(said(choice.id, !choice.on, w))
  } catch (e) {
    room?.fail(e.message)
  }
}
</script>
