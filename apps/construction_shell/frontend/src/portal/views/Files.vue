<template>
  <PageHead :crumb="`Client portal / ${data.project.name}`" title="Shared files" :meta="`${total} ${total === 1 ? 'item' : 'items'}`">
    <label v-if="canSend && groups.includes('files')"
      class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-4 bg-surface-blue-6 px-3 text-base text-ink-base hover:bg-surface-blue-7 has-[:disabled]:cursor-not-allowed has-[:disabled]:bg-surface-gray-2 has-[:disabled]:text-ink-gray-4"
      data-testid="portal-send-file">
      <span class="lucide-upload size-4" aria-hidden="true" />{{ sending ? 'Sending…' : 'Send a file' }}
      <input type="file" class="sr-only" :accept="accept" :disabled="sending" data-testid="portal-send-file-input" @change="pick" />
    </label>
  </PageHead>
  <p class="m-0 text-sm text-ink-gray-8">Files your project team shared with you, and the files you sent. A file you send is seen by you and the team until they share it.</p>
  <p v-if="canSend && hint" class="m-0 -mt-2 text-xs text-ink-gray-7" data-testid="portal-size-hint">{{ hint }}</p>
  <div v-if="groups.length > 1" class="cw-tabbuttons self-start" role="group" aria-label="Show">
    <router-link v-for="g in ['all', ...groups]" :key="g" :to="{ query: { tab: 'files', ...(g === 'all' ? {} : { group: g }) } }"
      class="cw-tabbutton no-underline" :aria-pressed="group === g">{{ g === 'all' ? 'All' : groupLabel(g, mode) }} <span class="text-ink-gray-7">{{ g === 'all' ? total : count(g) }}</span></router-link>
  </div>

  <section v-for="g in shown" :key="g" :aria-label="groupLabel(g, mode)" class="cw-card overflow-x-auto" data-testid="portal-group" :data-group="g">
    <div v-if="group === 'all'" class="cw-card-header"><h2 class="cw-card-title">{{ groupLabel(g, mode) }}</h2><span class="ml-auto text-xs text-ink-gray-7">{{ count(g) }}</span></div>

    <template v-if="g === 'files'">
      <p v-if="!data.files.length && !holds.length" class="m-0 px-4 py-3 text-sm text-ink-gray-7">No file yet.</p>
      <!-- P3-75 (D-417): a large file is scanned after it arrives; it is "Checking…" until it is clean, or says why not -->
      <div v-for="(h, i) in holds" :key="`${i}:${h.file_name}`" class="cw-list-row max-md:flex-wrap max-md:gap-y-0" data-testid="portal-hold" :data-state="h.checking ? 'checking' : 'refused'">
        <Badge class="min-w-10 flex-none justify-center font-semibold" size="sm" :theme="extTheme(fileExt(h.file_name))" :label="fileExt(h.file_name) || 'FILE'" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-base text-ink-gray-9" :title="h.file_name">{{ h.file_name }}</span>
          <span v-if="h.checking" class="block text-xs text-ink-gray-7">{{ word('checking_note') }}</span>
          <span v-else class="block text-xs text-ink-red-7">{{ word(REFUSED.includes(h.reason) ? `refused_${h.reason}` : 'refused') }}</span>
        </span>
        <span class="hidden basis-full max-md:block" aria-hidden="true" />
        <span v-if="h.size" class="w-16 flex-none text-right text-sm text-ink-gray-8 max-md:w-auto max-md:text-left">{{ formatSize(h.size) }}</span>
        <Badge v-if="h.checking" size="sm" theme="gray" :label="word('checking')" data-testid="portal-hold-status">
          <template #prefix><span class="lucide-loader-circle size-3 motion-safe:animate-spin" aria-hidden="true" /></template>
        </Badge>
        <Badge v-else size="sm" theme="red" :label="word('refused_label')" data-testid="portal-hold-status" />
      </div>
      <div v-for="(f, at) in data.files" :key="at" class="cw-list-row max-md:flex-wrap max-md:gap-y-0" :class="{ '!border-t-0': at === 0 && group !== 'all' }" data-testid="portal-file">
        <Badge class="min-w-10 flex-none justify-center font-semibold" size="sm" :theme="extTheme(fileExt(f.file_name))" :label="fileExt(f.file_name) || 'FILE'" />
        <span class="min-w-0 flex-1">
          <a :href="f.url" target="_blank" rel="noopener" class="block truncate text-base text-ink-gray-9 no-underline hover:underline" :title="f.file_name">{{ f.file_name }}</a>
          <span v-if="f.mine && !f.shared" class="block text-xs text-ink-gray-7">Only you and the project team see this file</span>
        </span>
        <span class="hidden basis-full max-md:block" aria-hidden="true" />
        <span v-if="f.size" class="w-16 flex-none text-right text-sm text-ink-gray-8 max-md:w-auto max-md:text-left">{{ formatSize(f.size) }}</span>
        <Badge size="sm" :theme="f.mine ? 'violet' : 'blue'" :label="fileStatus(f)" data-testid="portal-file-status" />
        <button v-if="canAsk" type="button" class="inline-flex h-7 items-center gap-1 rounded-4 border-0 bg-transparent px-2 text-base text-ink-gray-8 hover:bg-surface-gray-2 max-md:h-12 max-md:min-w-12 max-md:justify-center"
          :aria-label="`${askWord} · ${f.file_name}`" data-testid="portal-file-ask" @click="emit('ask', f.url)">
          <span class="lucide-message-square size-4" aria-hidden="true" /><span class="max-md:sr-only">{{ askWord }}</span>
        </button>
        <a :href="f.url" download class="inline-flex h-7 items-center gap-1 rounded-4 border border-outline-gray-2 bg-surface-base px-2 text-base text-ink-gray-8 no-underline hover:border-outline-gray-3 max-md:ml-auto max-md:h-12 max-md:min-w-12 max-md:justify-center">
          <span class="lucide-download size-4" aria-hidden="true" /><span class="max-md:sr-only">Download</span>
        </a>
      </div>
    </template>

    <template v-else-if="g === 'documents'">
      <p v-if="!data.documents.length" class="m-0 px-4 py-3 text-sm text-ink-gray-7">No document shared yet.</p>
      <div v-for="(d, at) in data.documents" :key="d.name" class="cw-list-row" :class="{ '!border-t-0': at === 0 && group !== 'all' }" data-testid="portal-document">
        <span class="w-24 flex-none font-mono text-xs font-semibold text-ink-gray-9">{{ d.document_number }}</span>
        <span class="min-w-0 flex-1 truncate text-base text-ink-gray-9">{{ d.title }}</span>
        <Badge v-if="d.revision" size="sm" :label="`Rev ${d.revision}`" />
      </div>
    </template>

    <template v-else-if="g === 'whiteboards'">
      <p v-if="!data.whiteboards.length" class="m-0 px-4 py-3 text-sm text-ink-gray-7">Nothing shared on the canvas yet.</p>
      <div v-for="(b, at) in data.whiteboards" :key="b.name" class="cw-list-row" :class="{ '!border-t-0': at === 0 && group !== 'all' }">
        <span class="lucide-pen-line size-4 flex-none text-ink-gray-6" aria-hidden="true" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-base text-ink-gray-9">{{ b.title }}</span>
          <span class="block text-xs text-ink-gray-7"><template v-if="b.last_saved_on">Updated {{ formatDate(b.last_saved_on) }} · </template>view only</span>
        </span>
        <Button label="View" :route="boardLink(project, b.name)" data-testid="portal-board-link" />
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageHead from '../../components/PageHead.vue'
import { extTheme, fileExt, formatDate, formatSize } from '../../sections/util.js'
import { useMode } from '../../mode.js'
import { groupLabel } from '../../words.js'
import { chatWord } from '../../chat/words.js'
import { fileStatus, portalBoardLink, sizeHintValues } from '../tabs.js'

