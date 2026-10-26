<template>
  <NotFound v-if="missing" />
  <div v-else class="flex min-w-0 flex-1 flex-wrap max-md:min-h-0 max-md:flex-col max-md:flex-nowrap" :class="fill ? 'md:flex-nowrap' : ''" data-testid="project-layout">
    <AppRail :frame="frame" :section="section" collapsible />
    <!-- P3-64: on a phone the folded rail is a bar above the page, which takes the rest of the screen (it was 0 px wide). -->
    <!-- P3-68: a section that fills the screen (`FILL`) is as tall as the screen: the page does not scroll, the section's own panes do. -->
    <main class="flex min-w-0 flex-1 flex-col max-md:min-h-0 max-md:overflow-y-auto" :class="fill ? 'md:min-h-0' : ''">
      <router-view v-if="frame" :frame="frame" />
      <p v-else-if="error" class="p-6 text-ink-red-7" role="alert">{{ error }}</p>
      <p v-else-if="!error" class="p-6 text-ink-gray-6">Loading…</p>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NotFound from './NotFound.vue'
import AppRail from '../components/AppRail.vue'
import { SECTIONS } from '../paths.js'
import { fetchFrame, rememberProject } from '../store.js'

const route = useRoute()
const router = useRouter()
const project = computed(() => route.params.project)
const section = computed(() => route.params.section)
// The sections whose page is a fixed-height screen on a wide display (P3-68): a flex row that wraps takes its height from its
// content, so a long room made the whole page scroll; one that does not wrap takes the screen's.
const FILL = new Set(['discuss'])
const fill = computed(() => FILL.has(section.value))
const frame = ref(null)
const missing = ref(false)
const error = ref('')

async function load(name) {
  frame.value = null
  missing.value = false
  error.value = ''
  try {
    const data = await fetchFrame(name)
    if (name !== project.value) return // the user moved on meanwhile
    frame.value = data
    rememberProject(name)
    // A section this project's rail does not show (switched from another project, or hidden in its settings): home.
    // A page never on the rail (sections.json `rail: false`, the client view) stays.
    const section = route.params.section
    if (SECTIONS[section]?.rail !== false && !data.rail.some((i) => i.section === section)) {
      router.replace({ name: 'section', params: { project: name, section: 'home' } })
    }
  } catch (e) {
    if (name !== project.value) return
    if (e.type === 'DoesNotExistError') missing.value = true
    else error.value = e.message || 'Could not load the project.'
  }
}

watch(project, load, { immediate: true })
</script>
