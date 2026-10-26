<template>
  <section class="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto [&>*]:shrink-0 bg-surface-base px-6 py-5 max-md:px-3" :aria-label="w('tab_title')" data-testid="request-page">
    <router-link :to="tabRoute(project)" class="inline-flex min-h-12 items-center text-sm text-ink-gray-7 no-underline hover:text-ink-gray-9 md:min-h-0" data-testid="request-back">← {{ w('rq_back') }}</router-link>
    <p v-if="error" class="m-0 text-ink-red-7" role="alert" data-testid="request-error">{{ error }}</p>
    <p v-else-if="!page" class="m-0 text-ink-gray-7" role="status">{{ w('tab_loading') }}</p>
    <template v-else>
      <div class="flex flex-wrap items-start gap-3">
        <div class="min-w-0 flex-[1_1_320px]">
          <div class="flex flex-wrap items-center gap-1.5 text-sm text-ink-gray-7">
            <span>{{ approvalWord(`kind.${page.kind}`, { mode }) }} · {{ page.reference }}</span>
            <Badge :label="w(`st_${page.overdue ? 'overdue' : page.state}`)" :theme="page.overdue || page.state === 'disputed' ? 'red' : page.state === 'approved' || page.state === 'recorded' ? 'green' : 'amber'" data-testid="request-state" />
          </div>
          <h1 class="m-0 mt-1 text-2xl font-semibold text-ink-gray-9" data-testid="request-title">{{ page.title }}</h1>
          <p class="m-0 mt-1 text-xs text-ink-gray-7">{{ w('rq_requested', { name: page.requested_by, when: whenText(page.requested_at) }) }}<template v-if="page.due_date"> · {{ w('rq_due', { date: dayText(page.due_date) }) }}</template></p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button v-if="canVoid(page) || page.internal?.waiting" variant="outline" class="max-md:!h-12" :label="w('act_nudge')" :disabled="busy" data-testid="act-nudge" @click="nudge" />
          <Button v-if="canVoid(page)" variant="outline" class="max-md:!h-12" :label="w('act_void')" :disabled="busy" data-testid="act-void" @click="voiding = true" />
        </div>
      </div>
      <p v-if="notice" class="m-0 text-sm text-ink-green-8" role="status" data-testid="request-notice">{{ notice }}</p>
      <p v-for="l in refusal" :key="l" class="m-0 text-sm text-ink-red-8" role="alert" data-testid="request-refusal">{{ l }}</p>

      <!-- what happened to it -->
      <div v-if="story.length" class="flex flex-col gap-1 rounded-5 border border-outline-gray-2 p-3" data-testid="request-story">
        <p v-for="s in story" :key="s" class="m-0 text-sm text-ink-gray-9">{{ s }}</p>
      </div>

      <!-- the next step (ApprovalNextSteps) -->
      <div v-if="steps.length || closing || canRecord(page) || canDispute(page)" class="flex flex-col gap-2 rounded-5 border border-outline-gray-2 p-3" data-testid="next-steps">
        <h2 class="m-0 text-xs font-semibold uppercase tracking-wide text-ink-gray-7">{{ w('rq_next') }}</h2>
        <div class="flex flex-wrap items-start gap-2">
          <div v-for="(s, i) in steps" :key="s.key" class="flex flex-col gap-1">
            <Button :variant="i === 0 ? 'solid' : 'outline'" :theme="i === 0 ? 'blue' : 'gray'" class="max-md:!h-12" :label="s.key === 'internal_step' ? w('rq_step_open', { step: s.label }) : w(`step_${s.key}`)" :disabled="!s.enabled || busy"
              :data-testid="`step-${s.key}`" @click="run(s)" />
            <router-link v-if="!s.enabled && s.fix === 'approvers'" :to="settingsRoute" class="text-xs text-ink-blue-link" data-testid="step-fix">{{ w('gate_fix_approvers') }}</router-link>
          </div>
          <Button v-if="closing" variant="outline" class="max-md:!h-12" :label="w('step_close_request')" :disabled="busy" data-testid="step-close_request"
            @click="act(() => post('api.void', { request: page.request, reason: CLOSE_REASON, note: '' }), '')" />
          <Button v-if="canRecord(page)" :variant="steps.length ? 'outline' : 'solid'" :theme="steps.length ? 'gray' : 'blue'" class="max-md:!h-12" :label="w('act_record')" data-testid="act-record" @click="recording = true" />
          <Button v-if="canDispute(page)" variant="outline" class="max-md:!h-12" :label="w('act_dispute')" data-testid="act-dispute" @click="disputing = true" />
        </div>
        <p v-for="s in steps.filter((x) => !x.enabled && x.reason)" :key="s.key" class="m-0 text-xs text-ink-gray-7" data-testid="step-reason">{{ s.reason }}</p>
      </div>

      <!-- P3-82: the internal steps, who does each and when (design 14.6) -->
      <section v-if="page.internal" class="cw-card flex flex-col gap-2 p-4" data-testid="request-steps">
        <h2 class="m-0 text-base font-semibold text-ink-gray-9">{{ w('rq_steps') }}</h2>
        <p v-if="page.internal.returned" class="m-0 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="steps-returned">
          {{ w('rq_step_returned', { name: page.internal.returned.by, step: page.internal.returned.step, when: whenText(page.internal.returned.at) }) }}<template v-if="page.internal.returned.reason">: {{ page.internal.returned.reason }}</template>
        </p>
        <ol class="m-0 flex list-none flex-col gap-2 p-0">
          <li v-for="s in page.internal.steps" :key="s.no" class="flex flex-col gap-0.5" data-testid="request-step" :data-state="stepState(s)">
            <span class="flex flex-wrap items-center gap-x-2 text-sm text-ink-gray-9">
              <span class="size-4 flex-none" :class="s.done ? 'lucide-circle-check text-ink-green-7' : s.current ? 'lucide-circle-dot text-ink-blue-7' : 'lucide-circle text-ink-gray-5'" aria-hidden="true" />
              <span class="font-medium">{{ s.no }}. {{ s.name }}</span>
              <span class="text-xs text-ink-gray-7">{{ w(s.position === 'after' ? 'rq_step_after' : 'rq_step_before') }}</span>
              <span v-if="s.current && s.due" class="text-xs text-ink-gray-7">{{ w('rq_step_due', { date: dayText(s.due) }) }}</span>
            </span>
            <span class="pl-6 text-sm text-ink-gray-7">{{ s.people.join(', ') }}</span>
            <span v-for="b in s.by" :key="b.name + b.at" class="pl-6 text-sm text-ink-gray-9" data-testid="step-by">
              {{ w('rq_step_by', { name: b.name, when: whenText(b.at) }) }}<span v-if="b.same_person" class="ml-2 rounded-4 bg-surface-amber-1 px-1.5 text-xs text-ink-amber-8" data-testid="same-person">{{ w('same_person') }}</span>
            </span>
          </li>
        </ol>
      </section>

      <!-- the terms and the frozen files -->
      <section class="cw-card flex flex-col gap-2 p-4" data-testid="request-terms">
        <h2 class="m-0 text-base font-semibold text-ink-gray-9">{{ w('rq_terms') }}</h2>
        <div v-if="chipRows.length" class="flex flex-wrap gap-4 text-sm text-ink-gray-9">
          <span v-for="[label, text] in chipRows" :key="label"><span class="text-ink-gray-7">{{ label }}</span> {{ text }}</span>
        </div>
        <ul v-if="options.length" class="m-0 flex list-none flex-col gap-1 p-0">
          <li v-for="o in options" :key="o.key" class="flex flex-wrap gap-x-3 text-sm text-ink-gray-9" data-testid="request-option">
            <span class="font-medium">{{ o.label }}</span><span class="text-ink-gray-7">{{ o.cost }} · {{ o.time }}</span>
          </li>
        </ul>
        <p v-if="page.note" class="m-0 text-sm text-ink-gray-8"><span class="text-ink-gray-7">{{ w('rq_note') }}:</span> {{ page.note }}</p>
        <h3 class="m-0 mt-1 text-sm font-semibold text-ink-gray-9">{{ w('rq_files') }}</h3>
        <ul class="m-0 flex list-none flex-col gap-1 p-0">
          <li v-for="f in page.files" :key="f.key" class="text-sm" data-testid="request-file">
            <a :href="f.url" target="_blank" rel="noopener" class="inline-flex min-h-12 items-center text-ink-blue-link md:min-h-0">{{ w('rq_file_line', { name: f.name, rev: f.rev }) }}</a>
            <span class="ml-2 break-all font-mono text-xs text-ink-gray-7">{{ f.shown_sha256.slice(0, 12) }}</span>
          </li>
          <li v-if="!page.files.length" class="text-sm text-ink-gray-7">{{ w('rq_no_files') }}</li>
        </ul>
      </section>

      <!-- the approvers -->
      <section class="cw-card overflow-hidden" data-testid="request-approvers">
        <h2 class="m-0 px-4 py-3 text-base font-semibold text-ink-gray-9">{{ w('rq_approvers') }}</h2>
        <div v-for="a in page.approvers" :key="a.member" class="cw-list-row flex-wrap" data-testid="request-approver">
          <Avatar :label="a.name" size="xl" />
          <div class="min-w-0 flex-[1_1_200px]">
            <div class="truncate text-base text-ink-gray-9">{{ a.name }}</div>
            <div class="text-sm text-ink-gray-7">{{ w(a.agreed ? 'rq_agreed' : 'rq_not_agreed') }}</div>
            <div v-if="a.must_reset" class="text-sm text-ink-amber-8" data-testid="must-reset">{{ w('set_must_reset') }}</div>
          </div>
          <Badge :label="w(a.confirmed ? 'set_state_confirmed' : 'set_state_waiting')" :theme="a.confirmed ? 'green' : 'amber'" />
          <template v-if="page.manager">
            <Button v-if="contactActions({ ...a, approver: true }).reset" variant="outline" class="max-md:!h-12" :label="w('set_send_reset')" :disabled="busy" data-testid="send-reset" @click="act(() => post('credentials.send_reset_link', { project: page.project, member: a.member }), w('set_reset_sent', { to: a.name }))" />
            <Button v-if="contactActions({ ...a, approver: true }).confirm" variant="solid" theme="blue" class="max-md:!h-12" :label="w('set_confirm')" :disabled="busy" data-testid="confirm-approver" @click="act(() => post('api.confirm_approver', { project: page.project, member: a.member }))" />
          </template>
        </div>
      </section>

      <!-- the receipts -->
      <section class="cw-card flex flex-col gap-2 p-4" data-testid="request-receipts">
        <h2 class="m-0 text-base font-semibold text-ink-gray-9">{{ w('rq_receipts') }}</h2>
        <p class="m-0 text-sm text-ink-gray-9" data-testid="receipts-state">{{ w(RECEIPT[page.receipts.state]) }}</p>
        <p v-for="p in page.receipts.people" :key="p.name" class="m-0 text-sm text-ink-gray-7" data-testid="receipt-person">{{ w('rcpt_person', { name: p.name, role: p.role, state: w(`rcpt_state_${p.state}`) }) }}, {{ whenText(p.at) }}</p>
        <div v-if="page.manager && page.receipts.state"><Button variant="outline" class="max-md:!h-12" :label="w('rcpt_resend')" :disabled="busy" data-testid="receipts-resend" @click="act(() => post('receipts.resend', { request: page.request }), w('rcpt_resent'))" /></div>
      </section>

      <!-- the timeline -->
      <section class="cw-card flex flex-col gap-2 p-4" data-testid="request-timeline">
        <h2 class="m-0 text-base font-semibold text-ink-gray-9">{{ w('rq_timeline') }}</h2>
        <ol class="m-0 flex list-none flex-col gap-1.5 p-0">
          <li v-for="(e, i) in page.timeline" :key="i" class="flex flex-wrap gap-x-3 text-sm" data-testid="timeline-row" :data-kind="e.kind">
            <time class="w-28 flex-none text-ink-gray-7">{{ whenText(e.at) }}</time>
            <span class="min-w-0 flex-1 break-words text-ink-gray-9">{{ lineText(e, w) }}<template v-if="e.reason"> · {{ e.reason }}</template></span>
          </li>
        </ol>
      </section>
    </template>

    <StepSheet v-model:open="stepping" :page="page" @done="stepped" />
    <Dialog v-model:open="voiding" size="md" :title="w('void_title')">
      <div class="staff-dialog flex flex-col gap-3" data-testid="void-form">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('void_why') }}
          <select v-model="voidReason" class="form-select w-full py-0 max-md:h-12" data-testid="void-reason">
            <option value="" />
            <option v-for="(key, reason) in VOID_REASONS" :key="reason" :value="reason">{{ w(key) }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('void_note') }}
          <textarea v-model="voidNote" rows="2" maxlength="500" class="form-textarea h-auto w-full" data-testid="void-note" />
        </label>
        <p class="m-0 text-xs text-ink-gray-7">{{ w('void_help') }}</p>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button class="max-md:!h-12" :label="w('ask_cancel')" @click="voiding = false" />
          <Button variant="solid" theme="blue" class="max-md:!h-12" :label="w('void_go')" :disabled="!voidReason || busy" data-testid="void-go"
            @click="act(() => post('api.void', { request: page.request, reason: voidReason, note: voidNote }), '', () => (voiding = false))" />
        </div>
      </template>
    </Dialog>
    <template v-if="page">
      <RecordedForm v-model:open="recording" :page="page" :files="files" @done="recorded" />
      <DisputeForm v-model:open="disputing" :page="page" :files="files" @done="load" />
      <DisputeForm v-model:open="resolving" resolve :page="page" @done="load" />
      <DecisionForm v-model:open="editing" :project="page.project" :name="page.kind === DECISION ? page.subject : ''" @ask="asked" />
      <AskSheet v-model:open="asking" :project="page.project" :doctype="target.doctype" :name="target.name" />
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Avatar, Badge, Button, Dialog } from 'frappe-ui'
import { call, updateDoc } from '../../api.js'
import { useMode } from '../../mode.js'
import { saveConfirming } from '../../sections/util.js'
import { approvalWord, approvalWords, staffWords } from '../words.js'
import { chips, dayText, optionRows, whenText } from '../terms.js'
import AskSheet from './AskSheet.vue'
import DecisionForm from './DecisionForm.vue'
import DisputeForm from './DisputeForm.vue'
import RecordedForm from './RecordedForm.vue'
import StepSheet from './StepSheet.vue'
import { DECISION, SECTION_OF, SENDABLE, refusalLines } from './ask.js'
import { VOID_REASONS, canDispute, canRecord, canVoid, evidenceRoute, lineText, requestRoute, stepsOf, tabRoute } from './request.js'
import { contactActions } from './settings.js'
import { CLOSE_REASON, closeStep, stepState } from './routes.js'

