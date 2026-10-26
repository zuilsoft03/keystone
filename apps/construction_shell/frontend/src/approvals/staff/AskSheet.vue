<template>
  <Dialog v-model:open="shown" size="xl" :title="w('ask_title')">
    <div class="staff-dialog flex flex-col gap-3.5" data-testid="ask-sheet">
      <p v-if="loading" class="m-0 text-sm text-ink-gray-7" role="status">{{ w('ask_loading') }}</p>
      <p v-else-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="ask-load-error">{{ error }}</p>
      <template v-else-if="pre">
        <!-- the preflight: every reason with its fix, or "Ready to send" -->
        <div v-if="pre.ready" class="flex items-center gap-2 rounded-4 bg-surface-green-1 px-3 py-2 text-base text-ink-green-8" data-testid="ask-ready">
          <span class="lucide-check size-4" aria-hidden="true" />{{ w('ask_ready') }}
        </div>
        <div v-else class="flex flex-col gap-1.5 rounded-4 bg-surface-amber-1 px-3 py-2.5 text-ink-gray-9" data-testid="ask-reasons">
          <div class="text-base font-medium">{{ pre.reasons.length === 1 ? w('ask_fix_one') : w('ask_fix_n', { count: pre.reasons.length }) }}</div>
          <div v-for="r in pre.reasons" :key="r.key" class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm" data-testid="ask-reason">
            <span class="min-w-0 flex-[1_1_200px]">{{ r.reason }}</span>
            <template v-for="f in [fixOf(r, { project, doctype })]" :key="r.key">
              <router-link v-if="f.route" :to="f.route" class="inline-flex min-h-12 items-center text-ink-blue-link md:min-h-0" data-testid="ask-fix" @click="shown = false">{{ w(f.word) }}</router-link>
              <span v-else-if="f.word" class="text-ink-gray-7">{{ w(f.word) }}</span>
            </template>
          </div>
        </div>

        <div class="rounded-4 border border-outline-gray-2 px-3 py-2.5" data-testid="ask-summary">
          <div class="text-xs text-ink-gray-7">{{ approvalWord(`kind.${doctype}`, { mode }) }}</div>
          <div class="text-base text-ink-gray-9"><span class="font-mono text-xs font-semibold">{{ name }}</span> {{ record.title || record.subject || '' }}</div>
          <div v-if="figures" class="text-sm text-ink-gray-7" data-testid="ask-figures">{{ figures }}</div>
        </div>

        <section aria-labelledby="ask-approvers">
          <h3 id="ask-approvers" class="m-0 mb-1.5 text-base font-semibold text-ink-gray-9">{{ w('ask_approvers') }}</h3>
          <p v-if="!pre.approvers.length" class="m-0 text-sm text-ink-gray-7">{{ w('ask_no_approvers') }}</p>
          <ul class="m-0 flex list-none flex-col gap-1 p-0">
            <li v-for="a in pre.approvers" :key="a.member || a.name" class="flex flex-wrap items-center gap-2 py-1" data-testid="ask-approver">
              <Avatar :label="a.name" size="md" />
              <span class="min-w-0 flex-[1_1_120px] truncate text-base text-ink-gray-9">{{ a.name }}</span>
              <Badge :label="w(a.agreed ? 'ask_agreed' : 'ask_not_agreed')" :theme="a.agreed ? 'green' : 'gray'" />
              <Badge v-if="!a.confirmed" :label="w('set_state_waiting')" theme="amber" />
              <template v-if="a.must_reset">
                <Badge :label="w('set_must_reset')" theme="amber" data-testid="ask-must-reset" />
                <Button variant="outline" class="max-md:!h-12" :label="w('set_send_reset')" :disabled="busy" data-testid="ask-send-reset" @click="sendReset(a)" />
              </template>
            </li>
          </ul>
          <p class="m-0 mt-1 text-xs text-ink-gray-7">{{ w('ask_approvers_note') }}</p>
          <p v-if="notice" class="m-0 mt-1 text-sm text-ink-green-8" role="status" data-testid="ask-notice">{{ notice }}</p>
        </section>

        <!-- P3-82: the checks the request follows, and who does each (design 14.6) -->
        <section v-if="route && route.steps.length" aria-labelledby="ask-route" data-testid="ask-route">
          <h3 id="ask-route" class="m-0 mb-1.5 text-base font-semibold text-ink-gray-9">{{ w('ask_route') }}</h3>
          <p class="m-0 mb-1.5 text-sm text-ink-gray-8" data-testid="ask-route-text">{{ route.text }}</p>
          <p class="m-0 mb-1.5 text-xs text-ink-gray-7">{{ route.covered ? w('ask_route_covered') : route.internal ? w('ask_route_internal') : '' }}</p>
          <ol class="m-0 flex list-none flex-col gap-1.5 p-0">
            <li v-for="st in route.steps" :key="st.no" class="flex flex-wrap items-baseline gap-x-2 text-sm" :class="st.applies === '0' ? 'text-ink-gray-6' : 'text-ink-gray-9'" data-testid="ask-route-step" :data-same="st.same_person ? '1' : '0'">
              <span class="font-medium">{{ st.no }}. {{ st.name }}</span>
              <span class="text-xs text-ink-gray-7">{{ w(st.position === 'after' ? 'ask_route_after' : 'rq_step_before') }} · {{ w(st.rule === 'all' ? 'ask_route_all' : 'ask_route_any') }}</span>
              <span class="min-w-0 flex-[1_1_100%] text-ink-gray-8">{{ st.applies === '0' ? w('ask_route_skipped') : st.applies === '' ? w('ask_route_client_option') : st.people.length ? st.people.join(', ') : w('ask_route_nobody') }}</span>
            </li>
          </ol>
          <p v-if="sameSteps.length" class="m-0 mt-2 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" role="status" data-testid="ask-same-person">{{ w('ask_same_warn', { steps: sameSteps.map((x) => x.name).join(', ') }) }}</p>
        </section>

        <fieldset v-if="kind === VARIATION" class="m-0 flex flex-col gap-1.5 border-0 p-0">
          <legend class="mb-1 p-0 text-base font-semibold text-ink-gray-9">{{ w('ask_work') }}</legend>
          <label class="flex min-h-12 items-center gap-2 text-base md:min-h-8"><input v-model="started" type="radio" :value="false" class="form-radio" data-testid="ask-work-no" />{{ w('ask_work_no') }}</label>
          <label class="flex min-h-12 items-center gap-2 text-base md:min-h-8"><input v-model="started" type="radio" :value="true" class="form-radio" data-testid="ask-work-yes" />{{ w('ask_work_yes') }}</label>
          <input v-if="started" v-model="startedOn" type="date" :max="today" class="form-input w-full max-w-[220px] max-md:h-12" :aria-label="w('ask_work_yes')" data-testid="ask-work-date" />
          <span class="text-xs text-ink-gray-7">{{ w('ask_work_help') }}</span>
        </fieldset>

        <label class="flex flex-col gap-1.5 text-base font-semibold text-ink-gray-9">{{ w('ask_due') }}
          <input v-model="due" type="date" :min="today" class="form-input w-full max-w-[220px] max-md:h-12" data-testid="ask-due" />
          <span class="text-xs font-normal text-ink-gray-7">{{ w('ask_due_help') }}</span>
        </label>
        <label class="flex flex-col gap-1.5 text-base font-semibold text-ink-gray-9">{{ w('ask_note') }}
          <textarea v-model="note" rows="3" maxlength="1000" class="form-textarea h-auto w-full" data-testid="ask-note" />
        </label>

        <div v-if="lines.length" class="rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="ask-refusal">
          <div v-for="l in lines" :key="l">{{ l }}</div>
        </div>
        <p v-if="sent" class="m-0 rounded-4 bg-surface-green-1 px-3 py-2 text-sm text-ink-green-8" role="status" data-testid="ask-sent">{{ w(sentInternal ? 'ask_sent_internal' : 'ask_sent') }}</p>
      </template>
    </div>
    <template #actions>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <Button class="mr-auto max-md:!h-12" icon-left="lucide-printer" :label="w('ask_print')" :disabled="!sent" :title="sent ? '' : w('ask_print_after')" data-testid="ask-print" @click="print" />
        <Button class="max-md:!h-12" :label="sent ? w('ask_done') : w('ask_cancel')" data-testid="ask-cancel" @click="shown = false" />
        <Button v-if="!sent" variant="solid" theme="blue" class="max-md:!h-12" :label="busy ? w('ask_sending') : w('ask_send')" :disabled="!sendable" data-testid="ask-send" @click="send" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Avatar, Badge, Button, Dialog } from 'frappe-ui'
