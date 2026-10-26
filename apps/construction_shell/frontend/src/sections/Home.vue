<template>
  <div class="flex flex-col gap-4 px-6 py-5" data-testid="section-page">
    <PageHead crumb="Workspace / Home" title="Dashboard">
      <template #meta>
        <span class="inline-flex flex-wrap items-center gap-2">
          <span data-testid="home-project">{{ p.project_name || p.name }}</span>
          <Badge :label="statusOf(p.status).label" :theme="statusOf(p.status).theme" />
          <Badge v-if="p.cc_phase" :label="p.cc_phase" theme="gray" />
        </span>
      </template>
      <template v-if="clientEntry">
        <Dropdown v-if="clientEntry.options" :options="clientEntry.options" align="end">
          <Button variant="outline" size="md" icon-left="lucide-monitor" label="Preview client portal" data-testid="view-as-client" />
        </Dropdown>
        <Button v-else variant="outline" size="md" icon-left="lucide-monitor" label="Preview client portal" :route="clientEntry.route" data-testid="view-as-client" />
      </template>
      <Dropdown v-if="quick.length" :options="quick" align="end">
        <Button variant="solid" theme="blue" size="md" icon-left="lucide-plus" label="Quick actions" data-testid="quick-actions" />
      </Dropdown>
    </PageHead>

    <div v-if="advanced || p.handover_in_days !== null" class="grid gap-3" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))">
      <template v-if="advanced">
        <KpiTile label="Open RFIs" :value="String(counts.rfi_open || 0)" sub="issued, awaiting an answer" />
        <KpiTile label="Pending submittals" :value="String(counts.submittal_open || 0)" sub="under review" />
        <KpiTile label="Open variations" :value="String(counts.vo_open || 0)" sub="change order requests" />
      </template>
      <KpiTile v-if="p.handover_in_days !== null" label="Days to handover" :value="handoverValue" :sub="shortDate(p.expected_end_date)" :sub-class="p.handover_in_days < 0 ? 'text-ink-red-7' : ''" />
    </div>

    <div class="flex flex-wrap items-start gap-3">
      <section v-if="advanced" class="cw-card min-w-0 flex-[2_1_420px] overflow-hidden" aria-labelledby="attention-h">
        <div class="cw-card-header">
          <h2 id="attention-h" class="cw-card-title">Needs your attention</h2>
          <Badge v-if="items.length" class="ml-auto" theme="red" size="sm" :label="String(items.length)" />
        </div>
        <p v-if="loading" class="px-4 py-3 text-ink-gray-7">Loading…</p>
        <p v-else-if="!items.length" class="px-4 py-3 text-ink-gray-7" data-testid="attention-empty">Nothing open right now.</p>
        <router-link
          v-for="(i, at) in items"
          :key="i.name"
          :to="{ name: 'section', params: { project: p.name, section: i.section, item: i.name } }"
          class="cw-list-row !items-start"
          :class="{ '!border-t-0': at === 0 }"
          data-testid="attention-item"
        >
          <span class="mt-[5px] size-2 flex-none rounded-full" :class="dotClass(i)" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm text-ink-gray-9"><strong class="font-semibold">{{ i.name }}</strong> {{ said(i.text) }}</span>
            <span class="block text-xs" :class="i.due_in_days !== null && i.due_in_days <= 0 ? 'text-ink-red-7' : 'text-ink-gray-7'">{{ dueText(i.due_in_days) || sectionLabel(i.section, mode) }}</span>
          </span>
        </router-link>
      </section>

      <section class="cw-card min-w-0 flex-[1_1_300px] px-4 py-3.5" aria-labelledby="portal-h">
        <div class="flex items-center">
          <h2 id="portal-h" class="cw-card-title">Client portal</h2>
          <router-link v-if="hasSettings" :to="{ name: 'section', params: { project: p.name, section: 'settings' } }" class="ml-auto text-sm text-ink-blue-link">Manage</router-link>
        </div>
        <p class="mb-2.5 mt-1.5 text-sm text-ink-gray-7">
          <template v-if="!frame.client_portal_enabled">The client portal is off for this project.</template>
          <template v-else-if="frame.clients.length">{{ frame.clients.length }} client {{ frame.clients.length === 1 ? 'contact' : 'contacts' }}. Switched on for clients:</template>
          <template v-else>No client contact yet. Switched on for clients:</template>
        </p>
        <div class="flex flex-wrap gap-1.5" data-testid="client-sections">
          <Badge v-for="s in frame.client_sections.filter((x) => SECTIONS[x]?.rail !== false)" :key="s" theme="blue" :label="sectionLabel(s, mode)" />
        </div>
        <p v-if="frame.client_portal_enabled" class="mb-0 mt-2.5 text-xs text-ink-gray-7">Each client sees these in their own Simple or Advanced view.</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, Dropdown } from 'frappe-ui'
