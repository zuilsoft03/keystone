<template>
  <Dialog v-model:open="shown" size="3xl" :title="w(name ? 'dec_title_edit' : 'dec_title_new')">
    <form id="decision-form" class="staff-dialog flex flex-col gap-3.5" data-testid="decision-form" @submit.prevent="save(false)">
      <p v-if="locked" class="m-0 rounded-4 bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8" data-testid="decision-final">{{ w('dec_final') }}</p>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dec_title') }}<span class="text-ink-red-7" aria-hidden="true"> *</span>
        <input v-model="d.title" maxlength="140" required :disabled="locked" class="form-input w-full max-md:h-12" data-testid="decision-title" />
      </label>
      <fieldset class="m-0 flex flex-wrap gap-1.5 border-0 p-0" :aria-label="w('dec_category')">
        <button v-for="c in CATEGORIES" :key="c" type="button" :disabled="locked" :aria-pressed="d.category === c"
          class="inline-flex min-h-12 cursor-pointer items-center rounded-full border px-3 text-sm md:min-h-8"
          :class="d.category === c ? 'border-outline-blue-6 bg-surface-blue-1 text-ink-blue-8' : 'border-outline-gray-2 bg-transparent text-ink-gray-8'"
          data-testid="decision-category" @click="d.category = c">{{ w(`dec_cat_${c}`) }}</button>
      </fieldset>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dec_description') }}
        <textarea v-model="d.description" rows="3" :disabled="locked" class="form-textarea h-auto w-full" data-testid="decision-description" />
      </label>
      <div class="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dec_currency') }}
          <input v-model="d.currency" maxlength="10" :disabled="locked" class="form-input w-full max-md:h-12" data-testid="decision-currency" />
          <span class="text-ink-gray-6">{{ w('dec_currency_help') }}</span>
        </label>
        <label class="flex min-h-12 items-center gap-2 self-end text-base text-ink-gray-9">
          <input v-model="d.amounts_include_vat" type="checkbox" :true-value="1" :false-value="0" :disabled="locked" class="form-checkbox rounded-1" data-testid="decision-vat" />{{ w('dec_vat') }}
        </label>
      </div>

      <section aria-labelledby="dec-options" class="flex flex-col gap-2.5">
        <h3 id="dec-options" class="m-0 text-base font-semibold text-ink-gray-9">{{ w('dec_options') }}</h3>
        <div v-for="(o, i) in d.options" :key="o.name || i" class="flex flex-col gap-2.5 rounded-5 border border-outline-gray-2 p-3" data-testid="decision-option">
          <div class="flex items-start gap-3">
            <img v-if="o.file && isImage(o.file)" :src="o.file" alt="" class="size-16 flex-none rounded-4 border border-outline-gray-1 object-cover" />
            <span v-else class="grid size-16 flex-none place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-5" aria-hidden="true"><span class="lucide-image size-6" /></span>
            <label class="flex min-w-0 flex-1 flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dec_picture') }}
              <select v-model="o.file" :disabled="locked" class="form-select w-full py-0 max-md:h-12" data-testid="decision-picture">
                <option value="">{{ w('dec_no_picture') }}</option>
                <option v-for="f in files" :key="f.name" :value="f.file_url">{{ f.file_name }}</option>
              </select>
            </label>
          </div>
          <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dec_label') }}<span class="text-ink-red-7" aria-hidden="true"> *</span>
            <input v-model="o.label" maxlength="140" :disabled="locked" class="form-input w-full max-md:h-12" data-testid="decision-label" />
          </label>
          <div class="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
            <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dec_cost') }}{{ d.currency ? ` (${d.currency})` : '' }}
              <input v-model="o.cost_difference" type="number" step="any" :disabled="locked" class="form-input w-full max-md:h-12" data-testid="decision-cost" />
            </label>
            <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dec_days') }}
              <input v-model="o.time_difference" type="number" step="1" :disabled="locked" class="form-input w-full max-md:h-12" data-testid="decision-days" />
            </label>
          </div>
          <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('dec_supplier') }}
            <input v-model="o.supplier" :disabled="locked" class="form-input w-full max-md:h-12" data-testid="decision-supplier" />
          </label>
          <div class="flex flex-wrap items-center justify-between gap-2">
            <label class="flex min-h-12 items-center gap-2 text-base text-ink-gray-9 md:min-h-8">
              <input v-model="d.recommended" type="radio" :value="i" :disabled="locked" class="form-radio" data-testid="decision-recommended" />{{ w('dec_recommended') }}
            </label>
            <Button variant="outline" theme="red" class="max-md:!h-12" :label="w('dec_remove')" :disabled="locked || d.options.length < 2" data-testid="decision-remove" @click="remove(i)" />
          </div>
        </div>
        <div>
          <Button variant="outline" icon-left="lucide-plus" class="max-md:!h-12" :label="w('dec_add')" :disabled="locked" data-testid="decision-add" @click="d.options.push(blankOption())" />
        </div>
        <p v-if="priced(d)" class="m-0 text-xs text-ink-gray-7" data-testid="decision-priced">{{ w('dec_priced_note') }}</p>
      </section>

      <div v-if="problems.length || lines.length" class="rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="decision-errors">
        <div v-for="p in problems" :key="p">{{ p }}</div>
        <div v-for="l in lines" :key="l">{{ l }}</div>
      </div>
      <p v-if="message" class="m-0 text-sm text-ink-green-8" role="status" data-testid="decision-message">{{ message }}</p>
    </form>
    <template #actions>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <Button v-if="canMakeVariation(d)" class="mr-auto max-md:!h-12" :label="w('dec_make')" :disabled="busy" data-testid="decision-make" @click="makeVariation" />
        <Button class="max-md:!h-12" :label="w('dec_close')" @click="shown = false" />
        <Button type="submit" form="decision-form" class="max-md:!h-12" :label="w('dec_save_draft')" :disabled="busy || locked" data-testid="decision-save" />
        <Button variant="solid" theme="blue" class="max-md:!h-12" :label="w('dec_ask')" :disabled="busy || locked" data-testid="decision-ask" @click="save(true)" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { call, updateDoc } from '../../api.js'
