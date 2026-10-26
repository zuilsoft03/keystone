<template>
  <Dialog v-model:open="shown" size="xl" :title="sheet ? w('ss_title', { step: sheet.name }) : w('ss_no_step')">
    <div class="staff-dialog flex flex-col gap-3.5" data-testid="step-sheet">
      <template v-if="sheet">
        <!-- the terms the step signs off, as the request page shows them -->
        <section class="rounded-4 border border-outline-gray-2 px-3 py-2.5" data-testid="step-terms">
          <div class="text-xs text-ink-gray-7">{{ w('ss_terms') }}</div>
          <div class="text-base font-medium text-ink-gray-9">{{ page.reference }} {{ page.title }}</div>
          <div v-if="chipRows.length" class="mt-1 flex flex-wrap gap-4 text-sm text-ink-gray-9">
            <span v-for="[label, text] in chipRows" :key="label"><span class="text-ink-gray-7">{{ label }}</span> {{ text }}</span>
          </div>
          <ul v-if="options.length" class="m-0 mt-1 flex list-none flex-col gap-1 p-0">
            <li v-for="o in options" :key="o.key" class="flex flex-wrap gap-x-3 text-sm text-ink-gray-9"><span class="font-medium">{{ o.label }}</span><span class="text-ink-gray-7">{{ o.cost }} · {{ o.time }}</span></li>
          </ul>
          <ul class="m-0 mt-1 flex list-none flex-col gap-1 p-0">
            <li v-for="f in page.files" :key="f.key" class="text-sm">
              <a :href="f.url" target="_blank" rel="noopener" class="inline-flex min-h-12 items-center text-ink-blue-link md:min-h-0">{{ w('rq_file_line', { name: f.name, rev: f.rev }) }}</a>
            </li>
          </ul>
        </section>
        <p v-if="sheet.action === 'acknowledge'" class="m-0 text-sm text-ink-gray-8">{{ w('ss_after_note') }}</p>
        <p v-if="!sheet.can" class="m-0 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="step-cannot">{{ w('ss_cannot', { reason: sheet.reason }) }}</p>
        <p v-else-if="sheet.same_person" class="m-0 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="step-same">{{ w('ss_same') }}</p>
        <label v-if="buttons.includes('return')" class="flex flex-col gap-1.5 text-base font-semibold text-ink-gray-9">{{ w('ss_reason') }}
          <textarea v-model="reason" rows="4" :maxlength="REASON_MAX" class="form-textarea h-auto w-full" data-testid="step-reason" />
          <span class="text-xs font-normal text-ink-gray-7">{{ w('ss_reason_help') }}</span>
        </label>
        <div v-if="lines.length" class="rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="step-refusal">
          <div v-for="l in lines" :key="l">{{ l }}</div>
        </div>
        <p v-if="done" class="m-0 rounded-4 bg-surface-green-1 px-3 py-2 text-sm text-ink-green-8" role="status" data-testid="step-done">{{ done }}</p>
      </template>
    </div>
    <template #actions>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <Button class="max-md:!h-12" :label="done ? w('ask_done') : w('ask_cancel')" data-testid="step-cancel" @click="shown = false" />
        <template v-if="!done">
          <Button v-if="buttons.includes('return')" variant="outline" class="max-md:!h-12" :label="w('ss_return')" :disabled="busy || !reason.trim()" data-testid="step-return" @click="go('return')" />
          <Button v-if="buttons.includes('approve')" variant="solid" theme="blue" class="max-md:!h-12" :label="w('ss_approve')" :disabled="busy" data-testid="step-approve" @click="go('approve')" />
          <Button v-if="buttons.includes('acknowledge')" variant="solid" theme="blue" class="max-md:!h-12" :label="w('ss_acknowledge')" :disabled="busy" data-testid="step-acknowledge" @click="go('acknowledge')" />
        </template>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { call } from '../../api.js'
import { useMode } from '../../mode.js'
import { approvalWords, staffWords } from '../words.js'
import { chips, optionRows } from '../terms.js'
import { refusalLines } from './ask.js'
import { REASON_MAX, STATE_WORD, sheetBody, sheetButtons, sheetPath } from './routes.js'

// The internal step sheet (P3-82; design 14.6): the terms of the request, then Approve and Return with a reason, or only
// Acknowledge for a step after the client. Staff are signed in, so there is no signature. The server decides again (it
// checks the terms token) and its refusals are shown as the sentences they come in.
const props = defineProps({ open: Boolean, page: { type: Object, default: null } })
const emit = defineEmits(['update:open', 'done'])
const mode = useMode()
const w = staffWords(mode)
const aw = approvalWords(mode)
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const sheet = computed(() => props.page?.internal?.sheet || null)
const buttons = computed(() => sheetButtons(sheet.value))
const chipRows = computed(() => (props.page ? chips(props.page.terms, aw) : []))
const options = computed(() => (props.page ? optionRows(props.page.terms, aw) : []))
const reason = ref('')
const lines = ref([])
const done = ref('')
const busy = ref(false)
let answered = null // the page is read again only when the sheet closes, so the sentence stays on screen

async function go(key) {
  busy.value = true
  lines.value = []
  try {
    const out = await call('construction_core.approvals.' + sheetPath(key), sheetBody(props.page.request, sheet.value, key === 'return' ? reason.value : ''), { post: true })
    done.value = w(STATE_WORD[out.state] || 'ss_done_waiting')
    answered = out
  } catch (e) {
    lines.value = refusalLines(e.message)
  } finally {
    busy.value = false
  }
}

watch(() => props.open, (v) => {
  if (v) return void ((reason.value = ''), (lines.value = []), (done.value = ''), (answered = null))
  if (answered) emit('done', answered)
})
</script>
