<template>
  <!-- P3-41 (D-292, D-294): Files as the live design draws it (canvas 1791955581-f999, frame Files): the folder pane,
       the folder's files as a list or a grid, the selection toolbar, and the details panel. A file shared with the
       client keeps a small Client badge (D-294); a file a client sent says so, and stays where the clients' rules keep it
       (D-158). Every action is one of the Files calls, which check permission in their own body (DR-5). -->
  <div class="flex min-h-0 flex-1 flex-wrap gap-3 bg-surface-gray-1 p-3 md:flex-nowrap" data-testid="section-page" @keydown.esc="clearAll">
    <h1 class="sr-only" data-testid="section-title">Files</h1>
    <div class="flex min-h-0 w-full flex-none flex-col md:w-auto" :style="wide ? { width: `${treeW}px` } : {}">
      <FileTree :rows="treeRowsShown" :current="view ? '' : folder" :view="view" :total="total" :can-upload="canUpload" :can-folder="canFolder"
        :upload-hint="uploadHint" @pick="pick" @toggle="toggle" @view="openView" @upload="chooseFiles" @folder="startFolder" />
    </div>
    <div v-if="wide" role="separator" aria-orientation="vertical" aria-label="Resize the folder panel" aria-valuemin="180" aria-valuemax="360"
      :aria-valuenow="treeW" tabindex="0" title="Drag to resize" class="group relative -mx-3 hidden w-3 flex-none cursor-col-resize touch-none select-none place-items-center md:grid"
      data-testid="splitter" @pointerdown="startDrag" @keydown.left.prevent="resize(-16)" @keydown.right.prevent="resize(16)">
      <span class="h-10 w-1 rounded-full bg-outline-gray-3 group-hover:h-16 group-hover:bg-surface-blue-6 group-focus-visible:bg-surface-blue-6" aria-hidden="true" />
    </div>

    <section :aria-label="heading" class="flex min-h-[420px] min-w-0 flex-1 flex-col overflow-hidden rounded-6 border border-outline-gray-1 bg-surface-base">
      <div class="flex min-h-12 flex-wrap items-center gap-2 border-b border-outline-gray-1 py-2 pl-4 pr-3">
        <nav class="flex min-w-0 flex-[1_1_200px] items-center text-base" aria-label="Folder path" data-testid="breadcrumb">
          <template v-if="view">
            <span class="px-0.5 text-ink-gray-6">Project files</span><span class="mx-0.5 text-ink-gray-4">/</span>
            <span class="truncate px-0.5 font-medium text-ink-gray-9">{{ heading }}</span>
          </template>
          <template v-else>
            <template v-for="(c, i) in crumbs" :key="c.path">
              <button v-if="i < crumbs.length - 1" type="button" class="truncate rounded-4 px-0.5 text-ink-gray-6 hover:text-ink-gray-8" @click="pick(c.folder)">{{ c.label }}</button>
              <span v-else class="truncate px-0.5 font-medium text-ink-gray-9">{{ c.label }}</span>
              <span v-if="i < crumbs.length - 1" class="mx-0.5 text-ink-gray-4" aria-hidden="true">/</span>
            </template>
          </template>
        </nav>
        <div class="cw-tabbuttons" role="group" aria-label="Layout">
          <button type="button" class="cw-tabbutton" aria-label="List layout" :aria-pressed="layout === 'list'" data-testid="layout-list" @click="setLayout('list')"><span class="lucide-list size-4" aria-hidden="true" /></button>
          <button type="button" class="cw-tabbutton" aria-label="Grid layout" :aria-pressed="layout === 'grid'" data-testid="layout-grid" @click="setLayout('grid')"><span class="lucide-layout-grid size-4" aria-hidden="true" /></button>
        </div>
        <button type="button" class="grid size-7 place-items-center rounded-4" :class="infoOpen ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-7 hover:bg-surface-gray-2'"
          aria-label="Details panel" :aria-pressed="infoOpen" data-testid="details-toggle" @click="setInfo(!infoOpen)">
          <span class="lucide-info size-4" aria-hidden="true" />
        </button>
      </div>

      <!-- The selection bar covers the filter chips, which keep their place (P3-48): selecting a file never moves the
           rows under the pointer, so a double-click lands on the row it started on. -->
      <div class="relative flex min-h-12 flex-wrap items-center gap-2 py-2 pl-4 pr-3">
        <div v-if="selected.size" role="toolbar" aria-label="Selected file actions" class="absolute left-4 right-3 top-2 z-10 flex h-8 items-center gap-0.5 rounded-5 bg-surface-gray-2 px-0.5" data-testid="selection-bar">
          <Button variant="ghost" icon="lucide-x" aria-label="Clear the selection" data-testid="clear-selection" @click="clearSelection" />
          <span class="ml-0.5 mr-2 text-sm font-medium text-ink-gray-9" data-testid="selected-count">{{ selected.size }} selected</span>
          <Button variant="ghost" :icon="allShared ? 'lucide-user-x' : 'lucide-user-plus'" :aria-label="allShared ? 'Stop sharing with the client' : 'Share with the client'" :title="allShared ? 'Stop sharing with the client' : 'Share with the client'"
            :disabled="busy || !canShareSelection" data-testid="bulk-share" @click="shareSelected(!allShared)" />
          <Button variant="ghost" icon="lucide-download" aria-label="Download" title="Download" data-testid="bulk-download" @click="downloadSelected" />
          <Button variant="ghost" icon="lucide-folder-input" aria-label="Move" title="Move" :disabled="busy || !canMoveSelection" data-testid="bulk-move" @click="startMove([...selected])" />
          <Button variant="ghost" icon="lucide-trash-2" aria-label="Move to the trash" title="Move to the trash" :disabled="busy" data-testid="bulk-trash" @click="trashFiles([...selected])" />
          <Button variant="ghost" icon="lucide-link" aria-label="Copy link" title="Copy link" :disabled="selected.size !== 1" data-testid="bulk-link" @click="copyLink([...selected][0])" />
        </div>
        <div class="contents" :class="selected.size ? 'invisible' : ''" :inert="selected.size > 0">
          <div v-for="c in chips" :key="c.id" class="relative">
            <button type="button" aria-haspopup="menu" :aria-expanded="chipOpen === c.id" class="inline-flex h-7 items-center gap-1 rounded-4 border px-2 text-base"
              :class="filters[c.id] ? 'border-outline-gray-4 bg-surface-gray-2 text-ink-gray-9' : 'border-outline-gray-2 text-ink-gray-8 hover:border-outline-gray-3'"
              :data-testid="`chip-${c.id}`" @click.stop="chipOpen = chipOpen === c.id ? '' : c.id">
              {{ filters[c.id] ? c.options.find((o) => o.value === filters[c.id])?.label : c.label }}
              <span class="lucide-chevron-down size-3.5 text-ink-gray-6" aria-hidden="true" />
            </button>
            <div v-if="chipOpen === c.id" role="menu" :aria-label="c.label" class="absolute left-0 top-[calc(100%+4px)] z-20 min-w-[180px] rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 shadow-lg" @click.stop>
              <button v-for="o in c.options" :key="o.value" type="button" role="menuitemradio" :aria-checked="filters[c.id] === o.value"
                class="flex h-8 w-full items-center gap-2 rounded-4 px-2 text-left text-base text-ink-gray-9 hover:bg-surface-gray-2" @click="setFilter(c.id, o.value)">
                <span :class="['lucide-check size-3.5', filters[c.id] === o.value ? '' : 'opacity-0']" aria-hidden="true" />{{ o.label }}
              </button>
            </div>
          </div>
          <TextInput v-model="query" class="ml-auto w-[170px]" placeholder="Filter files…" aria-label="Filter files" data-testid="files-filter">
            <template #prefix><span class="lucide-search size-4 text-ink-gray-6" aria-hidden="true" /></template>
          </TextInput>
        </div>
        <p v-if="current?.client_folder && !view" class="m-0 w-full text-xs text-ink-gray-7" data-testid="client-folder-note">
          Clients add files here. Share one to let all the project's clients see it.
        </p>
        <p v-else-if="sharedFolder && !view" class="m-0 w-full text-xs text-ink-gray-7" data-testid="shared-folder-note">Files you add here are shared with the client.</p>
      </div>
      <p v-if="error" class="m-0 px-4 pb-2 text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
      <p v-if="notice" class="m-0 px-4 pb-2 text-sm text-ink-green-7" role="status" data-testid="notice">{{ notice }}</p>

      <div v-if="layout === 'list'" class="min-h-0 flex-1 overflow-auto">
        <div class="min-w-[440px]" role="table" :aria-label="`Files in ${heading}`">
          <div role="row" class="grid h-8 items-center gap-3 border-y border-outline-gray-1 bg-surface-gray-1 pl-4 pr-2 text-sm text-ink-gray-7" :style="{ gridTemplateColumns: cols }">
            <button v-for="h in headers" :key="h.key" type="button" role="columnheader" :aria-sort="sort.key === h.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'"
              class="flex items-center gap-1.5 whitespace-nowrap text-left hover:text-ink-gray-9" :data-testid="`sort-${h.key}`" @click="sortBy(h.key)">
              {{ h.label }}<span v-if="sort.key === h.key" :class="[sort.dir === 'asc' ? 'lucide-arrow-up' : 'lucide-arrow-down', 'size-3.5 text-ink-gray-8']" aria-hidden="true" />
            </button>
            <span role="columnheader"><span class="sr-only">Actions</span></span>
          </div>
          <div v-for="f in shown" :key="f.name" role="row" :aria-selected="selected.has(f.name)" tabindex="0"
            class="grid min-h-10 cursor-pointer items-center gap-3 border-b border-outline-gray-1 py-1 pl-4 pr-2 outline-none focus-visible:bg-surface-gray-1"
            :class="selected.has(f.name) ? 'bg-surface-gray-2' : 'hover:bg-surface-gray-1'" :style="{ gridTemplateColumns: cols }"
            data-testid="file-row" :data-file="f.file_name" :data-name="f.name" @click="select(f, $event)" @dblclick="openFile(f)" @keydown.enter.self="openFile(f)" @keydown.space.self.prevent="select(f, $event)" @contextmenu.prevent="menuAtPointer(f, $event)">
            <span role="cell" class="flex min-w-0 items-center gap-3">
              <span :class="['grid size-[22px] flex-none place-items-center rounded-2', kindOf(f).tile]" aria-hidden="true"><span :class="[kindOf(f).icon, 'size-3.5']" /></span>
              <span class="min-w-0">
                <span class="flex min-w-0 items-center gap-2">
                  <span class="truncate text-base text-ink-gray-9" data-testid="file-name">{{ f.file_name }}</span>
                  <Badge :label="revLabel(f.rev)" size="sm" class="flex-none" data-testid="rev-badge" />
                  <Badge v-if="f.client_visible" label="Client" theme="blue" size="sm" class="flex-none" data-testid="client-badge" />
                  <Badge v-else-if="f.from_client" label="Sender only" theme="amber" size="sm" class="flex-none" />
                </span>
                <span v-if="f.from_client" class="block truncate text-xs text-ink-gray-7" data-testid="sender">Sent by {{ f.sender }}</span>
                <span v-else-if="view" class="block truncate text-xs text-ink-gray-7" data-testid="file-path">{{ ['Project files', ...String(f.path || '').split('/').filter(Boolean)].join(' / ') }}</span>
              </span>
            </span>
            <span role="cell" class="flex min-w-0 items-center gap-2 text-sm text-ink-gray-8"><Avatar :label="f.owner_name" size="sm" /><span class="truncate">{{ f.owner_name }}</span></span>
            <span role="cell" class="whitespace-nowrap text-sm text-ink-gray-8">{{ modifiedLabel(f.modified) }}</span>
            <span v-if="!infoOpen" role="cell" class="whitespace-nowrap text-sm text-ink-gray-8">{{ formatSize(f.file_size) }}</span>
            <span role="cell" class="relative flex justify-end" @click.stop>
              <Button variant="ghost" icon="lucide-ellipsis-vertical" :aria-label="`More actions for ${f.file_name}`" aria-haspopup="menu" :aria-expanded="menuFor === f.name"
                data-testid="row-menu" @click="toggleMenu(f.name)" />
              <FileMenu v-if="menuFor === f.name" :file="f" :href="linkOf(f)" :project="project" :busy="busy" :movable="movable(f)"
                :class="menuAt ? 'fixed' : 'absolute right-0 top-[calc(100%+2px)]'" :style="menuAt ? { left: `${menuAt.left}px`, top: `${menuAt.top}px` } : null"
                @open="openFile(f)" @close="menuFor = ''" @share="(on) => shareFiles([f.name], on)" @move="startMove([f.name])" @copy="copyLink(f.name)" @trash="trashFiles([f.name])"
                @discuss="discussFile(f)" />
            </span>
          </div>
          <p v-if="!shown.length" class="m-0 px-4 py-3 text-ink-gray-7" data-testid="no-files">{{ emptyLine }}</p>
        </div>
      </div>

      <div v-else class="min-h-0 flex-1 overflow-auto px-4 pb-4 pt-1">
        <div class="mb-2 text-sm text-ink-gray-7">Files</div>
        <div class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(180px, 1fr))">
          <button v-for="f in shown" :key="f.name" type="button" :aria-pressed="selected.has(f.name)" :aria-label="f.file_name"
            class="flex w-full flex-col overflow-hidden rounded-6 border p-0 text-left" :class="selected.has(f.name) ? 'border-outline-gray-4 bg-surface-gray-2' : 'border-outline-gray-2 bg-surface-base shadow-sm'"
            data-testid="file-card" :data-file="f.file_name" :data-name="f.name" @click="select(f, $event)" @dblclick="openFile(f)" @contextmenu.prevent="menuAtPointer(f, $event)">
            <span class="flex h-10 items-center gap-2.5 pl-2 pr-1">
              <span :class="['grid size-5 flex-none place-items-center rounded-2', kindOf(f).tile]" aria-hidden="true"><span :class="[kindOf(f).icon, 'size-3']" /></span>
              <span class="min-w-0 flex-1 truncate text-sm font-medium text-ink-gray-9">{{ f.file_name }}</span>
              <Badge v-if="f.client_visible" label="Client" theme="blue" size="sm" class="flex-none" />
            </span>
            <!-- P3-75: the preview where the renderer made one (canvas "Files": the 120 px thumbnail box); a quiet skeleton while it is made -->
            <span class="mx-2 grid h-[120px] place-items-center overflow-hidden rounded-4" :class="thumbOf(f) === 'image' ? 'bg-surface-gray-2' : kindOf(f).tile"
              :data-testid="`thumb-${thumbOf(f)}`">
              <img v-if="thumbOf(f) === 'image'" :src="book.src(f.name)" :alt="f.file_name" class="size-full object-contain" loading="lazy" @error="lost(f)" />
              <span v-else-if="thumbOf(f) === 'pending'" class="size-full bg-surface-gray-3 motion-safe:animate-pulse"><span class="sr-only">{{ word('preparing') }}</span></span>
              <img v-else-if="kindName(f.file_name) === 'image'" :src="linkOf(f)" :alt="f.file_name" class="size-full object-cover" loading="lazy" />
              <span v-else :class="[kindOf(f).icon, 'size-10']" aria-hidden="true" />
            </span>
            <span class="flex h-10 min-w-0 items-center gap-2 px-2 text-xs text-ink-gray-7"><Avatar :label="f.owner_name" size="sm" class="flex-none" /><span class="truncate">{{ firstName(f.owner_name) }} · {{ modifiedLabel(f.modified) }}</span></span>
          </button>
        </div>
        <p v-if="!shown.length" class="m-0 py-3 text-ink-gray-7" data-testid="no-files">{{ emptyLine }}</p>
        <FileMenu v-if="menuFile && menuAt" :file="menuFile" :href="linkOf(menuFile)" :project="project" :busy="busy" :movable="movable(menuFile)"
          class="fixed" :style="{ left: `${menuAt.left}px`, top: `${menuAt.top}px` }"
          @open="openFile(menuFile)" @close="menuFor = ''" @share="(on) => shareFiles([menuFile.name], on)" @move="startMove([menuFile.name])"
          @copy="copyLink(menuFile.name)" @trash="trashFiles([menuFile.name])" @discuss="discussFile(menuFile)" />
      </div>
    </section>

    <FilePanel v-if="infoOpen" class="w-full flex-none md:w-[332px]" :file="detail" :project="project" :preview="panelPreview" :count="selected.size" :busy="busy" :error="detailError"
      @close="setInfo(false)" @share="(on) => detail && shareFiles([detail.name], on)"
      @upload-version="startVersion('upload')" @restore="(v) => startVersion('restore', v)" @compare="startCompare" @view="detail && openFile(detail)" />

    <DiscussThis ref="discuss" :project="project" />

    <FileViewer v-if="viewing" :file="viewing" :src="linkOf(viewing)" :project="project" @close="closeViewer" @saved="afterCadSave" />

    <input ref="picker" type="file" class="sr-only" multiple :disabled="!canUpload" data-testid="upload" @change="send" />

    <VersionDialog v-model:open="versioning" :mode="versionMode" :file="detail" :restoring="restoring" :busy="busy" @submit="saveVersion" />
    <CompareDialog v-model:open="comparing" :file-name="detail?.file_name || ''" :older="compareOlder" :newer="detail?.versions?.[0] || null" />

    <Dialog v-model:open="moving" title="Move files">
      <p class="m-0 mb-3 text-p-base text-ink-gray-7">Move {{ moveNames.length === 1 ? 'the file' : `${moveNames.length} files` }} to another folder of this project.</p>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Folder
        <select v-model="moveTarget" class="form-select w-full" data-testid="move-target">
          <option v-for="t in moveTargets" :key="t.folder" :value="t.folder">{{ t.label }}</option>
        </select>
      </label>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="close" />
          <Button variant="solid" theme="blue" label="Move" :disabled="busy || !moveTarget" data-testid="move-confirm" @click="move" />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:open="naming" title="New folder">
      <p class="m-0 mb-3 text-p-base text-ink-gray-7">A folder inside {{ current?.label || 'Project files' }}.</p>
      <form id="new-folder-form" @submit.prevent="createFolder">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Folder name
          <input v-model="folderName" maxlength="80" required class="form-input w-full" placeholder="Example: Renders" data-testid="new-folder-name" />
        </label>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="close" />
          <Button type="submit" form="new-folder-form" variant="solid" theme="blue" label="Create folder" :disabled="busy || !folderName.trim()" data-testid="new-folder-create" />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Avatar, Badge, Button, Dialog, TextInput } from 'frappe-ui'
