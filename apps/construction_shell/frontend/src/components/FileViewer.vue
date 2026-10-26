<template>
  <div class="fixed inset-0 z-50 flex bg-black-overlay-200 p-0 md:p-6" data-testid="file-viewer-backdrop" @mousedown.self="requestClose">
    <div ref="box" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1"
      class="flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-surface-base shadow-2xl outline-none md:rounded-8" data-testid="file-viewer"
      :data-viewer="kind" :data-ready="ready ? '1' : null" @keydown.esc.stop="requestClose">
      <header class="flex h-12 flex-none items-center gap-2.5 border-b border-outline-gray-1 pl-4 pr-2">
        <span :class="['grid size-[22px] flex-none place-items-center rounded-2', tile.tile]" aria-hidden="true"><span :class="[tile.icon, 'size-3.5']" /></span>
        <h2 :id="titleId" class="m-0 min-w-0 flex-1 truncate text-base-semibold text-ink-gray-9" data-testid="viewer-title">{{ file.file_name }}</h2>
        <!-- On a narrow screen the header keeps the title, Edit and Close; the badges and links come back from sm up. -->
        <Badge v-if="file.rev" :label="revLabel(file.rev)" size="sm" class="hidden flex-none sm:inline-flex" />
        <Badge v-if="kind === 'office' || (kind === 'cad' && !editing)" label="View only" theme="amber" size="sm" class="hidden flex-none sm:inline-flex" />
        <Badge v-else-if="kind === 'cad'" label="Editing" theme="green" size="sm" class="flex-none" data-testid="viewer-cad-editing" />
        <Button v-if="kind === 'cad' && !editing" variant="solid" theme="blue" label="Edit" icon-left="lucide-pencil" :disabled="starting || !!refusal || (program === 'ocs' && !ready)"
          :title="refusal || undefined" class="flex-none" data-testid="viewer-cad-edit" @click="editDrawing" />
        <Button v-if="kind === 'office' && !officeDown" variant="solid" theme="blue" :label="file.from_client ? 'Open in Office' : 'Edit in Office'" :route="officeRoute" class="flex-none" data-testid="viewer-edit-office" />
        <a :href="src" target="_blank" rel="noopener" class="hidden size-8 flex-none items-center sm:inline-flex justify-center rounded-4 text-ink-gray-7 hover:bg-surface-gray-2"
          title="Open in new tab" aria-label="Open in new tab" data-testid="viewer-new-tab"><span class="lucide-external-link size-4" aria-hidden="true" /></a>
        <a :href="src" :download="file.file_name" class="hidden size-8 flex-none items-center sm:inline-flex justify-center rounded-4 text-ink-gray-7 hover:bg-surface-gray-2"
          title="Download" aria-label="Download" data-testid="viewer-download"><span class="lucide-download size-4" aria-hidden="true" /></a>
        <Button ref="closer" variant="ghost" icon="lucide-x" class="flex-none" aria-label="Close the viewer" data-testid="viewer-close" @click="requestClose" />
      </header>

      <div class="relative flex min-h-0 flex-1 flex-col bg-surface-gray-1">
        <div v-if="kind === 'image'" class="grid min-h-0 flex-1 place-items-center overflow-auto p-4">
          <img :src="src" :alt="file.file_name" class="max-h-full max-w-full object-contain" data-testid="viewer-image" />
        </div>

        <div v-else-if="kind === 'pdf'" ref="pages" class="min-h-0 flex-1 overflow-auto p-4" data-testid="viewer-pdf">
          <p v-if="pdfNote" class="m-0 mb-3 text-center text-sm text-ink-gray-7">{{ pdfNote }}</p>
        </div>

        <template v-else-if="kind === 'cad'">
          <!-- The drawing viewer's tools (P3-49): the drawing itself is read-only; a measure is clicked on the drawing. -->
          <div v-if="program === 'viewer'" class="flex h-10 flex-none items-center gap-1 overflow-x-auto border-b border-outline-gray-1 bg-surface-base px-2" role="group" aria-label="Drawing tools" data-testid="viewer-cad-tools">
            <Button variant="ghost" size="sm" icon-left="lucide-maximize" label="Fit" :disabled="!ready" data-testid="viewer-cad-fit" @click="view?.fit()" />
            <Button variant="ghost" size="sm" icon-left="lucide-ruler" label="Distance" :disabled="!ready" data-testid="viewer-cad-measure-distance" @click="view?.measure('distance')" />
            <Button variant="ghost" size="sm" icon-left="lucide-square-dashed" label="Area" :disabled="!ready" data-testid="viewer-cad-measure-area" @click="view?.measure('area')" />
            <Button variant="ghost" size="sm" icon-left="lucide-eraser" label="Clear measures" :disabled="!ready" data-testid="viewer-cad-measure-clear" @click="view?.clearMeasures()" />
            <Button variant="ghost" size="sm" icon-left="lucide-layers" :label="`Layers (${layers.length})`" class="ml-auto" :disabled="!ready || !layers.length"
              :aria-pressed="showLayers ? 'true' : 'false'" data-testid="viewer-cad-layers-toggle" @click="showLayers = !showLayers" />
          </div>
          <div class="relative flex min-h-0 flex-1">
            <iframe v-if="program === 'viewer'" ref="frame" :src="CAD_VIEW" title="Drawing viewer" class="min-h-0 w-full flex-1 border-0" data-testid="viewer-cad" @load="openView" />
            <iframe v-else-if="storageReady" ref="frame" :src="CAD_APP" title="Open CAD Studio" class="min-h-0 w-full flex-1 border-0" data-testid="viewer-cad" @load="openDrawing" />
            <aside v-if="program === 'viewer' && showLayers" class="flex w-64 flex-none flex-col gap-1 overflow-y-auto border-l border-outline-gray-1 bg-surface-base p-3" aria-label="Layers" data-testid="viewer-cad-layers">
              <h3 class="cw-label m-0 mb-1 text-ink-gray-7">Layers</h3>
              <label v-for="layer in layers" :key="layer.name" class="flex items-center gap-2 truncate text-xs text-ink-gray-8" data-testid="viewer-cad-layer">
                <input type="checkbox" class="form-checkbox rounded-1" :checked="layer.on" @change="showLayer(layer, $event.target)" />
                <span class="size-2.5 flex-none rounded-full border border-outline-gray-2" :style="{ background: layer.color }" aria-hidden="true" />
                <span class="truncate">{{ layer.name }}</span>
              </label>
            </aside>
          </div>
          <div class="flex min-h-8 flex-none flex-wrap items-center gap-x-1.5 gap-y-0.5 border-t border-outline-gray-1 bg-surface-base px-4 py-1.5 text-xs text-ink-gray-7">
            <span v-if="saveNote" :class="saveFailed ? 'text-ink-red-7' : 'text-ink-green-7'" :role="saveFailed ? 'alert' : 'status'" data-testid="viewer-cad-saved">{{ saveNote }}</span>
            <span v-else-if="editing" data-testid="viewer-cad-save-hint">Save (Ctrl+S) uploads a new version.</span>
            <span v-else-if="fallback" role="status" data-testid="viewer-cad-fallback">{{ fallback }}</span>
            <span v-if="program === 'ocs'" class="ml-auto">Open CAD Studio, free software under the GPL-3.0 licence.
              <a :href="CAD_SOURCE" target="_blank" rel="noopener" class="text-ink-gray-8 underline">Source</a></span>
            <span v-else class="ml-auto" data-testid="viewer-cad-notice">Drawing viewer: cad-simple-viewer (MIT,
              <a :href="CAD_VIEW_SOURCE" target="_blank" rel="noopener" class="text-ink-gray-8 underline">source</a>) with LibreDWG (GPL-3.0,
              <a :href="DWG_SOURCE" target="_blank" rel="noopener" class="text-ink-gray-8 underline">source</a>); free software under the GPL-3.0 licence as a whole.
              <a :href="CAD_VIEW_NOTICE" target="_blank" rel="noopener" class="text-ink-gray-8 underline" data-testid="viewer-cad-licences">Licences and source</a></span>
          </div>
        </template>

        <OfficeEditor v-else-if="kind === 'office'" :project="project" :item="file.name" embedded @unavailable="officeDown = true" />

        <div v-if="status" class="absolute inset-0 grid place-items-center bg-surface-gray-1/80" data-testid="viewer-status">
          <p class="m-0 max-w-md px-6 text-center text-base" :class="failed ? 'text-ink-red-7' : 'text-ink-gray-8'" :role="failed ? 'alert' : 'status'">{{ status }}</p>
        </div>
      </div>
    </div>
    <VersionDialog v-model:open="saving" mode="upload" :file="details" :preset="savedFile" :busy="uploading" @submit="uploadSaved" />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import OfficeEditor from '../sections/OfficeEditor.vue'
