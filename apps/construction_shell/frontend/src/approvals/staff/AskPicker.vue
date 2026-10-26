<template>
  <Dialog v-model:open="shown" size="xl" :title="w('ask_title')">
    <div class="staff-dialog flex flex-col gap-2" data-testid="ask-picker">
      <p class="m-0 text-xs text-ink-gray-7">{{ w('picker_help') }}</p>
      <p v-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert">{{ error }}</p>
      <p v-else-if="loading" class="m-0 py-3 text-sm text-ink-gray-7" role="status">{{ w('ask_loading') }}</p>
      <p v-else-if="!rows.length" class="m-0 py-3 text-sm text-ink-gray-7" role="status" data-testid="ask-picker-none">{{ w('picker_none') }}</p>
      <ul class="m-0 flex max-h-[360px] list-none flex-col gap-1 overflow-y-auto p-0">
        <li v-for="r in rows" :key="r.doctype + r.name">
          <button type="button" class="flex min-h-12 w-full cursor-pointer items-center gap-2.5 rounded-5 border border-outline-gray-2 bg-transparent px-3 py-2 text-left hover:bg-surface-gray-2 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-transparent"
            :disabled="r.waiting" data-testid="ask-picker-row" :data-waiting="r.waiting ? '1' : '0'" @click="pick(r)">
            <span class="min-w-0 flex-1">
              <span class="block truncate text-base font-medium text-ink-gray-9">{{ r.title }}</span>
              <span class="block truncate text-xs text-ink-gray-7">{{ approvalWord(`kind.${r.doctype}`, { mode }) }} · {{ r.name }}</span>
            </span>
            <Badge v-if="r.waiting" theme="amber" :label="w('picker_waiting')" data-testid="ask-picker-waiting" />
          </button>
        </li>
      </ul>
    </div>
    <template #actions>
      <div class="flex justify-end"><Button class="max-md:!h-12" :label="w('ask_cancel')" @click="shown = false" /></div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, Dialog } from 'frappe-ui'
import { call } from '../../api.js'
import { useMode } from '../../mode.js'
import { approvalWord, staffWords } from '../words.js'
import { SENDABLE } from './ask.js'

// "Ask the client to approve…" in the Client room's message box: the project's records that can be sent now (Variations,
// Submittals, Documents, Decisions); choosing one opens the Ask sheet for it (`picked`). Which are ready is the sheet's preflight.
const props = defineProps({ open: Boolean, project: { type: String, default: '' } })
const emit = defineEmits(['update:open', 'picked'])
const mode = useMode()
const w = staffWords(mode)
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const rows = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const lists = await Promise.all(Object.entries(SENDABLE).map(async ([doctype, { field, states }]) => {
      const found = await call('frappe.client.get_list', { doctype, fields: ['name', 'title'], filters: { project: props.project, [field]: ['in', states] }, order_by: 'modified desc', limit_page_length: 50 })
      return found.map((r) => ({ doctype, name: r.name, title: r.title || r.name }))
    }))
    // a record that already has an Open request is shown but cannot be picked (the server refuses a second one)
    const open = await call('frappe.client.get_list', { doctype: 'Approval Request', fields: ['subject_doctype', 'subject_name'], filters: { project: props.project, status: 'Open' }, limit_page_length: 200 })
    const waiting = new Set(open.map((o) => `${o.subject_doctype}/${o.subject_name}`))
    rows.value = lists.flat().map((r) => ({ ...r, waiting: waiting.has(`${r.doctype}/${r.name}`) }))
  } catch (e) {
    rows.value = []
    error.value = e.message || w('ask_error')
  } finally {
    loading.value = false
  }
}

function pick(r) {
  emit('picked', { doctype: r.doctype, name: r.name })
  shown.value = false
}

watch(() => props.open, (v) => v && load(), { immediate: true })
</script>