import { useMode } from '../../mode.js'
import { staffWords } from '../words.js'
import { refusalLines } from './ask.js'
import { CATEGORIES, FINAL, blankDecision, blankOption, canMakeVariation, decisionErrors, fromDoc, priced, recommendedKey, toDoc } from './decision.js'

// The Decision form (P3-80; design §3.3; canvas ApprovalStaffForms "Decision form"): a title, the options with pictures,
// cost and days, the recommended option, the currency and VAT basis. It saves a Client Decision (the server keeps each
// option's key and the status), "Ask the client to choose" saves and hands the Decision to the Ask sheet (`ask`), and
// "Make the variation" sits on a decided priced Decision. The pictures are the project's own files.
const props = defineProps({ open: Boolean, project: { type: String, required: true }, name: { type: String, default: '' } })
const emit = defineEmits(['update:open', 'ask', 'saved'])
const mode = useMode()
const w = staffWords(mode)
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const d = reactive(blankDecision())
const files = ref([])
const busy = ref(false)
const lines = ref([])
const message = ref('')
const tried = ref(false)
const locked = computed(() => FINAL.includes(d.status))
const problems = computed(() => (tried.value ? decisionErrors(d).map((k) => w(k)) : []))
const isImage = (url) => /\.(jpe?g|png|webp|gif)$/i.test(url)

function reset(next) {
  Object.keys(d).forEach((k) => delete d[k])
  Object.assign(d, next)
  lines.value = []
  message.value = ''
  tried.value = false
}

async function load() {
  reset(props.name ? fromDoc(await call('frappe.client.get', { doctype: 'Client Decision', name: props.name })) : blankDecision())
  try {
    const options = await call('construction_shell.api.record_options', { project: props.project })
    files.value = options.files.filter((f) => isImage(f.file_name))
  } catch {
    files.value = []
  }
}

function remove(i) {
  d.options.splice(i, 1)
  if (d.recommended === i) d.recommended = -1
  else if (d.recommended > i) d.recommended -= 1
}

// Saves the Decision; with `ask`, hands it to the Ask sheet. The recommended option is set after the save, from the key the server gave its row.
async function save(ask) {
  tried.value = true
  lines.value = []
  message.value = ''
  if (decisionErrors(d).length) return
  busy.value = true
  try {
    const body = toDoc(d, props.project)
    let saved = d.name
      ? await updateDoc('Client Decision', d.name, { modified: d.modified, ...body })
      : await call('frappe.client.insert', { doc: { doctype: 'Client Decision', ...body } }, { post: true })
    const key = recommendedKey(saved, d.recommended)
    if (key !== (saved.recommended_option || '')) saved = await updateDoc('Client Decision', saved.name, { modified: saved.modified, recommended_option: key })
    reset(fromDoc(saved))
    message.value = w('dec_saved')
    emit('saved', saved)
    if (ask) emit('ask', { doctype: 'Client Decision', name: saved.name })
  } catch (e) {
    lines.value = refusalLines(e.message)
  } finally {
    busy.value = false
  }
}

async function makeVariation() {
  busy.value = true
  lines.value = []
  try {
    const out = await call('construction_core.approvals.api.make_variation', { decision: d.name }, { post: true })
    message.value = w('dec_made', { name: out.variation || out.name || '' })
  } catch (e) {
    lines.value = refusalLines(e.message)
  } finally {
    busy.value = false
  }
}

watch(() => props.open, (v) => v && load(), { immediate: true })
</script>