import CompareDialog from '../components/CompareDialog.vue'
import DiscussThis from '../components/DiscussThis.vue'
import FileMenu from '../components/FileMenu.vue'
import FilePanel from '../components/FilePanel.vue'
import FileViewer from '../components/FileViewer.vue'
import FileTree from '../components/FileTree.vue'
import VersionDialog from '../components/VersionDialog.vue'
import { call, upload } from '../api.js'
import { ACCESS, KINDS, MODIFIED, crumbsOf, fileLink, filterFiles, freshUrl, revLabel, kindOf as kindName, modifiedLabel, nextSelection, ownerOptions,
  parentsOf, sortFiles, totalCount, treeRows, typeOptions } from '../files.js'
import { menuPlace, viewerOf } from '../viewer.js'
import { chatWord } from '../chat/words.js'
import { useMode } from '../mode.js'
import { PreviewBook, previewable } from '../previews.js'
import { formatSize } from './util.js'

const props = defineProps({ frame: Object, project: String, section: String })
const route = useRoute()
const router = useRouter()
const API = 'construction_core.files.api.'
const store = (key, fallback) => { try { return localStorage.getItem(key) ?? fallback } catch { return fallback } }
const keep = (key, value) => { try { localStorage.setItem(key, value) } catch { /* private window */ } }

