<template>
  <!-- P3-55 (W7): what every new project starts with: the folder tree, the default rates and the cost codes. A new project
       takes the rates from Firm Settings and its folders from the Folder Template; this only edits them. -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-defaults" data-testid="defaults-panel">
    <h2 id="sec-defaults" class="cw-card-title">Project defaults</h2>
    <form v-if="loaded" class="flex flex-col gap-3" @submit.prevent="save">
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Folders <span class="text-ink-gray-6">One a line. Use a slash for a folder inside a folder, like Drawings/Structural</span>
        <textarea v-model="form.folders" rows="6" class="form-textarea w-full" spellcheck="false" data-testid="defaults-folders" />
      </label>
      <div class="grid gap-3 sm:grid-cols-3">
        <label v-for="r in RATES" :key="r.key" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ r.label }} (%)
          <input v-model.number="form[r.key]" type="number" min="0" max="100" step="0.01" class="form-input h-12 w-full md:h-8" :data-testid="`defaults-${r.key}`" />
        </label>
      </div>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Cost codes <span class="text-ink-gray-6">One a line: the code, then the name. Example: 03-100 Concrete</span>
        <textarea v-model="form.codes" rows="6" class="form-textarea w-full" spellcheck="false" data-testid="defaults-codes" />
      </label>
      <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="defaults-error">{{ error }}</p>
      <p v-if="done" class="m-0 text-ink-green-7" data-testid="defaults-done">{{ done }}</p>
      <Button type="submit" variant="solid" theme="blue" label="Save" class="self-start max-md:!h-12" :loading="busy" :disabled="busy" data-testid="defaults-save" />
    </form>
    <p v-else-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="defaults-error">{{ error }}</p>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Button } from 'frappe-ui'
import { call } from '../../api.js'
import { costCodesText, linesOf, parseCostCodes, post, useRun } from './setup.js'

const emit = defineEmits(['saved'])
const P = 'construction_core.project_defaults.'
const RATES = [
  { key: 'default_vat', label: 'VAT' },
  { key: 'default_retention', label: 'Retention' },
  { key: 'default_withholding', label: 'Withholding tax' },
]
const form = reactive({ folders: '', codes: '', default_vat: 0, default_retention: 0, default_withholding: 0 })
const loaded = ref(false)
const { busy, error, done, run } = useRun()

onMounted(async () => {
  const got = await run(() => call(`${P}get`))
  if (!got) return
  const d = got.out
  Object.assign(form, { folders: (d.folder_tree || []).join('\n'), codes: costCodesText(d.cost_codes), default_vat: d.default_vat, default_retention: d.default_retention, default_withholding: d.default_withholding })
  loaded.value = true
})

async function save() {
  const args = { folder_tree: linesOf(form.folders), cost_codes: parseCostCodes(form.codes) }
  for (const r of RATES) args[r.key] = form[r.key] === '' ? 0 : form[r.key]
  if (await run(() => post(`${P}save`, args), 'Saved.')) emit('saved')
}
</script>
