<template>
  <section :data-testid="`${prefix}gallery`">
    <h3 class="cw-label m-0 mb-1.5 text-ink-gray-7">{{ w('core.files_here') }} · {{ cards.length }}</h3>
    <p v-if="!cards.length && !loading" class="m-0 text-sm text-ink-gray-7">{{ w('attachments.gallery_empty') }}</p>
    <div v-else class="grid grid-cols-3 gap-1.5">
      <component :is="c.kind === 'photo' && c.preview?.state === 'ready' ? 'button' : 'a'" v-for="c in cards" :key="c.attachment || c.url"
        v-bind="c.kind === 'photo' && c.preview?.state === 'ready' ? { type: 'button' } : { href: c.url, target: '_blank', rel: 'noopener' }"
        class="min-w-0 overflow-hidden rounded-4 border border-outline-gray-2 bg-surface-base p-0 text-left no-underline"
        :title="c.file_name" :data-testid="`${prefix}gallery-file`" @click="open(c)">
        <img v-if="c.kind === 'photo' && c.preview?.state === 'ready'" :src="c.preview.src" alt="" class="block h-[72px] w-full object-cover" loading="lazy" />
        <span v-else class="grid h-[72px] place-items-center bg-surface-gray-2">
          <Badge size="sm" :theme="extTheme(fileExt(c.file_name))" :label="fileExt(c.file_name) || w('attachments.file')" />
        </span>
        <span class="block truncate px-1.5 py-1 text-[11px] text-ink-gray-8">{{ c.file_name }}</span>
      </component>
    </div>
    <Button v-if="cursor" class="mt-2" size="sm" variant="ghost" :label="w('core.older')" :loading="loading" @click="more" />
    <PhotoViewer v-if="viewing !== null" :photos="photos" :start="viewing" :portal="portal" :prefix="prefix" :thread="thread" :capabilities="capabilities" @close="viewing = null" />
  </section>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { extTheme, fileExt } from '../../../sections/util.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import PhotoViewer from './PhotoViewer.vue'

// Files in this conversation (design §3.2, canvas "Discussion hub" details): the conversation's files, newest first,
// from the server's gallery read, which is built from the reader's own visible messages (rule 9: no staff note's file
// reaches a client). A view that cannot read it (the staff preview) shows the files of the messages it has loaded.
const props = defineProps({
  thread: { type: String, required: true },
  capabilities: { type: Array, default: null }, // the thread's, where the room does not say (the details panel): whether a picture can be marked up
  fallback: { type: Array, default: () => [] },
  portal: Boolean,
  prefix: { type: String, default: '' },
})
const host = inject(HOST_KEY)
const w = wordsFor(useMode(), props.portal)
const read = ref(null) // the server's cards, or null while the fallback is shown
const cursor = ref(null)
const loading = ref(false)
const viewing = ref(null)
const cards = computed(() => read.value ?? props.fallback)
const photos = computed(() => cards.value.filter((c) => c.kind === 'photo' && c.preview?.state === 'ready'))

const flatten = (messages) => messages.flatMap((m) => m.parts?.attachments || []).filter((c) => c && c.url)

async function load(after = null) {
  if (host.viewer === 'preview') return
  loading.value = true
  try {
    const out = await host.read('gallery', { thread: props.thread, ...(after ? { cursor: after } : {}) })
    const got = flatten(out.messages || [])
    read.value = after ? [...(read.value || []), ...got] : got
    cursor.value = out.cursor || null
  } catch {
    read.value = null // the loaded messages' files stand in
  } finally {
    loading.value = false
  }
}

const more = () => load(cursor.value)

function open(c) {
  const i = photos.value.indexOf(c)
  if (i >= 0) viewing.value = i
}

watch(() => props.thread, () => load(), { immediate: true })
defineExpose({ reload: () => load() })
</script>
