<template>
  <!-- P3-41 (D-292): the design's details panel for the selected file: a preview where the file allows one, who sees
       it, the file's details, and its activity. P3-43 (D-301, D-303): its versions, newest first, with Upload new
       version, Open, Compare and Restore. -->
  <aside aria-label="Details" class="flex min-w-0 flex-col overflow-hidden rounded-6 border border-outline-gray-1 bg-surface-base" data-testid="file-panel">
    <div class="flex min-h-12 items-center gap-2.5 py-2 pl-4 pr-2">
      <span v-if="file" :class="['grid size-[22px] flex-none place-items-center rounded-2', kind.tile]" aria-hidden="true"><span :class="[kind.icon, 'size-3.5']" /></span>
      <h2 class="m-0 min-w-0 flex-1 break-all text-base font-semibold text-ink-gray-9" data-testid="panel-name">{{ file ? file.file_name : 'Details' }}</h2>
      <Button variant="ghost" icon="lucide-x" aria-label="Close details" data-testid="panel-close" @click="$emit('close')" />
    </div>

    <div v-if="file" class="flex gap-1 border-b border-outline-gray-1 px-2" role="tablist" aria-label="Details panel">
      <button v-for="t in TABS" :key="t.id" type="button" role="tab" :aria-selected="tab === t.id"
        class="-mb-px h-9 border-b px-2.5 text-base" :class="tab === t.id ? 'border-outline-gray-8 text-ink-gray-9' : 'border-transparent text-ink-gray-6 hover:text-ink-gray-7'"
        :data-testid="`panel-tab-${t.id}`" @click="tab = t.id">{{ t.label }}</button>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div v-if="!file" class="flex flex-col items-center gap-4 px-6 py-10 text-center" data-testid="panel-empty">
        <span class="lucide-file-search size-12 text-ink-gray-4" aria-hidden="true" />
        <div class="text-base text-ink-gray-8">{{ count > 1 ? `${count} files selected` : 'Select a file to see its details' }}</div>
      </div>
      <p v-else-if="error" role="alert" class="m-4 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-gray-9">{{ error }}</p>

      <div v-else-if="tab === 'details'" class="flex flex-col gap-3 p-4" data-testid="panel-details">
        <div v-if="kindName === 'image'" class="overflow-hidden rounded-5 bg-surface-gray-2">
          <img :src="link" :alt="file.file_name" class="block max-h-[220px] w-full object-contain" data-testid="panel-preview" />
        </div>
        <!-- P3-75 (canvas "Files", details panel): the first page or drawing in a 200 px frame; a quiet skeleton while it is made -->
        <div v-else-if="preview?.entry?.state === 'ready' && !lost" class="grid h-[200px] place-items-center overflow-hidden rounded-5 bg-surface-gray-3 p-3" data-testid="panel-preview-box">
          <img :src="preview.src" :alt="file.file_name" class="max-h-full max-w-full bg-surface-base object-contain shadow-sm" data-testid="panel-preview-image" @error="lost = true" />
        </div>
        <div v-else-if="preview?.entry?.state === 'pending'" class="grid h-[200px] place-items-center rounded-5 bg-surface-gray-3 text-sm text-ink-gray-7 motion-safe:animate-pulse" data-testid="panel-preview-pending">
          {{ word('preparing') }}
        </div>
        <div v-else class="grid h-[120px] place-items-center rounded-5" :class="kind.tile">
          <span :class="[kind.icon, 'size-10']" aria-hidden="true" />
        </div>
        <p v-if="noPreview" class="m-0 -mt-1 text-xs text-ink-gray-7" data-testid="panel-preview-reason">{{ word(`reason_${noPreview}`) }}</p>
        <div class="flex flex-wrap gap-2">
          <Button v-if="office" variant="solid" theme="blue" size="md" class="flex-1" :label="file.from_client ? 'View in Office' : 'Edit in Office'" :route="officeRoute" />
          <Button v-else-if="kindName === 'cad'" variant="solid" theme="blue" size="md" class="flex-1" label="Open the drawing" :route="{ name: 'section', params: { project, section: 'takeoff' } }" />
          <Button v-if="viewable" size="md" class="flex-1" label="Open" data-testid="panel-open" @click="$emit('view')" />
          <a v-else :href="link" target="_blank" rel="noopener" class="inline-flex h-8 flex-1 items-center justify-center rounded-4 border border-outline-gray-2 text-base text-ink-gray-8 no-underline hover:border-outline-gray-3">Open</a>
          <a :href="link" download class="inline-flex h-8 flex-1 items-center justify-center rounded-4 border border-outline-gray-2 text-base text-ink-gray-8 no-underline hover:border-outline-gray-3">Download</a>
        </div>

        <h3 class="m-0 mt-1 text-base font-semibold text-ink-gray-9">Who can see it</h3>
        <div class="text-sm text-ink-gray-8" data-testid="panel-access">
          <template v-if="file.client_visible"><Badge label="Client" theme="blue" size="sm" /> Shared with the client: the project's clients can see and download it.</template>
          <template v-else-if="file.from_client"><Badge label="Sender only" theme="amber" size="sm" /> Sent by {{ file.owner_name }}. Only they and the team see it until you share it.</template>
          <template v-else><Badge label="Team only" theme="amber" size="sm" /> Project team only ({{ file.team }} {{ file.team === 1 ? 'person' : 'people' }}). Clients can't see this file.</template>
        </div>
        <Button v-if="canShare" variant="outline" class="self-start" :label="file.client_visible ? 'Stop sharing with the client' : 'Share with the client'" :disabled="busy" data-testid="panel-share" @click="$emit('share', !file.client_visible)" />

        <div class="-mx-4 my-1 h-px bg-outline-gray-2" />
        <h3 class="m-0 text-base font-semibold text-ink-gray-9">File details</h3>
        <dl class="m-0 flex flex-col gap-2.5 text-base">
          <div v-for="d in facts" :key="d.label"><dt class="text-xs font-medium text-ink-gray-7">{{ d.label }}</dt><dd class="m-0 mt-0.5 break-words text-ink-gray-9">{{ d.value }}</dd></div>
          <div><dt class="text-xs font-medium text-ink-gray-7">Versions</dt>
            <dd class="m-0 mt-0.5 text-ink-gray-9" data-testid="panel-versions-fact">{{ revLabel(file.rev) }} · {{ versionCount(versions.length) }} ·
              <button type="button" class="p-0 text-ink-gray-8 underline" data-testid="panel-see-versions" @click="tab = 'versions'">see all</button></dd></div>
        </dl>
      </div>

      <div v-else-if="tab === 'versions'" class="flex flex-col gap-3 p-4" data-testid="panel-versions">
        <div class="flex items-center justify-between gap-2">
          <Button variant="outline" icon-left="lucide-upload" label="Upload new version" :disabled="busy || !canRevise"
            :title="canRevise ? '' : 'A file a client sent stays as they sent it'" data-testid="panel-upload-version" @click="$emit('upload-version')" />
          <span class="text-xs text-ink-gray-7" data-testid="version-count">{{ versionCount(versions.length) }}</span>
        </div>
        <ol class="m-0 flex list-none flex-col gap-2 p-0">
          <li v-for="v in versions" :key="v.rev" class="rounded-5 border p-3" :class="v.current ? 'border-outline-gray-3 bg-surface-base' : 'border-outline-gray-1 bg-surface-gray-1'"
            data-testid="version-card" :data-rev="v.rev">
            <div class="flex gap-3">
              <span class="grid size-7 flex-none place-items-center rounded-4 text-sm font-semibold" :class="v.current ? 'bg-surface-gray-8 text-ink-base' : 'bg-surface-gray-3 text-ink-gray-8'" aria-hidden="true">{{ v.rev }}</span>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2"><span class="text-base font-medium text-ink-gray-9">{{ revLabel(v.rev) }}</span>
                  <Badge v-if="v.current" :label="file.client_visible ? 'Shared' : 'Current'" :theme="file.client_visible ? 'blue' : 'gray'" size="sm" />
                  <Badge v-else label="Archived" size="sm" /></div>
                <div class="mt-0.5 truncate text-xs text-ink-gray-7">{{ v.who }} · {{ modifiedLabel(v.when) }} · {{ formatSize(v.file_size) }}</div>
                <div v-if="v.note" class="mt-1 break-words text-sm text-ink-gray-9">{{ v.note }}</div>
                <div class="mt-2 flex flex-wrap gap-1">
                  <a :href="freshUrl(v.url, v.content_hash)" target="_blank" rel="noopener" class="inline-flex h-7 items-center rounded-4 bg-surface-gray-2 px-2.5 text-sm text-ink-gray-8 no-underline hover:bg-surface-gray-3" data-testid="version-open">Open</a>
                  <template v-if="!v.current">
                    <Button variant="subtle" label="Compare" :title="`Compare with ${revLabel(versions[0].rev)}`" data-testid="version-compare" @click="$emit('compare', v)" />
                    <Button variant="ghost" label="Restore" :disabled="busy || !canRevise" data-testid="version-restore" @click="$emit('restore', v)" />
                  </template>
                </div>
              </div>
            </div>
          </li>
        </ol>
        <p class="m-0 text-xs text-ink-gray-7">Restore copies an old version back as the next revision. Nothing is deleted, and the history stays complete.</p>
      </div>

      <ol v-else class="m-0 flex list-none flex-col px-4 pb-4 pt-2" data-testid="panel-activity">
        <li v-for="(e, i) in file.events" :key="i" class="flex gap-3 border-b border-outline-gray-1 py-2.5">
          <Avatar :label="e.who" size="xl" />
          <div class="min-w-0"><div class="text-base text-ink-gray-9"><strong class="font-semibold">{{ e.who }}</strong> {{ lower(e.what) }}</div><div class="mt-0.5 text-xs text-ink-gray-7">{{ modifiedLabel(e.when) }}</div></div>
        </li>
      </ol>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import { KINDS, freshUrl, kindOf, modifiedLabel, revLabel, typeLabel, versionCount } from '../files.js'
