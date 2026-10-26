<template>
  <section class="relative min-h-[300px] overflow-hidden rounded-7 bg-surface-gray-10 text-ink-base shadow-md dark:border dark:border-outline-gray-2 dark:bg-surface-base dark:text-ink-gray-9" aria-label="Project summary" data-testid="portal-banner">
    <!-- No building photo yet (D-167): the design's tile pattern, drawn in the theme's own colours (D-125). The design
         keeps the banner dark in both themes, so the dark theme has its own dark tokens here. The mask's white sets
         only how much shows; it paints nothing. -->
    <svg class="absolute inset-0 size-full" viewBox="0 0 980 320" preserveAspectRatio="xMaxYMid slice" aria-hidden="true" data-testid="banner-pattern">
      <defs>
        <pattern id="cc-banner-tiles" width="34" height="34" patternUnits="userSpaceOnUse"><rect class="fill-surface-gray-8 dark:fill-surface-gray-3" x="2" y="2" width="28" height="28" rx="7" /></pattern>
        <linearGradient id="cc-banner-fade" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0.3" stop-color="white" stop-opacity="0" /><stop offset="0.75" stop-color="white" stop-opacity="0.55" /><stop offset="1" stop-color="white" stop-opacity="0.8" />
        </linearGradient>
        <mask id="cc-banner-mask"><rect width="980" height="320" fill="url(#cc-banner-fade)" /></mask>
      </defs>
      <g mask="url(#cc-banner-mask)">
        <rect width="980" height="320" fill="url(#cc-banner-tiles)" />
        <rect class="fill-surface-blue-5" x="716" y="70" width="28" height="28" rx="7" />
        <rect class="fill-surface-green-5" x="852" y="138" width="28" height="28" rx="7" />
        <rect class="fill-surface-amber-5" x="784" y="206" width="28" height="28" rx="7" />
        <rect class="fill-surface-blue-5" x="920" y="36" width="28" height="28" rx="7" />
      </g>
    </svg>
    <div class="relative flex min-h-[300px] flex-col px-[26px] py-6">
      <div class="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-gray-3 dark:text-ink-gray-6">{{ data.project.name }}<template v-if="data.project.cc_phase"> · {{ data.project.cc_phase }}</template></div>
      <h1 class="m-0 mt-1.5 text-4xl-semibold text-ink-base dark:text-ink-gray-9">{{ data.project.project_name || data.project.name }}</h1>
      <p class="m-0 mt-1.5 max-w-[460px] text-base text-ink-gray-3 dark:text-ink-gray-7" data-testid="greeting">{{ greeting(new Date().getHours(), viewerName ?? boot.full_name) }}. Here is what the project team has shared with you.</p>
      <div v-if="summary.length" class="mt-auto flex flex-wrap gap-2 pt-5">
        <router-link v-for="s in summary" :key="s.tab" :to="{ query: { tab: s.tab } }"
          class="flex items-center gap-2.5 rounded-5 border border-[color:var(--surface-gray-8)] bg-surface-gray-9 px-3 py-2 no-underline hover:bg-surface-gray-8 dark:border-outline-gray-2 dark:bg-surface-gray-2 dark:hover:bg-surface-gray-3"
          data-testid="portal-summary">
          <span class="text-2xl-semibold text-ink-base dark:text-ink-gray-9">{{ s.count }}</span>
          <span class="text-sm text-ink-gray-3 dark:text-ink-gray-7">{{ s.label }}</span>
          <span class="lucide-arrow-right size-4 text-ink-gray-3 dark:text-ink-gray-7" aria-hidden="true" />
        </router-link>
      </div>
    </div>
  </section>

  <!-- P3-79 (approvals design §3.12; ApprovalPortalHome): the approver's own count. The rows hold an Open request only for a
       confirmed approver, so anyone else has no card. -->
  <section v-if="has('approvals') && waiting.length" class="cw-card flex flex-wrap items-center gap-3.5 px-4 py-3.5" :aria-label="aw('waiting_title')" data-testid="portal-approvals-card">
    <span class="grid size-12 flex-none place-items-center rounded-5 bg-surface-blue-2 text-2xl-semibold text-ink-blue-8" data-testid="portal-approvals-count">{{ waiting.length }}</span>
    <div class="min-w-0 flex-[1_1_240px]">
      <h2 class="cw-card-title">{{ aw('waiting_title') }}</h2>
      <div class="text-sm text-ink-gray-7" data-testid="portal-approvals-line">{{ approvalsLine }}</div>
    </div>
    <Button variant="solid" theme="blue" size="md" class="max-md:!h-12" :label="aw('review')" :route="{ query: { tab: 'approvals' } }" data-testid="portal-approvals-review" />
  </section>

  <div class="flex flex-wrap items-start gap-4">
    <section v-if="has('discuss')" class="cw-card min-w-0 flex-[1_1_400px] overflow-hidden" aria-labelledby="latest-h">
      <div class="cw-card-header">
        <h2 id="latest-h" class="cw-card-title">Latest messages</h2>
        <router-link :to="{ query: { tab: 'discuss' } }" class="ml-auto text-sm text-ink-blue-link">Open Discussion</router-link>
      </div>
      <p v-if="!latest.length" class="px-4 py-3 text-sm text-ink-gray-7">No message yet.</p>
      <router-link v-for="(m, at) in latest" :key="m.name" :to="{ query: { tab: 'discuss', thread: m.threadName } }"
        class="cw-list-row !items-start" :class="{ '!border-t-0': at === 0 }">
        <Avatar :label="m.author_name" size="md" :theme="themeOf(m.author_name)" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-sm text-ink-gray-9"><strong class="font-semibold">{{ m.author_name }}</strong> {{ said(m.text) }}</span>
          <span class="block text-xs text-ink-gray-7">{{ m.thread }} · {{ m.when }}</span>
        </span>
      </router-link>
    </section>

    <section v-if="has('files')" class="cw-card min-w-0 flex-[1_1_360px] overflow-hidden" aria-labelledby="files-h">
      <div class="cw-card-header">
        <h2 id="files-h" class="cw-card-title">Recently shared files</h2>
        <router-link :to="{ query: { tab: 'files', group: 'files' } }" class="ml-auto text-sm text-ink-blue-link">All files</router-link>
      </div>
      <p v-if="!shared.length" class="px-4 py-3 text-sm text-ink-gray-7">No file shared yet.</p>
      <a v-for="(f, at) in shared.slice(0, 5)" :key="at" :href="f.url" target="_blank" rel="noopener"
        class="cw-list-row" :class="{ '!border-t-0': at === 0 }">
        <Badge class="min-w-10 flex-none justify-center font-semibold" size="sm" :theme="extTheme(fileExt(f.file_name))" :label="fileExt(f.file_name) || 'FILE'" />
        <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-9">{{ f.file_name }}</span>
      </a>
    </section>
  </div>

  <section v-if="has('whiteboards') && board" class="cw-card flex flex-wrap items-center gap-3.5 px-4 py-3.5" aria-labelledby="board-h">
    <span class="grid h-[86px] w-[140px] flex-none place-items-center rounded-4 border border-outline-gray-2 bg-surface-gray-1" aria-hidden="true">
      <span class="lucide-pen-line size-6 text-ink-gray-6" />
    </span>
    <div class="min-w-0 flex-[1_1_240px]">
      <h2 id="board-h" class="cw-card-title">Shared canvas: {{ board.title }}</h2>
      <div class="text-sm text-ink-gray-7"><template v-if="board.last_saved_on">Updated {{ formatDate(board.last_saved_on) }} · </template>view only</div>
    </div>
    <Button variant="outline" size="md" label="Open canvas" :route="boardLink(project, board.name)" data-testid="portal-board-link" />
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import { boot } from '../../boot.js'
import { themeOf } from '../../frame.js'
import { extTheme, fileExt, formatDate } from '../../sections/util.js'
import { plain } from '../../chat/tokens.js'
import { wordsFor } from '../../chat/words.js'
import { useMode } from '../../mode.js'
import { dayText, names, soonest, waitingRows } from '../../approvals/terms.js'
import { approvalWords } from '../../approvals/words.js'
import { greeting, latestMessages, portalBoardLink } from '../tabs.js'

