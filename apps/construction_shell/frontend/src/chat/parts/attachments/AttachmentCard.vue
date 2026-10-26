<template>
  <div class="mt-2 flex flex-col gap-2" :data-testid="`${prefix}attachments`">
    <!-- One photo, or several as a grid that opens the viewer (canvas "Message cards": Photos) -->
    <figure v-if="photos.length === 1" class="m-0 w-80 max-w-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base"
      :data-testid="`${prefix}attachment`" data-kind="photo">
      <button type="button" class="block w-full cursor-zoom-in border-0 bg-surface-gray-2 p-0" :aria-label="w('attachments.open_photo', { name: photos[0].file_name })"
        :data-testid="`${prefix}photo`" @click="view(0)">
        <img :src="photos[0].preview.src" :alt="photos[0].file_name" class="block h-auto w-full" :width="photos[0].preview.w" :height="photos[0].preview.h" loading="lazy"
          @error="broken(photos[0])" />
      </button>
      <figcaption class="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-ink-gray-7">
        <span class="lucide-camera size-3.5 flex-none" aria-hidden="true" />
        <span class="flex-none">{{ caption }}</span>
        <span class="ml-auto min-w-0 truncate">{{ photos[0].file_name }}</span>
      </figcaption>
    </figure>
    <figure v-else-if="photos.length > 1" class="m-0 w-[340px] max-w-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base"
      :data-testid="`${prefix}attachment`" data-kind="photos">
      <div class="grid grid-cols-2 gap-0.5">
        <button v-for="(p, i) in photos.slice(0, 4)" :key="p.attachment" type="button"
          class="relative aspect-[4/3] cursor-zoom-in overflow-hidden border-0 bg-surface-gray-2 p-0"
          :aria-label="w('attachments.open_photo_n', { n: i + 1, count: photos.length })" :data-testid="`${prefix}photo`" @click="view(i)">
          <img :src="p.preview.src" :alt="p.file_name" class="block size-full object-cover" loading="lazy" @error="broken(p)" />
          <template v-if="i === 3 && photos.length > 4">
            <span class="absolute inset-0 bg-surface-gray-7 opacity-70 dark:bg-surface-base" aria-hidden="true" />
            <span class="absolute inset-0 grid place-items-center text-lg font-semibold text-ink-base dark:text-ink-gray-9">+{{ photos.length - 4 }}</span>
          </template>
        </button>
      </div>
      <figcaption class="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-ink-gray-7">
        <span class="lucide-camera size-3.5 flex-none" aria-hidden="true" />
        <span>{{ w('attachments.photos', { count: photos.length }) }} · {{ caption }}</span>
      </figcaption>
    </figure>

    <!-- Every other file: a fixed preview box (no layout jump), type, size and the revision sent; staff also see the
         revision it has now (§3.2, §15.6, canvas "Message cards": Documents, Drawings and models) -->
    <div v-for="c in files" :key="c.attachment" class="flex w-[420px] max-w-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base"
      :data-testid="`${prefix}attachment`" :data-kind="c.kind" :data-preview="viewOf(c).box" :data-reason="viewOf(c).reason || null">
      <div class="grid w-[132px] flex-none place-items-center bg-surface-gray-2 p-2.5 max-sm:w-[108px] max-sm:p-2">
        <div class="relative grid h-[110px] w-[116px] place-items-center overflow-hidden rounded-3 max-sm:w-[92px]" :data-testid="`${prefix}preview-box`">
          <img v-if="viewOf(c).box === 'image'" :src="viewOf(c).image.src" :alt="c.file_name" :width="viewOf(c).image.w || undefined" :height="viewOf(c).image.h || undefined"
            class="size-full bg-surface-base object-contain" loading="lazy" :data-testid="`${prefix}preview-image`" @error="broken(c)" />
          <div v-else-if="viewOf(c).box === 'pending'" class="grid size-full place-items-center bg-surface-gray-3 text-center text-[11px] leading-snug text-ink-gray-7 motion-safe:animate-pulse"
            :data-testid="`${prefix}preview-pending`">
            <span class="px-1">{{ w('attachments.preparing') }}</span>
          </div>
          <div v-else-if="viewOf(c).box === 'info'" class="flex size-full flex-col items-center justify-center gap-1 bg-surface-base px-1.5 text-center text-[11px] leading-snug text-ink-gray-8"
            :data-testid="`${prefix}preview-info`">
            <span class="lucide-box size-6 flex-none text-ink-gray-6" aria-hidden="true" />
            <span v-if="viewOf(c).schema" class="max-w-full break-words font-medium">{{ w('attachments.ifc_schema', { schema: viewOf(c).schema }) }}</span>
            <span v-if="viewOf(c).app" class="line-clamp-3 max-w-full break-words text-ink-gray-7">{{ w('attachments.ifc_app', { app: viewOf(c).app }) }}</span>
          </div>
          <div v-else class="flex size-full flex-col items-center justify-center gap-1 rounded-3 border border-dashed border-outline-gray-4 px-1.5 text-center text-[11px] leading-snug text-ink-gray-7"
            :data-testid="`${prefix}preview-none`">
            <span :class="viewOf(c).lock ? 'lucide-lock' : 'lucide-image-off'" class="size-5 flex-none" aria-hidden="true" />
            <span>{{ viewOf(c).reason === 'not_supported' ? w('attachments.no_preview_type', { type: typeOf(c) }) : w('attachments.no_preview') }}</span>
          </div>
        </div>
      </div>
      <div class="flex min-w-0 flex-1 flex-col gap-1 px-3 py-2.5">
        <div class="flex flex-wrap items-center gap-1.5">
          <Badge size="sm" :theme="cardTheme(c.file_name)" :label="typeOf(c) || w('attachments.file')" />
          <Badge v-if="c.badge?.rev" size="sm" theme="green" :label="w('attachments.rev', { rev: c.badge.rev })" />
          <Badge v-if="viewOf(c).lock" size="sm" theme="amber" :data-testid="`${prefix}lock`">
            <template #prefix><span class="lucide-lock size-3" aria-hidden="true" /></template>{{ w('attachments.locked') }}
          </Badge>
          <span v-if="c.rev_now" class="text-xs text-ink-gray-7" :data-testid="`${prefix}rev-now`">{{ w('attachments.rev_now', { rev: c.rev_now }) }}</span>
        </div>
        <div class="truncate text-base font-medium text-ink-gray-9">{{ c.file_name }}</div>
        <div class="text-xs text-ink-gray-7">{{ typeOf(c) }} · {{ formatSize(c.size) }}</div>
        <div v-if="viewOf(c).reason && viewOf(c).reason !== 'not_supported'" class="text-xs text-ink-gray-7" :data-testid="`${prefix}preview-reason`">{{ w(`attachments.reason_${viewOf(c).reason}`) }}</div>
        <div class="mt-auto flex flex-wrap gap-1.5 pt-1.5">
          <button v-if="viewOf(c).action === 'open'" type="button" :class="BUTTON" class="border-0 bg-surface-gray-2 text-ink-gray-8 hover:bg-surface-gray-3"
            :data-testid="`${prefix}attachment-open`" @click="openFile(c)">
            <span class="lucide-eye size-4" aria-hidden="true" />{{ w('attachments.open') }}
          </button>
          <a :href="c.url" :download="c.file_name" :class="[BUTTON, 'text-ink-gray-8', viewOf(c).action === 'download' ? 'bg-surface-gray-2 hover:bg-surface-gray-3' : 'bg-transparent hover:bg-surface-gray-2']"
            :data-testid="`${prefix}attachment-download`">
            <span class="lucide-download size-4" aria-hidden="true" />{{ w('attachments.download') }}
          </a>
        </div>
      </div>
    </div>

    <!-- A P3-07 message's file: the chip it always had -->
    <div v-if="legacy.length" class="flex flex-wrap gap-2">
      <a v-for="card in legacy" :key="card.url" :href="card.url" target="_blank" rel="noopener"
        class="inline-flex max-w-full items-center gap-2 rounded-4 border border-outline-gray-2 bg-surface-base px-2.5 py-1.5 text-[13px] text-ink-gray-9 no-underline hover:bg-surface-gray-1"
        :data-testid="`${prefix}attachment`">
        <Badge class="flex-none font-semibold" size="sm" :theme="extTheme(fileExt(card.file_name))" :label="fileExt(card.file_name) || w('attachments.file')" />
        <span class="min-w-0 truncate">{{ card.file_name }}</span>
      </a>
    </div>
    <PhotoViewer v-if="viewing !== null" :photos="photos" :start="viewing" :portal="portal" :prefix="prefix" @close="viewing = null" />
    <FileViewer v-if="opened" :file="opened" :src="freshUrl(opened.url, opened.content_hash)" :project="host.project" @close="opened = null" />
    <p v-if="openError" class="m-0 text-xs text-ink-red-7" role="alert">{{ openError }}</p>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, inject, reactive, ref } from 'vue'
