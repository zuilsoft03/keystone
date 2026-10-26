<template>
  <Dialog v-model:open="shown" size="xl" :title="w('rec_title')">
    <form class="staff-dialog flex flex-col gap-3" data-testid="recorded-form" @submit.prevent="send">
      <p class="m-0 text-sm text-ink-gray-8">{{ page.reference }} · {{ page.title }}</p>
      <fieldset class="m-0 flex flex-col gap-1.5 border-0 p-0">
        <legend class="mb-1 p-0 text-xs text-ink-gray-7">{{ w('rec_how') }}</legend>
        <label v-for="m in METHODS" :key="m" class="flex min-h-12 cursor-pointer items-center gap-2 text-base text-ink-gray-9">
          <input v-model="form.method" type="radio" name="rec-method" :value="m" :data-testid="`rec-method-${m}`" />{{ w(`rec_${m}`) }}
        </label>
        <p v-if="form.method === 'phone'" class="m-0 text-xs text-ink-gray-7" data-testid="rec-phone-note">{{ w('rec_phone_note') }}</p>
      </fieldset>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rec_member') }}
        <select v-model="form.member" class="form-select w-full py-0 max-md:h-12" data-testid="rec-member">
          <option value="">{{ w('rec_member_pick') }}</option>
          <option v-for="a in approvers" :key="a.member" :value="a.member">{{ a.name }}</option>
        </select>
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rec_when') }}
        <input v-model="form.given_at" type="datetime-local" class="form-input w-full max-md:h-12" data-testid="rec-when" />
        <span>{{ w('rec_when_help') }}</span>
      </label>
      <label v-if="decision" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rec_option') }}
        <select v-model="form.option" class="form-select w-full py-0 max-md:h-12" data-testid="rec-option">
          <option value="" />
          <option v-for="o in page.terms.options" :key="o.key" :value="o.key">{{ o.label }}</option>
        </select>
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rec_proof') }}
        <select v-model="form.proof" class="form-select w-full py-0 max-md:h-12" data-testid="rec-proof">
          <option value="">{{ w('rec_pick_file') }}</option>
          <option v-for="f in files" :key="f.name" :value="f.name">{{ f.file_name }}</option>
        </select>
        <span>{{ w('rec_proof_help') }}</span>
      </label>
      <label v-if="form.method === 'paper'" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rec_original') }}
        <input v-model="form.original" maxlength="500" class="form-input w-full max-md:h-12" data-testid="rec-original" />
        <span>{{ w('rec_original_help') }}</span>
      </label>
      <p class="m-0 text-xs text-ink-gray-7">{{ w('rec_confirm_note') }}</p>
      <p v-for="m in missing" :key="m" class="m-0 text-sm text-ink-amber-8" data-testid="rec-missing">{{ w(m) }}</p>
      <p v-for="l in refusal" :key="l" class="m-0 text-sm text-ink-red-8" role="alert" data-testid="rec-error">{{ l }}</p>
    </form>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button class="max-md:!h-12" :label="w('ask_cancel')" @click="shown = false" />
        <Button variant="solid" theme="blue" class="max-md:!h-12" :label="w('rec_go')" :disabled="busy || missing.length > 0" data-testid="rec-go" @click="send" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { call } from '../../api.js'
import { useMode } from '../../mode.js'
import { staffWords } from '../words.js'
import { isDecision } from '../terms.js'
import { refusalLines } from './ask.js'
import { METHODS, blankRecorded, recordedBody, recordedErrors } from './request.js'

// "Record an approval" (P3-80; design §3.9; ApprovalStaffForms board 16): how it was given, which named approver, when, the
// required proof file, and for paper who keeps the original; a Decision also asks the option. The server checks it all again;
// its refusals are shown as sentences.
const props = defineProps({ open: Boolean, page: { type: Object, required: true }, files: { type: Array, default: () => [] } })
const emit = defineEmits(['update:open', 'done'])
const w = staffWords(useMode())
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const form = reactive(blankRecorded())
const busy = ref(false)
const refusal = ref([])
const approvers = computed(() => props.page.approvers.filter((a) => a.confirmed))
const decision = computed(() => isDecision(props.page.terms))
const missing = computed(() => recordedErrors(form, decision.value))

async function send() {
  if (missing.value.length || busy.value) return
  busy.value = true
  refusal.value = []
  try {
    const out = await call('construction_core.approvals.recorded.record', recordedBody(props.page.request, form, decision.value), { post: true })
    emit('done', out)
    shown.value = false
  } catch (e) {
    refusal.value = refusalLines(e.message)
  } finally {
    busy.value = false
  }
}

watch(() => props.open, (v) => v && (Object.assign(form, blankRecorded()), (refusal.value = [])))
</script>