import VersionDialog from './VersionDialog.vue'
import { call, upload } from '../api.js'
import { KINDS, extOf, kindOf as kindName, revLabel } from '../files.js'
import { ENGINES } from '../loader.js'
import { holdCadLock, primeCad, wipeCadIfAlone, wipeCadWhenIdle } from '../cadstore.js'
import { CAD_APP, CAD_SOURCE, CAD_VIEW, CAD_VIEW_NOTICE, CAD_VIEW_SOURCE, CadCancelled, DWG_SOURCE, cadFull, cadOpen, cadRaw, cadView, dwgNotForViewer, NOT_FOR_VIEWER, toBase64, viewDeadline, viewerOf } from '../viewer.js'

// The Files tab's viewer popup (P3-48, D-315, D-316): images, PDF through the vendored pdf.js, DWG and DXF in the
// drawing viewer in a same-origin frame (P3-49, D-328; the bytes come from the file's own permission-checked address),
// and Office files in the Document Server in view mode. Edit opens the drawing in the whole of Open CAD Studio in the
// same place, and a save there becomes the file's next revision through the Upload new version dialog (D-319). A
// drawing the viewer cannot read (a DWG older than AutoCAD 2000, a LibreDWG fault, or no answer in time) is shown by
// Open CAD Studio as a viewer instead, as in P3-48, so every drawing can still be viewed.
// Edit in Office opens the editor page.
const props = defineProps({ file: { type: Object, required: true }, src: { type: String, required: true }, project: String })
const emit = defineEmits(['close', 'saved'])
const titleId = `cc-viewer-${Math.random().toString(36).slice(2)}`
// A PDF opens in the Document Server; when that is not there, pdf.js draws it here instead (D-327).
const officeDown = ref(false)
const kind = computed(() => (officeDown.value && extOf(props.file.file_name) === 'pdf' ? 'pdf' : viewerOf(props.file.file_name)))
watch(officeDown, async (down) => { if (down && kind.value === 'pdf') { await nextTick(); renderPdf() } })
const tile = computed(() => KINDS[kindName(props.file.file_name)])
const officeRoute = computed(() => ({ name: 'section', params: { project: props.project, section: 'files', item: props.file.name, action: 'edit' } }))
const box = ref(null)
const closer = ref(null)
const frame = ref(null)
const pages = ref(null)
const status = ref('')
const failed = ref(false)
const pdfNote = ref('')
const ready = ref(false)
const editing = ref(false)
const saving = ref(false)
const uploading = ref(false)
const savedFile = ref(null)
const details = ref(null)
const saveNote = ref('')
const saveFailed = ref(false)
// Edit is offered only when a save could become the next revision: the server's reason otherwise (files.api.details)
const refusal = computed(() => (details.value ? details.value.revisable || '' : 'Checking whether this file can be edited…'))
const storageReady = ref(false) // Open CAD Studio's frame loads once its storage is wiped and primed (cadstore.js)
const program = ref('viewer') // which frame shows the drawing: the drawing viewer, or Open CAD Studio ('ocs')
const starting = ref(false) // Open CAD Studio asked for, not yet up
const fallback = ref('') // why Open CAD Studio shows a drawing the viewer could not
let releaseCadLock = null // held while Open CAD Studio's frame lives
const view = shallowRef(null) // the drawing viewer's calls (viewer.js cadView), from the frame's own page
const layers = ref([])
const showLayers = ref(false)
let drawing = null // the drawing's bytes: one fetch, shared by the viewer and Open CAD Studio
let stopLayers = null
const unsaved = ref(false) // a save the program handed over that is not yet a revision (its tab now looks clean)
let session = null // the sign-out message from another tab (AccountMenu.vue)
const PDF_PAGES = 50
const PDF_PIXELS = 4_000_000 // a page's canvas at most, so a drawing set of 50 pages stays within memory
let before = null
let gone = false
let pdfTask = null
const cancelled = () => gone

