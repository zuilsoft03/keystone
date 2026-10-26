<template>
  <section class="evidence-screen flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto bg-surface-gray-1 px-6 py-5 max-md:px-3" :aria-label="w('ev_title')" data-testid="evidence-page">
    <div class="no-print flex flex-wrap items-center gap-3">
      <router-link :to="requestRoute(project, request)" class="inline-flex min-h-12 items-center text-sm text-ink-gray-7 no-underline hover:text-ink-gray-9 md:min-h-0" data-testid="evidence-back">← {{ ev ? w('ev_crumb', { ref: ev.summary.reference }) : w('rq_back') }}</router-link>
      <span class="flex-1" />
      <Button v-if="ev" variant="solid" theme="blue" class="max-md:!h-12" icon-left="lucide-printer" :label="w('ev_print')" data-testid="evidence-print" @click="print" />
    </div>
    <p v-if="error" class="m-0 text-ink-red-7" role="alert" data-testid="evidence-error">{{ error }}</p>
    <p v-else-if="!ev" class="m-0 text-ink-gray-7" role="status">{{ w('tab_loading') }}</p>
    <!-- the paper stays light in dark mode: fixed colours, no theme tokens -->
    <article v-else class="evidence-paper mx-auto flex w-full max-w-3xl flex-col gap-4 rounded-5 border p-6 max-md:p-4" style="border-color: oklch(.9 0 0)" data-testid="evidence-paper" :data-stage="ev.stage">
      <header class="flex flex-wrap items-center gap-3 border-b pb-3" style="border-color: oklch(.9 0 0)">
        <div class="min-w-0 flex-1">
          <div class="text-base font-semibold">{{ ev.project_name }}</div>
          <div class="text-xs" style="color: oklch(.44 0 0)">{{ w('ev_title') }}</div>
        </div>
        <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :style="ev.stage === 'Final' ? 'background:oklch(.96 .05 150);color:oklch(.4 .1 150)' : 'background:oklch(.96 .06 90);color:oklch(.45 .1 60)'" data-testid="evidence-stage">{{ w(ev.stage === 'Final' ? 'ev_final' : 'ev_interim') }}</span>
      </header>
      <section v-for="s in sections" :key="s.id" class="flex flex-col gap-1.5">
        <h2 class="m-0 text-sm font-semibold">{{ s.title }}</h2>
        <dl class="m-0 grid grid-cols-[150px_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm max-md:grid-cols-1">
          <template v-for="[label, value] in s.rows" :key="label">
            <dt style="color: oklch(.44 0 0)">{{ label }}</dt>
            <dd class="m-0 break-words">{{ value }}</dd>
          </template>
        </dl>
        <img v-if="s.id === 'signature' && ev.signature?.url" :src="ev.signature.url" :alt="w('ev_sig_alt')" class="mt-1 max-h-32 max-w-full self-start rounded-3 border" style="border-color: oklch(.9 0 0); background: oklch(1 0 0)" data-testid="evidence-signature" />
      </section>
      <!-- P3-82: the firm's internal sign-offs, with the saved steps they ran on (managers only; the server gates it) -->
      <section v-if="ev.internal?.length" class="flex flex-col gap-1.5" data-testid="evidence-internal">
        <h2 class="m-0 text-sm font-semibold">{{ w('ev_internal') }}</h2>
        <ol class="m-0 flex list-none flex-col gap-1 p-0 text-sm">
          <li v-for="(e, i) in ev.internal" :key="i" class="flex flex-wrap gap-x-3" data-testid="internal-row"><time class="w-28 flex-none" style="color: oklch(.44 0 0)">{{ whenText(e.at) }}</time><span class="min-w-0 flex-1 break-words">{{ lineText(e, w) }}<template v-if="e.reason"> · {{ e.reason }}</template></span></li>
        </ol>
      </section>
      <section class="flex flex-col gap-1.5">
        <h2 class="m-0 text-sm font-semibold">{{ w('ev_timeline') }}</h2>
        <ol class="m-0 flex list-none flex-col gap-1 p-0 text-sm">
          <li v-for="(e, i) in ev.timeline" :key="i" class="flex flex-wrap gap-x-3"><time class="w-28 flex-none" style="color: oklch(.44 0 0)">{{ whenText(e.at) }}</time><span class="min-w-0 flex-1 break-words">{{ lineText(e, w) }}</span></li>
        </ol>
      </section>
    </article>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { call } from '../../api.js'
import { useMode } from '../../mode.js'
import { approvalWords, staffWords } from '../words.js'
import { costText, dayText, timeText, whenText } from '../terms.js'
import { lineText, requestRoute, shortHash } from './request.js'

// The evidence record page (P3-80; design §3.12, §4.1; canvas ApprovalEvidence) for managers: the summary, the answer and
// the chosen option, the signature picture, the evidence block, the timeline and the fingerprints. "Interim" while the
// request is open, "Final" after. Print uses the browser's print with the paper look below (no PDF: that is P3-81). Anyone
// else gets the server's "Not found", shown as such.
const props = defineProps({ project: { type: String, required: true }, request: { type: String, required: true } })
const mode = useMode()
const w = staffWords(mode)
const aw = approvalWords(mode)
const ev = ref(null)
const error = ref('')

