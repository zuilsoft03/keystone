<template>
  <div class="flex min-w-0 flex-1 flex-wrap" data-testid="projects-page">
    <AppRail :frame="lastFrame" dashboard />

    <main class="flex min-w-0 flex-[999_1_560px] flex-col gap-4 px-6 py-5">
      <PageHead crumb="Workspace / Project Dashboard" title="Projects" :meta="state.loaded ? portfolioLine(state.projects) : ''">
        <Button v-if="canCreate" variant="solid" theme="blue" size="md" icon-left="lucide-plus" label="Create project" data-testid="create-project" @click="creating = true" />
      </PageHead>
      <NewProjectDialog v-if="canCreate" v-model:open="creating" @created="created" />

      <!-- P3-58: Getting started, for System Managers; one line for each skipped set-up step, gone when none is left or on Dismiss -->
      <section v-if="todo.length" class="cw-card flex flex-col gap-2 px-4 py-3.5" aria-labelledby="sec-started" data-testid="getting-started">
        <div class="flex flex-wrap items-center gap-2.5">
          <h2 id="sec-started" class="cw-card-title flex-1">Getting started</h2>
          <Button label="Dismiss" class="max-md:!h-12" data-testid="dismiss-checklist" @click="dismiss" />
        </div>
        <a v-for="c in todo" :key="c.step" :href="checklistLink(c)" class="flex min-h-12 items-center gap-2.5 rounded-4 px-2 text-base text-ink-gray-9 no-underline hover:bg-surface-gray-2" data-testid="checklist-item">
          <span class="lucide-circle size-4 flex-none text-ink-gray-6" aria-hidden="true" />{{ c.title }}
        </a>
      </section>

      <p v-if="state.error" class="text-ink-red-7" role="alert">{{ state.error }}</p>
      <p v-else-if="!state.loaded" class="text-ink-gray-7">Loading your projects…</p>
      <template v-else>
        <div class="grid gap-3" style="grid-template-columns: repeat(auto-fit, minmax(210px, 1fr))">
          <KpiTile v-for="k in tiles" :key="k.label" v-bind="k" />
        </div>
        <ProjectMap :projects="state.projects" :counts-of="countsOf" :advanced="advanced" @open="open" />

        <div class="cw-card flex flex-wrap items-center gap-2.5 px-3 py-2.5">
          <TextInput v-model="query" class="w-full sm:w-[280px]" size="md" placeholder="Search name, code or client" aria-label="Search projects" data-testid="project-search">
            <template #prefix><span class="lucide-search size-4 text-ink-gray-6" aria-hidden="true" /></template>
          </TextInput>
          <div class="cw-tabbuttons" role="group" aria-label="Filter by status">
            <button
              v-for="[id, label] in FILTERS"
              :key="id"
              type="button"
              class="cw-tabbutton"
              :aria-pressed="filter === id"
              data-testid="filter"
              @click="filter = id"
            >{{ label }} <span class="text-ink-gray-7">{{ filterCount(state.projects, id) }}</span></button>
          </div>
          <span class="ml-auto text-sm text-ink-gray-7" data-testid="shown-count">{{ shown.length }} of {{ state.projects.length }}</span>
          <label class="flex items-center gap-2 text-sm text-ink-gray-7">
            Sort by
            <select v-model="sort" class="form-select h-7 py-0 text-sm">
              <option value="handover">Handover date</option>
              <option value="name">Name</option>
            </select>
          </label>
          <div class="cw-tabbuttons" role="group" aria-label="View">
            <button v-for="v in ['Grid', 'List']" :key="v" type="button" class="cw-tabbutton" :aria-pressed="view === v" @click="view = v">{{ v }}</button>
          </div>
        </div>

        <p v-if="!shown.length" class="text-ink-gray-7" data-testid="no-projects">
          {{ state.projects.length ? 'No project matches.' : 'You are not a member of any project yet.' }}
        </p>
        <div v-else-if="view === 'Grid'" class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(300px, 1fr))">
          <div
            v-for="p in shown"
            :key="p.name"
            class="cw-card flex cursor-pointer flex-col gap-3 px-4 py-3.5 hover:border-outline-gray-3"
            data-testid="project-card"
            :data-project="p.name"
            @click="open(p)"
          >
            <div class="flex items-start gap-2.5">
              <ProjectBadge :name="p.name" :label="p.project_name" size="lg" />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5">
                  <span class="truncate text-base font-semibold text-ink-gray-9">{{ p.project_name || p.name }}</span>
                  <Badge v-if="p.name === state.lastProject" label="Current" theme="blue" size="sm" data-testid="current-badge" />
                </div>
                <div class="truncate text-xs text-ink-gray-7">{{ p.name }}<template v-if="p.clients.length"> · {{ p.clients.join(', ') }}</template></div>
              </div>
              <Badge :label="statusOf(p.status).label" :theme="statusOf(p.status).theme" />
            </div>
            <div v-if="p.cc_phase" class="text-xs text-ink-gray-7">{{ p.cc_phase }}</div>
            <div class="grid border-t border-outline-gray-1 pt-2.5" :class="advanced ? 'grid-cols-3' : 'grid-cols-1'">
              <div v-if="advanced"><div class="text-[10px] font-semibold tracking-[0.06em] text-ink-gray-6">OPEN RFIS</div><div class="text-sm font-semibold text-ink-gray-9" data-testid="card-rfi">{{ countsOf(p.name).rfi_open || 0 }}</div></div>
              <div v-if="advanced" class="text-center"><div class="text-[10px] font-semibold tracking-[0.06em] text-ink-gray-6">SUBMITTALS</div><div class="text-sm font-semibold text-ink-gray-9">{{ countsOf(p.name).submittal_open || 0 }}</div></div>
              <div :class="advanced ? 'text-right' : ''"><div class="text-[10px] font-semibold tracking-[0.06em] text-ink-gray-6">HANDOVER</div><div class="text-sm font-semibold text-ink-gray-9" :title="handoverText(p.handover_in_days)">{{ shortDate(p.expected_end_date) || '—' }}</div></div>
            </div>
            <div class="flex items-center">
              <Button class="ml-auto" variant="solid" theme="blue" :route="home(p)" label="Open" @click.stop />
            </div>
          </div>
        </div>
        <div v-else class="cw-card overflow-x-auto">
          <div class="min-w-[640px]">
            <div class="cw-list-head grid" :class="listCols">
              <span>Project</span><span>Status</span><template v-if="advanced"><span>Open RFIs</span><span>Submittals</span></template><span>Handover</span><span />
            </div>
            <div
              v-for="p in shown"
              :key="p.name"
              class="cw-list-row grid cursor-pointer"
              :class="listCols"
              data-testid="project-card"
              :data-project="p.name"
              @click="open(p)"
            >
              <span class="flex min-w-0 items-center gap-2.5">
                <ProjectBadge :name="p.name" :label="p.project_name" size="md" />
                <span class="min-w-0"><span class="block truncate text-ink-gray-9">{{ p.project_name || p.name }}</span><span class="block truncate text-xs text-ink-gray-7">{{ p.name }}</span></span>
              </span>
              <span><Badge :label="statusOf(p.status).label" :theme="statusOf(p.status).theme" /></span>
              <template v-if="advanced">
                <span class="text-sm">{{ countsOf(p.name).rfi_open || 0 }}</span>
                <span class="text-sm">{{ countsOf(p.name).submittal_open || 0 }}</span>
              </template>
              <span class="text-sm">{{ shortDate(p.expected_end_date) || '—' }}</span>
              <span class="text-right"><Button :route="home(p)" label="Open" @click.stop /></span>
            </div>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, TextInput } from 'frappe-ui'
