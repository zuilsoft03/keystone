<template>
  <div v-if="poll" aria-live="off" class="mt-2 flex w-[420px] max-w-full flex-col gap-2 rounded-5 border border-outline-gray-2 bg-surface-base p-3" :data-testid="`${prefix}poll`"
    :data-closed="poll.closed ? 'true' : 'false'" :data-quick="quick ? 'true' : 'false'">
    <div class="flex items-center gap-1.5 text-xs text-ink-gray-7">
      <span class="lucide-chart-bar-big size-3.5 flex-none" aria-hidden="true" />
      <span :data-testid="`${prefix}poll-kind`">{{ kind }}</span>
      <Badge v-if="poll.closed" size="sm" theme="gray" :label="w('polls.closed')" :data-testid="`${prefix}poll-closed`" />
      <span v-else-if="closes" class="ml-auto" :data-testid="`${prefix}poll-closes`">{{ w('polls.closes_at', { when: closes }) }}</span>
    </div>
    <div class="text-base font-semibold text-ink-gray-9" :data-testid="`${prefix}poll-question`">{{ poll.question }}</div>
    <ul role="group" :aria-label="poll.question" class="m-0 flex list-none flex-col gap-2 p-0">
      <li v-for="o in options" :key="o.key">
        <button type="button" :aria-pressed="o.mine ? 'true' : 'false'" :aria-label="o.label" :disabled="!canAct || busy"
          class="relative flex min-h-12 w-full items-center gap-2.5 overflow-hidden rounded-4 border bg-surface-base p-1.5 pr-2.5 text-left disabled:cursor-default max-md:flex-col max-md:items-stretch"
          :class="[o.mine ? 'border-outline-blue-6' : 'border-outline-gray-2', canAct ? 'cursor-pointer hover:bg-surface-gray-1' : '']"
          :data-testid="`${prefix}poll-option`" :data-key="o.key" :data-mine="o.mine ? 'true' : undefined" @click="vote(o.key)">
          <span class="absolute inset-y-0 left-0 bg-surface-blue-1" :style="{ width: `${o.share}%` }" aria-hidden="true" />
          <span v-if="o.picture" class="relative grid size-9 flex-none place-items-center overflow-hidden rounded-3 bg-surface-gray-3 max-md:h-40 max-md:w-full max-md:rounded-4" data-testid="poll-picture">
            <img v-if="o.picture.src" :src="o.picture.src" alt="" class="size-full object-cover" loading="lazy" />
            <span v-else class="lucide-image size-4 text-ink-gray-7 max-md:size-8" aria-hidden="true" />
          </span>
          <span class="relative flex min-w-0 flex-1 flex-col max-md:flex-none max-md:px-1">
            <span class="text-base text-ink-gray-9">{{ o.text }}</span>
            <span v-if="o.voters" class="truncate text-xs text-ink-gray-7" :data-testid="`${prefix}poll-voters`">{{ w('polls.voted_by', { names: o.voters }) }}</span>
          </span>
          <span class="relative flex flex-none items-center gap-1.5 max-md:absolute max-md:right-3 max-md:top-3 max-md:rounded-full max-md:bg-surface-base max-md:px-2 max-md:py-0.5">
            <span v-if="o.mine" class="lucide-check size-4 text-ink-blue-8" aria-hidden="true" />
            <span class="text-sm font-semibold text-ink-gray-8" aria-live="off" :data-testid="`${prefix}poll-votes`">{{ o.votes }}</span>
          </span>
        </button>
      </li>
    </ul>
    <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-gray-7">
      <span :data-testid="`${prefix}poll-foot`">{{ foot }}</span>
      <template v-if="poll.can_close && host.act">
        <Button v-if="!asking" class="ml-auto max-md:!h-12" size="sm" variant="ghost" :label="w('polls.close')" :data-testid="`${prefix}poll-close`" @click="asking = true" />
        <span v-else class="ml-auto inline-flex flex-wrap items-center gap-1.5 text-ink-gray-8" role="group" :aria-label="w('polls.close_ask')">
          <span>{{ w('polls.close_ask') }}</span>
          <Button size="sm" variant="subtle" :label="w('polls.close_yes')" :loading="busy" class="max-md:!h-12" :data-testid="`${prefix}poll-close-yes`" @click="close" />
          <Button size="sm" variant="ghost" :label="w('polls.close_no')" class="max-md:!h-12" @click="asking = false" />
        </span>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { HOST_KEY, ROOM_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { closesText, nextVote, picturesOf, share, voterLine } from './view.js'

// The poll card (design §3.7; canvas "Message cards": Poll, team room and client room). Pressing an option votes at once
// and the server's answer carries the new counts (the room merges it), so the card never waits for a re-read; pressing
// your own choice again takes the vote back; in a poll of several choices each press toggles one. A closed poll shows its
// results and no buttons that act. In a client conversation the card says "Quick poll · not an approval" and the poll is
// named. A voter list is drawn only when the server sends it (a named poll). Counts are not live regions: the room says
// the reader's own change once, politely.
const props = defineProps({ items: { type: [Array, Object], default: null }, message: { type: Object, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const host = inject(HOST_KEY)
const room = inject(ROOM_KEY, null)
const w = wordsFor(useMode(), props.portal)
const busy = ref(false)
const canAct = computed(() => Boolean(poll.value?.can_vote && host.act)) // the staff preview of a portal can press nothing
const asking = ref(false)
const poll = computed(() => (props.items && typeof props.items === 'object' && !Array.isArray(props.items) ? props.items : null))
const quick = computed(() => props.portal || room?.thread?.audience === 'Client')
const closes = computed(() => closesText(poll.value?.closes_on))
const kind = computed(() => {
  if (quick.value) return w('polls.quick')
  return [w('polls.poll'), w(poll.value.multiple ? 'polls.several_choices' : 'polls.one_choice'), w(poll.value.anonymous ? 'polls.anonymous_word' : 'polls.named_word')].join(' · ')
})
const pictures = computed(() => picturesOf(props.message.parts?.attachments))
const options = computed(() => (poll.value?.options || []).map((o, i) => {
  const text = o.text || w('polls.option_n', { n: i + 1 })
  const voters = voterLine(o)
  return { ...o, text, share: share(poll.value, o), voters, picture: o.picture ? pictures.value[o.picture] || { src: '', name: '' } : null,
    label: [text, w(o.votes === 1 ? 'polls.vote_one' : 'polls.votes', { count: o.votes }), o.mine ? w('polls.your_vote') : '', voters ? w('polls.voted_by', { names: voters }) : ''].filter(Boolean).join(', ') }
}))
const foot = computed(() => {
  const p = poll.value
  const people = w(p.people === 1 ? 'polls.person_voted' : 'polls.people_voted', { count: p.people })
  return `${people} · ${w(p.closed ? 'polls.hint_closed' : 'polls.hint_open')}`
})

async function vote(key) {
  if (!canAct.value || busy.value) return
  const keys = nextVote(poll.value, key)
  await run(() => host.act('polls', 'vote', { message: props.message.name, options: keys }), keys.length ? 'polls.said_voted' : 'polls.said_taken_back')
}

async function close() {
  await run(() => host.act('polls', 'close', { message: props.message.name }), 'polls.said_closed')
  asking.value = false
}

async function run(request, said) {
  busy.value = true
  try {
    room?.merge(await request())
    room?.say(w(said))
  } catch (e) {
    room?.fail(e.message)
  } finally {
    busy.value = false
  }
}
</script>
