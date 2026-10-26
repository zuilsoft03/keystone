<template>
  <section class="flex min-w-0 flex-1 flex-col overflow-y-auto bg-surface-base" :aria-label="w('tab_title')" data-testid="approvals-tab">
    <header class="flex flex-wrap items-center gap-3 border-b border-outline-gray-2 px-4 py-3 max-md:px-3">
      <router-link v-if="isPhone" :to="{ name: 'section', params: { project, section: 'discuss' } }" class="grid size-12 flex-none place-items-center rounded-4 text-ink-gray-8 hover:bg-surface-gray-2"
        :aria-label="w('rq_back')" data-testid="approvals-back"><span class="lucide-chevron-left size-5" aria-hidden="true" /></router-link>
      <div class="min-w-0 flex-[1_1_240px]">
        <h2 class="m-0 text-lg font-semibold text-ink-gray-9">{{ w('tab_title') }}</h2>
        <p class="m-0 truncate text-xs text-ink-gray-7" data-testid="approvals-approvers">{{ data.approvers?.length ? w('tab_approvers', { names: names(data.approvers) }) : w('tab_no_approvers') }}</p>
      </div>
      <Button variant="outline" class="max-md:!h-12" :label="w('new_decision')" data-testid="new-decision" @click="want = 'decision'" />
      <Button variant="solid" theme="blue" class="max-md:!h-12" icon-left="lucide-plus" :label="w('new_request')" data-testid="new-request" @click="want = 'ask'" />
    </header>
    <div class="flex flex-wrap gap-x-1 border-b border-outline-gray-1 px-2" role="tablist" :aria-label="w('filter_aria')">
      <button v-for="f in TAB_FILTERS" :key="f" type="button" role="tab" :aria-selected="show === f"
        class="-mb-px inline-flex h-9 items-center gap-1.5 border-b bg-transparent px-2.5 text-base max-md:h-12"
        :class="show === f ? 'border-outline-gray-8 text-ink-gray-9' : 'border-transparent text-ink-gray-6 hover:text-ink-gray-7'"
        :data-testid="`approvals-filter-${f}`" @click="show = f">{{ w(`f_${f}`) }} <Badge size="sm" :label="String(countOf(data.counts, f))" /></button>
    </div>
    <p v-if="error" class="m-0 px-4 py-3 text-ink-red-7" role="alert" data-testid="approvals-error">{{ error }}</p>
    <p v-else-if="loading" class="m-0 px-4 py-3 text-ink-gray-7" role="status">{{ w('tab_loading') }}</p>
    <p v-else-if="!shown.length" class="m-0 px-4 py-3 text-ink-gray-7" data-testid="approvals-empty">{{ w('tab_empty') }}</p>
    <ul v-else class="m-0 list-none p-0">
      <li v-for="r in shown" :key="r.name">
        <router-link :to="requestRoute(project, r.name)" class="grid min-h-14 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 border-b border-outline-gray-1 px-4 py-2 no-underline hover:bg-surface-gray-1 max-md:grid-cols-[minmax(0,1fr)_auto] max-md:px-3"
          data-testid="approval-row" :data-request="r.name" :data-group="r.group">
          <span class="min-w-0">
            <span class="block truncate text-sm text-ink-gray-7">{{ approvalWord(`kind.${r.kind}`, { mode }) }} · {{ r.reference }}</span>
            <span class="block truncate text-base font-medium text-ink-gray-9">{{ r.title }}</span>
            <span v-if="r.waiting_on" class="block truncate text-sm" :class="r.waiting_on_me ? 'font-medium text-ink-blue-8' : 'text-ink-gray-7'" data-testid="approval-waiting-on">{{ r.waiting_on }}</span>
          </span>
          <span class="flex items-center gap-2 max-md:row-start-2">
            <Avatar v-for="n in r.approvers" :key="n" :label="n" size="sm" :title="n" />
            <span v-if="r.due_date" class="text-xs" :class="r.group === 'overdue' ? 'text-ink-red-8' : 'text-ink-gray-7'" data-testid="approval-due">{{ dueText(r) }}</span>
            <span class="text-xs text-ink-gray-7" data-testid="approval-age">{{ ageText(r.age_days, w) }}</span>
          </span>
          <span class="flex flex-col items-end gap-1 max-md:row-start-1 max-md:col-start-2">
            <Badge :label="w(`st_${r.group === 'overdue' ? 'overdue' : r.state}`)" :theme="THEME[r.group === 'overdue' ? 'overdue' : r.state] || 'gray'" data-testid="approval-state" />
            <span v-if="r.needs_reconfirmation" class="text-xs text-ink-amber-8">{{ w('reconfirm') }}</span>
          </span>
        </router-link>
      </li>
    </ul>
    <AskFlow :project="project" :want="want" @done="want = ''" />
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import { useMode } from '../../mode.js'
import { isPhone } from '../../portal/state.js'
import { approvalWord, staffWords } from '../words.js'
import { dayText, names } from '../terms.js'
import AskFlow from './AskFlow.vue'
import { ageText, countOf, requestRoute } from './request.js'
import { TAB_FILTERS, rowsFor } from './routes.js'

// The Approvals tab in Discussion (P3-80; canvas DiscussApprovals): the project's requests from staff.requests, filtered by
// the server's own group, with each filter's count. A row opens the request page; New request and New Decision open T2's flows.
// The rows come from the Discussion screen, which also shows the count beside the tab.
const props = defineProps({ project: { type: String, required: true }, data: { type: Object, default: () => ({}) }, loading: Boolean, error: { type: String, default: '' } })
const mode = useMode()
const w = staffWords(mode)
const show = ref('waiting')
const want = ref('')
const shown = computed(() => rowsFor(props.data.rows, show.value))
const THEME = { waiting: 'amber', internal_review: 'blue', overdue: 'red', approved: 'green', recorded: 'green', returned: 'amber', disputed: 'red' }
const dueText = (r) => (r.group === 'overdue' ? `${dayText(r.due_date)} · ${w('st_overdue').toLowerCase()}` : w('due_on', { date: dayText(r.due_date) }))
</script>
