<template>
  <nav :aria-label="w('core.rooms')" class="flex flex-col gap-1 px-2 py-3" data-testid="room-list">
    <h2 class="cw-label m-0 px-2.5 pb-1 text-ink-gray-7">{{ w('core.rooms') }}</h2>
    <p v-if="loaded && !rooms.length" class="px-2.5 py-2 text-sm text-ink-gray-7">{{ w('core.no_rooms') }}</p>
    <div class="flex flex-col gap-0.5" data-thread-list>
      <router-link v-for="r in rooms" :key="r.name" :to="linkOf(r)"
        class="flex min-h-14 items-start gap-2.5 rounded-5 px-2.5 py-2 no-underline"
        :class="r.name === current ? 'bg-surface-blue-1' : 'hover:bg-surface-gray-2'"
        :aria-current="r.name === current ? 'page' : undefined" data-testid="room-row" :data-room="r.name" :data-audience="r.audience">
        <span class="mt-0.5 grid size-8 flex-none place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-7">
          <span :class="r.audience === 'Internal' ? 'lucide-users' : 'lucide-message-circle'" class="size-[18px]" aria-hidden="true" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="flex items-center gap-1.5">
            <span class="truncate text-base font-semibold" :class="r.name === current ? 'text-ink-blue-9' : 'text-ink-gray-9'">{{ nameOf(r) }}</span>
            <span v-if="subtitleOf(r)" class="flex-none text-[11px] text-ink-gray-7" data-testid="room-subtitle">{{ subtitleOf(r) }}</span>
            <Badge v-if="r.unread" class="ml-auto" variant="solid" theme="blue" size="sm" :label="String(r.unread)"
              :aria-label="w('core.unread', { count: r.unread })" data-testid="room-unread" />
          </span>
          <span v-if="summaryOf(r)" class="mt-0.5 block truncate text-xs text-ink-gray-7" data-testid="room-line">{{ summaryOf(r) }}</span>
          <span v-if="summaries[r.name]?.needs_reply" class="inline-flex items-center gap-1 text-[11px] font-medium text-ink-amber-8" data-testid="room-needs-reply">
            <span class="lucide-reply size-3" aria-hidden="true" />{{ w('inbox.needs_reply') }}
          </span>
        </span>
      </router-link>
    </div>
  </nav>
</template>

<script setup>
import { Badge } from 'frappe-ui'
import { useMode } from '../mode.js'
import { lineOf } from './inbox/store.js'
import { roomName } from './rooms.js'
import { wordsFor } from './words.js'

// The room list (R-32 §14.1, canvas "Discussion hub" frame 1): one row per room the reader may read, Team first, with
// its audience word and the reader's unread count. P3-74 (§14.6): the Discussion inbox's rows head it too, each room's
// newest line and Needs a reply (`summaries`, discussion_inbox for this project).
const props = defineProps({
  rooms: { type: Array, default: () => [] },
  current: { type: String, default: '' },
  company: { type: String, default: '' },
  loaded: Boolean,
  linkOf: { type: Function, required: true },
  summaries: { type: Object, default: () => ({}) }, // room -> its discussion_inbox row
})
const w = wordsFor(useMode())
function summaryOf(r) {
  const row = props.summaries[r.name]
  if (!row?.last) return ''
  const { who, text } = lineOf(row, w)
  return who ? `${who}: ${text}` : text
}
const nameOf = (r) => roomName(r, { viewer: 'staff', company: props.company, w })
// The audience word under the name: "Staff only" for Team; for the client's room "Client" under the company's name, as
// the design draws it, and nothing when the name is already "Client" (no "Client  Client").
function subtitleOf(r) {
  if (r.audience === 'Internal') return w('core.badge_team')
  const word = w('core.badge_client')
  return nameOf(r) === word ? '' : word
}
</script>
