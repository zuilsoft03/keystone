<template>
  <!-- P3-52 (W1): the firm's details. The company name goes to Brand Settings and the rest to Firm Settings, both through
       setup.save_firm. The Company page uses this panel as it is. Built from Settings' cards and fields (D-196). -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-firm" data-testid="firm-panel">
    <h2 id="sec-firm" class="cw-card-title">Your firm</h2>
    <form class="flex flex-col gap-3" @submit.prevent="save">
      <label v-for="f in FIELDS" :key="f.key" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">
        <span>{{ f.label }} <span class="text-ink-gray-6">{{ f.hint }}</span></span>
        <textarea v-if="f.area" v-model="form[f.key]" rows="3" maxlength="500" class="form-textarea w-full" :data-testid="`firm-${f.key}`" />
        <input v-else v-model="form[f.key]" :type="f.type || 'text'" maxlength="140" :required="f.required" class="form-input h-12 w-full md:h-8" :data-testid="`firm-${f.key}`" />
      </label>
      <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="firm-error">{{ error }}</p>
      <p v-if="done" class="m-0 text-ink-green-7" data-testid="firm-done">{{ done }}</p>
      <Button type="submit" variant="solid" theme="blue" label="Save" class="self-start max-md:!h-12" :loading="busy" :disabled="busy || !form.company_name.trim() || !form.privacy_email.trim()" data-testid="firm-save" />
    </form>
  </section>
</template>

<script setup>
import { onMounted, reactive } from 'vue'
import { Button } from 'frappe-ui'
import { SETUP, post, useRun } from './setup.js'
import { call } from '../../api.js'

const emit = defineEmits(['saved'])
const FIELDS = [
  { key: 'company_name', label: 'Company name', hint: 'Shown to your team and clients', required: true },
  { key: 'legal_name', label: 'Registered name', hint: 'As on your papers' },
  { key: 'tin', label: 'Tax number (TIN)' },
  { key: 'address', label: 'Office address', area: true },
  { key: 'phone', label: 'Phone', type: 'tel' },
  { key: 'privacy_email', label: 'Privacy contact email', hint: 'Where people write about their data', type: 'email', required: true },
]
const form = reactive(Object.fromEntries(FIELDS.map((f) => [f.key, ''])))
const { busy, error, done, run } = useRun()

function fill(firm) {
  for (const f of FIELDS) form[f.key] = (firm && firm[f.key]) || ''
}

onMounted(async () => {
  const first = await run(() => call(`${SETUP}state`))
  if (first) fill(first.out.firm)
})

async function save() {
  const out = await run(() => post(`${SETUP}save_firm`, { ...form }), 'Saved.')
  if (out) {
    fill(out.out.firm)
    emit('saved')
  }
}
</script>
