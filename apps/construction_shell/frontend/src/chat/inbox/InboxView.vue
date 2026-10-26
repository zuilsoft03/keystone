<template>
  <main class="flex min-w-0 flex-1 flex-col gap-3.5 overflow-y-auto px-6 py-5 max-md:px-4" data-testid="inbox-page">
    <PageHead :crumb="w('inbox.crumb')" :title="w('inbox.title')" />
    <div class="flex flex-wrap items-center gap-2.5">
      <div class="cw-tabbuttons" role="tablist" :aria-label="w('inbox.filter')">
        <button v-for="f in filters" :key="f.id" type="button" role="tab" class="cw-tabbutton max-md:!h-12 max-md:px-3" :aria-selected="state.query.show === f.id"
          :data-testid="`inbox-filter-${f.id || 'all'}`" @click="inbox.set({ show: f.id })">
          {{ f.label }}<span v-if="f.count" class="text-ink-gray-7">{{ f.count }}</span>
        </button>
      </div>
      <select :value="choice" class="form-select h-7 py-0 text-sm max-md:h-12" :aria-label="w('inbox.project_filter')" data-testid="inbox-project" @change="choose($event.target.value)">
        <option value="">{{ w('inbox.all_projects') }}</option>
        <option v-for="p in known" :key="p.name" :value="p.name">{{ p.title }}</option>
        <option :value="CLOSED">{{ w('inbox.closed_projects') }}</option>
      </select>
      <span class="ml-auto text-xs text-ink-gray-7 max-md:ml-0">{{ w('inbox.reply_hint') }}</span>
    </div>
    <p v-if="state.error" role="alert" class="m-0 text-ink-red-7" data-testid="inbox-error">{{ w('inbox.error') }}</p>
    <p v-else-if="!state.loaded || (state.loading && !state.rooms.length)" class="m-0 text-ink-gray-7">{{ w('core.loading') }}</p>
    <p v-else-if="!state.rooms.length" class="m-0 text-ink-gray-7" data-testid="inbox-empty">{{ state.query.show ? w('inbox.empty_filter') : w('inbox.empty') }}</p>
    <section v-if="groups.length" class="cw-card overflow-hidden" :aria-label="w('inbox.rooms_by_project')" data-testid="inbox-rooms">
      <div v-for="g in groups" :key="g.project" data-testid="inbox-project-group" :data-project="g.project">
        <div class="flex items-center gap-2 px-4 pb-1.5 pt-3.5">
          <span class="truncate text-sm font-semibold text-ink-gray-9">{{ g.title }}</span>
          <span class="text-xs text-ink-gray-7">{{ g.project }}</span>
          <Badge v-if="closedStatus(g.status)" size="sm" theme="gray" :label="w('inbox.closed')" />
        </div>
        <InboxRow v-for="r in g.rooms" :key="r.room" :row="r" :to="roomLink(r)" :title="nameOf(r)" :subtitle="subtitleOf(r)" />
      </div>
    </section>
    <div v-if="state.more" class="self-center">
      <Button variant="outline" :label="w('inbox.more')" :loading="state.loading" data-testid="inbox-more" @click="inbox.next()" />
    </div>
  </main>
</template>

<script setup>
import { computed, inject, onUnmounted, ref, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageHead from '../../components/PageHead.vue'
import { staffWords } from '../../approvals/words.js'
import { setInboxUnread } from '../../store.js'
import { useMode } from '../../mode.js'
import { HOST_KEY } from '../host.js'
import { roomName } from '../rooms.js'
import { wordsFor } from '../words.js'
import InboxRow from './InboxRow.vue'
import { Inbox, byProject, roomLink } from './store.js'

// The staff Discussion inbox (P3-74, canvas "Discussion inbox" frame 4, version 1792453304-ed70; design §14.6, D-414):
// every room of the reader's member projects, grouped by project, with the filters All, Unread, Needs a reply and
// Mentions me, a project choice and the closed projects behind their own choice. A row opens the room at its newest
// line, with the thread open when the line is in one. The page's host comes from its page (pages/Inbox.vue, F1).
const CLOSED = '__closed'
const CLOSED_STATES = ['Completed', 'Cancelled']
const host = inject(HOST_KEY)
const w = wordsFor(useMode())
const sw = staffWords(useMode())
const inbox = new Inbox(host)
const state = inbox.state
const known = ref([]) // the active projects, from a read with no project chosen
const groups = computed(() => byProject(state.rooms, state.projects))
const choice = computed(() => (state.query.closed ? CLOSED : state.query.project))
const filters = computed(() => [
  { id: '', label: w('inbox.all'), count: 0 },
  { id: 'unread', label: w('inbox.unread'), count: state.totals.unread || 0 },
  { id: 'reply', label: w('inbox.reply'), count: state.totals.reply || 0 },
  { id: 'mentions', label: w('inbox.mentions'), count: state.totals.mentions || 0 },
  { id: 'waiting', label: sw('inbox_waiting'), count: state.totals.waiting || 0 },
])
const nameOf = (r) => roomName(r, { viewer: 'staff', w })
const subtitleOf = (r) => (r.audience === 'Internal' ? w('core.badge_team') : '')
const closedStatus = (s) => CLOSED_STATES.includes(s)

function choose(value) {
  if (value === CLOSED) return inbox.set({ project: '', closed: 1 })
  return inbox.set({ project: value, closed: 0 })
}

watch(() => [state.projects, state.query.project, state.query.closed], ([projects, project, closed]) => {
  if (!project && !closed) known.value = projects
})
// The top bar's count follows this read: all active projects, or the one chosen (never the closed ones).
inbox.onLoad = (s) => !s.query.closed && setInboxUnread(s.totals.by_project, !s.query.project)
inbox.load()
inbox.listen()
onUnmounted(() => inbox.close())
</script>
