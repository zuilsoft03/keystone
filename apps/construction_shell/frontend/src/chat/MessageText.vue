<template>
  <div class="text-p-base mt-0.5 whitespace-pre-wrap break-words text-ink-gray-9" :data-testid="`${prefix}text`">
    <template v-for="(p, i) in pieces" :key="i">
      <span v-if="p.type === 'text'">{{ p.text }}</span>
      <span v-else-if="p.type === 'mention'" :class="[CHIP, p.item ? (mine(p.item) ? MINE : OTHER) : NEUTRAL]"
        :title="p.item && mine(p.item) ? w('mentions.you') : undefined" :data-testid="`${prefix}mention-chip`" :data-mine="p.item && mine(p.item) ? 'true' : undefined"
        :data-user="p.item?.user">@{{ p.item ? p.item.name : w('mentions.someone') }}</span>
      <!-- P3-79 (§3.14): an approval's chip reads reference, title and status, and a client's opens the approval sheet. It never approves. -->
      <RouterLink v-else-if="p.item && !hidden(p.item) && approvalTo(p.item)" :to="approvalTo(p.item)" :class="[CHIP, OTHER_REF, 'no-underline hover:bg-surface-gray-3']"
        :data-testid="`${prefix}ref-chip`" data-kind="approval">#{{ chipText(p.item) }}<span class="ml-1 text-xs font-normal text-ink-gray-7">{{ chipState(p.item) }}</span></RouterLink>
      <span v-else :class="[CHIP, p.item && !hidden(p.item) ? OTHER_REF : NEUTRAL]" :data-testid="`${prefix}ref-chip`" :data-neutral="p.item && !hidden(p.item) ? undefined : 'true'"
        :data-kind="p.item?.doctype === 'Approval Request' ? 'approval' : undefined">{{
        p.item && !hidden(p.item) ? '#' + chipText(p.item) : w('refs.unavailable') }}<span v-if="p.item && !hidden(p.item) && chipState(p.item)" class="ml-1 text-xs font-normal text-ink-gray-7">{{ chipState(p.item) }}</span></span>
    </template>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { RouterLink } from 'vue-router'
import { boot } from '../boot.js'
import { useMode } from '../mode.js'
import { HOST_KEY } from './host.js'
import { approvalState, hiddenInSimple, openTarget } from './parts/refs/cards.js'
import { parse } from './tokens.js'
import { wordsFor } from './words.js'

// A message's text with its mentions and tags drawn as chips (P3-66, design §3.4, §3.5; canvas "The composer": 3 and 4).
// The text holds tokens (@[u:1], #[r:1]); the server's chips give each one's name or title for this reader. A token with
// no chip is the neutral chip, never its token, and your own mention is drawn stronger. Everything is drawn with
// {{ }}, so a name or a title is never markup. Simple mode shows only what it offers, as the cards do (rule 13).
const props = defineProps({ text: { type: String, default: '' }, parts: { type: Object, default: () => ({}) }, portal: Boolean, prefix: { type: String, default: '' } })
const mode = useMode()
const w = wordsFor(mode, props.portal)
const CHIP = 'inline rounded-3 px-0.5 font-medium'
const OTHER = 'bg-surface-blue-2 text-ink-blue-8'
const MINE = 'bg-surface-blue-6 text-ink-base'
const OTHER_REF = 'bg-surface-gray-2 text-ink-gray-9'
const NEUTRAL = 'bg-surface-gray-2 text-ink-gray-7'
const pieces = computed(() => parse(props.text, { mentions: props.parts?.mentions, refs: props.parts?.refs }))
const mine = (item) => Boolean(boot.user) && item.user === boot.user
const hidden = (item) => mode.value !== 'advanced' && hiddenInSimple(item)
// An approval is known by its reference (VO-0007) and shows its status; only a stored one has a name to open (an unsent message's has not).
const host = inject(HOST_KEY, null)
const isApproval = (item) => item.doctype === 'Approval Request'
const chipText = (item) => (isApproval(item) && item.number ? `${item.number} ${item.title}` : item.title)
const chipState = (item) => (isApproval(item) && item.state ? w(`approval.state.${approvalState(item.state)}`) : '')
const approvalTo = (item) => (isApproval(item) && item.name && host ? openTarget(item, { viewer: host.viewer, project: host.project })?.to : null)
</script>
