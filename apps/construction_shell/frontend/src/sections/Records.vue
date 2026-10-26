<template>
  <div class="flex flex-col gap-3.5 px-6 py-5" data-testid="section-page">
    <p v-if="error" class="text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
    <p v-if="!meta" class="text-ink-gray-7">Loading…</p>

    <!-- The list -->
    <template v-else-if="!item">
      <PageHead :crumb="`Workspace / ${label}`" :title="label" :meta="`${frame.project.name} · ${frame.project.project_name || ''}`">
        <Button variant="solid" theme="blue" size="md" icon-left="lucide-plus" :label="newLabel(section, mode)"
          :route="{ name: 'section', params: { project, section, item: 'new' } }" data-testid="new-record" />
      </PageHead>
      <section class="cw-card overflow-hidden">
        <div class="flex flex-wrap gap-x-1 border-b border-outline-gray-1 px-2" role="tablist" aria-label="Filter by state">
          <button v-for="s in ['all', ...meta.states]" :key="s" type="button" role="tab" :aria-selected="stateFilter === s"
            class="-mb-px inline-flex h-9 items-center gap-1.5 border-b px-2.5 text-base"
            :class="stateFilter === s ? 'border-outline-gray-8 text-ink-gray-9' : 'border-transparent text-ink-gray-6 hover:text-ink-gray-7'"
            data-testid="state-filter" @click="stateFilter = s"
          >{{ s === 'all' ? 'All' : stateLabel(s, mode) }} <Badge size="sm" :label="String(s === 'all' ? rows.length : counts[s] || 0)" /></button>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[640px] text-left">
            <thead class="bg-surface-gray-1 text-[11px] uppercase tracking-[0.06em] text-ink-gray-7">
              <tr><th class="h-8 px-4 font-semibold">Number</th><th v-for="c in meta.columns" :key="c.fieldname" class="h-8 px-4 font-semibold">{{ c.label }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in shown" :key="r.name" class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1" data-testid="record-row" @click="open(r.name)">
                <td class="whitespace-nowrap px-4 py-2.5 font-mono text-xs font-semibold">
                  <router-link :to="{ name: 'section', params: { project, section, item: r.name } }" class="text-ink-blue-8 no-underline">{{ r.name }}</router-link>
                </td>
                <td v-for="c in meta.columns" :key="c.fieldname" class="px-4 py-2.5" :class="c.fieldname === meta.title_field ? 'text-base text-ink-gray-9' : 'text-sm text-ink-gray-7'">
                  <Badge v-if="c.fieldname === meta.state_field" :label="stateLabel(r[c.fieldname], mode)" :theme="stateTheme(r[c.fieldname])" />
                  <template v-else>{{ display(c, r[c.fieldname]) }}</template>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="!shown.length" class="border-t border-outline-gray-1 px-4 py-3 text-ink-gray-7" data-testid="no-records">Nothing here yet.</p>
        </div>
      </section>
    </template>

    <!-- One record, or a new one -->
    <template v-else-if="doc">
      <div class="text-xs text-ink-gray-7">
        <router-link :to="{ name: 'section', params: { project, section } }" class="text-ink-gray-7 no-underline hover:text-ink-gray-9">← {{ label }}</router-link>
      </div>
      <div class="flex flex-wrap items-end gap-3">
        <div class="min-w-0 flex-[1_1_320px]">
          <div v-if="!isNew" class="flex flex-wrap items-center gap-1.5">
            <span class="font-mono text-xs font-semibold text-ink-blue-8">{{ doc.name }}</span>
            <Badge :label="stateLabel(doc[meta.state_field], mode)" :theme="stateTheme(doc[meta.state_field])" data-testid="record-state" />
          </div>
          <h1 class="mt-1 text-3xl-semibold text-ink-gray-9" data-testid="record-title">{{ isNew ? newTitle : doc[meta.title_field] || doc.name }}</h1>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button v-for="t in nextStates" :key="t" variant="outline" size="md" :label="stateLabel(t, mode)" :disabled="busy || Boolean(gatedReason(gate, t))" data-testid="transition" @click="move(t)" />
          <Button v-if="!isNew" class="max-md:!h-12" variant="outline" size="md" icon-left="lucide-messages-square" :label="chatWord('refs.discuss_this', { mode })" data-testid="discuss-this" @click="discuss?.start(meta.doctype, doc.name)" />
          <Button v-if="!isNew && askable" class="max-md:!h-12" variant="outline" size="md" icon-left="lucide-square-check" :label="sw('picker_menu')" data-testid="ask-approval" @click="asking = true" />
          <a v-if="!isNew" :href="`/app/${slug}/${encodeURIComponent(doc.name)}`" class="text-sm text-ink-blue-link">Open in Desk</a>
        </div>
      </div>
      <p v-if="blocked" class="m-0 -mt-1 flex flex-wrap items-center gap-x-2 text-sm text-ink-gray-7" data-testid="gate-reason">
        {{ blocked }}
        <router-link v-if="gate.fix === 'approvers'" :to="{ name: 'section', params: { project, section: 'settings' } }" class="text-ink-blue-link" data-testid="gate-fix">{{ sw('gate_fix_approvers') }}</router-link>
      </p>
      <form class="cw-card grid max-w-3xl gap-4 p-5 md:grid-cols-2" @submit.prevent="save">
        <div v-for="f in meta.fields" :key="f.fieldname" :class="wide(f) ? 'md:col-span-2' : ''">
          <template v-if="f.fieldtype === 'Check'">
            <label class="flex items-center gap-2 text-base">
              <input v-model="doc[f.fieldname]" type="checkbox" class="form-checkbox rounded-1" :true-value="1" :false-value="0" :disabled="!canEdit(f)" :data-field="f.fieldname" />
              {{ f.label }}
            </label>
          </template>
          <template v-else>
            <label class="mb-1.5 block text-xs text-ink-gray-7" :for="`f-${f.fieldname}`">{{ f.label }}<span v-if="f.reqd" class="text-ink-red-7" aria-hidden="true"> *</span></label>
            <template v-if="!canEdit(f)">
              <div class="min-h-7 whitespace-pre-wrap py-1 text-ink-gray-9" :id="`f-${f.fieldname}`" :data-field="f.fieldname">{{ display(f, doc[f.fieldname]) || '—' }}</div>
            </template>
            <textarea v-else-if="f.fieldtype === 'Text Editor' || f.fieldtype === 'Small Text'" :id="`f-${f.fieldname}`" v-model="text[f.fieldname]"
              rows="4" class="form-textarea h-auto w-full" :data-field="f.fieldname" />
            <select v-else-if="f.fieldtype === 'Select'" :id="`f-${f.fieldname}`" v-model="doc[f.fieldname]" class="form-select w-full py-0" :data-field="f.fieldname">
              <option v-for="o in f.options" :key="o" :value="o">{{ o || '—' }}</option>
            </select>
            <select v-else-if="f.fieldtype === 'Link' && f.options === 'User'" :id="`f-${f.fieldname}`" v-model="doc[f.fieldname]" class="form-select w-full py-0" :data-field="f.fieldname">
              <option value="">—</option>
              <option v-for="m in options.members" :key="m.user" :value="m.user">{{ m.name }}</option>
            </select>
            <select v-else-if="f.fieldtype === 'Link' && f.options === 'File'" :id="`f-${f.fieldname}`" v-model="doc[f.fieldname]" class="form-select w-full py-0" :data-field="f.fieldname">
              <option value="">—</option>
              <option v-for="file in options.files" :key="file.name" :value="file.name">{{ file.file_name }}</option>
            </select>
            <input v-else :id="`f-${f.fieldname}`" v-model="doc[f.fieldname]" :type="inputType(f)" class="form-input w-full" :data-field="f.fieldname" />
          </template>
        </div>
        <div class="flex items-center gap-3 md:col-span-2">
          <Button type="submit" variant="solid" theme="blue" size="md" :label="isNew ? 'Create' : 'Save'" :disabled="busy || (!isNew && !dirty)" data-testid="save" />
          <span v-if="saved" class="text-sm text-ink-green-7" data-testid="saved">Saved</span>
        </div>
      </form>
    </template>
    <DiscussThis ref="discuss" :project="project" />
    <AskSheet v-if="askable" v-model:open="asking" :project="project" :doctype="meta?.doctype || ''" :name="doc?.name || ''" />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import DiscussThis from '../components/DiscussThis.vue'
import PageHead from '../components/PageHead.vue'
import AskSheet from '../approvals/staff/AskSheet.vue'
import { SECTION_OF } from '../approvals/staff/ask.js'
import { gatedReason } from '../approvals/staff/request.js'
import { staffWords } from '../approvals/words.js'
import { chatWord } from '../chat/words.js'
import { call, updateDoc } from '../api.js'
import { useMode } from '../mode.js'
import { newLabel, noun, sectionLabel, stateLabel } from '../words.js'
import { changes, countByState, editableFields, formatDate, plainText, saveConfirming, stateTheme } from './util.js'

// The records sections (RFIs, Submittals, Variations, Documents) as the live design draws its Project Management screen
// (D-124, version 1791648865-5845): the page header, state tabs with counts, mono numbers and state badges. One rail
// entry per section stays until OD-3 is decided (R-11).
const props = defineProps({ frame: Object, project: String, section: String })
const router = useRouter()
const route = router.currentRoute
const item = computed(() => route.value.params.item)
const isNew = computed(() => item.value === 'new')
// The words follow the person's mode (D-155, D-162); the stored states and the transitions sent stay as they are.
const mode = useMode()
const label = computed(() => sectionLabel(props.section, mode.value))
const newTitle = computed(() => (mode.value === 'advanced' ? `New ${meta.value.doctype}` : `New ${noun(props.section, mode.value)}`))
const slug = computed(() => (meta.value ? meta.value.doctype.toLowerCase().replace(/ /g, '-') : ''))

const sw = staffWords(mode)
const asking = ref(false) // "Ask the client to approve…" (P3-80): the Ask sheet, for the kinds that can be sent
const askable = computed(() => Boolean(meta.value && SECTION_OF[meta.value.doctype] && !isNew.value))
const gate = ref(null) // staff.gate (P3-80, O4): why the record's gated move waits for the client, if it does
const blocked = computed(() => nextStates.value.map((t) => gatedReason(gate.value, t)).find(Boolean) || '')
const discuss = ref(null) // "Discuss this" (P3-66, design §3.5): the record's conversation
const meta = ref(null)
const options = reactive({ members: [], files: [] })
const rows = ref([])
const stateFilter = ref('all')
const doc = ref(null)
const original = ref({})
const text = reactive({})
const error = ref('')
const busy = ref(false)
const saved = ref(false)

const counts = computed(() => (meta.value ? countByState(rows.value, meta.value.state_field) : {}))
const shown = computed(() => rows.value.filter((r) => stateFilter.value === 'all' || r[meta.value.state_field] === stateFilter.value))
const nextStates = computed(() => (meta.value && doc.value && !isNew.value ? meta.value.transitions[doc.value[meta.value.state_field]] || [] : []))
const editable = computed(() => (meta.value ? editableFields(meta.value) : []))
const dirty = computed(() => Object.keys(pending()).length > 0)

function canEdit(f) {
  return editable.value.includes(f)
}
function wide(f) {
  return ['Text Editor', 'Small Text'].includes(f.fieldtype) || f.fieldname === meta.value.title_field
}
function inputType(f) {
  return { Date: 'date', Int: 'number', Float: 'number', Currency: 'number' }[f.fieldtype] || 'text'
}
function display(f, value) {
  if (value === null || value === undefined || value === '') return ''
  if (f.fieldtype === 'Text Editor') return plainText(value)
  if (f.fieldtype === 'Date' || f.fieldtype === 'Datetime') return formatDate(value)
  if (f.fieldtype === 'Check') return value ? 'Yes' : 'No'
  if (f.fieldtype === 'Link' && f.options === 'User') return options.members.find((m) => m.user === value)?.name || value
  if (f.fieldtype === 'Link' && f.options === 'File') return options.files.find((x) => x.name === value)?.file_name || value
  if (f.fieldtype === 'Currency') return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2 })
  return String(value)
}
// Text Editor values are edited as plain text and sent back as text (Frappe sanitises them on save).
function pending() {
  if (!doc.value || !meta.value) return {}
  const current = { ...doc.value }
  for (const f of editable.value) if (f.fieldname in text) current[f.fieldname] = text[f.fieldname]
  const base = { ...original.value }
  for (const f of editable.value) if (f.fieldtype === 'Text Editor') base[f.fieldname] = plainText(base[f.fieldname])
  return changes(base, current, editable.value)
}