import { call } from '../../api.js'
import { useMode } from '../../mode.js'
import { approvalWord, staffWords } from '../words.js'
import { VARIATION, askBody, canSend, fixOf, printUrl, refusalLines } from './ask.js'
import { samePersonSteps } from './routes.js'

// The Ask sheet (P3-80; design §3.4; canvas ApprovalStaffForms 14): the preflight with each reason and its fix, the
// approvers with their agreement and must-reset states, the due date, the note, "Has work started?" for a Variation,
// Print for signature (the sent request's frozen terms, in a new tab) and Send. Send waits for a ready preflight; the
// server checks it all again and its refusal sentences are shown as they come.
const props = defineProps({ open: Boolean, project: { type: String, required: true }, doctype: { type: String, default: '' }, name: { type: String, default: '' } })
const emit = defineEmits(['update:open', 'sent'])
const mode = useMode()
const w = staffWords(mode)
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const kind = computed(() => props.doctype)
const API = 'construction_core.approvals.'
const today = new Date().toLocaleDateString('en-CA')

const pre = ref(null)
const record = ref({})
const route = ref(null)
const sameSteps = computed(() => samePersonSteps(route.value))
const loading = ref(false)
const error = ref('')
const busy = ref(false)
const lines = ref([])
const notice = ref('')
const sent = ref('')
const sentInternal = ref(false) // the answer's internal: the steps come before the client
const due = ref('')
const note = ref('')
const started = ref(false)
const startedOn = ref('')

