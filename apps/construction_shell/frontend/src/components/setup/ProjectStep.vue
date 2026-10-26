<template>
  <!-- P3-57 (W8): the first project, through the New project panel as built (P3-39). Done when a project exists. -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-project" data-testid="project-step">
    <h2 id="sec-project" class="cw-card-title">Your first project</h2>
    <p v-if="list.length" class="m-0 text-ink-green-7" data-testid="project-exists">{{ list.length === 1 ? 'A project exists' : `${list.length} projects exist` }}: {{ list.map((p) => p.project_name).join(', ') }}.</p>
    <p v-else-if="loaded" class="m-0 text-sm text-ink-gray-7">No project yet.</p>
    <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="project-error">{{ error }}</p>
    <Button variant="solid" theme="blue" :label="list.length ? 'Make another project' : 'Make the first project'" class="self-start max-md:!h-12" data-testid="project-new" @click="creating = true" />
    <NewProjectDialog v-model:open="creating" @created="load" />
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import NewProjectDialog from '../NewProjectDialog.vue'
import { projects } from './setup.js'

const emit = defineEmits(['saved'])
const list = ref([])
const loaded = ref(false)
const error = ref('')
const creating = ref(false)

async function load() {
  try {
    list.value = await projects()
    loaded.value = true
    if (list.value.length) emit('saved')
  } catch (e) {
    error.value = e.message || 'The projects could not be read.'
  }
}
onMounted(load)
</script>
