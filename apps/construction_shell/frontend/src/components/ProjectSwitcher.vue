<template>
  <Popover side="bottom" align="start">
    <template #trigger="{ setOpen, open: isOpen }">
      <button
        type="button"
        class="relative flex w-full items-center gap-2.5 overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base p-2.5 text-left shadow-sm"
        :aria-label="`Current project: ${frame.project.project_name || frame.project.name}. Switch project`"
        :aria-expanded="isOpen"
        data-testid="project-switcher"
        @click="setOpen(!isOpen)"
      >
        <span class="absolute bottom-2.5 left-0 top-2.5 w-[3px] rounded-r-[3px] bg-surface-blue-6" aria-hidden="true" />
        <ProjectBadge :name="frame.project.name" :label="frame.project.project_name" :status="frame.project.status" size="lg" />
        <span class="min-w-0 flex-1 leading-tight">
          <span class="block truncate text-sm font-semibold text-ink-gray-9" data-testid="current-project">{{ frame.project.project_name || frame.project.name }}</span>
          <span class="mt-[3px] block truncate text-[11px] text-ink-gray-7">{{ frame.project.name }}<template v-if="frame.clients.length"> · {{ frame.clients[0] }}</template></span>
        </span>
        <span class="lucide-chevrons-up-down size-4 flex-none text-ink-gray-6" aria-hidden="true" />
      </button>
    </template>
    <template #default="{ close }">
      <div class="w-[300px] rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 shadow-lg" data-testid="switcher-list">
        <TextInput v-model="query" class="mb-1.5" placeholder="Search projects…" aria-label="Search projects" @keydown.esc="close()" />
        <button
          v-for="p in matches"
          :key="p.name"
          type="button"
          class="flex w-full items-center gap-2.5 rounded-4 px-2.5 py-2 text-left hover:bg-surface-gray-2"
          :class="{ 'bg-surface-blue-1': p.name === frame.project.name }"
          data-testid="switch-to"
          :data-project="p.name"
          @click="go(p.name); close()"
        >
          <ProjectBadge :name="p.name" :label="p.project_name" />
          <span class="min-w-0 flex-1">
            <span class="block truncate font-medium">{{ p.project_name || p.name }}</span>
            <span class="block truncate text-[11px] text-ink-gray-6">{{ p.name }}</span>
          </span>
          <Badge :label="statusOf(p.status).label" :theme="statusOf(p.status).theme" />
        </button>
        <p v-if="!matches.length" class="px-2.5 py-2 text-xs text-ink-gray-6">No project matches.</p>
      </div>
    </template>
  </Popover>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Popover, TextInput } from 'frappe-ui'
import ProjectBadge from './ProjectBadge.vue'
import { recentProjects, statusOf, switchTarget } from '../frame.js'
import { state } from '../store.js'

const props = defineProps({ frame: { type: Object, required: true } })
const route = useRoute()
const router = useRouter()
const query = ref('')
const matches = computed(() => {
  const q = query.value.trim().toLowerCase()
  // The last project first (the dashboard's old Recent list lives on here), then the rest.
  return recentProjects(state.projects, state.lastProject, Infinity).filter((p) => !q || `${p.project_name} ${p.name}`.toLowerCase().includes(q))
})

// Keep the section; ProjectLayout goes home when the target project's rail does not have it.
function go(name) {
  query.value = ''
  router.push({ name: 'section', params: { project: name, section: switchTarget(route.params.section, null) } })
}
</script>