const tree = ref([])
const files = ref([])
const error = ref('')
const notice = ref('')
const busy = ref(false)
const query = ref('')
const filters = ref({ type: '', owner: '', modified: '', access: '' })
const chipOpen = ref('')
const sort = ref({ key: 'modified', dir: 'desc' })
const layout = ref(store('cw-files-layout', 'list') === 'grid' ? 'grid' : 'list')
const infoOpen = ref(store('cw-files-info', '1') !== '0')
const treeW = ref(Math.max(180, Math.min(360, Number(store('cw-files-tree-w', 236)) || 236)))
const open = ref(new Set(JSON.parse(store('cw-files-open', '[]') || '[]')))
const selected = ref(new Set())
const anchor = ref(null)
const menuFor = ref('')
const menuAt = ref(null)
const viewing = ref(null)
const detail = ref(null)
const detailError = ref('')
const moving = ref(false)
const moveNames = ref([])
const moveTarget = ref('')
const naming = ref(false)
const folderName = ref('')
const picker = ref(null)
// P3-75 (design §15): previews of the files shown, read in one batch per list (previews.api.states), for the grid's
// thumbnails and the details panel. A picture that does not load leaves the file's icon.
const book = new PreviewBook('file')
const lostPreviews = ref(new Set())
const wordMode = useMode()
const word = (key) => chatWord(`attachments.${key}`, { mode: wordMode.value })
const thumbOf = (f) => {
  const entry = book.of(f.name)
  if (entry?.state === 'ready' && !lostPreviews.value.has(f.name)) return 'image'
  return entry?.state === 'pending' ? 'pending' : 'icon'
}
const lost = (f) => (lostPreviews.value = new Set([...lostPreviews.value, f.name]))
const panelPreview = computed(() => {
  const name = detail.value?.name
  if (!name || lostPreviews.value.has(name)) return null
  return { entry: book.of(name), src: book.src(name) }
})
const wide = ref(typeof window !== 'undefined' ? window.innerWidth >= 768 : true)

