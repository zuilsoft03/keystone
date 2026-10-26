<template>
  <div class="flex flex-col gap-3.5" data-testid="approval-sheet" :data-can-answer="String(sheet.can_answer)" :data-status="sheet.status">
    <!-- SLOT notice (S2): refusal banners and "Must reset password before approving", above the terms. -->
    <slot name="notice" :sheet="sheet" />
    <!-- A confirmed approver who must reset their password hears it here, before pressing anything; once the flow is open its
         stopped step says it (so the sentence shows once). The preview forces can_answer false, so it never shows there. -->
    <p v-if="sheet.can_answer && sheet.must_reset && !step" role="status" class="m-0 flex items-start gap-2 rounded-4 bg-surface-gray-2 px-3 py-2.5 text-base text-ink-gray-9" data-testid="approval-must-reset">
      <span class="lucide-info mt-0.5 size-4 flex-none text-ink-gray-7" aria-hidden="true" />{{ sheet.must_reset }}
    </p>

    <section class="flex items-start gap-3 rounded-5 border border-outline-gray-2 bg-surface-gray-1 p-3" :aria-label="sheet.title" data-testid="approval-terms">
      <span class="grid size-9 flex-none place-items-center rounded-4" :class="look[1]" aria-hidden="true"><span :class="look[0]" class="size-4" /></span>
      <div class="min-w-0 flex-1">
        <div class="text-xs text-ink-gray-7" data-testid="approval-kind-line">{{ kind }} · {{ refOf(sheet) }}<template v-if="decision && sheet.terms.category"> · {{ sheet.terms.category }}</template><template v-else-if="rev"> · rev {{ rev }}</template></div>
        <div class="break-words text-base font-semibold text-ink-gray-9" data-testid="approval-title">{{ sheet.title }}</div>
        <div v-if="chipRows.length" class="mt-1.5 flex flex-wrap gap-2">
          <span v-for="[k, v] in chipRows" :key="k" class="inline-flex flex-col gap-0.5 rounded-4 border border-outline-gray-2 bg-surface-base px-3 py-2" data-testid="approval-chip">
            <span class="text-xs text-ink-gray-7">{{ k }}</span><strong class="text-base font-semibold text-ink-gray-9">{{ v }}</strong>
          </span>
        </div>
        <div v-if="decision && sheet.due_date" class="mt-1 text-sm text-ink-gray-8" data-testid="approval-due">{{ w('due', { date: dayText(sheet.due_date) }) }}</div>
      </div>
    </section>

    <p v-if="sheet.terms.description" class="m-0 whitespace-pre-wrap text-sm text-ink-gray-8" data-testid="approval-description">{{ sheet.terms.description }}</p>

    <Options v-if="decision" :model-value="option" :request="sheet.request" :rows="options" :files="sheet.files" :pick="sheet.can_answer && sheet.status === 'Open'" :w="w"
      @update:model-value="(key) => $emit('update:option', key)" />

    <!-- the frozen copy the client is approving: its picture through the approval-copy preview, and Open (the file itself) -->
    <div v-for="f in decision ? [] : sheet.files" :key="f.key" class="flex items-center gap-3 rounded-5 border border-outline-gray-2 p-2.5" data-testid="approval-file">
      <Picture :request="sheet.request" :file-key="f.key" :name="f.name" :alt="f.name" box="size-16 flex-none rounded-3" icon="lucide-file-text" />
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm font-medium text-ink-gray-9">{{ f.name }}</div>
        <div class="text-xs text-ink-gray-7">{{ w('exact_file', { size: sizeText(f.size) }) }}</div>
        <!-- The file endpoint writes an "opened" event as the signed-in user: the staff preview (T31 writes nothing) draws no link to it; its picture above is the preview's -->
        <Button v-if="!preview" class="mt-2 max-md:!h-12" variant="subtle" size="md" icon-left="lucide-external-link" :label="w('open')" :href="f.url" data-testid="approval-file-open" />
      </div>
    </div>

    <dl v-if="details.length" class="m-0 grid grid-cols-[110px_1fr] gap-x-3 gap-y-2 sm:grid-cols-[150px_1fr]">
      <template v-for="[k, v] in details" :key="k"><dt class="text-sm text-ink-gray-7">{{ k }}</dt><dd class="m-0 whitespace-pre-line text-sm text-ink-gray-9">{{ v }}</dd></template>
    </dl>

    <div v-if="sheet.note" class="border-l-[3px] border-outline-gray-4 bg-surface-gray-1 px-3 py-2.5 text-sm text-ink-gray-9" data-testid="approval-note">
      <div class="text-xs text-ink-gray-7">{{ w('team_note') }}</div>{{ sheet.note }}
    </div>

    <p class="m-0 flex items-center gap-2 text-sm text-ink-gray-8" data-testid="approval-who">
      <span class="size-4 flex-none" :class="open ? 'lucide-shield-check text-ink-green-7' : 'lucide-info text-ink-gray-6'" aria-hidden="true" />{{ who }}
    </p>

    <!-- SLOT flow (S2): the answering flow, drawn while `step` is set ('review' or 'return'): the agreement, the password
         step, the signing panel with its location choice, the refusals and the result. It owns its own buttons, so the
         footer below is not drawn then (until a flow is given, the buttons stay and only set the step). Slot props: sheet, option (the picked option's key), step, setStep(step).
         Reload (cc_approval_changed) updates `sheet` in place and keeps this slot mounted, so typed text stays. -->
    <slot v-if="step && $slots.flow" name="flow" :sheet="sheet" :option="option" :step="step" :set-step="setStep" />
    <footer v-else class="flex flex-wrap items-center justify-end gap-2 border-t border-outline-gray-1 pt-3" data-testid="approval-actions">
      <template v-if="sheet.can_answer && open">
        <span v-if="needsOption" class="mr-auto text-xs text-ink-gray-7" data-testid="approval-choose">{{ w('choose_option') }}</span>
        <Button variant="subtle" size="md" class="max-md:!h-12" :label="w('return')" data-testid="approval-return" @click="setStep('return')" />
        <Button variant="solid" theme="blue" size="md" class="max-md:!h-12" :label="w('review_sign')" :disabled="needsOption" data-testid="approval-review" @click="setStep('review')" />
      </template>
      <template v-else>
        <Button v-if="open && canMessage" variant="subtle" size="md" class="max-md:!h-12" :label="w('message_team')" data-testid="approval-message" @click="$emit('message')" />
        <Button variant="subtle" size="md" class="max-md:!h-12" :label="w('close')" data-testid="approval-close" @click="$emit('close')" />
      </template>
    </footer>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Button } from 'frappe-ui'
