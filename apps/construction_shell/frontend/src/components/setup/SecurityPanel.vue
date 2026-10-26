<template>
  <!-- P3-52 (W5): People's two-step requirement switch (D-231), the same call and the same words. The server refuses a
       requirement while outgoing email is not set up, or while the person asking has not turned it on for themself. -->
  <section class="cw-card flex flex-col gap-2.5 px-4 py-3.5" aria-labelledby="sec-security" data-testid="security-panel">
    <h2 id="sec-security" class="cw-card-title">Two-step sign-in</h2>
    <p class="m-0 text-sm text-ink-gray-7">Each person may turn it on from their account menu. You can require it. To require it, turn it on for yourself first and set up outgoing email.</p>
    <div v-if="status" class="cw-tabbuttons flex-wrap self-start" role="group" aria-label="Who must use two-step sign-in">
      <button v-for="[id, label] in SCOPES" :key="id" type="button" class="cw-tabbutton max-md:!h-12 max-md:px-3" :aria-pressed="status.requirement === id"
        :disabled="busy" :data-testid="`security-${id}`" @click="choose(id)">{{ label }}</button>
    </div>
    <p v-if="status && status.requirement !== 'nobody' && status.not_set_up.length" class="m-0 text-sm text-ink-gray-8" data-testid="security-waiting">
      Not set up yet ({{ status.not_set_up.length }}): their next sign-in emails them a setup link.
    </p>
    <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="security-error">{{ error }}</p>
    <p v-if="done" class="m-0 text-ink-green-7" data-testid="security-done">{{ done }}</p>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { call } from '../../api.js'
import { post, useRun } from './setup.js'

const emit = defineEmits(['saved'])
const T = 'construction_core.accounts.two_step.'
const SCOPES = [['nobody', 'Each person chooses'], ['team', 'Required for the team'], ['everyone', 'Required for everyone']]
const status = ref(null)
const { busy, error, done, run } = useRun()

async function load() {
  try {
    status.value = await call(`${T}requirement_status`)
  } catch (e) {
    error.value = e.message || 'That did not work.'
  }
}
onMounted(load)

async function choose(scope) {
  if (scope === status.value.requirement) return emit('saved') // keeping the current choice is a choice
  const who = scope === 'team' ? 'for the team' : 'for everyone'
  const ask = scope === 'nobody' ? 'Let each person choose two-step sign-in?' : `Require two-step sign-in ${who}? Whoever has not set it up gets a setup email at their next sign-in.`
  if (!window.confirm(ask)) return
  if (await run(() => post(`${T}set_requirement`, { scope }), 'Saved.')) {
    await load()
    emit('saved')
  }
}
</script>