// The URL is the source of truth: ?folder=<id>, or ?view=shared|recent; the project's root folder when none.
const view = computed(() => (['shared', 'recent'].includes(route.query.view) ? route.query.view : ''))
const folder = computed(() => route.query.folder || tree.value.find((n) => n.path === '')?.folder || '')
const current = computed(() => tree.value.find((f) => f.folder === folder.value))
const total = computed(() => totalCount(tree.value))
const treeRowsShown = computed(() => treeRows(tree.value, open.value))
const crumbs = computed(() => crumbsOf(current.value?.path || '', tree.value))
const heading = computed(() => (view.value === 'shared' ? 'Shared with client' : view.value === 'recent' ? 'Recent' : current.value?.label || 'Project files'))
const inClientFolder = computed(() => !!current.value?.client_folder)
const sharedFolder = computed(() => !!(current.value?.client_visible && current.value?.path && !inClientFolder.value))
const canUpload = computed(() => !view.value && !!folder.value && !inClientFolder.value)
const canFolder = computed(() => !view.value && !!folder.value && !String(current.value?.path || '').startsWith('06_Client'))
const uploadHint = computed(() => (view.value ? 'Open a folder to add files to it.' : inClientFolder.value ? "Only the project's clients add files here." : ''))
const shown = computed(() => sortFiles(filterFiles(files.value, { query: query.value, ...filters.value }), sort.value.key, sort.value.dir))
const cols = computed(() => (infoOpen.value ? 'minmax(170px, 2fr) minmax(96px, 1fr) 84px 32px' : 'minmax(200px, 2fr) minmax(120px, 1fr) 110px 80px 32px'))
const headers = computed(() => [
  { key: 'name', label: 'Name' }, { key: 'owner', label: 'Owner' }, { key: 'modified', label: 'Date modified' },
  ...(infoOpen.value ? [] : [{ key: 'size', label: 'File size' }]),
])
const chips = computed(() => [
  { id: 'type', label: 'Type', options: typeOptions(files.value) },
  { id: 'owner', label: 'People', options: ownerOptions(files.value) },
  { id: 'modified', label: 'Modified', options: MODIFIED },
  { id: 'access', label: 'Client access', options: ACCESS },
])
const emptyLine = computed(() => (files.value.length ? 'No file matches.' : view.value === 'shared' ? 'Nothing is shared with the client yet.'
  : view.value === 'recent' ? 'No file yet.' : 'This folder is empty.'))
