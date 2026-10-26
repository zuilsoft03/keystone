<template>
  <component :is="view" :key="viewKey" :frame="frame" :project="route.params.project" :section="route.params.section" />
</template>

<script setup>
import { computed, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'

// One view per section. A section not yet in the shell opens in Desk (DeskSection), which stays available.
const Records = defineAsyncComponent(() => import('../sections/Records.vue'))
const VIEWS = {
  home: defineAsyncComponent(() => import('../sections/Home.vue')),
  files: defineAsyncComponent(() => import('../sections/Files.vue')),
  discuss: defineAsyncComponent(() => import('../sections/Discuss.vue')),
  rfi: Records,
  submittals: Records,
  variations: Records,
  documents: Records,
  whiteboards: defineAsyncComponent(() => import('../sections/Whiteboards.vue')),
  takeoff: defineAsyncComponent(() => import('../sections/Takeoff.vue')),
  settings: defineAsyncComponent(() => import('../sections/Settings.vue')),
  'client-view': defineAsyncComponent(() => import('../sections/ClientView.vue')),
}
const OfficeEditor = defineAsyncComponent(() => import('../sections/OfficeEditor.vue'))
const DeskSection = defineAsyncComponent(() => import('../sections/DeskSection.vue'))

defineProps({ frame: { type: Object, required: true } })
const route = useRoute()
// files/<file>/edit is the office editor (sections.json: files has the action "edit").
const view = computed(() =>
  route.params.section === 'files' && route.params.action === 'edit' ? OfficeEditor : VIEWS[route.params.section] || DeskSection,
)
// A new office file is a new editor session, and each client contact a new client view: remount for each one.
const viewKey = computed(() => {
  if (route.params.action === 'edit') return `edit:${route.params.item}`
  if (route.params.section === 'client-view') return `client-view:${route.params.item || ''}`
  return route.params.section
})
</script>