// The request page (P3-80; design §3.12; canvas ApprovalNextSteps): the terms and the frozen files, the approvers with their
// states, the receipts and the timeline, and the next step. Every move is an existing endpoint; the server decides again and
// its refusals are shown as sentences. "Close request" and "Record a note" have no write yet and are not drawn.
const props = defineProps({ project: { type: String, required: true }, request: { type: String, required: true } })
const emit = defineEmits(['changed'])
const router = useRouter()
const mode = useMode()
const w = staffWords(mode)
const aw = approvalWords(mode)
const API = 'construction_core.approvals.'
const RECEIPT = { '': 'rcpt_none', not_sent: 'rcpt_not_sent', sent: 'rcpt_sent', failed: 'rcpt_failed' }
const page = ref(null)
const files = ref([])
const error = ref('')
const refusal = ref([])
const notice = ref('')
const busy = ref(false)
const recording = ref(false)
const disputing = ref(false)
const resolving = ref(false)
const voiding = ref(false)
const voidReason = ref('')
const voidNote = ref('')
const editing = ref(false)
const stepping = ref(false)
const asking = ref(false)
const target = ref({ doctype: '', name: '' })

const steps = computed(() => stepsOf(page.value?.next))
// only a request returned at an internal step can be closed (api.void refuses one the client returned)
const closing = computed(() => Boolean(page.value?.internal?.returned) && closeStep(page.value)?.enabled !== false && Boolean(closeStep(page.value)))
const chipRows = computed(() => (page.value ? chips(page.value.terms, aw) : []))
const options = computed(() => (page.value ? optionRows(page.value.terms, aw) : []))
const settingsRoute = computed(() => ({ name: 'section', params: { project: props.project, section: 'settings' } }))
// What happened to the request, said once at the top: the answer, a dispute, a void, a replacement.
const story = computed(() => {
  const p = page.value
  if (!p) return []
  const a = p.answer
  return [
    a && a.kind === 'approved' && w('rq_approved', { name: a.by, when: whenText(a.at) }),
    a && a.kind === 'returned' && w('rq_returned', { name: a.by, when: whenText(a.at) }),
    a?.reason && w('rq_reason', { reason: a.reason }),
    p.dispute && w(`rq_dispute_${p.dispute}`),
    p.state === 'voided' && w('rq_void', { reason: p.void_reason }),
    p.state === 'replaced' && w('rq_replaced'),
  ].filter(Boolean)
})