const menuFile = computed(() => (layout.value === 'grid' && files.value.find((f) => f.name === menuFor.value)) || null)
const picked = computed(() => files.value.filter((f) => selected.value.has(f.name)))
const allShared = computed(() => picked.value.length > 0 && picked.value.every((f) => f.client_visible))
const canShareSelection = computed(() => picked.value.length > 0)
const canMoveSelection = computed(() => picked.value.length > 0 && picked.value.every(movable))
const moveTargets = computed(() => tree.value.filter((n) => n.folder !== folder.value && !n.client_folder)
  .map((n) => ({ folder: n.folder, label: ['Project files', ...n.path.split('/').filter(Boolean)].join(' / ') })))

const kindOf = (f) => KINDS[kindName(f.file_name)]
const firstName = (name) => String(name || '').split(' ')[0]
function movable(f) {
  return !f.from_client && !String(f.path ?? current.value?.path ?? '').startsWith('06_Client/')
}

function go(query) {
  router.push({ name: 'section', params: { project: props.project, section: 'files' }, query })
}
function pick(id) {
  const node = tree.value.find((n) => n.folder === id)
  if (node?.path) toggle(node.path, true)
  go({ folder: id })
}
function openView(id) {
  go({ view: id })
}
function toggle(path, forceOpen = false) {
  const next = new Set(open.value)
  if (next.has(path) && !forceOpen) next.delete(path)
  else next.add(path)
  open.value = next
  keep('cw-files-open', JSON.stringify([...next]))
}
function setLayout(v) {
  layout.value = v
  keep('cw-files-layout', v)
}
function setInfo(v) {
  infoOpen.value = v
  keep('cw-files-info', v ? '1' : '0')
}
function setFilter(id, value) {
  filters.value = { ...filters.value, [id]: value }
  chipOpen.value = ''
}
function sortBy(key) {
  sort.value = sort.value.key === key ? { key, dir: sort.value.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'modified' ? 'desc' : 'asc' }
}
function select(f, event) {
  const ordered = shown.value.map((r) => r.name)
  selected.value = nextSelection(selected.value, ordered, f.name, { ctrl: event?.ctrlKey || event?.metaKey, shift: event?.shiftKey }, anchor.value)
  if (!event?.shiftKey) anchor.value = f.name
}
function clearSelection() {
  selected.value = new Set()
  anchor.value = null
}
function clearAll() {
  menuFor.value = ''
  chipOpen.value = ''
  clearSelection()
}
// P3-43: a file keeps its address through its revisions; the content's hash asks the browser for the current bytes
const linkOf = (f) => freshUrl(f.url, f.content_hash)

