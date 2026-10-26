<template>
  <router-link :to="to" class="grid min-h-[60px] grid-cols-[36px_minmax(0,180px)_minmax(0,1fr)_auto_auto] items-center gap-3 border-t border-outline-gray-1 bg-surface-base px-4 py-2 no-underline hover:bg-surface-gray-1 max-md:grid-cols-[36px_minmax(0,1fr)_auto] max-md:gap-x-3 max-md:gap-y-1"
    :aria-label="label" data-testid="inbox-row" :data-room="row.room" :data-audience="row.audience">
    <span class="grid size-9 place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-7 max-md:row-span-2">
      <span :class="row.audience === 'Internal' ? 'lucide-users' : 'lucide-message-circle'" class="size-[18px]" aria-hidden="true" />
    </span>
    <span class="min-w-0">
      <span class="block truncate text-base font-semibold text-ink-gray-9" data-testid="inbox-room-name">{{ title }}</span>
      <span v-if="subtitle" class="block truncate text-xs text-ink-gray-7">{{ subtitle }}</span>
      <!-- P3-80: the Client room of a project with an approval request still open names who it waits on -->
      <span v-if="row.waiting" class="flex items-start gap-1 text-xs font-medium text-ink-amber-8" data-testid="inbox-waiting"><span class="lucide-clock mt-0.5 size-3 flex-none" aria-hidden="true" /><span class="min-w-0 break-words">{{ row.waiting.text }}</span></span>
    </span>
    <span class="flex min-w-0 items-center gap-2 max-md:col-start-2 max-md:col-end-4 max-md:row-start-2">
      <Avatar v-if="row.last" :image="row.last.author?.image || undefined" :label="line.who" size="sm" :theme="themeOf(row.last.author?.user)" />
      <span class="min-w-0 truncate text-sm text-ink-gray-8" data-testid="inbox-line">
        <strong v-if="line.who" class="font-semibold text-ink-gray-9">{{ line.who }}:</strong> {{ line.text }}
      </span>
    </span>
    <span class="flex items-center gap-2 max-md:hidden">
      <span v-if="row.needs_reply" class="inline-flex h-[22px] items-center gap-1 rounded-full bg-surface-amber-2 px-2 text-xs font-medium text-ink-amber-8" data-testid="inbox-needs-reply">
        <span class="lucide-reply size-3.5" aria-hidden="true" />{{ w('inbox.needs_reply') }}
      </span>
      <Badge v-if="row.mentions" size="sm" theme="blue" :label="w('inbox.mention')" :aria-label="w('inbox.mention_aria')" data-testid="inbox-mention" />
    </span>
    <span class="flex min-w-[92px] flex-col items-end gap-1">
      <time v-if="row.last" class="text-xs text-ink-gray-7" :datetime="row.last.creation">{{ when }}</time>
      <span v-if="counts" class="flex items-center gap-1 whitespace-nowrap text-xs" data-testid="inbox-counts">
        <span v-if="row.unread" class="rounded-full bg-surface-blue-6 px-1.5 font-semibold leading-[18px] text-ink-base">{{ w('inbox.new', { count: row.unread }) }}</span>
        <span v-if="row.unread && row.in_threads" class="text-ink-gray-7" aria-hidden="true">·</span>
        <span v-if="row.in_threads" class="font-medium text-ink-blue-8">{{ w('inbox.in_threads', { count: row.in_threads }) }}</span>
      </span>
      <span v-if="row.needs_reply || row.mentions" class="hidden items-center gap-1.5 max-md:flex">
        <span v-if="row.needs_reply" class="rounded-full bg-surface-amber-2 px-2 text-xs font-medium leading-5 text-ink-amber-8">{{ w('inbox.needs_reply') }}</span>
        <Badge v-if="row.mentions" size="sm" theme="blue" :label="w('inbox.mention')" />
      </span>
    </span>
  </router-link>
</template>

<script setup>
import { computed } from 'vue'
import { Avatar, Badge } from 'frappe-ui'
import { themeOf } from '../../frame.js'
import { useMode } from '../../mode.js'
import { clockTime, stampTime } from '../../sections/util.js'
import { wordsFor } from '../words.js'
import { countsLine, lineOf } from './store.js'

// One inbox row (canvas "Discussion inbox", frame 4): the room, its newest line (who and the first line), Needs a
// reply and "@ you" for staff, the time, and "3 new · 2 in threads" (D-414). The portal's rows use it without the
// staff flags, which the server never sends a client; their time names the date, never "today" (D-354).
const props = defineProps({
  row: { type: Object, required: true },
  to: { type: [Object, String], required: true },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  portal: Boolean,
})
const w = wordsFor(useMode(), props.portal)
const line = computed(() => lineOf(props.row, w))
const counts = computed(() => countsLine(props.row, w))
const when = computed(() => (props.portal ? stampTime : clockTime)(props.row.last?.creation))
const label = computed(() => [props.title, props.subtitle, counts.value, props.row.needs_reply ? w('inbox.needs_reply') : '',
  props.row.mentions ? w('inbox.mention_aria') : '', props.row.waiting?.text || '', line.value.who ? `${line.value.who}: ${line.value.text}` : line.value.text]
  .filter(Boolean).join(', '))
</script>
