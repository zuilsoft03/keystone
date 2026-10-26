<template>
  <div class="flex flex-col gap-3.5 px-6 py-5" data-testid="section-page">
    <PageHead :crumb="`Workspace / ${label}`" :title="label" :meta="frame.project.project_name || frame.project.name" />
    <div class="cw-card flex max-w-xl flex-col items-start gap-2 px-4 py-3.5">
      <p class="m-0 text-ink-gray-8">This section still opens in Desk.</p>
      <a v-if="link" :href="link" class="text-base font-medium text-ink-blue-link" data-testid="desk-link">Open {{ label }} in Desk</a>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PageHead from '../components/PageHead.vue'
import { deskLink } from '../frame.js'
import { useMode } from '../mode.js'
import { sectionLabel } from '../words.js'

const props = defineProps({ frame: Object, project: String, section: String })
const mode = useMode()
const label = computed(() => sectionLabel(props.section, mode.value))
const link = computed(() => deskLink(props.section, props.project))
</script>