// P3-43 (D-301, D-302, D-303): versions, from the details panel
const versioning = ref(false)
const versionMode = ref('upload')
const restoring = ref(null)
const comparing = ref(false)
const compareOlder = ref(null)
function startVersion(mode, version = null) {
  versionMode.value = mode
  restoring.value = version
  versioning.value = true
}
function startCompare(version) {
  compareOlder.value = version
  comparing.value = true
}
async function saveVersion({ file, note, takeoffs }) {
  const name = detail.value?.name
  if (!name) return
  const mode = versionMode.value
  const version = restoring.value?.version
  versioning.value = false
  let out = null
  await run(async () => {
    out = mode === 'upload'
      ? await upload(`${API}upload_version`, { file: name, note, takeoffs: takeoffs || '' }, file)
      : await call(`${API}restore`, { version, takeoffs: takeoffs || '' }, { post: true })
  })
  if (!out) return
  notice.value = mode === 'upload' ? `Rev ${out.rev} uploaded.` : `Restored as Rev ${out.rev}.`
  if (out.drawings?.length) router.push({ name: 'section', params: { project: props.project, section: 'takeoff', item: out.drawings[0] } })
}

// P3-48 (D-315): a double-click, Enter or the menu's Open shows the file in the viewer popup; a file it has no
// viewer for opens in a new tab as before.
function openFile(f) {
  menuFor.value = ''
  if (viewerOf(f.file_name)) viewing.value = f
  else window.open(linkOf(f), '_blank', 'noopener')
}