const dash = (v) => v || '—'
const receiptLine = (r) => (r.state === 'sent' ? w('ev_receipt_sent') : r.state === 'failed' ? w('ev_receipt_failed') : r.state === 'not_sent' ? w('ev_receipt_not_sent') : '—')

const sections = computed(() => {
  const e = ev.value
  if (!e) return []
  const { summary: s, answer: a, evidence: x, signature: sig, fingerprints: fp, parties } = e
  const cost = [s.total !== '' && costText(s.total, s.currency), s.days !== '' && timeText(s.days, aw)].filter(Boolean).join(' · ')
  const rec = x?.recorded
  return [
    { id: 'summary', title: w('ev_summary'), rows: [
      [w('ev_item'), [s.reference, s.title, s.revision && `rev ${s.revision}`].filter(Boolean).join(' · ')],
      [w('ev_cost'), dash(cost)],
      [w('ev_requested'), s.due_date ? w('ev_requested_val', { when: whenText(s.requested_at), name: s.requested_by, due: dayText(s.due_date) }) : w('ev_requested_nodue', { when: whenText(s.requested_at), name: s.requested_by })],
      [w('ev_answer'), a ? w(a.kind === 'approved' ? 'ev_approved' : 'ev_returned') + (a.reason ? ` · ${a.reason}` : '') : w('ev_open_answer')],
      [w('ev_option'), a?.option ? a.option.label : w('ev_no_options')],
      [w('ev_receipt'), receiptLine(e.receipts)],
    ] },
    { id: 'parties', title: w('ev_parties'), rows: [
      [w('ev_client_party'), [parties.client_legal_name, parties.client_address].filter(Boolean).join(' · ') || '—'],
      [w('ev_entered'), parties.entered_by ? w('ev_entered_val', { name: parties.entered_by, when: whenText(parties.entered_at) }) : '—'],
      [w('ev_contract'), [parties.contract_document, parties.contract_date && `${dayText(parties.contract_date)} ${parties.contract_date.slice(0, 4)}`, parties.contract_clause].filter(Boolean).join(', ') || '—'],
    ] },
    { id: 'signature', title: w('ev_signature'), rows: [[w('ev_signature'), sig ? w('ev_sign_val', { kind: w(`sign_${sig.kind}`), typed: sig.typed_name || w('ev_none') }) : w('ev_not_signed')]] },
    { id: 'evidence', title: w('ev_evidence'), rows: !x ? [[w('ev_evidence'), w('ev_when_open')]] : [
      [w('ev_time'), `${whenText(a.at)} · ${x.time_zone}`],
      [w('ev_account'), [x.account.name, x.account.email].filter(Boolean).join(' · ')],
      [w('ev_network'), `${dash(x.network_address)} ${w('ev_network_note')}`],
      [w('ev_browser'), dash([x.browser, x.system].filter(Boolean).join(' · '))],
      // a place is shown only when the client chose to share it
      ...(x.location?.state === 'shared' ? [[w('ev_location'), w('ev_location_val', { meters: Math.round(x.location.accuracy || 0) })]] : []),
      [w('ev_session'), w('ev_session_val', { password: w(x.session.password_step === '1' ? 'ev_asked' : 'ev_not_asked'), two: w(x.session.two_step === '1' ? 'ev_on' : 'ev_off') })],
      [w('ev_statements'), dash(Object.entries(x.statement_versions || {}).map(([k, v]) => v || k).join(' · '))],
      ...(rec ? [[w('ev_recorded'), w('ev_recorded_val', { label: rec.label, given: dash(rec.given_at), proof: dash(rec.proof_name), original: dash(rec.original) })],
        [w('ev_confirmed_by', { name: rec.confirmed_by }), rec.same_person ? w('ev_same_person') : '—']] : []),
    ] },
    { id: 'fingerprints', title: w('ev_fingerprints'), rows: [
      [w('ev_fp_version'), shortHash(fp.version)], [w('ev_fp_signature'), dash(shortHash(fp.signature))],
      [w('ev_fp_answer'), fp.answer ? shortHash(fp.answer.hash) : '—'], [w('ev_fp_chain'), fp.chain_head ? shortHash(fp.chain_head.hash) : '—'],
      [w('ev_fp_doc'), shortHash(fp.document)],
    ] },
  ]
})

const print = () => window.print()

async function load() {
  error.value = ''
  ev.value = null
  try {
    ev.value = await call('construction_core.approvals.staff.evidence', { request: props.request })
  } catch {
    error.value = w('ev_not_found') // the same sentence for a missing request and for staff who are not managers
  }
}

watch(() => props.request, load, { immediate: true })
</script>

<style>
.evidence-paper { background: oklch(1 0 0); color: oklch(.2 0 0); }
@media print {
  /* only the paper prints: the shell around it is hidden, and its scroll boxes let the page run on */
  body * { visibility: hidden; }
  .evidence-paper, .evidence-paper * { visibility: visible; }
  .evidence-paper { position: absolute; left: 0; top: 0; width: 100%; max-width: none; border: 0; border-radius: 0; padding: 0; }
  html, body { height: auto !important; overflow: visible !important; }
  /* the paper is placed against the page, not against the shell's rail and top band, and it prints on white in either colour scheme */
  :has(.evidence-paper):not(.evidence-paper) { position: static !important; transform: none !important; overflow: visible !important; height: auto !important; background: oklch(1 0 0) !important; color-scheme: light; }
  .no-print { display: none !important; }
}
</style>
