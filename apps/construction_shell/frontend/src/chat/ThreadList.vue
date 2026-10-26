<template>
  <section v-if="threads.length || showEmpty" class="flex flex-col gap-0.5" :data-testid="testid">
    <h2 class="cw-label m-0 px-2.5 pb-1 pt-2 text-ink-gray-7">{{ heading }}</h2>
    <p v-if="!threads.length" class="m-0 px-2.5 py-1 text-sm text-ink-gray-7">{{ emptyWord || w('core.no_threads') }}</p>
    <router-link v-for="t in threads" :key="t.name" :to="linkOf(t)"
      class="flex min-h-9 items-center gap-2 rounded-4 px-2.5 py-1 no-underline"
      :class="t.name === current ? 'bg-surface-blue-1' : 'hover:bg-surface-gray-2'"
      :aria-current="t.name === current ? 'true' : undefined" data-testid="thread-row" :data-thread="t.name">
      <span class="lucide-messages-square size-4 flex-none text-ink-gray-6" aria-hidden="true" />
      <span class="min-w-0 flex-1">
        <span class="block truncate text-sm text-ink-gray-9">{{ threadTitle(t, w) }}</span>
        <span class="block truncate text-[11px] text-ink-gray-7">{{ subtitleOf(t) }}</span>
      </span>
      <Badge v-if="newReplies(t)" variant="solid" theme="blue" size="sm" :label="String(newReplies(t))"
        :aria-label="w('core.replies_new', { count: newReplies(t) })" data-testid="thread-unread" />
    </router-link>
  </section>
</template>

<script setup>
import { Badge } from 'frappe-ui'
import { useMode } from '../mode.js'
import { newReplies, threadTitle } from './threads.js'
import { wordsFor } from './words.js'

// A list of threads (P3-64): a room's "Active threads", or the "Threads you follow" across rooms (canvas frame 1),
// each with its replies, or the room it is in, and its new replies when the reader follows it (§14.5).
const props = defineProps({
  threads: { type: Array, default: () => [] },
  heading: { type: String, default: '' },
  current: { type: String, default: '' },
  linkOf: { type: Function, required: true },
  roomOf: { type: Function, default: null }, // "in Acme Corp" under each row of a list across rooms
  portal: Boolean,
  showEmpty: Boolean,
  emptyWord: { type: String, default: '' }, // P3-66: what an empty list says under a filter
  testid: { type: String, default: 'thread-list' },
})
const w = wordsFor(useMode(), props.portal)

function subtitleOf(t) {
  if (props.roomOf) return w('core.in_room', { room: props.roomOf(t) })
  const n = Number(t.replies) || 0
  return n === 1 ? w('core.replies_one') : w('core.replies', { count: n })
}
</script>