// Focus goes back to the file's row or card, since the menu item that opened the viewer is gone.
async function closeViewer() {
  const name = viewing.value?.name
  viewing.value = null
  await nextTick()
  if (name && (document.activeElement === document.body || !document.activeElement)) {
    document.querySelector(`[data-testid="${layout.value === 'grid' ? 'file-card' : 'file-row'}"][data-name="${CSS.escape(name)}"]`)?.focus()
  }
}

// P3-48 (D-319): a drawing saved in the viewer's Open CAD Studio is the file's next revision; the lists catch up.
async function afterCadSave(out) {
  notice.value = `Rev ${out.rev} uploaded.`
  await Promise.all([loadFiles(), loadTree()])
  await loadDetail()
}

// The row menu: under its ⋮ button, or at the pointer on a right-click (the keyboard's menu key: at the row).
function toggleMenu(name) {
  menuAt.value = null
  menuFor.value = menuFor.value === name ? '' : name
}
async function menuAtPointer(f, e) {
  if (!selected.value.has(f.name)) select(f, null)
  const r = e.currentTarget.getBoundingClientRect()
  const x = e.clientX || r.left + 24
  const y = e.clientY || r.top + r.height / 2
  menuAt.value = { left: x, top: y }
  menuFor.value = f.name
  await nextTick()
  const el = document.querySelector('[data-testid="row-menu-items"]')
  if (el) menuAt.value = menuPlace(x, y, el.getBoundingClientRect(), { width: window.innerWidth, height: window.innerHeight })
}

async function loadTree() {
  try {
    tree.value = await call(`${API}tree`, { project: props.project })
    const here = tree.value.find((n) => n.folder === folder.value)
    if (here) {
      const next = new Set(open.value)
      for (const p of [...parentsOf(here.path), here.path]) if (p) next.add(p)
      open.value = next
    }
  } catch (e) {
    error.value = e.message
  }
}

async function loadFiles() {
  error.value = ''
  menuFor.value = ''
  try {
    if (view.value) files.value = await call(`${API}list_view`, { project: props.project, view: view.value })
    else if (folder.value) files.value = await call(`${API}list_files`, { project: props.project, folder: folder.value })
    else files.value = []
  } catch (e) {
    error.value = e.message
    files.value = []
  }
  const keepOnly = new Set(files.value.map((f) => f.name))
  selected.value = new Set([...selected.value].filter((n) => keepOnly.has(n)))
  if (route.query.file && keepOnly.has(route.query.file) && !selected.value.size) selected.value = new Set([route.query.file])
}

async function loadDetail() {
  detailError.value = ''
  if (selected.value.size !== 1 || !infoOpen.value) {
    detail.value = null
    return
  }
  const name = [...selected.value][0]
  try {
    const d = await call(`${API}details`, { file: name })
    if (selected.value.has(name)) detail.value = d
  } catch (e) {
    detail.value = null
    detailError.value = e.message
  }
}

async function run(job, after = '') {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await job()
    notice.value = after
  } catch (e) {
    error.value = e.message || 'That did not work.'
  } finally {
    busy.value = false
    menuFor.value = ''
    await Promise.all([loadFiles(), loadTree()])
    await loadDetail()
  }
}

