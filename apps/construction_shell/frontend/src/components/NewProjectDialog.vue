<template>
  <!-- P3-39 (D-285): create a project inside the workspace, in place of Desk's form. Built from the design's dialogs and
       Settings fields (D-196). The server's own rules decide: create permission, the contract date (D-071), a site's
       both-or-neither coordinates (P3-09); the creator becomes a member and the workspace and its folders are made. -->
  <Dialog v-model:open="open" title="New project" description="The project gets its code (PROJ-…), its folders and its workspace when you create it. You are added to its team.">
    <form id="new-project-form" class="flex flex-col gap-3" data-testid="new-project" @submit.prevent="create">
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Project name
        <input v-model="name" maxlength="140" required class="form-input w-full" placeholder="Example: Costa Hiraya Villa" data-testid="np-name" />
      </label>
      <div class="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Contract signed on <span class="text-ink-gray-6">A project starts at contract signature</span>
          <input v-model="signed" type="date" required class="form-input w-full" data-testid="np-signed" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Phase <span class="text-ink-gray-6">Optional</span>
          <input v-model="phase" maxlength="140" list="np-phases" class="form-input w-full" placeholder="Example: Design development" data-testid="np-phase" />
          <datalist id="np-phases"><option v-for="p in PHASES" :key="p" :value="p" /></datalist>
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Start date <span class="text-ink-gray-6">Optional</span>
          <input v-model="start" type="date" class="form-input w-full" data-testid="np-start" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Handover date <span class="text-ink-gray-6">Optional</span>
          <input v-model="end" type="date" :min="start || undefined" class="form-input w-full" data-testid="np-end" />
        </label>
      </div>
      <label v-if="templates.length > 1" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Folders <span class="text-ink-gray-6">The folder set the project starts with</span>
        <select v-model="template" class="form-select w-full" data-testid="np-template">
          <option v-for="t in templates" :key="t" :value="t">{{ t }}</option>
        </select>
      </label>
      <fieldset class="m-0 flex flex-col gap-1.5 border-0 p-0">
        <legend class="mb-1.5 p-0 text-xs text-ink-gray-7">Site location <span class="text-ink-gray-6">Optional. The team sees it on the project map; clients never do.</span></legend>
        <input v-model="place" maxlength="140" class="form-input w-full" placeholder="Example: Quezon City, Metro Manila" aria-label="Site place" data-testid="np-place" />
        <SitePicker v-if="open" v-model="pin" />
      </fieldset>
      <p v-if="error" role="alert" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="np-error">{{ error }}</p>
    </form>
    <template #actions="{ close }">
      <div class="flex flex-wrap items-center justify-end gap-2">
        <a href="/app/construction-project/new" class="mr-auto text-sm text-ink-gray-7 underline underline-offset-2" data-testid="np-desk">Open the full form in Desk</a>
        <Button label="Cancel" @click="close" />
        <Button type="submit" form="new-project-form" variant="solid" theme="blue" :label="busy ? 'Creating…' : 'Create project'" :disabled="busy || !name.trim() || !signed || datesWrong" data-testid="np-create" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import SitePicker from './SitePicker.vue'
import { call } from '../api.js'

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['created'])
const PHASES = ['Concept', 'Schematic design', 'Design development', 'Construction documents', 'Construction', 'Handover']
const today = () => new Date().toISOString().slice(0, 10)
const name = ref('')
const signed = ref(today())
const phase = ref('')
const start = ref('')
const end = ref('')
const place = ref('')
const pin = ref(null)
const templates = ref([])
const template = ref('')
const busy = ref(false)
const error = ref('')
const datesWrong = computed(() => !!(start.value && end.value && end.value < start.value))

watch(open, async (now) => {
  if (!now) return
  name.value = phase.value = start.value = end.value = place.value = error.value = ''
  signed.value = today()
  pin.value = null
  try {
    const rows = await call('frappe.client.get_list', { doctype: 'Folder Template', fields: ['name'], limit_page_length: 50, order_by: 'name asc' })
    templates.value = rows.map((r) => r.name)
    template.value = templates.value.includes('Standard') ? 'Standard' : templates.value[0] || ''
  } catch {
    templates.value = [] // the server's default set then
  }
})

async function create() {
  if (busy.value || datesWrong.value) return
  busy.value = true
  error.value = ''
  try {
    const doc = await call('frappe.client.insert', {
      doc: {
        doctype: 'Construction Project',
        project_name: name.value.trim(),
        status: 'Open',
        cc_workspace_enabled: 1,
        cc_contract_signed_on: signed.value,
        cc_phase: phase.value.trim() || null,
        expected_start_date: start.value || null,
        expected_end_date: end.value || null,
        cc_folder_template: template.value || null,
        cc_site_place: place.value.trim() || null,
        cc_latitude: pin.value ? pin.value.lat : null,
        cc_longitude: pin.value ? pin.value.lng : null,
      },
    }, { post: true })
    open.value = false
    emit('created', doc.name)
  } catch (e) {
    error.value = e.message || 'The project could not be created.'
  } finally {
    busy.value = false
  }
}
</script>
