<template>
  <main class="mx-auto flex w-full max-w-[1120px] flex-col gap-4 px-5 py-6" data-testid="portal-projects">
    <PageHead crumb="Client portal" title="Your projects" :meta="loaded ? `${projects.length} ${projects.length === 1 ? 'project' : 'projects'}` : ''" />
    <p v-if="error" class="text-ink-red-7" role="alert">{{ error }}</p>
    <p v-else-if="loaded && !projects.length" class="text-ink-gray-7">You have no project to see yet.</p>
    <section v-if="conversations.length > 1" class="cw-card overflow-hidden" :aria-labelledby="'portal-conversations'" data-testid="portal-conversations">
      <div class="px-4 pb-1.5 pt-3.5">
        <h2 id="portal-conversations" class="cw-card-title">{{ w('inbox.portal_heading') }}</h2>
        <p class="m-0 text-xs text-ink-gray-7">{{ w('inbox.portal_line') }}</p>
      </div>
      <InboxRow v-for="r in conversations" :key="r.room" :row="r" :to="portalLink(r)" :title="projectTitle(r.project)"
        :subtitle="w('inbox.portal_with')" portal />
    </section>
    <div class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))">
      <router-link v-for="p in projects" :key="p.name" :to="{ name: 'portal-project', params: { project: p.name } }"
        class="cw-card flex items-center gap-3 px-4 py-3.5 text-ink-gray-9 no-underline hover:border-outline-gray-3"
        data-testid="portal-project-card">
        <ProjectBadge :name="p.name" :label="p.project_name" :status="p.status" size="lg" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-base font-semibold">{{ p.project_name || p.name }}</span>
          <span class="block truncate text-xs text-ink-gray-7">{{ p.cc_phase || p.name }}</span>
        </span>
        <Badge :label="statusOf(p.status).label" :theme="statusOf(p.status).theme" />
      </router-link>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Badge } from 'frappe-ui'
import PageHead from '../components/PageHead.vue'
import ProjectBadge from '../components/ProjectBadge.vue'
import { call } from '../api.js'
import { statusOf } from '../frame.js'
import { useMode } from '../mode.js'
import { createHost } from '../chat/host.js'
import InboxRow from '../chat/inbox/InboxRow.vue'
import { Inbox, portalLink } from '../chat/inbox/store.js'
import { wordsFor } from '../chat/words.js'

const projects = ref([])
const loaded = ref(false)
const error = ref('')
// P3-74 (§14.6, D-414): one row per Client room the client reads, with its unread and newest line, shown only with two
// or more (one goes straight to its project). The server reads them as the client: a project with the portal or its
// Discussion off drops out, and a client's row has no Needs a reply. Only pages make a chat host (F1).
const w = wordsFor(useMode(), true)
const inbox = new Inbox(createHost({ viewer: 'client' }))
const conversations = computed(() => inbox.state.rooms)
const projectTitle = (name) => projects.value.find((p) => p.name === name)?.project_name || inbox.state.projects.find((p) => p.name === name)?.title || name
inbox.load()
inbox.listen()
onUnmounted(() => inbox.close())

onMounted(async () => {
  try {
    projects.value = await call('construction_core.portal_api.projects')
  } catch (e) {
    error.value = e.message
  } finally {
    loaded.value = true
  }
})
</script>
