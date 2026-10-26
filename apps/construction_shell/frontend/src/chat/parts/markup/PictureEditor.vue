<template>
  <Teleport to="body">
    <div ref="root" class="fixed inset-0 z-[60] flex flex-col bg-surface-base outline-none" role="dialog" aria-modal="true" :aria-label="w('markup.editor')" tabindex="-1"
      :data-testid="`${prefix}markup-editor`" @keydown.esc="esc" @keydown.tab="keep">
      <div class="flex min-h-14 items-center gap-2 border-b border-outline-gray-2 px-3">
        <h2 class="m-0 text-base font-medium text-ink-gray-9">{{ w('markup.title') }}</h2>
        <Button class="ml-auto max-md:!h-12 max-md:!min-w-12" variant="ghost" size="md" :label="w('core.cancel')" :data-testid="`${prefix}markup-cancel`" @click="cancel" />
        <Button class="max-md:!h-12 max-md:!min-w-12" variant="solid" theme="blue" size="md" icon-left="lucide-check" :label="w('markup.add')" :loading="saving"
          :disabled="!ready" :data-testid="`${prefix}markup-save`" @click="save" />
      </div>
      <p v-if="error" class="m-0 px-4 py-2 text-sm text-ink-red-7" role="alert" :data-testid="`${prefix}markup-error`">{{ error }}</p>
      <div class="relative min-h-0 flex-1">
        <!-- The React root lives on this element only, which fills its parent; the loading line floats over it so the stage never moves. -->
        <div ref="stage" class="absolute inset-0" :data-testid="`${prefix}markup-stage`" />
        <p v-if="!ready && !error" class="absolute left-0 top-0 m-0 px-4 py-2 text-sm text-ink-gray-7" role="status">{{ w('markup.loading') }}</p>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Button, useColorScheme } from 'frappe-ui'
import { ENGINES, loadScript } from '../../../loader.js'
import { useMode } from '../../../mode.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { trayOf } from '../attachments/tray.js'
import { sceneOf } from './board.js'
import { UI_OPTIONS, markedBlob, markedName } from './editor.js'

// The picture editor (P3-70, design §3.11, D-372, D-457; no canvas frame, drawn like the photo viewer): a full-screen dialog around the
// vendored Excalidraw, loaded as the boards load it. The picture opens locked, so a mark cannot move it. "Add to message" puts a new JPEG,
// "<name>-marked.jpg", in the conversation's tray, where the person adds a note and presses Send. The original is never changed (L-4).
// Escape and Cancel close it and add nothing.
// `picture`: board.js jpegOf's answer, so a phone photo is oriented and no larger than 2048 px; `thread`: the conversation.
const props = defineProps({ picture: { type: Object, required: true }, name: { type: String, required: true }, thread: { type: String, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['cancel', 'done'])
const w = wordsFor(useMode(), props.portal)
const host = inject(HOST_KEY)
const root = ref(null)
const stage = ref(null)
const ready = ref(false)
const saving = ref(false)
const error = ref('')
let lib = null
let api = null
let react = null
let closed = false
let before = null

// Excalidraw follows the Light/Dark choice (D-126), as the boards do.
const { resolvedColorScheme } = useColorScheme()
watch(resolvedColorScheme, (theme) => api?.updateScene({ appState: { theme } }))

function cancel() {
  emit('cancel')
}

// Escape ends a text being typed in the editor's own boxes; only elsewhere does it close the dialog.
function esc(e) {
  if (e.target.closest?.('input, textarea, [contenteditable="true"]')) return
  e.stopPropagation()
  cancel()
}

// Tab stays inside the dialog: from the last control to the first, and back.
function keep(e) {
  const inside = [...root.value.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])')].filter((el) => el.offsetParent)
  if (!inside.length) return
  const [first, last] = [inside[0], inside.at(-1)]
  const leaving = e.shiftKey ? [first, root.value].includes(document.activeElement) : document.activeElement === last
  if (!leaving) return
  e.preventDefault()
  const next = e.shiftKey ? last : first
  next.focus()
}

// Excalidraw's first change is the picture arriving: it opens whole (as a board does), and "Add to message" is ready.
function opened() {
  if (ready.value || !api) return
  api.scrollToContent(undefined, { fitToContent: true })
  ready.value = true
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const blob = await markedBlob(lib, api)
    trayOf(host, props.thread).add([new File([blob], markedName(props.name), { type: 'image/jpeg' })])
    emit('done')
  } catch {
    error.value = w('markup.save_failed')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  before = document.activeElement
  root.value.focus()
  try {
    await loadScript(ENGINES.whiteboard)
    lib = await window.ccWhiteboard.load()
    if (closed) return // closed while the editor was loading
    const { dataURL, width, height } = props.picture
    react = window.ReactDOM.createRoot(stage.value)
    react.render(window.React.createElement(lib.Excalidraw, {
      initialData: sceneOf(dataURL, width, height, Date.now()),
      theme: resolvedColorScheme.value,
      UIOptions: UI_OPTIONS,
      excalidrawAPI: (a) => (api = a),
      onChange: opened,
    }))
  } catch {
    error.value = w('markup.editor_failed')
  }
})
onBeforeUnmount(() => {
  closed = true
  react?.unmount()
  before?.focus?.()
})
</script>
