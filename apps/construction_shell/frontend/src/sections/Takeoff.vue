<template>
  <TakeoffView v-if="item" :key="item" :name="item" :project="project" />
  <div v-else class="flex flex-col gap-3.5 px-6 py-5" data-testid="section-page">
    <PageHead :crumb="`Workspace / ${label}`" :title="label" meta="DXF and PDF drawings, measured on the server">
      <Button variant="solid" theme="blue" size="md" icon-left="lucide-plus" label="New drawing" data-testid="new-drawing" @click="toggleNew" />
    </PageHead>
    <form v-if="creating" class="cw-card flex flex-wrap items-end gap-3 p-4" @submit.prevent="create">
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Title
        <input v-model="draft.title" required maxlength="140" class="form-input w-64" data-testid="drawing-title" />
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Drawing file (DXF or PDF)
        <select v-model="draft.file" required class="form-select w-72 py-0" data-testid="drawing-file">
          <option value="" disabled>Choose a project file</option>
          <option v-for="f in drawingFiles" :key="f.name" :value="f.file_url">{{ f.file_name }}</option>
        </select>
      </label>
      <label v-if="isPdf" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Page
        <input v-model.number="draft.page" type="number" min="1" class="form-input w-20" />
      </label>
      <Button type="submit" variant="solid" theme="blue" label="Create" data-testid="create-drawing" />
      <p class="w-full text-xs text-ink-gray-7">Upload the file in Files first. A DWG drawing must be saved as DXF from the CAD program.</p>
    </form>
    <p v-if="error" class="text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
    <section class="cw-card overflow-x-auto">
      <table class="w-full min-w-[560px] text-left">
        <thead class="bg-surface-gray-1 text-[11px] uppercase tracking-[0.06em] text-ink-gray-7">
          <tr><th class="h-8 px-4 font-semibold">Drawing</th><th class="h-8 px-4 font-semibold">Source</th><th class="h-8 px-4 font-semibold">Units</th><th class="h-8 px-4 font-semibold">Scale</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in drawings" :key="d.name" class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1" data-testid="drawing-row" @click="open(d.name)">
            <td class="px-4 py-2.5 text-base text-ink-gray-9">{{ d.title }}</td>
            <td class="px-4 py-2.5"><Badge size="sm" :theme="d.source === 'PDF' ? 'red' : 'violet'" :label="d.source === 'PDF' ? `PDF p. ${d.page}` : d.source" /></td>
            <td class="px-4 py-2.5 text-sm text-ink-gray-7">{{ d.units || '—' }}</td>
            <td class="px-4 py-2.5 text-sm text-ink-gray-7">{{ d.calibrated ? 'calibrated' : d.unit_to_m ? 'from the file' : 'not set' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!drawings.length" class="border-t border-outline-gray-1 px-4 py-3 text-ink-gray-7">No drawing yet.</p>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageHead from '../components/PageHead.vue'
import TakeoffView from '../components/TakeoffView.vue'
import { call } from '../api.js'
import { useMode } from '../mode.js'
import { sectionLabel } from '../words.js'

const props = defineProps({ frame: Object, project: String, section: String })
const mode = useMode()
const label = computed(() => sectionLabel('takeoff', mode.value)) // Measure in Simple mode (D-162)
const route = useRoute()
const router = useRouter()
const item = computed(() => route.params.item)
const drawings = ref([])
const files = ref([])
const creating = ref(false)
const draft = reactive({ title: '', file: '', page: 1 })
const error = ref('')
const drawingFiles = computed(() => files.value.filter((f) => /\.(dxf|pdf)$/i.test(f.file_name)))
const isPdf = computed(() => /\.pdf$/i.test(draft.file))

// The project's files can change while the list is open (an upload in Files): reload them for the form.
async function toggleNew() {
  creating.value = !creating.value
  if (creating.value) {
    try {
      files.value = (await call('construction_shell.api.record_options', { project: props.project })).files
    } catch (e) {
      error.value = e.message
    }
  }
}

function open(name) {
  router.push({ name: 'section', params: { project: props.project, section: 'takeoff', item: name } })
}

async function load() {
  try {
    const [list, options] = await Promise.all([
      call('frappe.client.get_list', {
        doctype: 'CAD Drawing', filters: { project: props.project },
        fields: ['name', 'title', 'source', 'page', 'units', 'unit_to_m', 'calibrated'], order_by: 'modified desc', limit_page_length: 500,
      }),
      call('construction_shell.api.record_options', { project: props.project }),
    ])
    drawings.value = list
    files.value = options.files
  } catch (e) {
    error.value = e.message
  }
}

async function create() {
  error.value = ''
  try {
    const d = await call('frappe.client.insert', {
      doc: { doctype: 'CAD Drawing', project: props.project, title: draft.title, file: draft.file, page: isPdf.value ? draft.page : 0 },
    }, { post: true })
    creating.value = false
    open(d.name)
  } catch (e) {
    error.value = e.message
  }
}

watch(() => [props.project, item.value], () => !item.value && load(), { immediate: true })
</script>