async function load() {
  error.value = ''
  try {
    page.value = await call(API + 'staff.page', { request: props.request })
    emit('changed')
  } catch (e) {
    page.value = null
    error.value = e.message || w('ev_not_found')
  }
}

// The proof files a form offers: the project's files, as the settings offer the contract's.
async function loadFiles() {
  if (files.value.length) return
  try {
    files.value = (await call('construction_shell.api.record_options', { project: props.project })).files
  } catch { /* the forms then show no files, and the server refuses a missing proof */ }
}

const post = (name, args) => call(API + name, args, { post: true })

// One write, then the page again; a refusal shows as sentences.
async function act(send, done = '', after = () => {}) {
  busy.value = true
  refusal.value = []
  notice.value = ''
  try {
    const out = await send()
    after(out)
    notice.value = done
    await load()
    return out
  } catch (e) {
    refusal.value = refusalLines(e.message)
  } finally {
    busy.value = false
  }
}

// A step answered: the page again, and the tab's counts; the sheet shows its own sentence.
const stepped = () => load()
const nudge = () => act(() => post('api.nudge', { request: props.request }), w('act_nudged'))
const recorded = (out) => {
  notice.value = w(out.self_confirm ? 'rec_done_self' : 'rec_done')
  load()
}
const asked = (t) => {
  target.value = t
  editing.value = false
  asking.value = true
}

