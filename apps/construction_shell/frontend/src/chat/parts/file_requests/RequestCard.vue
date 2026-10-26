<template>
  <section v-if="card" :aria-label="card.title" class="mt-2 flex w-[420px] max-w-full flex-col gap-2 rounded-5 border border-outline-gray-2 bg-surface-base p-3"
    :data-testid="`${prefix}request`" :data-status="card.status" :data-role="card.role" :data-request="card.request">
    <div class="flex items-center gap-1.5 text-xs text-ink-gray-7">
      <span class="lucide-arrow-up-to-line size-3.5 flex-none" aria-hidden="true" />
      <span class="min-w-0 truncate" :data-testid="`${prefix}request-kind`">{{ kind }}</span>
      <Badge v-if="card.status === 'Done'" size="sm" theme="green" :label="w('file_requests.status_done')" :data-testid="`${prefix}request-done`" />
      <Badge v-else-if="card.status === 'Cancelled'" size="sm" theme="gray" :label="w('file_requests.status_cancelled')" :data-testid="`${prefix}request-cancelled`" />
      <span v-if="due" class="ml-auto flex-none" :data-testid="`${prefix}request-due`">{{ w('file_requests.due', { date: due }) }}</span>
    </div>
    <p v-if="showTitle" class="m-0 text-sm font-medium text-ink-gray-9" :data-testid="`${prefix}request-title`">{{ card.title }}</p>
    <strong class="text-sm font-semibold text-ink-gray-9" :data-testid="`${prefix}request-count`">{{ count }}</strong>
    <div class="h-1.5 overflow-hidden rounded-full bg-surface-gray-3" role="progressbar" aria-valuemin="0" :aria-valuemax="bar.total" :aria-valuenow="bar.received" :aria-label="count">
      <span class="block h-full bg-surface-green-7" :style="{ width: `${bar.percent}%` }" />
    </div>
    <ul class="m-0 flex list-none flex-col gap-1.5 p-0">
      <li v-for="i in view.items" :key="i.item" class="flex flex-col gap-1" :data-testid="`${prefix}request-item`" :data-item="i.item" :data-state="i.state">
        <div class="flex items-center gap-2 text-sm text-ink-gray-9">
          <span class="grid size-[18px] flex-none place-items-center rounded-full" :class="mark(i.state)" aria-hidden="true">
            <span v-if="i.state === 'received' || i.state === 'accepted'" class="lucide-check size-3" />
            <span v-else-if="i.state === 'again'" class="lucide-rotate-ccw size-3" />
          </span>
          <span class="min-w-0 flex-1 truncate">{{ itemName(i, w) }}<span v-if="!i.required" class="ml-1.5 text-xs text-ink-gray-7">{{ w('file_requests.optional') }}</span></span>
          <span class="flex-none text-xs text-ink-gray-7" :data-testid="`${prefix}request-state`">{{ w(`file_requests.state_${i.state}`) }}</span>
        </div>
        <div v-if="i.held && view.staff" class="ml-[26px] flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-gray-7">
          <span class="min-w-0 max-w-full truncate" :data-testid="`${prefix}request-held`">{{ heldLine(i) }}</span>
          <template v-if="i.reviews || i.accepts || i.asksAgain">
            <a v-if="i.reviews" :href="host.heldUrl(i.item)" target="_blank" rel="noopener" :aria-label="w('file_requests.review_item', { name: itemName(i, w) })"
              class="inline-flex h-7 items-center rounded-4 bg-surface-gray-2 px-2.5 text-sm text-ink-gray-8 hover:bg-surface-gray-3 max-md:h-12 max-md:px-4" :data-testid="`${prefix}request-review`">{{ w('file_requests.review') }}</a>
            <Button v-if="i.accepts" size="sm" variant="subtle" class="max-md:!h-12" :label="w('file_requests.accept')" :aria-label="w('file_requests.accept_item', { name: itemName(i, w) })"
              :disabled="busy" :data-testid="`${prefix}request-accept`" @click="accept(i)" />
            <Button v-if="i.asksAgain" size="sm" variant="ghost" class="max-md:!h-12" :label="w('file_requests.ask_again')" :aria-label="w('file_requests.ask_item', { name: itemName(i, w) })"
              :disabled="busy" :data-testid="`${prefix}request-ask-again`" @click="asking = i" />
          </template>
        </div>
        <p v-if="i.reason && i.state === 'again' && view.staff" class="m-0 ml-[26px] text-xs text-ink-gray-7" :data-testid="`${prefix}request-reason`">{{ i.reason }}</p>
      </li>
    </ul>
    <div v-if="view.sends || view.opens || view.nudges || view.cancels" class="flex flex-wrap items-center gap-1.5">
      <Button v-if="view.sends" size="sm" variant="solid" theme="blue" class="max-md:!h-12" icon-left="lucide-upload" :label="w('file_requests.send_files')" :data-testid="`${prefix}request-send`" @click="open" />
      <Button v-if="view.nudges" size="sm" variant="subtle" class="max-md:!h-12" icon-left="lucide-bell" :label="w('file_requests.nudge')" :loading="nudging" :disabled="busy" :data-testid="`${prefix}request-nudge`" @click="nudge" />
      <Button v-if="view.opens" size="sm" variant="subtle" class="max-md:!h-12" :label="w('file_requests.open_request')" :data-testid="`${prefix}request-open`" @click="open" />
      <template v-if="view.cancels">
        <Button v-if="!cancelling" size="sm" variant="ghost" class="max-md:!h-12" :label="w('file_requests.cancel')" :disabled="busy" :data-testid="`${prefix}request-cancel`" @click="cancelling = true" />
        <span v-else class="inline-flex flex-wrap items-center gap-1.5 text-xs text-ink-gray-8" role="group" :aria-label="w('file_requests.cancel_ask')">
          <span>{{ w('file_requests.cancel_ask') }}</span>
          <Button size="sm" variant="subtle" class="max-md:!h-12" :label="w('file_requests.cancel_yes')" :loading="busy" :data-testid="`${prefix}request-cancel-yes`" @click="cancel" />
          <Button size="sm" variant="ghost" class="max-md:!h-12" :label="w('file_requests.cancel_no')" @click="cancelling = false" />
        </span>
      </template>
    </div>
    <p v-if="nudged" class="m-0 text-xs text-ink-gray-8" role="status" :data-testid="`${prefix}request-nudged`">{{ nudged }}</p>
    <AskAgainDialog v-if="asking" v-model:open="askOpen" :item="asking" :name="itemName(asking, w)" :prefix="prefix" @done="asked" />
  </section>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { HOST_KEY, ROOM_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import AskAgainDialog from './AskAgainDialog.vue'
import { cardView, dayText, itemName, nudgeWords, progressOf, whoLine } from './view.js'

// The file request card (design §3.10; canvas "Message cards": File requests, staff view and client view): "File request ·
// who", the due date, "3 of 5 files received", a bar and the files with their state. Staff review a Received file (Review
// opens it from the server's held endpoint), Accept it or Ask again with a reason; they Nudge and Cancel (asked first:
// it deletes the files already sent). A person asked gets Send files, which opens the request page. What a button needs
// is also what the screen can do: the staff preview of a portal has no act, so it draws none. The server checks again.
const props = defineProps({ items: { type: [Array, Object], default: null }, message: { type: Object, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const host = inject(HOST_KEY)
const room = inject(ROOM_KEY, null)
const route = useRoute()
const router = useRouter()
const w = wordsFor(useMode(), props.portal)
const busy = ref(false)
const nudging = ref(false)
const cancelling = ref(false)
const asking = ref(null)
const nudged = ref('')
const card = computed(() => (props.items && typeof props.items === 'object' && !Array.isArray(props.items) ? props.items : null))
const view = computed(() => cardView(card.value, { act: Boolean(host.act), upload: Boolean(host.requestUpload) }))
const bar = computed(() => progressOf(card.value))
const due = computed(() => dayText(card.value?.due_on))
const count = computed(() => w(bar.value.total === 1 ? 'file_requests.progress_one' : 'file_requests.progress', { received: bar.value.received, total: bar.value.total }))
const kind = computed(() => (view.value.staff ? w('file_requests.card_for', { who: whoLine(card.value.recipients) }) : w('file_requests.asked_for')))
// The message's text is the title unless the sender wrote a note above it; the canvas card names no title of its own.
const showTitle = computed(() => (props.message.text || '').trim() !== card.value.title)
const askOpen = computed({ get: () => Boolean(asking.value), set: (v) => { if (!v) asking.value = null } })
const MARK = { received: 'bg-surface-green-2 text-ink-green-8', accepted: 'bg-surface-green-2 text-ink-green-8', again: 'bg-surface-amber-2 text-ink-amber-8', waiting: 'bg-surface-gray-2 text-ink-gray-6' }
const mark = (state) => MARK[state]

function heldLine(i) {
  const h = i.held
  if (h.checking) return w('file_requests.held_checking', { file: h.file_name })
  if (h.refused) return w('file_requests.held_refused', { file: h.file_name, reason: h.refused })
  return [h.file_name, i.uploaded_by ? w('file_requests.sent_by', { name: i.uploaded_by.name }) : ''].filter(Boolean).join(' · ')
}

// The request page: a panel beside the conversation in the workspace, the portal's own screen for a client (their routes
// read ?request=). The rest of the address stays as it is.
function open() {
  router.push({ query: { ...route.query, request: card.value.request } })
}

// An action answers the request's page, not the message: the message is read again, and the room puts it in the list.
async function refresh() {
  room?.merge(await host.read('message', { name: props.message.name }))
}

async function run(request, said) {
  busy.value = true
  try {
    const answer = await request()
    await refresh()
    if (said) room?.say(w(said))
    return answer
  } catch (e) {
    room?.fail(e.message)
    return null
  } finally {
    busy.value = false
  }
}

const accept = (i) => run(() => host.act('file_requests', 'accept', { item: i.item }), 'file_requests.said_accepted')

async function cancel() {
  await run(() => host.act('file_requests', 'cancel', { request: card.value.request }), 'file_requests.said_cancelled')
  cancelling.value = false
}

async function asked() {
  asking.value = null
  busy.value = true
  try {
    await refresh()
    room?.say(w('file_requests.said_asked'))
  } catch (e) {
    room?.fail(e.message)
  } finally {
    busy.value = false
  }
}

async function nudge() {
  nudging.value = true
  nudged.value = ''
  try {
    const lines = nudgeWords(await host.act('file_requests', 'nudge', { request: card.value.request })).map((l) => w(l.key, l.values))
    nudged.value = lines.join(' ')
    room?.say(nudged.value)
  } catch (e) {
    room?.fail(e.message)
  } finally {
    nudging.value = false
  }
}
</script>
