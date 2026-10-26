<template>
  <!-- P3-43 (D-303): an earlier revision beside the current one. Pictures and PDFs are shown side by side; for other
       kinds the facts are compared: who, when, size, what changed, and whether the content is the same. -->
  <Dialog :open="open" size="4xl" :title="older && newer ? `Compare Rev ${older.rev} with Rev ${newer.rev}` : 'Compare'"
    @update:open="(v) => $emit('update:open', v)">
    <div v-if="older && newer" class="flex flex-col gap-3" data-testid="compare-dialog">
      <p class="m-0 text-p-base text-ink-gray-7">{{ fileName }}</p>
      <p class="m-0 text-sm" :class="same ? 'text-ink-gray-8' : 'text-ink-gray-9'" data-testid="compare-same">
        {{ same ? 'The two revisions have the same content.' : 'The content differs between the two revisions.' }}
      </p>
      <div class="grid gap-3 md:grid-cols-2">
        <section v-for="r in [older, newer]" :key="r.rev" class="flex min-w-0 flex-col gap-2 rounded-5 border border-outline-gray-2 p-3" :aria-label="`Rev ${r.rev}`">
          <div class="flex items-center gap-2">
            <span class="text-base font-semibold text-ink-gray-9">Rev {{ r.rev }}</span>
            <Badge :label="r.current ? 'Current' : 'Archived'" size="sm" />
          </div>
          <div class="grid h-[300px] place-items-center overflow-hidden rounded-4 bg-surface-gray-2">
            <img v-if="preview === 'image'" :src="freshUrl(r.url, r.content_hash)" :alt="`Rev ${r.rev}`" class="max-h-full max-w-full object-contain" />
            <iframe v-else-if="preview === 'pdf'" :src="freshUrl(r.url, r.content_hash)" :title="`Rev ${r.rev}`" class="size-full border-0" />
            <span v-else :class="[kind.icon, 'size-10 text-ink-gray-5']" aria-hidden="true" />
          </div>
          <div class="text-sm text-ink-gray-7">{{ r.who }} · {{ modifiedLabel(r.when) }} · {{ formatSize(r.file_size) }}</div>
          <div class="min-h-5 text-sm text-ink-gray-9">{{ r.note || 'No note' }}</div>
          <a :href="freshUrl(r.url, r.content_hash)" target="_blank" rel="noopener" class="self-start text-sm text-ink-gray-8 underline">Open Rev {{ r.rev }}</a>
        </section>
      </div>
    </div>
  </Dialog>
</template>

<script setup>
import { computed } from 'vue'
import { Badge, Dialog } from 'frappe-ui'
import { KINDS, freshUrl, kindOf, modifiedLabel, previewOf } from '../files.js'
import { formatSize } from '../sections/util.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  fileName: { type: String, default: '' },
  older: { type: Object, default: null }, // revisions from the panel's details: rev, current, who, when, note, url…
  newer: { type: Object, default: null },
})
defineEmits(['update:open'])
const preview = computed(() => previewOf(props.fileName))
const kind = computed(() => KINDS[kindOf(props.fileName)])
const same = computed(() => !!props.older?.content_hash && props.older.content_hash === props.newer?.content_hash)
</script>