function close() {
  emit('close')
}
// In Edit, closing asks first when the drawing has changes that were not saved as a revision.
async function requestClose() {
  if (editing.value && frame.value?.contentWindow) {
    let dirty = false
    try {
      const state = await cadRaw(frame.value.contentWindow, { op: 'state' }, { deadline: Date.now() + 2000 })
      dirty = (state.documents || []).some((d) => d.dirty)
    } catch { /* no answer: close as asked */ }
    dirty = dirty || unsaved.value
    if (dirty && !window.confirm('Close without saving your changes? Save in Open CAD Studio (Ctrl+S) to keep them as a new version.')) return
  }
  close()
}
function fail(message) {
  status.value = message
  failed.value = true
  fallback.value = '' // a note that Open CAD Studio shows the drawing no longer holds
}

// The drawing's bytes, from its own address, fetched once (Edit pressed during the viewer's fetch waits for the same
// one). no-store: they stay out of the browser's HTTP cache, which no wipe or sign-out clears.
function readDrawing() {
  drawing ||= fetch(props.src, { credentials: 'same-origin', cache: 'no-store' })
    .then(async (res) => {
      if (!res.ok) throw new Error('The drawing could not be read.')
      return new Uint8Array(await res.arrayBuffer())
    })
    .catch((e) => {
      drawing = null // a later try fetches again
      throw e
    })
  return drawing
}

