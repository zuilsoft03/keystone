<template>
  <div v-if="cards.length" class="mt-1.5 flex flex-col gap-2" :data-testid="`${prefix}ref-cards`">
    <template v-for="c in cards" :key="c.pos">
      <!-- The neutral card: an item the reader cannot read, was removed, or Simple mode does not show. It names nothing. -->
      <div v-if="c.view.neutral" class="flex w-[420px] max-w-full items-center gap-2.5 rounded-5 border border-l-[3px] border-outline-gray-2 border-l-outline-gray-4 bg-surface-gray-1 px-3 py-2.5"
        role="note" :data-testid="`${prefix}ref-card`" data-state="neutral">
        <span class="grid size-8 flex-none place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-7" aria-hidden="true"><span :class="[NEUTRAL_ICON, 'size-4']" /></span>
        <span class="min-w-0 flex-1 text-sm text-ink-gray-7">{{ w('refs.unavailable') }}</span>
      </div>
      <div v-else class="flex w-[420px] max-w-full items-center gap-2.5 rounded-5 border border-l-[3px] border-outline-gray-2 border-l-outline-gray-4 bg-surface-base px-3 py-2.5 max-md:flex-wrap"
        :data-testid="`${prefix}ref-card`" :data-type="c.view.key" data-state="ready">
        <span class="grid size-8 flex-none place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-8" aria-hidden="true"><span :class="[c.view.icon, 'size-4']" /></span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-1.5 text-xs text-ink-gray-7">
            <span>{{ w(`refs.${c.view.key}`) }}</span>
            <Badge v-if="c.view.state" size="sm" :theme="c.view.theme || stateTheme(c.view.stateRaw)" :label="c.view.state" :data-testid="`${prefix}ref-state`" />
          </div>
          <div class="truncate text-base font-medium text-ink-gray-9" :data-testid="`${prefix}ref-title`">{{ c.view.title }}</div>
          <div v-if="c.view.number || c.view.size" class="truncate text-xs text-ink-gray-7">{{ [c.view.number, c.view.size].filter(Boolean).join(' · ') }}</div>
        </div>
        <template v-if="c.target">
          <a v-if="c.target.href" :href="c.target.href" target="_blank" rel="noopener" :class="OPEN" :data-testid="`${prefix}ref-open`">{{ w('refs.open') }}</a>
          <router-link v-else :to="c.target.to" :class="OPEN" :data-testid="`${prefix}ref-open`">{{ w('refs.open') }}</router-link>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Badge } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { stateTheme } from '../../../sections/util.js'
import { HOST_KEY } from '../../host.js'
import { refPositions } from '../../tokens.js'
import { wordsFor } from '../../words.js'
import { NEUTRAL_ICON, cardView, openTarget } from './cards.js'

// The refs part (P3-66, design §3.5; canvas "Message cards": Records from tags): a card under the message for each
// token in its text, drawn for this reader when the message is read. The server sends a card only for an item this
// reader may read now; a token with none draws the neutral card, so an item that is unshared or removed looks the same
// as one that never existed (rule 2). Simple mode hides record numbers and draws what it does not offer as neutral.
const props = defineProps({ items: { type: [Array, Object], default: () => [] }, message: Object, portal: Boolean, prefix: { type: String, default: '' } })
const host = inject(HOST_KEY)
const mode = useMode()
const w = wordsFor(mode, props.portal)
const OPEN = 'inline-flex h-7 flex-none items-center rounded-4 bg-surface-gray-2 px-2.5 text-sm font-medium text-ink-gray-8 no-underline hover:bg-surface-gray-3 max-md:h-12 max-md:min-w-12 max-md:justify-center'
const list = computed(() => (Array.isArray(props.items) ? props.items : [props.items]).filter(Boolean))
const cards = computed(() => {
  const place = host ? { viewer: host.viewer, project: host.project } : { viewer: 'staff', project: '' }
  const positions = refPositions(props.message?.text)
  const wanted = positions.length ? positions : list.value.map((i) => i.pos)
  return wanted.map((pos) => {
    const item = list.value.find((i) => i.pos === pos) || null
    const view = cardView(item, { mode: mode.value, portal: props.portal })
    return { pos, view, target: view.neutral ? null : openTarget(item, place) }
  })
})
</script>
