<template>
  <section class="cw-card overflow-hidden" :aria-label="row.title" data-testid="approval-waiting" :data-request="row.name">
    <div class="flex flex-wrap items-start gap-3 px-4 pb-2.5 pt-3.5">
      <span class="grid size-9 flex-none place-items-center rounded-4" :class="look[1]" aria-hidden="true"><span :class="look[0]" class="size-4" /></span>
      <div class="min-w-0 flex-[1_1_240px]">
        <div class="flex flex-wrap items-center gap-2 text-xs text-ink-gray-7">
          {{ kind }}<span aria-hidden="true">·</span><span class="font-medium text-ink-gray-8" data-testid="approval-reference">{{ row.reference }}</span>
          <Badge theme="amber" size="sm" :label="w('badge_waiting')" />
        </div>
        <div class="mt-0.5 break-words text-lg-semibold text-ink-gray-9" data-testid="approval-title">{{ row.title }}</div>
      </div>
      <div v-if="row.due_date" class="flex items-center gap-1.5 text-sm text-ink-gray-8" data-testid="approval-due">
        <span class="lucide-calendar size-4 text-ink-gray-6" aria-hidden="true" />{{ w('due', { date: dayText(row.due_date) }) }}
      </div>
    </div>
    <div class="flex flex-col gap-2.5 px-4 pb-3">
      <div v-if="chipRows.length" class="flex flex-wrap gap-2">
        <span v-for="[k, v] in chipRows" :key="k" class="rounded-4 bg-surface-gray-2 px-2.5 py-1.5 text-sm text-ink-gray-9" data-testid="approval-chip">
          <span class="text-ink-gray-7">{{ k }}</span> <strong class="font-semibold">{{ v }}</strong>
        </span>
      </div>
      <Options v-if="decision" v-model="picked" :request="row.name" :rows="options" :files="row.files" :pick="!preview" :w="w" />
      <p v-if="row.note" class="m-0 text-sm text-ink-gray-8"><strong class="font-semibold">{{ w('team_note') }}</strong> {{ row.note }}</p>
    </div>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-2.5">
      <router-link v-if="link.sheet" :to="open" class="inline-flex min-h-12 items-center text-sm md:min-h-0" data-testid="approval-open">{{ link.label }}</router-link>
      <a v-else :href="link.href" target="_blank" rel="noopener" class="inline-flex min-h-12 items-center text-sm md:min-h-0" data-testid="approval-open">{{ link.label }}</a>
      <router-link v-if="comments" :to="{ query: { tab: 'discuss' } }" class="inline-flex min-h-12 items-center text-sm md:min-h-0" data-testid="approval-comments">{{ w('comments') }}</router-link>
      <span v-if="needsOption && !preview" class="text-xs text-ink-gray-7" data-testid="approval-choose">{{ w('choose_option') }}</span>
      <span v-if="!preview" class="ml-auto flex flex-wrap gap-2">
        <Button variant="subtle" size="md" class="max-md:!h-12" :label="w('return')" :route="approvalLink(row.name, '', 'return')" data-testid="approval-return" />
        <Button variant="solid" theme="blue" size="md" class="max-md:!h-12" :label="w('approve')" :disabled="needsOption"
          :route="needsOption ? undefined : approvalLink(row.name, picked, 'review')" data-testid="approval-approve" />
      </span>
    </div>
  </section>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { HOST_KEY } from '../chat/host.js'
import { useMode } from '../mode.js'
import Options from './Options.vue'
import { approvalLink, chips, dayText, isDecision, kindWord, openLink, optionRows } from './terms.js'

// One request waiting for this approver (PortalApprovals, approvals design §3.12): what it is, what it costs or takes (or
// a Decision's options with pictures), the team's note, a link to the exact version, and the buttons. Approve and Return
// only open the sheet, on its signing step or its reason step below the terms (the sheet's own first button is "Review
// and sign", design §12, accepted); a Decision's Approve stays disabled with "Choose an option to approve it." until an
// option is picked. Nothing here answers.
const props = defineProps({
  row: { type: Object, required: true },
  w: { type: Function, required: true },
  comments: Boolean, // Discussion is on: Comments goes to it
})
const mode = useMode()
const preview = Boolean(inject(HOST_KEY, null)?.readOnly) // T31: the staff preview of the portal draws no Approve or Return
const picked = ref('')
const decision = computed(() => isDecision(props.row.terms))
const needsOption = computed(() => decision.value && !picked.value)
const options = computed(() => optionRows(props.row.terms, props.w))
const chipRows = computed(() => chips(props.row.terms, props.w))
const kind = computed(() => kindWord(props.row.kind, mode.value))
// A card's file link is the endpoint that records an "opened" event as the signed-in user: the preview (T31) opens the sheet instead.
const link = computed(() => {
  const l = openLink(props.row, props.w)
  return preview && l.href ? { label: props.w('open_details'), sheet: true } : l
})
const open = computed(() => approvalLink(props.row.name, picked.value))
// [icon, tone]: a Decision, a priced record, any other record
const look = computed(() => (decision.value ? ['lucide-list-checks', 'bg-surface-green-2 text-ink-green-8']
  : props.row.terms?.total !== undefined ? ['lucide-file-diff', 'bg-surface-amber-2 text-ink-amber-8'] : ['lucide-file-text', 'bg-surface-blue-2 text-ink-blue-8']))
</script>