// The drawing viewer (P3-49): read-only, with layers, pan and zoom, and measures. Once Open CAD Studio has been asked
// for (Edit, or a fallback), nothing here touches the popup again.
let leftViewer = false // Open CAD Studio was asked for: the viewer's answers no longer count, even if it fails to start
const stale = () => gone || leftViewer
async function openView() {
  if (stale() || !frame.value?.contentWindow) return
  status.value = 'Reading the drawing…'
  failed.value = false
  try {
    const bytes = await readDrawing()
    if (stale()) return
    const skip = dwgNotForViewer(props.file.file_name, bytes)
    if (skip) return startOcs({ edit: false, why: NOT_FOR_VIEWER[skip] })
    status.value = 'Opening the drawing…'
    // The viewer copies the bytes into its own page, so Open CAD Studio still has them. A viewer that does not start,
    // throws, or gives no answer in time fails like one that cannot read the drawing.
    let timer
    const late = new Promise((resolve) => { timer = setTimeout(() => resolve({ ok: false, error: 'The drawing viewer did not finish opening this drawing.' }), viewDeadline(bytes.length)) })
    const opening = cadView(frame.value.contentWindow, { cancelled }).then(async (c) => ({ ...(await c.open(props.file.file_name, bytes.buffer)), calls: c }))
    const reply = await Promise.race([opening, late])
      .catch((e) => (e instanceof CadCancelled ? null : { ok: false, error: e.message || 'The drawing viewer did not start.' }))
      .finally(() => clearTimeout(timer))
    if (!reply || stale()) return
    const calls = reply.calls
    if (!reply?.ok) return startOcs({ edit: false, why: `${reply?.error || 'The drawing viewer could not read this drawing.'} Open CAD Studio shows it.` })
    view.value = calls
    layers.value = reply.layers || []
    stopLayers = calls.onLayers((list) => { layers.value = list })
    status.value = ''
    ready.value = true
  } catch (e) {
    if (!stale() && !(e instanceof CadCancelled)) fail(e.message || 'The drawing could not be opened.')
  }
}

// A layer's box: the viewer answers whether the layer is shown now (a frozen layer is thawed to show it), and the box
// shows that, so a refused change never leaves it wrong.
function showLayer(layer, box) {
  box.checked = !!view.value?.setLayer(layer.name, box.checked)
}