import { chatWord } from '../chat/words.js'
import { REASONS } from '../chat/parts/attachments/cards.js'
import { OFFICE } from '../loader.js'
import { useMode } from '../mode.js'
import { viewerOf } from '../viewer.js'
import { formatSize, stampTime } from '../sections/util.js'

const props = defineProps({
  file: { type: Object, default: null },
  project: { type: String, required: true },
  count: { type: Number, default: 0 },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  preview: { type: Object, default: null }, // P3-75: { entry: the preview's state, src } for the selected file
})
defineEmits(['close', 'share', 'upload-version', 'restore', 'compare', 'view'])
const TABS = [{ id: 'details', label: 'Details' }, { id: 'versions', label: 'Versions' }, { id: 'activity', label: 'Activity' }]
const tab = ref('details')
const wordMode = useMode()
const word = (key) => chatWord(`attachments.${key}`, { mode: wordMode.value })
const lost = ref(false) // the preview picture did not load: the file's icon stays
// Why a file has no preview, when the renderer said (locked, too large, blank, failed, service down); "not supported" is no news.
const noPreview = computed(() => {
  const entry = props.preview?.entry
  return entry?.state === 'none' && REASONS.includes(entry.reason) && entry.reason !== 'not_supported' && kindName.value !== 'image' ? entry.reason : ''
})
const kindName = computed(() => (props.file ? kindOf(props.file.file_name) : 'other'))
const kind = computed(() => KINDS[kindName.value])
const office = computed(() => !!props.file && OFFICE.test(props.file.file_name))
const viewable = computed(() => !!viewerOf(props.file?.file_name)) // P3-48 (D-315): Open shows the viewer popup
const officeRoute = computed(() => ({ name: 'section', params: { project: props.project, section: 'files', item: props.file.name, action: 'edit' } }))
const canShare = computed(() => !!props.file)
const versions = computed(() => props.file?.versions || [])
const link = computed(() => (props.file ? freshUrl(props.file.url, props.file.content_hash) : ''))
const canRevise = computed(() => !!props.file && !props.file.from_client) // D-158: a client's file stays as sent
const facts = computed(() => (props.file ? [
  { label: 'Type', value: typeLabel(props.file.file_name) },
  { label: 'Size', value: formatSize(props.file.file_size) },
  { label: 'Folder', value: ['Project files', ...String(props.file.path || '').split('/').filter(Boolean)].join(' / ') },
  { label: 'Owner', value: props.file.owner_name },
  { label: 'Modified', value: stampTime(props.file.modified) },
  { label: 'Added', value: stampTime(props.file.creation) },
] : []))
const lower = (what) => String(what || '').replace(/^[A-Z](?=[a-z])/, (c) => c.toLowerCase())

watch(() => props.file && props.file.name, () => { tab.value = 'details'; lost.value = false })
</script>
