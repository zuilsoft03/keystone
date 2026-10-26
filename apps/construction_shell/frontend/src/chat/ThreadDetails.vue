<template>
  <div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4 py-3" :data-testid="`${prefix}thread-details`">
    <section v-if="root">
      <h3 class="cw-label m-0 mb-1.5 text-ink-gray-7">{{ w('core.about_thread') }}</h3>
      <div class="rounded-5 border border-outline-gray-2 px-3 py-2">
        <div class="text-sm font-semibold text-ink-gray-9">{{ root.author.name }}</div>
        <p class="m-0 mt-0.5 line-clamp-3 whitespace-pre-wrap text-sm text-ink-gray-8">{{ plain(root.text, w) || w(`kind.${root.kind}`) }}</p>
      </div>
    </section>
    <Gallery :thread="thread.name" :capabilities="thread.capabilities" :fallback="files" :portal="portal" :prefix="prefix" />
    <section>
      <h3 class="cw-label m-0 mb-1.5 text-ink-gray-7">{{ w('core.people') }} · {{ people.length }}</h3>
      <ul class="m-0 flex list-none flex-col gap-2 p-0">
        <li v-for="p in people" :key="p.user" class="flex items-center gap-2" :data-testid="`${prefix}details-person`">
          <Avatar :image="p.image || undefined" :label="p.name" size="md" :theme="themeOf(p.user)" />
          <span class="truncate text-sm text-ink-gray-9">{{ p.name }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Avatar } from 'frappe-ui'
import { themeOf } from '../frame.js'
import { useMode } from '../mode.js'
import Gallery from './parts/attachments/Gallery.vue'
import { plain } from './tokens.js'
import { wordsFor } from './words.js'

// The thread's details (P3-64, canvas frame 1 "Details"), the working parts only: the root it hangs off, Files in this
// conversation (P3-65: the server's gallery read; the loaded messages' files where it cannot be read) and the people
// who wrote. A record's card waits for a later row, roles for the people list for P3-27. The root's text reads its tokens as
// words (P3-66).
const props = defineProps({
  thread: { type: Object, required: true },
  root: { type: Object, default: null },
  messages: { type: Array, default: () => [] },
  portal: Boolean,
  prefix: { type: String, default: '' },
})
const w = wordsFor(useMode(), props.portal)
const all = computed(() => [...(props.root ? [props.root] : []), ...props.messages])
const files = computed(() => {
  const seen = new Map()
  for (const m of all.value) for (const f of m.parts?.attachments || []) if (f?.url && !seen.has(f.url)) seen.set(f.url, f)
  return [...seen.values()]
})
const people = computed(() => {
  const seen = new Map()
  for (const m of all.value) if (m.kind !== 'System' && m.author?.user && !seen.has(m.author.user)) seen.set(m.author.user, m.author)
  return [...seen.values()]
})
</script>