const sendable = computed(() => canSend({ pre: pre.value, busy: busy.value, kind: kind.value, started: started.value, startedOn: startedOn.value }))
const figures = computed(() => {
  const r = record.value
  const money = Number(r.vo_delta_sum || 0)
  const days = Number(r.time_extension_days || 0)
  return [money && `${money > 0 ? '+' : ''}${money.toLocaleString()}`, days && `${days > 0 ? '+' : ''}${days} days`].filter(Boolean).join(' · ')
})

async function load() {
  loading.value = true
  error.value = ''
  lines.value = []
  notice.value = ''
  sent.value = ''
  sentInternal.value = false
  due.value = ''
  note.value = ''
  started.value = false
  startedOn.value = ''
  try {
    const [p, r, rt] = await Promise.all([
      call(API + 'staff.preflight', { project: props.project, doctype: props.doctype, name: props.name }),
      call('frappe.client.get', { doctype: props.doctype, name: props.name }),
      call(API + 'routes.ask', { doctype: props.doctype, name: props.name }).catch(() => null), // no route to show is not a reason to stop the sheet
    ])
    pre.value = p
    record.value = r
    route.value = rt
  } catch (e) {
    pre.value = null
    error.value = e.message || w('ask_error')
  } finally {
    loading.value = false
  }
}

async function send() {
  busy.value = true
  lines.value = []
  try {
    const out = await call(API + 'api.request', askBody({ doctype: props.doctype, name: props.name, due: due.value, note: note.value, kind: kind.value, started: started.value, startedOn: startedOn.value }), { post: true })
    sent.value = out.request
    sentInternal.value = !!out.internal
    emit('sent', out)
  } catch (e) {
    lines.value = refusalLines(e.message)
    if (!lines.value.length) lines.value = [w('ask_error')]
  } finally {
    busy.value = false
  }
}

async function sendReset(a) {
  busy.value = true
  lines.value = []
  notice.value = ''
  try {
    const out = await call(API + 'credentials.send_reset_link', { project: props.project, member: a.member }, { post: true })
    notice.value = w('set_reset_sent', { to: out.sent_to })
  } catch (e) {
    lines.value = refusalLines(e.message)
  } finally {
    busy.value = false
  }
}

// The printable page of the frozen terms; it runs no script, so the person prints it from the browser.
function print() {
  if (sent.value) window.open(printUrl(sent.value), '_blank', 'noopener')
}

watch(() => props.open, (v) => v && props.name && load(), { immediate: true })
</script>