// Open CAD Studio in the viewer's place: as the whole program for Edit (P3-48), or as a viewer for a drawing the
// drawing viewer could not read. It shares our origin and storage (cadstore.js): copies other sessions left are wiped,
// the lock is held while its frame lives, then autosave goes off before it loads.
async function startOcs({ edit, why = '' }) {
  if (starting.value || program.value === 'ocs') return
  leftViewer = true
  starting.value = true
  status.value = 'Starting Open CAD Studio…'
  failed.value = false
  fallback.value = why
  stopLayers?.()
  view.value = null
  ready.value = false
  showLayers.value = false
  try {
    await readDrawing()
    await wipeCadWhenIdle()
    const release = await holdCadLock()
    if (gone) {
      release().then(() => wipeCadWhenIdle()) // closed while starting: never keep the lock
      return
    }
    releaseCadLock = release
    primeCad()
    editing.value = edit
    program.value = 'ocs'
    storageReady.value = true
  } catch (e) {
    starting.value = false
    if (!gone) fail(e.message || 'Open CAD Studio could not start.')
  }
}

// Edit: the whole of Open CAD Studio. From the drawing viewer it starts Open CAD Studio with the drawing; where Open CAD
// Studio already shows it as a viewer, CLEANSCREEN brings back its ribbon and panels (P3-48).
async function editDrawing() {
  if (refusal.value || starting.value) return
  if (program.value !== 'ocs') return startOcs({ edit: true })
  starting.value = true // CLEANSCREEN is a toggle: a second press while it runs would undo it
  try {
    const win = frame.value.contentWindow
    win.openCadStudioSaveFile = (name, bytes) => onSaved(name, bytes)
    const reply = await cadFull(win, { cancelled })
    if (reply.ok === false || reply.status === 'failed') throw new Error(reply.error || reply.code)
    editing.value = true
  } catch (e) {
    if (!gone && !(e instanceof CadCancelled)) fail(`Open CAD Studio could not switch to editing: ${e.message}`)
  } finally {
    starting.value = false
  }
}

async function openDrawing() {
  if (gone || !frame.value?.contentWindow) return
  // Open CAD Studio keeps its working files in the browser's origin-private storage, which only HTTPS (or localhost)
  // gives; production is HTTPS only (deploy/Caddyfile).
  if (frame.value.contentWindow.isSecureContext === false) {
    starting.value = false
    return fail('Drawings open only over HTTPS. Open this site by its https:// address.')
  }
  status.value = 'Opening the drawing in Open CAD Studio…'
  failed.value = false
  try {
    const win = frame.value.contentWindow
    // web.md: while this is defined, Save, Save As, the save-before-close prompt and the exports hand their bytes here
    // instead of downloading them. Set for Edit; as a viewer, as in P3-48, it is set when Edit is pressed.
    if (editing.value) win.openCadStudioSaveFile = (name, bytes) => onSaved(name, bytes)
    const reply = await cadOpen(win, props.file.file_name, toBase64(await readDrawing()), { cancelled, clean: !editing.value })
    if (gone) return
    if (reply.ok === false || reply.status === 'failed') throw new Error(`Open CAD Studio could not open this drawing: ${reply.error || reply.code}`)
    status.value = ''
    ready.value = true
    setTimeout(() => { if (!gone) wipeCadIfAlone() }, 1500) // the copy the program kept of what it just opened
  } catch (e) {
    if (!gone && !(e instanceof CadCancelled)) fail(e.message || 'The drawing could not be opened.')
  } finally {
    starting.value = false
  }
}

async function onSaved(name, bytes) {
  saveNote.value = ''
  saveFailed.value = false
  setTimeout(() => { if (!gone) wipeCadIfAlone() }, 1500) // the copy the program kept of what it saved
  // An export or a plot (another type than the drawing) is not a revision: it goes to the user's downloads.
  if (extOf(name) !== extOf(props.file.file_name)) {
    const url = URL.createObjectURL(new Blob([bytes]))
    const link = Object.assign(document.createElement('a'), { href: url, download: name })
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 10000)
    saveNote.value = `${name} was saved to your downloads.`
    return
  }
  unsaved.value = true
  try {
    details.value = await call('construction_core.files.api.details', { file: props.file.name })
    savedFile.value = new File([bytes], name || props.file.file_name)
    saving.value = true
  } catch (e) {
    saveNote.value = e.message || 'The drawing could not be saved.'
    saveFailed.value = true
  }
}