import KpiTile from '../components/KpiTile.vue'
import PageHead from '../components/PageHead.vue'
import { call } from '../api.js'
import { dueText, shortDate, statusOf } from '../frame.js'
import { plain } from '../chat/tokens.js'
import { wordsFor } from '../chat/words.js'
import { useMode } from '../mode.js'
import { sectionLabel, shows } from '../words.js'
import { clientViewEntry } from '../portal/tabs.js'
import { SECTIONS } from '../paths.js'
import { countsOf } from '../store.js'

// The project home of the live design (D-124, version 1791699712-925e). The phase stepper and recent activity have no
// data yet and are not drawn (D-058); Quick actions are the create forms the rail already offers; "Preview client
// portal" opens the staff preview of a client's portal (P3-05).
const props = defineProps({ frame: { type: Object, required: true }, project: String, section: String })
const p = computed(() => props.frame.project)
const counts = computed(() => countsOf(p.value.name))
const mode = useMode()
// Simple mode (D-154) leaves out the project-management figures and the open-items list, which hold only RFIs,
// submittals and variations; Quick actions offer only the sections this mode lists.
const advanced = computed(() => mode.value === 'advanced')
const hasSettings = computed(() => props.frame.rail.some((i) => i.section === 'settings'))
const handoverValue = computed(() => {
  const d = p.value.handover_in_days
  return d >= 0 ? String(d) : `${-d} late`
})
const CREATE = [
  ['rfi', 'New RFI', 'lucide-circle-help'],
  ['submittals', 'New submittal', 'lucide-square-check'],
  ['variations', 'New variation', 'lucide-arrow-left-right'],
  ['documents', 'New document', 'lucide-file-text'],
]
const quick = computed(() =>
  CREATE.filter(([s]) => shows(s, mode.value) && props.frame.rail.some((i) => i.section === s)).map(([section, label, icon]) => ({
    label,
    icon,
    route: { name: 'section', params: { project: p.value.name, section, item: 'new' } },
  })),
)
// The staff preview of a client's portal (P3-05, D-136), labelled and placed as the live design draws it (D-172): one
// contact opens it, several give a list, none draw nothing (D-058). The server lists the contacts and checks each call.
const clientContacts = ref([])
const clientEntry = computed(() => clientViewEntry(props.project, clientContacts.value))
watch(() => props.project, async (project) => {
  try {
    clientContacts.value = await call('construction_core.portal_preview.contacts', { project })
  } catch {
    clientContacts.value = []
  }
}, { immediate: true })
const items = ref([])
const loading = ref(true)

function dotClass(i) {
  if (i.due_in_days !== null && i.due_in_days <= 0) return 'bg-surface-red-6'
  if (i.due_in_days !== null && i.due_in_days <= 3) return 'bg-surface-amber-6'
  return 'bg-surface-blue-6'
}

async function load() {
  if (!advanced.value) return // Simple draws no open-items list
  loading.value = true
  try {
    items.value = (await call('construction_shell.api.attention', { project: p.value.name })).items
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

// Reload when the project changes and when its counts change (an item opened or closed elsewhere).
watch(() => [p.value.name, JSON.stringify(counts.value), mode.value], load, { immediate: true })

// P3-66: a message's mentions and tags read as words here, never as tokens
const chatW = wordsFor(mode)
const said = (text) => plain(text, chatW)
</script>