// "Approve the change": the record's own save into the gated state, with its `modified` so a newer save is refused.
async function approveChange(step) {
  const { kind, subject } = page.value
  const { modified } = await call('frappe.client.get_value', { doctype: kind, filters: { name: subject }, fieldname: 'modified' })
  await saveConfirming((v) => updateDoc(kind, subject, v), { modified, [SENDABLE[kind].field]: step.to[0] }, (m) => window.confirm(m))
}

function run(step) {
  const { kind, subject } = page.value
  if (step.key === 'approve_change') return act(() => approveChange(step), w('step_done_change'))
  if (step.key === 'internal_step') return void (stepping.value = true)
  if (step.key === 'evidence') return router.push(evidenceRoute(props.project, props.request))
  if (step.key === 'open_successor') return router.push(requestRoute(props.project, step.request))
  if (step.key === 'resolve') return void (resolving.value = true)
  if (step.key === 'make_variation') return act(() => post('api.make_variation', { decision: subject }), '', (out) => (notice.value = w('dec_made', { name: out.variation })))
  if (step.key === 'confirm_record') return act(() => post('recorded.confirm', { request: step.request, recorded: step.event }), w('step_done_confirm'))
  if (step.key === 'edit_send_again') {
    if (kind === DECISION) return void (editing.value = true)
    return router.push({ name: 'section', params: { project: props.project, section: SECTION_OF[kind], item: subject } })
  }
}

watch(() => props.request, load, { immediate: true })
watch([recording, disputing], ([a, b]) => (a || b) && loadFiles())
</script>