function open(name) {
  router.push({ name: 'section', params: { project: props.project, section: props.section, item: name } })
}

// Every save of the open record: one that replaces its approval request asks first (saveConfirming).
function update(values) {
  return saveConfirming((v) => updateDoc(meta.value.doctype, doc.value.name, v), values, (m) => window.confirm(m))
}

async function loadList() {
  const fields = ['name', meta.value.title_field, meta.value.state_field, ...meta.value.columns.map((c) => c.fieldname)]
  rows.value = await call('frappe.client.get_list', {
    doctype: meta.value.doctype, fields: [...new Set(fields)], filters: { project: props.project },
    order_by: 'modified desc', limit_page_length: 500,
  })
}

async function loadGate() {
  gate.value = null
  if (!askable.value || !doc.value) return
  try {
    gate.value = await call('construction_core.approvals.staff.gate', { doctype: meta.value.doctype, name: doc.value.name })
  } catch { /* no reason is shown, and the server refuses the move all the same */ }
}

async function loadDoc() {
  saved.value = false
  for (const k of Object.keys(text)) delete text[k]
  if (isNew.value) {
    doc.value = { doctype: meta.value.doctype, project: props.project }
    for (const f of meta.value.fields) if (f.fieldtype === 'Select' && f.options.length) doc.value[f.fieldname] = f.options[0]
    original.value = {}
  } else {
    doc.value = await call('frappe.client.get', { doctype: meta.value.doctype, name: item.value })
    original.value = { ...doc.value }
  }
  for (const f of editable.value) if (f.fieldtype === 'Text Editor' || f.fieldtype === 'Small Text') text[f.fieldname] = plainText(doc.value[f.fieldname])
  await loadGate()
}

