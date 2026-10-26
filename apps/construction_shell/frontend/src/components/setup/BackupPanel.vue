<template>
  <!-- P3-55 (W6): how long backups are kept, and Back up now. The step is done when a backup reports OK. This page cannot
       connect the off-site folder (a host task); when it is missing the panel says so and names RUNBOOK §10.5. -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-backup" data-testid="backup-panel">
    <h2 id="sec-backup" class="cw-card-title">Backups</h2>
    <template v-if="st">
      <p v-if="!st.offsite_folder_present" class="m-0 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="backup-offsite-missing">
        The off-site folder is not connected yet, so backups stay on this server only. Ask your IT person to connect it ({{ st.runbook || 'RUNBOOK §10.5' }}).
      </p>
      <p class="m-0 text-sm text-ink-gray-9" data-testid="backup-last">{{ lastLine }}</p>
      <form class="flex flex-wrap items-end gap-3" @submit.prevent="save">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Days to keep backups
          <input v-model.number="days" type="number" min="1" max="365" required class="form-input h-12 w-32 md:h-8" data-testid="backup-days" />
        </label>
        <Button type="submit" label="Save" class="max-md:!h-12" :disabled="busy" data-testid="backup-save" />
      </form>
      <Button variant="solid" theme="blue" :label="waiting ? 'Backing up…' : 'Back up now'" class="self-start max-md:!h-12" :loading="waiting || !!st.running" :disabled="busy || waiting || !!st.running" data-testid="backup-now" @click="now" />
    </template>
    <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="backup-error">{{ error }}</p>
    <p v-if="done" class="m-0 text-ink-green-7" data-testid="backup-done">{{ done }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { call } from '../../api.js'
import { post, useRun } from './setup.js'

const emit = defineEmits(['saved'])
const B = 'construction_core.backups.'
const st = ref(null)
const days = ref(14)
const waiting = ref(false)
const { busy, error, done, run, stopped } = useRun()
const lastLine = computed(() => {
  const l = st.value?.last
  if (!l) return 'No backup yet.'
  return l.ok ? `Last backup: ${l.at}, ${l.size}. It worked.` : `Last backup: ${l.at}. It failed${l.error ? `: ${l.error}` : ''}. Try again, or ask your IT person.`
})

async function load(keepDays = false) {
  try {
    st.value = await call(`${B}state`)
    if (!keepDays) days.value = st.value.keep_days
  } catch (e) {
    error.value = e.message || 'That did not work.'
  }
}
onMounted(load)

async function save() {
  if (await run(() => post(`${B}save`, { keep_days: days.value }), 'Saved.')) await load()
}

// The backup runs in the background; read the state every few seconds until a new one shows up (at most about a minute).
async function now() {
  const before = st.value?.last?.at
  if (!(await run(() => post(`${B}backup_now`), ''))) return
  waiting.value = true
  for (let i = 0; i < 20 && !stopped(); i++) {
    await new Promise((r) => setTimeout(r, 3000))
    await load(true)
    if (st.value?.last && st.value.last.at !== before) break
  }
  waiting.value = false
  if (stopped()) return
  if (st.value?.last?.ok) {
    done.value = 'The backup worked.'
    emit('saved')
  } else if (!error.value) error.value = st.value?.last ? 'The backup did not work. Try again, or ask your IT person.' : 'The backup is taking a while. Check again in a minute.'
}
</script>