// Files on the live design (D-124, version 1791699712-925e; D-127): shared files, the document register and the
// shared canvas boards as groups ("Canvas", D-142). "Send a file", each file's size and status (P3-07); the design's
// SHARED date has no data and is not drawn (D-058, D-179).
const emit = defineEmits(['send-file', 'ask'])
const props = defineProps({
  data: { type: Object, required: true },
  project: String,
  groups: { type: Array, required: true },
  group: { type: String, default: 'all' },
  boardLink: { type: Function, default: portalBoardLink }, // the staff preview (P3-05) opens boards in its own panel
  // P3-07: the client's own portal opts in; the staff preview never sends (ClientView passes none of these).
  canSend: { type: Boolean, default: false },
  sending: Boolean,
  accept: { type: String, default: '' },
  // P3-65: "Ask about this file" opens the Client room with the file in its box (the client's own portal only)
  canAsk: { type: Boolean, default: false },
  // P3-75: the client's large sends being checked or refused, read by the project page
  holds: { type: Array, default: () => [] },
})
const askWord = chatWord('attachments.ask', { mode: useMode().value, portal: true })
const wordMode = useMode()
const word = (key, values = {}) => chatWord(`attachments.${key}`, { mode: wordMode.value, portal: true, values })
const REFUSED = ['threat', 'could_not_check', 'not_stored']
const hint = computed(() => {
  const values = sizeHintValues(props.data.upload)
  return values ? word('size_hint', values) : ''
})
function pick(event) {
  const [file] = event.target.files
  event.target.value = ''
  if (file) emit('send-file', file)
}
// Group names follow the client's mode: Simple calls the published documents "Final documents" (D-163).
const mode = useMode()
const KEY = { files: 'files', documents: 'documents', whiteboards: 'whiteboards' }
const count = (g) => (props.data[KEY[g]] || []).length
const shown = computed(() => (props.group === 'all' ? props.groups : [props.group]))
const total = computed(() => props.groups.reduce((n, g) => n + count(g), 0))
</script>