// The portal's Home on the live design (D-124, version 1791695385-af29). The banner has no building photo yet, so it
// shows the design's tile pattern (D-167). Progress, days to handover, "waiting for you" and milestones have no data
// in the portal yet and are not drawn (D-058, D-137): the summary counts only what the team shared.
const props = defineProps({
  data: { type: Object, required: true },
  project: String,
  tabs: { type: Array, required: true },
  // The staff preview (P3-05) greets the client it shows and opens boards in its own panel; the portal keeps its own.
  viewerName: { type: String, default: undefined },
  boardLink: { type: Function, default: portalBoardLink },
})
const has = (group) => props.tabs.some((t) => t.groups.includes(group))
const aw = approvalWords(useMode())
const waiting = computed(() => waitingRows(props.data))
const approvalsLine = computed(() => {
  const refs = names(waiting.value.map((r) => r.reference))
  const first = dayText(soonest(waiting.value))
  return first ? aw('home_line', { refs, date: first }) : aw('home_line_open', { refs })
})
const latest = computed(() => latestMessages(props.data.threads))
const board = computed(() => props.data.whiteboards[0])
// P3-07: Files also lists what the client sent; Home shows what the team shared with them.
const shared = computed(() => props.data.files.filter((f) => f.shared))
const summary = computed(() => {
  const d = props.data
  const list = (g) => (g === 'files' ? shared.value : d[{ rfi: 'rfis', discuss: 'threads' }[g] || g] || [])
  const count = (groups) => groups.filter(has).reduce((n, g) => n + list(g).length, 0)
  return [
    { tab: 'discuss', groups: ['discuss'], label: 'conversations' },
    { tab: 'approvals', groups: ['submittals', 'variations', 'rfi'], label: 'records in Approvals' },
    { tab: 'files', groups: ['files', 'documents', 'whiteboards'], label: 'shared files and boards' },
  ].filter((s) => s.groups.some(has)).map((s) => ({ ...s, count: count(s.groups) })) // an Approvals tab of requests only has no records to count
})

// P3-66: a message's mentions and tags read as words here, never as tokens
const chatW = wordsFor(useMode(), true)
const said = (text) => plain(text, chatW)
</script>