async function load() {
  error.value = ''
  try {
    if (!meta.value || meta.value.section !== props.section) {
      meta.value = await call('construction_shell.api.form_meta', { section: props.section })
      Object.assign(options, await call('construction_shell.api.record_options', { project: props.project }))
    }
    if (item.value) await loadDoc()
    else await loadList()
  } catch (e) {
    error.value = e.message || 'Could not load.'
    doc.value = null
  }
}

async function save() {
  busy.value = true
  error.value = ''
  try {
    if (isNew.value) {
      const values = { ...doc.value }
      for (const f of editable.value) if (f.fieldname in text) values[f.fieldname] = text[f.fieldname]
      const created = await call('frappe.client.insert', { doc: values }, { post: true })
      router.replace({ name: 'section', params: { project: props.project, section: props.section, item: created.name } })
      return
    }
    // Only the changed fields, with `modified`, so the server refuses a save over someone else's newer one.
    const updated = await update({ modified: doc.value.modified, ...pending() })
    doc.value = updated
    original.value = { ...updated }
    for (const f of editable.value) if (f.fieldname in text) text[f.fieldname] = plainText(updated[f.fieldname])
    saved.value = true
  } catch (e) {
    error.value = e.message || 'Could not save.'
  } finally {
    busy.value = false
  }
}

// A state change is a save of the state field; the controller allows or refuses it (its TRANSITIONS and rules).
async function move(state) {
  busy.value = true
  error.value = ''
  try {
    const updated = await update({ modified: doc.value.modified, ...pending(), [meta.value.state_field]: state })
    doc.value = updated
    original.value = { ...updated }
    for (const f of editable.value) if (f.fieldname in text) text[f.fieldname] = plainText(updated[f.fieldname])
    saved.value = true
    await loadGate()
  } catch (e) {
    error.value = e.message || 'Could not change the state.'
  } finally {
    busy.value = false
  }
}

watch(() => [props.section, props.project, item.value], load, { immediate: true })
</script>
