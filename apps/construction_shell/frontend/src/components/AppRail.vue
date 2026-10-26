<template>
  <nav aria-label="Workspace" class="flex w-full flex-col border-r border-outline-gray-2 bg-surface-base md:min-h-0 md:w-[224px] md:flex-none md:overflow-y-auto md:overflow-x-hidden max-md:border-b max-md:border-r-0" data-testid="rail">
    <button v-if="folded" type="button" class="flex h-12 w-full flex-none items-center gap-2.5 px-4 text-left text-base text-ink-gray-9"
      :aria-expanded="open ? 'true' : 'false'" aria-controls="rail-body" data-testid="rail-toggle" @click="open = !open">
      <span class="lucide-menu size-5 flex-none text-ink-gray-7" aria-hidden="true" />
      <span class="min-w-0 flex-1 truncate font-semibold">{{ frame.project.project_name || frame.project.name }}</span>
      <Badge v-if="unread" variant="solid" theme="red" size="sm" :label="String(unread)" :aria-label="chatWord('core.unread', { mode, values: { count: unread } })" />
      <span :class="open ? 'lucide-chevron-up' : 'lucide-chevron-down'" class="size-4 flex-none text-ink-gray-7" aria-hidden="true" />
    </button>
    <div v-show="!folded || open" id="rail-body" class="flex flex-col">
    <div class="flex flex-col gap-2 px-2.5 pb-1.5 pt-2.5">
      <router-link
        :to="{ name: 'projects' }"
        class="relative flex items-center gap-2 overflow-hidden rounded-5 bg-surface-gray-10 p-2.5 text-ink-base no-underline shadow-md dark:border dark:border-outline-gray-2 dark:bg-surface-base dark:text-ink-gray-9"
        :aria-current="dashboard ? 'page' : undefined"
        data-testid="dashboard-tile"
      >
        <svg class="absolute -right-2.5 -top-1.5 h-14 w-24 fill-surface-gray-8 opacity-35 dark:fill-surface-gray-3" viewBox="0 0 96 56" aria-hidden="true">
          <rect v-for="(x, i) in [0, 24, 48, 72, 0, 24, 48, 72]" :key="i" :x="x" :y="i < 4 ? 0 : 24" width="20" height="20" rx="5" />
        </svg>
        <span class="relative grid size-8 flex-none place-items-center rounded-4 bg-surface-blue-6">
          <span class="lucide-layout-grid size-4" aria-hidden="true" />
        </span>
        <span class="relative min-w-0 flex-1 leading-tight">
          <span class="block truncate text-sm font-semibold tracking-normal">Project Dashboard</span>
          <span class="mt-[3px] flex items-center gap-1.5 text-[11px] text-ink-gray-3 dark:text-ink-gray-7">
            <span class="inline-flex" aria-hidden="true">
              <span class="size-2 rounded-full bg-surface-blue-5 ring-2 ring-[color:var(--surface-gray-10)] dark:ring-[color:var(--surface-base)]" />
              <span class="-ml-0.5 size-2 rounded-full bg-surface-green-5 ring-2 ring-[color:var(--surface-gray-10)] dark:ring-[color:var(--surface-base)]" />
              <span class="-ml-0.5 size-2 rounded-full bg-surface-amber-5 ring-2 ring-[color:var(--surface-gray-10)] dark:ring-[color:var(--surface-base)]" />
            </span>
            <span class="truncate" data-testid="portfolio">{{ state.loaded ? portfolioLine(state.projects) : 'Your projects' }}</span>
          </span>
        </span>
        <span class="lucide-chevron-right relative size-3.5 flex-none" aria-hidden="true" />
      </router-link>
      <ProjectSwitcher v-if="frame" :frame="frame" />
    </div>
    <div v-if="frame" class="flex flex-col gap-0.5 px-2.5 py-1">
      <template v-for="item in items" :key="item.section">
        <div v-if="item.divider" class="mx-1 my-1.5 border-t border-outline-gray-1" aria-hidden="true" />
        <router-link
          :to="{ name: 'section', params: { project: frame.project.name, section: item.section } }"
          class="flex h-[34px] items-center gap-2.5 rounded-4 px-2.5 text-base no-underline"
          :class="!dashboard && item.section === section ? 'bg-surface-blue-1 font-semibold text-ink-blue-8' : 'text-ink-gray-8 hover:bg-surface-gray-2'"
          :aria-current="!dashboard && item.section === section ? 'page' : undefined"
          data-testid="rail-item"
          :data-section="item.section"
        >
          <SectionIcon :section="item.section" />
          <span class="truncate">{{ item.label }}</span>
          <Badge
            v-if="item.section === 'discuss' && unread"
            class="ml-auto"
            variant="solid"
            theme="red"
            size="sm"
            :label="String(unread)"
            :aria-label="chatWord('core.unread', { mode, values: { count: unread } })"
            data-testid="rail-unread"
          />
          <Badge
            v-else-if="item.count_key && counts[item.count_key]"
            class="ml-auto"
            variant="solid"
            theme="red"
            size="sm"
            :label="String(counts[item.count_key])"
            :aria-label="`${counts[item.count_key]} open`"
            data-testid="rail-count"
          />
        </router-link>
      </template>
    </div>
    </div>
  </nav>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Badge } from 'frappe-ui'
import { isPhone } from '../portal/state.js'
import { chatWord } from '../chat/words.js'
import ProjectSwitcher from './ProjectSwitcher.vue'
import SectionIcon from './SectionIcon.vue'
import { portfolioLine, railGroups, visibleRail } from '../frame.js'
import { SECTIONS } from '../paths.js'
import { useMode } from '../mode.js'
import { chatUnreadOf, countsOf, state } from '../store.js'

// The staff rail of the live design (D-124, version 1791699712-925e): the dark Project Dashboard tile, dark in both
// themes (D-169), the current project's switcher card, then its sections in the design's groups. The same rail on the
// dashboard (for the last project) and on every project page. Search, help, notifications and "All services online" have no data and are not
// drawn (D-058).
const props = defineProps({
  frame: { type: Object, default: null },
  section: { type: String, default: '' },
  dashboard: { type: Boolean, default: false },
  // P3-64: on a phone a project's rail folds into one bar over the page, so the page keeps the screen (canvas frame 2).
  collapsible: { type: Boolean, default: false },
})
const open = ref(false)
const folded = computed(() => props.collapsible && isPhone.value && Boolean(props.frame))
watch(() => props.section, () => (open.value = false))
const mode = useMode()
// Simple lists its own sections (D-161), and the one open now; Advanced lists the whole rail (D-154).
// A page never on the rail (sections.json `rail: false`, the client view) stays off it, even if a Workspace Section row
// names it.
const onRail = computed(() => (props.frame?.rail || []).filter((i) => SECTIONS[i.section]?.rail !== false))
const items = computed(() => railGroups(visibleRail(onRail.value, mode.value, props.dashboard ? '' : props.section)))
// Live: the store's counts, which cc_workspace_counts updates (App.vue).
const counts = computed(() => countsOf(props.frame?.project.name))
// P3-64: Discuss shows the reader's unread room messages: the store's count, which the frame brings and the Discuss
// page's chat host keeps current (F1: only pages make a host).
const unread = computed(() => (props.dashboard || !props.frame ? 0 : chatUnreadOf(props.frame.project.name)))
</script>
