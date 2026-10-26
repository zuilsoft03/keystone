<template>
  <section v-if="card" :aria-label="card.title" class="mt-2 flex w-[420px] max-w-full flex-col gap-1.5 rounded-5 border border-outline-gray-2 bg-surface-base p-3"
    :data-testid="`${prefix}approval`" :data-state="card.state" :data-request="card.request">
    <div class="flex items-center gap-1.5 text-xs text-ink-gray-7">
      <span class="lucide-square-check size-3.5 flex-none" aria-hidden="true" />
      <span class="min-w-0 truncate">{{ w('approval.label') }}</span>
      <span v-if="badge" class="ml-auto flex-none rounded-full px-2 py-0.5 text-xs font-medium" :class="look[1]" :data-testid="`${prefix}approval-badge`">{{ badge }}</span>
    </div>
    <p class="m-0 break-words text-sm font-medium text-ink-gray-9"><span v-if="card.reference && card.reference !== card.title" class="font-normal text-ink-gray-7" :data-testid="`${prefix}approval-reference`">{{ card.reference }} · </span><span :data-testid="`${prefix}approval-title`">{{ card.title }}</span></p>
    <p v-if="due" class="m-0 text-xs text-ink-gray-7" :data-testid="`${prefix}approval-due`">{{ due }}</p>
    <div class="flex items-start gap-2">
      <p class="m-0 flex min-w-0 flex-1 items-start gap-2 text-sm text-ink-gray-9" :data-testid="`${prefix}approval-state`">
        <span class="mt-px grid size-[18px] flex-none place-items-center rounded-full" :class="look[1]" aria-hidden="true"><span :class="look[0]" class="size-3" /></span>
        <span class="min-w-0 flex-1 break-words">{{ card.text }}</span>
      </p>
      <!-- Open goes to the approval sheet (a client) or the request page (staff): a card never carries an approve control (§3.14). -->
      <RouterLink v-if="target" :to="target" class="inline-flex h-7 flex-none items-center rounded-4 bg-surface-gray-2 px-2.5 text-sm font-medium text-ink-gray-8 no-underline hover:bg-surface-gray-3 max-md:h-12 max-md:min-w-12 max-md:justify-center"
        :data-testid="`${prefix}approval-open`">{{ w('approval.open') }}</RouterLink>
    </div>
  </section>
</template>

<script setup>
import { computed, inject } from 'vue'
import { RouterLink } from 'vue-router'
import { requestRoute } from '../../../approvals/staff/request.js'
import { approvalLink, dayText } from '../../../approvals/terms.js'
import { useMode } from '../../../mode.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'

// The approval card (approvals design §3.12, §3.14; P3-78, P3-79): one card per request in the Client room, read again on every
// page, so its state line changes in place. It draws what the server's part gives this reader (discuss/parts/approval.py,
// approvals/card.py): the record's title and reference, the due date and the state line in words. It has no approve button.
// A mention never approves; the approval sheet is the one place to answer, and Open leads there.
const props = defineProps({ items: { type: [Array, Object], default: null }, message: Object, portal: Boolean, prefix: { type: String, default: '' } })
const w = wordsFor(useMode(), props.portal)
const host = inject(HOST_KEY, null)
const card = computed(() => (props.items && typeof props.items === 'object' && !Array.isArray(props.items) ? props.items : null))
// [icon, tone] per state of approvals.card.state; a state the screen does not know is drawn as a quiet clock.
const GRAY = 'bg-surface-gray-2 text-ink-gray-7'
const AMBER = 'bg-surface-amber-2 text-ink-amber-8'
const GREEN = 'bg-surface-green-2 text-ink-green-8'
const LOOK = {
  waiting: ['lucide-clock', AMBER], returned: ['lucide-rotate-ccw', AMBER], approved: ['lucide-check', GREEN], recorded: ['lucide-check', GREEN],
  disputed: ['lucide-circle-alert', 'bg-surface-red-2 text-ink-red-8'], replaced: ['lucide-x', GRAY], voided: ['lucide-x', GRAY],
}
const look = computed(() => LOOK[card.value?.state] || ['lucide-clock', GRAY])
const badge = computed(() => (card.value?.state in LOOK ? w(`approval.state.${card.value.state}`) : ''))
const due = computed(() => (card.value?.due_date ? w('approval.due', { date: dayText(card.value.due_date) }) : ''))

// A client opens the sheet in the portal. A staff member opens the request page (P3-80, O3). The preview opens nothing.
const target = computed(() => {
  const c = card.value
  if (!c?.route || !host || host.viewer === 'preview') return null
  if (host.viewer === 'client') return { name: 'portal-project', params: { project: c.route.project }, query: approvalLink(c.route.request).query }
  return requestRoute(c.route.project, c.route.request)
})
</script>