import AppRail from '../components/AppRail.vue'
import KpiTile from '../components/KpiTile.vue'
import PageHead from '../components/PageHead.vue'
import ProjectBadge from '../components/ProjectBadge.vue'
import NewProjectDialog from '../components/NewProjectDialog.vue'
import ProjectMap from '../components/ProjectMap.vue'
import { boot } from '../boot.js'
import { call } from '../api.js'
import { checklistLink } from '../company.js'
import { FILTERS, filterCount, handoverText, kpis, portfolioLine, shortDate, shownProjects, statusOf } from '../frame.js'
import { useMode } from '../mode.js'
import { countsOf, fetchFrame, loadProjects, state } from '../store.js'

// The projects dashboard of the live design (D-124, version 1791648865-5845), with the data the server has (D-058):
// progress, owner, contract value and member avatars wait for data; the map shows the projects with a site (P3-09).
const router = useRouter()
const filter = ref('all')
const sort = ref('handover')
const query = ref('')
const view = ref('Grid')
const shown = computed(() => shownProjects(state.projects, filter.value, sort.value, query.value))
const mode = useMode()
// Simple mode (D-154) leaves out the project-management figures: open RFIs, submittals, variations.
const advanced = computed(() => mode.value === 'advanced')
const tiles = computed(() => kpis(state.projects, countsOf, mode.value))
const listCols = computed(() => (advanced.value ? 'grid-cols-[minmax(220px,2fr)_100px_90px_90px_110px_70px]' : 'grid-cols-[minmax(220px,2fr)_100px_110px_70px]'))
const canCreate = computed(() => state.canCreate)
const home = (p) => ({ name: 'section', params: { project: p.name, section: 'home' } })
const open = (p) => router.push(home(p))
// P3-39 (D-285): a project is created here, in the New project panel; Desk's full form stays a link inside it.
const creating = ref(false)
async function created(name) {
  await loadProjects()
  router.push(home({ name }))
}

// The rail shows the last project, as the design's dashboard does; none yet, the rail is the tile alone.
const lastFrame = computed(() => state.frames[state.lastProject] || null)
watch(() => state.lastProject, (name) => {
  if (name && !state.frames[name]) fetchFrame(name).catch(() => {})
}, { immediate: true })

// The Getting started card (P3-58): the server lists the skipped steps; a failed read just leaves the card out.
const todo = ref([])
onMounted(async () => {
  if (!boot.system_manager) return
  try {
    const page = await call('construction_core.accounts.company.page')
    todo.value = page.checklist_dismissed ? [] : page.checklist
  } catch { /* no card */ }
})
async function dismiss() {
  await call('construction_core.accounts.company.dismiss_checklist', {}, { post: true })
  todo.value = []
}
</script>