import { Badge } from 'frappe-ui'
import { freshUrl } from '../../../files.js'
import { useMode } from '../../../mode.js'
import { extTheme, fileExt, formatSize } from '../../../sections/util.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { cardTheme, cardView, groupCards, previewKey, takenValues, typeOf } from './cards.js'
import PhotoViewer from './PhotoViewer.vue'

// The attachments part (design §13.2 F2, §15.6; canvas "Message cards", P3-65): the cards of the files a message
// carries, as the server built them for this reader (no File id ever reaches the screen, P3-07). A photo shows its
// 400 px preview, read through the chat's preview endpoint; the original loads in the viewer or with Download. Other
// types show a fixed preview box (P3-75, design §15.6): the picture, "Preparing preview" while it is made, the IFC schema
// and app, or why there is none. Staff open PDF, Office and drawing files in the viewer; everyone else downloads.
const props = defineProps({ items: { type: [Array, Object], default: () => [] }, message: Object, portal: Boolean, prefix: { type: String, default: '' } })
const w = wordsFor(useMode(), props.portal)
const BUTTON = 'inline-flex h-8 items-center gap-1.5 rounded-4 px-2.5 text-base no-underline max-md:h-12 max-md:px-3'
const host = inject(HOST_KEY, null)
// The P3-48 viewer, for staff only: the card resolves to its File on the server (host.fileOf); clients get Download.
const FileViewer = defineAsyncComponent(() => import('../../../components/FileViewer.vue'))
const opened = ref(null)
const openError = ref('')
// A preview that does not load (a restored site rebuilding it, a removed file) leaves its photo as a file card, and any
// other card as "The preview could not be made". It is tried again when the server gives the card a new preview: the
// key holds the preview's state and address (a realtime re-read after the renderer finishes).
const failed = reactive(new Set())
const broken = (c) => failed.add(previewKey(c))
const groups = computed(() => groupCards(props.items))
const photos = computed(() => groups.value.photos.filter((c) => !failed.has(previewKey(c))))
const files = computed(() => [...groups.value.files, ...groups.value.photos.filter((c) => failed.has(previewKey(c)))])
const views = computed(() => new Map(files.value.map((c) => [c.attachment, cardView(failed.has(previewKey(c)) ? { ...c, preview: { state: 'none' }, reason: 'failed' } : c, { canOpen: Boolean(host?.fileOf) })])))
const viewOf = (c) => views.value.get(c.attachment)
const legacy = computed(() => groups.value.legacy)
const viewing = ref(null)
const caption = computed(() => {
  const at = takenValues(photos.value)
  return at.taken ? w('attachments.taken_sent', at) : w('attachments.sent_at', at)
})
const view = (i) => (viewing.value = i)

async function openFile(c) {
  openError.value = ''
  try {
    opened.value = await host.fileOf(c.attachment)
  } catch (e) {
    openError.value = e.message || ''
  }
}
</script>
