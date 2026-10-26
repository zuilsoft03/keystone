<template>
  <!-- P3-52 (W12): what is done, what was skipped, and Finish. setup.finish() refuses unless W1 is done and every other
       step is done or skipped; a skipped step stays on the Company page's checklist. -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-summary" data-testid="summary-step">
    <h2 id="sec-summary" class="cw-card-title">Your set-up</h2>
    <ul v-if="state" class="m-0 flex list-none flex-col p-0">
      <li v-for="s in rows" :key="s.id" class="flex min-h-12 flex-wrap items-center gap-x-3 border-t border-outline-gray-1 py-1 first:border-t-0" :data-testid="`summary-${s.id}`">
        <span class="min-w-0 flex-1 text-base text-ink-gray-9">{{ s.title }}</span>
        <Badge :label="stateWord(state, s.id)" :theme="THEME[stateOf(state, s.id)] || 'amber'" />
        <Button v-if="stateOf(state, s.id) !== 'done'" label="Do it" class="max-md:!h-12" :data-testid="`summary-go-${s.id}`" @click="$emit('goto', s.id)" />
      </li>
    </ul>
    <p v-if="state && !canFinish(state)" class="m-0 text-sm text-ink-gray-8" data-testid="summary-open">Finish needs your firm's details and an answer for every other step: do it, or skip it.</p>
    <p v-else-if="state && skipped" class="m-0 text-sm text-ink-gray-8" data-testid="summary-skipped">Skipped steps wait on the Company page, in the Getting started list.</p>
    <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="summary-error">{{ error }}</p>
    <Button variant="solid" theme="blue" label="Finish set-up" class="self-start max-md:!h-12" :loading="busy" :disabled="busy || !state || !canFinish(state)" data-testid="summary-finish" @click="finish" />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { call } from '../../api.js'
import { SETUP, canFinish, post, stateOf, stateWord, useRun, visibleSteps } from './setup.js'

const emit = defineEmits(['finished', 'goto'])
const THEME = { done: 'green', skipped: 'gray' }
const state = ref(null)
const { busy, error, run } = useRun()
const rows = computed(() => visibleSteps(state.value).filter((s) => s.id !== 'W12'))
const skipped = computed(() => rows.value.some((s) => stateOf(state.value, s.id) === 'skipped'))

onMounted(async () => {
  const got = await run(() => call(`${SETUP}state`))
  if (got) state.value = got.out
})

async function finish() {
  if (await run(() => post(`${SETUP}finish`))) emit('finished')
}
</script>
