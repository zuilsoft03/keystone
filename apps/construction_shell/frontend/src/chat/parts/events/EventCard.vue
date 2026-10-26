<template>
  <div v-if="view" role="note" class="relative my-0.5 flex items-center gap-2 rounded-4 bg-surface-gray-2 px-2.5 py-1.5 text-[13px] text-ink-gray-8 max-md:min-h-12"
    :data-testid="`${prefix}event`" :data-event="item.event">
    <span :class="view.icon" class="size-[15px] flex-none text-ink-gray-7" aria-hidden="true" />
    <span class="min-w-0 flex-1 break-words" :data-testid="`${prefix}event-line`">{{ sentence[0] }}<template v-if="view.title"><template v-if="view.target"><a v-if="view.target.href" :href="view.target.href" target="_blank" rel="noopener" :class="LINK" :data-testid="`${prefix}event-open`">{{ view.title }}</a><router-link v-else :to="view.target.to" :class="LINK" :data-testid="`${prefix}event-open`">{{ view.title }}</router-link></template><strong v-else class="font-semibold" :data-testid="`${prefix}event-title`">{{ view.title }}</strong></template>{{ sentence[1] }}</span>
    <time v-if="time" :datetime="datetime" class="flex-none text-xs text-ink-gray-7" :data-testid="`${prefix}event-time`">{{ time }}</time>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { useMode } from '../../../mode.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { eventView } from './view.js'

// A design event under a System message (P3-69, design §3.9; canvas "Message cards": System events and send states): one quiet
// line with the record's title in bold, as the title opens the record for this reader. A record this reader may not see by
// name gets the neutral word and no link. The line is a plain note: it is not a live region (the chat has one, polite). The
// message's time is at its right, as the canvas draws it (MessageItem draws no header for these). On a phone the title's link
// covers the whole line (a 48 px target).
const props = defineProps({
  item: { type: Object, required: true }, portal: Boolean, prefix: { type: String, default: '' }, actor: { type: String, default: '' },
  time: { type: String, default: '' }, datetime: { type: String, default: '' },
})
const host = inject(HOST_KEY)
const mode = useMode()
const w = wordsFor(mode, props.portal)
const LINK = 'font-semibold text-ink-gray-8 no-underline hover:underline max-md:after:absolute max-md:after:inset-0'
const MARK = '\u0001' // stands for {title}: the sentence is cut there, so the title is drawn as its own element with {{ }}
const view = computed(() => eventView(props.item, {
  mode: mode.value, portal: props.portal, viewer: host?.viewer || 'staff', project: host?.project || '', actor: props.actor,
}))
const sentence = computed(() => w(view.value.word, { actor: props.actor, title: MARK }).split(MARK))
</script>
