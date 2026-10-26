<template>
  <PageHead :crumb="`Client portal / ${data.project.name}`" :title="waiting.length ? w('waiting_title') : groupLabel('approvals', mode)" :meta="meta" />
  <template v-if="approvalsOn && group === 'all'">
    <p v-if="waiting.length" class="m-0 flex items-center gap-2 text-sm text-ink-gray-8" data-testid="approval-approver-line">
      <span class="lucide-shield-check size-4 flex-none text-ink-green-7" aria-hidden="true" />{{ w('named_approver', { names: names(waiting[0].approvers) }) }}
    </p>
    <section v-if="waiting.length" :aria-label="w('waiting_title')" class="flex flex-col gap-3.5" data-testid="approval-waiting-list">
      <WaitingCard v-for="r in waiting" :key="r.name" :row="r" :w="w" :comments="discuss" />
    </section>
    <section aria-labelledby="approvals-decided-h" class="flex flex-col gap-2.5" data-testid="approval-decided-list">
      <h2 id="approvals-decided-h" class="m-0 text-xl-semibold text-ink-gray-9">{{ w('decided_title') }}</h2>
      <p v-if="!decided.length" class="m-0 text-sm text-ink-gray-7">{{ w('nothing_decided') }}</p>
      <template v-else>
        <div class="cw-card divide-y divide-outline-gray-1 overflow-hidden"><DecidedCard v-for="r in decided" :key="r.name" :row="r" :w="w" /></div>
        <p class="m-0 text-xs text-ink-gray-7">{{ w('no_undo') }}</p>
      </template>
    </section>
  </template>
  <div v-if="legacy.length > 1" class="cw-tabbuttons self-start" role="group" aria-label="Show">
    <router-link v-for="g in ['all', ...legacy]" :key="g" :to="{ query: { tab: 'approvals', ...(g === 'all' ? {} : { group: g }) } }"
      class="cw-tabbutton no-underline" :aria-pressed="group === g">{{ g === 'all' ? 'All' : groupLabel(g, mode) }} <span class="text-ink-gray-7">{{ g === 'all' ? total : rows(g).length }}</span></router-link>
  </div>
  <p v-if="legacy.length" class="m-0 text-sm text-ink-gray-7">The records your project team shares with you, to read.<template v-if="discuss"> To comment, write to the team in Discussion.</template></p>

  <section v-for="g in shown" :key="g" :aria-label="groupLabel(g, mode)" class="flex flex-col gap-2.5" data-testid="portal-group" :data-group="g">
    <h2 v-if="group === 'all'" class="cw-label m-0 text-ink-gray-7">{{ groupLabel(g, mode) }}</h2>
    <p v-if="!rows(g).length" class="m-0 text-sm text-ink-gray-7">Nothing shared yet.</p>
    <article v-for="r in rows(g)" :key="r.name" class="cw-card overflow-hidden pb-3.5" data-testid="portal-row">
      <div class="flex flex-wrap items-start gap-2.5 px-4 pt-3.5">
        <div class="min-w-0 flex-[1_1_300px]">
          <div class="text-lg-semibold text-ink-gray-9">{{ r.title }}</div>
          <div class="mt-0.5 font-mono text-xs text-ink-gray-7">{{ r.name }}</div>
        </div>
        <Badge :theme="KIND[g].theme" :label="kindLabel(g)" />
        <Badge v-if="r.state" :theme="stateTheme(r.state)" :label="portalStateLabel(r.state, mode)" />
      </div>
      <div v-if="r.facts.length" class="flex flex-wrap gap-2 px-4 pt-2.5">
        <span v-for="[k, v] in r.facts" :key="k" class="rounded-4 bg-surface-gray-2 px-2.5 py-1.5 text-sm text-ink-gray-9">
          <span class="text-ink-gray-7">{{ k }}</span> <strong class="font-semibold">{{ v }}</strong>
        </span>
      </div>
      <div v-if="r.answer" class="mx-4 mt-2.5 rounded-4 border border-outline-gray-1 px-3 py-2">
        <div class="cw-label text-ink-gray-7">Answer</div>
        <div class="mt-1 whitespace-pre-wrap text-sm text-ink-gray-9">{{ r.answer }}</div>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import PageHead from '../../components/PageHead.vue'
import DecidedCard from '../../approvals/DecidedCard.vue'
import WaitingCard from '../../approvals/WaitingCard.vue'
import { decidedRows, names, waitingRows } from '../../approvals/terms.js'
import { approvalWords } from '../../approvals/words.js'
import { formatDate, stateTheme } from '../../sections/util.js'
import { useMode } from '../../mode.js'
import { groupLabel, noun, portalStateLabel } from '../../words.js'

// Approvals on the live design (D-124, version 1791648865-5845; D-127): Submittals, Variations and RFIs as read-only
// groups, which carry no Approve or Return button (D-058). Since P3-79 the tab's first group is the requests the team
// sent for approval, with their own cards (src/approvals/).
const KIND = {
  submittals: { theme: 'blue' },
  variations: { theme: 'amber' },
  rfi: { theme: 'gray' },
}
// The words follow the client's mode (D-155, D-162): "Question" in Simple, "RFI" in Advanced.
const mode = useMode()
const kindLabel = (g) => {
  const n = noun(g, mode.value)
  return n.charAt(0).toUpperCase() + n.slice(1)
}
const props = defineProps({
  data: { type: Object, required: true },
  groups: { type: Array, required: true },
  group: { type: String, default: 'all' },
  discuss: Boolean, // Discussion is on for this project: point to it
})
// P3-79 (design §3.12): the "approvals" group is the requests waiting for this client and the ones decided, drawn by the
// approvals screens; the groups after it are the read-only records above (Advanced mode, or an old link).
const w = approvalWords(mode)
const approvalsOn = computed(() => props.groups.includes('approvals'))
const legacy = computed(() => props.groups.filter((g) => g !== 'approvals'))
const waiting = computed(() => (approvalsOn.value ? waitingRows(props.data) : []))
const decided = computed(() => (approvalsOn.value ? decidedRows(props.data) : []))
const shown = computed(() => (props.group === 'all' ? legacy.value : [props.group]))
const total = computed(() => legacy.value.reduce((n, g) => n + rows(g).length, 0))
const meta = computed(() => (waiting.value.length ? w(waiting.value.length === 1 ? 'item_one' : 'items', { count: waiting.value.length })
  : legacy.value.length ? `${total.value} ${total.value === 1 ? 'record' : 'records'}` : ''))

function rows(g) {
  const d = props.data
  if (g === 'submittals') return d.submittals.map((r) => ({ name: r.name, title: r.title, state: r.status, facts: r.current_revision ? [['Revision', r.current_revision]] : [] }))
  if (g === 'variations') return d.variations.map((r) => ({ name: r.name, title: r.title, state: r.stage, facts: r.amount ? [['Cost', r.amount]] : [] }))
  if (g === 'rfi') return d.rfis.map((r) => ({ name: r.name, title: r.subject, state: r.status, facts: r.due_date ? [['Due', formatDate(r.due_date)]] : [], answer: r.response }))
  return []
}
</script>