import { HOST_KEY } from '../chat/host.js'
import { useMode } from '../mode.js'
import Options from './Options.vue'
import Picture from './Picture.vue'
import { chips, dateText, dayText, isDecision, kindWord, names, optionRows, refOf, revOf, sizeText, whenText } from './terms.js'

// The approval sheet's read views (design §3.5 item 1, §12; ApprovalDecide boards 1, 2 and 7): the terms, the frozen copy
// or the Decision's options with pictures, the due date, the team's note and who can approve. It draws one `sheet`
// (approvals.answer.sheet) and holds no state of its own: the picked option and the step are the parent's (v-model), so
// the answering flow (S2) and a reload of the sheet keep them. Nothing here answers; "Review and sign" and "Return with
// a reason" only set the step.
const props = defineProps({
  sheet: { type: Object, required: true },
  option: { type: String, default: '' },
  step: { type: String, default: '' },
  w: { type: Function, required: true },
  canMessage: Boolean, // Discussion is on: a contact who cannot approve may message the team
})
const emit = defineEmits(['update:option', 'update:step', 'close', 'message'])
const mode = useMode()
const preview = Boolean(inject(HOST_KEY, null)?.readOnly) // T31: the staff preview opens no file through the endpoint that records an open
const setStep = (step) => emit('update:step', step)
const decision = computed(() => isDecision(props.sheet.terms))
const open = computed(() => props.sheet.status === 'Open')
const needsOption = computed(() => decision.value && !props.option)
const kind = computed(() => kindWord(props.sheet.kind, mode.value))
const rev = computed(() => revOf(props.sheet))
const options = computed(() => optionRows(props.sheet.terms, props.w))
const chipRows = computed(() => chips(props.sheet.terms, props.w))
const look = computed(() => (decision.value ? ['lucide-list-checks', 'bg-surface-green-2 text-ink-green-8']
  : props.sheet.terms.total !== undefined ? ['lucide-file-diff', 'bg-surface-amber-2 text-ink-amber-8'] : ['lucide-file-text', 'bg-surface-blue-2 text-ink-blue-8']))
// Due (a Decision's is in the summary) and the lines of a priced change, as the frozen terms hold them
const details = computed(() => {
  const rows = []
  const lines = (props.sheet.terms.lines || []).map((l) => l.description).filter(Boolean)
  if (lines.length) rows.push([props.w('line_changes'), lines.join('\n')])
  if (!decision.value && props.sheet.due_date) rows.push([props.w('due_label'), dayText(props.sheet.due_date)])
  return rows
})
// The sentence under the terms: who can answer, or how it ended
const who = computed(() => {
  const s = props.sheet
  if (s.status === 'Superseded') return props.w('replaced')
  if (s.status === 'Voided') return props.w('voided')
  if (!open.value) return props.w(s.status === 'Returned' ? 'returned_other' : 'approved_other', { name: s.decided?.by || '', when: whenText(s.decided?.at) || dateText(s.decided?.at) })
  const people = names(s.approvers, s.can_answer ? 'and' : 'or')
  return s.can_answer ? props.w('can_approve', { names: people }) : props.w(people ? 'waiting_for' : 'waiting_for_any', { names: people })
})
</script>
