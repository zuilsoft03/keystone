<template>
  <section class="cw-card overflow-hidden" aria-labelledby="sec-steps" data-testid="approval-steps">
    <div class="px-4 py-3.5">
      <h2 id="sec-steps" class="cw-card-title">{{ w('rt_title') }}</h2>
      <p class="mt-1 text-sm text-ink-gray-7">{{ w('rt_note') }}</p>
    </div>
    <p v-if="loading" class="px-4 pb-3 text-sm text-ink-gray-7" role="status">{{ w('rt_loading') }}</p>
    <p v-if="error" class="mx-4 mb-3 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="steps-error">{{ error }}</p>
    <template v-if="data">
      <p v-if="!data.can_edit" class="mx-4 mb-3 rounded-4 bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8" data-testid="steps-read-only">{{ w('rt_read_only') }}</p>
      <RouteCard v-for="c in data.routes" :key="c.kind" :card="c" :can-edit="data.can_edit" @saved="(n) => (data.routes = data.routes.map((x) => (x.kind === n.kind ? n : x)))" />
    </template>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { call } from '../../api.js'
import { useMode } from '../../mode.js'
import { staffWords } from '../words.js'
import { refusalLines } from './ask.js'
import RouteCard from './RouteCard.vue'

// Settings, Approval steps (P3-82; design 14.6): one card per record kind. Routes belong to the site, not a project, so
// this loads once. Staff read it; a System Manager (routes.can_edit) changes it.
const mode = useMode()
const w = staffWords(mode)
const data = ref(null)
const loading = ref(true)
const error = ref('')

call('construction_core.approvals.routes.routes')
  .then((d) => (data.value = d))
  .catch((e) => (error.value = refusalLines(e.message).join(' ')))
  .finally(() => (loading.value = false))
</script>
