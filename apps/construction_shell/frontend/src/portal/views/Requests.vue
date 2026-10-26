<template>
  <section class="cw-card mx-auto flex w-full max-w-[720px] flex-col gap-3 p-5 max-md:-mx-5 max-md:-my-6 max-md:max-w-none max-md:rounded-none max-md:border-0 max-md:px-4" data-testid="portal-requests">
    <header class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <router-link :to="back" class="inline-flex min-h-12 items-center gap-1 rounded-4 pr-2 text-sm text-ink-gray-8 hover:text-ink-gray-9 md:min-h-8" data-testid="portal-requests-back">
        <span class="lucide-chevron-left size-4" aria-hidden="true" />{{ w('file_requests.back') }}
      </router-link>
      <h1 class="m-0 text-xl font-semibold text-ink-gray-9" data-testid="portal-requests-title">{{ w('file_requests.page_heading') }}</h1>
    </header>
    <RequestPage :request="request" portal prefix="portal-" @loaded="(page) => (thread = page.thread || '')" />
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useMode } from '../../mode.js'
import { wordsFor } from '../../chat/words.js'
import RequestPage from '../../chat/parts/file_requests/RequestPage.vue'

// "Files we asked for" (P3-71, design §3.10; D-166: a client sees what the team asked, never what is owed). The request page
// for a client at /portal/<project>?tab=discuss&request=<name>, with a way back to the conversation it came from (the Client
// room, or the thread the request was sent in). A request the client may not see answers "not found" on the page itself.
const props = defineProps({ request: { type: String, required: true }, room: { type: String, default: '' } })
const w = wordsFor(useMode(), true)
const thread = ref('')
const back = computed(() => ({ query: { tab: 'discuss', ...(thread.value && thread.value !== props.room ? { thread: thread.value } : {}) } }))
</script>
