<template>
  <Dialog v-model:open="shown" size="xl" :title="w(resolve ? 'res_title' : 'dis_title')">
    <form class="staff-dialog flex flex-col gap-3" :data-testid="resolve ? 'resolve-form' : 'dispute-form'" @submit.prevent="send">
      <p class="m-0 text-sm text-ink-gray-8">{{ page.reference }} · {{ page.title }}</p>
      <template v-if="resolve">
        <fieldset class="m-0 flex flex-col gap-1.5 border-0 p-0">
          <legend class="mb-1 p-0 text-xs text-ink-gray-7">{{ w('res_outcome') }}</legend>
          <label v-for="o in OUTCOMES" :key="o" class="flex min-h-12 cursor-pointer items-center gap-2 text-base text-ink-gray-9">
            <input v-model="form.outcome" type="radio" name="res-outcome" :value="o" :data-testid="`res-${o}`" />{{ w(`res_${o}`) }}
          </label>
        </fieldset>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('res_reason') }}
          <textarea v-model="form.reason" rows="3" maxlength="500" class="form-textarea h-auto w-full" data-testid="res-reason" />
        </label>
      </template>
      <template v-else>
        <fieldset class="m-0 flex flex-col gap-1.5 border-0 p-0">
          <legend class="mb-1 p-0 text-xs text-ink-gray-7">{{ w('dis_how') }}</legend>
          <label v-for="h in HOWS" :key="h" class="flex min-h-12 cursor-pointer items-center gap-2 text-base text-ink-gray-9">
            <input v-model="form.how" type="radio" name="dis-how" :value="h" :data-testid="`dis-${h}`" />{{ w(`dis_${h}`) }}
          </label>
        </fieldset>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dis_reason') }}
          <textarea v-model="form.reason" rows="3" maxlength="500" class="form-textarea h-auto w-full" data-testid="dis-reason" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dis_proof') }}
          <select v-model="form.proof" class="form-select w-full py-0 max-md:h-12" data-testid="dis-proof">
            <option value="">{{ w('rec_pick_file') }}</option>
            <option v-for="f in files" :key="f.name" :value="f.name">{{ f.file_name }}</option>
          </select>
          <span>{{ w('dis_proof_help') }}</span>
        </label>
        <p class="m-0 text-xs text-ink-gray-7">{{ w('dis_note') }}</p>
      </template>
      <p v-for="m in missing" :key="m" class="m-0 text-sm text-ink-amber-8" data-testid="dis-missing">{{ w(m) }}</p>
      <p v-for="l in refusal" :key="l" class="m-0 text-sm text-ink-red-8" role="alert" data-testid="dis-error">{{ l }}</p>
    </form>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button class="max-md:!h-12" :label="w('ask_cancel')" @click="shown = false" />
        <Button variant="solid" theme="blue" class="max-md:!h-12" :label="w(resolve ? 'res_go' : 'dis_go')" :disabled="busy || missing.length > 0" data-testid="dis-go" @click="send" />
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
import { refusalLines } from './ask.js'
import { HOWS, OUTCOMES, blankDispute, disputeBody, disputeErrors, resolveBody, resolveErrors } from './request.js'

// "Record a dispute" (P3-80; design §3.7; board 17): how the client reported it, the reason and the proof file; and
// "Resolve…" (withdrawn, upheld or closed, with a reason). One dialog for both: `resolve` picks which. Managers only
// (the server checks); its refusals are shown as sentences.
const props = defineProps({ open: Boolean, resolve: Boolean, page: { type: Object, required: true }, files: { type: Array, default: () => [] } })
const emit = defineEmits(['update:open', 'done'])
const w = staffWords(useMode())
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const blank = () => ({ ...blankDispute(), outcome: '' })
const form = reactive(blank())
const busy = ref(false)
const refusal = ref([])
const missing = computed(() => (props.resolve ? resolveErrors(form) : disputeErrors(form)))

async function send() {
  if (missing.value.length || busy.value) return
  busy.value = true
  refusal.value = []
  try {
    const name = props.resolve ? 'resolve' : 'record'
    const body = props.resolve ? resolveBody(props.page.request, form) : disputeBody(props.page.request, form)
    await call(`construction_core.approvals.dispute.${name}`, body, { post: true })
    emit('done')
    shown.value = false
  } catch (e) {
    refusal.value = refusalLines(e.message)
  } finally {
    busy.value = false
  }
}

watch(() => props.open, (v) => v && (Object.assign(form, blank()), (refusal.value = [])))
</script>