function chooseFiles() {
  picker.value?.click()
}
function send(event) {
  const chosen = [...event.target.files]
  event.target.value = ''
  if (!chosen.length) return
  run(async () => {
    for (const file of chosen) {
      await upload(`${API}upload`, { project: props.project, folder: folder.value, client_visible: sharedFolder.value ? 1 : 0 }, file)
    }
  }, chosen.length === 1 ? `${chosen[0].name} uploaded.` : `${chosen.length} files uploaded.`)
}
function shareFiles(names, on) {
  run(async () => {
    for (const name of names) await call(`${API}set_client_visible`, { file: name, visible: on ? 1 : 0 }, { post: true })
  }, on ? 'Shared with the client.' : 'No longer shared with the client.')
}
function shareSelected(on) {
  shareFiles([...selected.value], on)
}
function trashFiles(names) {
  const what = names.length === 1 ? (files.value.find((f) => f.name === names[0])?.file_name || 'this file') : `${names.length} files`
  if (!window.confirm(`Move ${what} to the trash? It leaves every list; the file is kept.`)) return
  run(async () => {
    for (const name of names) await call(`${API}trash`, { file: name }, { post: true })
    clearSelection()
  }, names.length === 1 ? 'Moved to the trash.' : `${names.length} files moved to the trash.`)
}
function downloadSelected() {
  for (const f of picked.value) {
    const a = document.createElement('a')
    a.href = linkOf(f)
    a.download = f.file_name
    document.body.appendChild(a)
    a.click()
    a.remove()
  }
}
function startMove(names) {
  menuFor.value = ''
  moveNames.value = names
  moveTarget.value = moveTargets.value[0]?.folder || ''
  moving.value = true
}
function move() {
  const names = moveNames.value
  const target = moveTarget.value
  moving.value = false
  run(() => call(`${API}move`, { project: props.project, files: JSON.stringify(names), folder: target }, { post: true }),
    names.length === 1 ? 'Moved.' : `${names.length} files moved.`)
}
function startFolder() {
  folderName.value = ''
  naming.value = true
}
function createFolder() {
  const name = folderName.value.trim()
  naming.value = false
  run(async () => {
    const out = await call(`${API}new_folder`, { project: props.project, parent: folder.value, name }, { post: true })
    if (current.value?.path !== undefined) toggle(current.value.path, true)
    go({ folder: out.folder })
  }, `Folder ${name} created.`)
}
// "Discuss this" (P3-66, design §3.5): the file's conversation, in the Team room or the Client room when both may have it
const discuss = ref(null)
function discussFile(f) {
  menuFor.value = ''
  discuss.value?.start('File', f.name)
}
async function copyLink(name) {
  menuFor.value = ''
  const f = files.value.find((r) => r.name === name)
  const link = fileLink(window.location.origin, props.project, view.value ? f?.folder : folder.value, name)
  try {
    await navigator.clipboard.writeText(link)
    notice.value = 'Link copied.'
  } catch {
    notice.value = link
  }
}

// The folder panel's width: drag the splitter, or use the arrow keys on it (180 to 360 px, kept per browser).
function resize(delta) {
  treeW.value = Math.max(180, Math.min(360, treeW.value + delta))
  keep('cw-files-tree-w', String(treeW.value))
}
function startDrag(e) {
  e.preventDefault()
  const x0 = e.clientX
  const w0 = treeW.value
  const moveTo = (ev) => { treeW.value = Math.max(180, Math.min(360, Math.round(w0 + ev.clientX - x0))) }
  const up = () => {
    window.removeEventListener('pointermove', moveTo)
    window.removeEventListener('pointerup', up)
    keep('cw-files-tree-w', String(treeW.value))
  }
  window.addEventListener('pointermove', moveTo)
  window.addEventListener('pointerup', up)
}

function away(e) {
  if (!e.target.closest('[data-testid="row-menu-items"]') && !e.target.closest('[data-testid="row-menu"]')) menuFor.value = ''
  chipOpen.value = ''
}
const onResize = () => { wide.value = window.innerWidth >= 768 }
const onKey = (e) => { if (e.key === 'Escape') menuFor.value = '' }
const onScroll = () => { if (menuAt.value) menuFor.value = '' }
onMounted(() => {
  document.addEventListener('click', away)
  document.addEventListener('keydown', onKey)
  document.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  book.stop()
  document.removeEventListener('click', away)
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('resize', onResize)
})

watch(() => props.project, () => { clearSelection(); loadTree() }, { immediate: true })
watch([folder, view], () => { clearSelection(); notice.value = ''; loadFiles() }, { immediate: true })
watch([() => [...selected.value].join('|'), infoOpen], loadDetail)
// Thumbnails exist in the grid only; the details panel asks for the one file it shows.
watch([shown, layout], () => {
  if (layout.value === 'grid') book.want(shown.value.filter((f) => previewable(f.file_name)).map((f) => ({ id: f.name, stamp: String(f.modified || '') })))
}, { immediate: true })
watch(detail, (d) => d && previewable(d.file_name) && book.want([{ id: d.name, stamp: String(d.modified || '') }]))
</script>