async function uploadSaved({ file, note, takeoffs }) {
  uploading.value = true
  try {
    const out = await upload('construction_core.files.api.upload_version', { file: props.file.name, note, takeoffs: takeoffs || '' }, file)
    saving.value = false
    unsaved.value = false
    saveNote.value = `Saved as Rev ${out.rev}.`
    saveFailed.value = false
    emit('saved', out)
  } catch (e) {
    saving.value = false
    saveNote.value = e.message || 'The drawing could not be saved.'
    saveFailed.value = true
  } finally {
    uploading.value = false
  }
}

async function renderPdf() {
  status.value = 'Opening the PDF…'
  try {
    const pdfjs = await import(/* @vite-ignore */ ENGINES.pdfjs + 'pdf.min.js')
    pdfjs.GlobalWorkerOptions.workerSrc = ENGINES.pdfjs + 'pdf.worker.min.js'
    if (gone) return
    pdfTask = pdfjs.getDocument({
      url: props.src, isEvalSupported: false, cMapUrl: ENGINES.pdfjs + 'cmaps/', cMapPacked: true,
      standardFontDataUrl: ENGINES.pdfjs + 'standard_fonts/',
    })
    const doc = await pdfTask.promise
    status.value = ''
    if (doc.numPages > PDF_PAGES) pdfNote.value = `The first ${PDF_PAGES} of ${doc.numPages} pages. Open it in a new tab to see them all.`
    const width = Math.min(1100, (pages.value?.clientWidth || 900) - 32)
    for (let n = 1; n <= Math.min(doc.numPages, PDF_PAGES) && !gone; n++) {
      const page = await doc.getPage(n)
      const fit = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width })
      // sharp on a high-density screen, but never above the cap: a very tall page is drawn a little softer instead
      const sharp = Math.min(window.devicePixelRatio || 1, Math.sqrt(PDF_PIXELS / (fit.width * fit.height)))
      const viewport = page.getViewport({ scale: fit.scale * sharp })
      const canvas = document.createElement('canvas')
      canvas.width = viewport.width
      canvas.height = viewport.height
      canvas.style.width = `${width}px`
      canvas.className = 'mx-auto mb-4 block shadow-sm'
      canvas.setAttribute('aria-label', `Page ${n}`)
      canvas.dataset.testid = 'viewer-pdf-page'
      pages.value?.appendChild(canvas)
      await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise
    }
    ready.value = !gone
  } catch (e) {
    if (!gone) fail(e.message || 'The PDF could not be opened.')
  }
}

onMounted(async () => {
  before = document.activeElement
  // A sign-out in another tab closes this viewer at once (its wipe is forced; nothing here may write again).
  if (typeof BroadcastChannel !== 'undefined') {
    session = new BroadcastChannel('cc-session')
    session.onmessage = (e) => { if (e.data === 'signout') close() }
  }
  await nextTick()
  ;(closer.value?.$el || box.value)?.focus()
  if (kind.value === 'pdf') renderPdf()
  if (kind.value === 'cad') details.value = await call('construction_core.files.api.details', { file: props.file.name }).catch((e) => ({ revisable: e.message || 'This file cannot be edited here.' }))
})
onBeforeUnmount(() => {
  gone = true
  pdfTask?.destroy() // a loading or loaded PDF: its worker and pages
  stopLayers?.()
  session?.close()
  if (before?.isConnected) before.focus()
})
// Once Open CAD Studio's frame is gone (never under a running open, which a wipe would fail): its copies go too.
onUnmounted(() => {
  if (!releaseCadLock) return
  releaseCadLock()
    .then(() => wipeCadWhenIdle())
    .then((clean) => { if (!clean) setTimeout(() => wipeCadWhenIdle(), 2000) })
})
</script>
