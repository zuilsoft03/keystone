<template>
  <div :class="embedded ? 'flex min-h-0 flex-1 flex-col gap-2' : 'flex min-h-0 flex-1 flex-col gap-3.5 px-6 py-5'" data-testid="office-view">
    <div v-if="!embedded" class="flex flex-wrap items-end gap-3">
      <div class="min-w-0 flex-[1_1_320px]">
        <div class="text-xs text-ink-gray-7"><router-link :to="{ name: 'section', params: { project, section: 'files' } }" class="text-ink-gray-7 no-underline hover:text-ink-gray-9">← Files</router-link></div>
        <div class="mt-1 flex flex-wrap items-baseline gap-2.5">
          <h1 class="m-0 truncate text-3xl-semibold text-ink-gray-9" data-testid="office-title">{{ title }}</h1>
          <Badge v-if="mode" :theme="mode === 'edit' ? 'green' : 'amber'" :label="mode === 'edit' ? 'Editing' : 'View only'" data-testid="office-mode" />
        </div>
      </div>
    </div>
    <p v-if="message" class="text-ink-amber-8" data-testid="office-message">{{ message }}</p>
    <p v-if="error" class="text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
    <!-- DocsAPI replaces this element with its iframe; Vue never renders inside it. -->
    <div :class="embedded ? 'min-h-0 flex-1 overflow-hidden' : 'cw-card min-h-[75vh] flex-1 overflow-hidden'"><div :id="holder" /></div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Badge } from 'frappe-ui'
import { call } from '../api.js'
import { loadScript } from '../loader.js'

// A project's Word, Excel or PowerPoint file in the ONLYOFFICE Document Server at /office/, on the same API as the
// Desk page (P1-17, D-073). The server signs the configuration; saves come back through its signed callback.
// Embedded in the Files tab's viewer popup (P3-48, D-315) it shows only the editor, in view mode, for `item`.
const props = defineProps({ frame: Object, project: String, section: String, item: String, embedded: Boolean })
const emit = defineEmits(['unavailable']) // no editor could start: the Files popup then shows a PDF itself
const route = useRoute()
const holder = `cc-office-${Math.random().toString(36).slice(2)}`
const title = ref('Office editor')
const mode = ref('')
const message = ref('')
const error = ref('')
let editor = null
let gone = false

onMounted(async () => {
  try {
    // POST: opening a session stores its key on the file (construction_core.office.api.editor_config).
    const r = await call('construction_core.office.api.editor_config', { file: props.item || route.params.item, view: props.embedded ? 1 : 0 }, { post: true })
    title.value = r.config.document.title
    mode.value = r.mode
    if (r.limited) message.value = 'The editing limit is reached; this file opens read-only for now.'
    if (r.locked) message.value = 'This file belongs to a document under review or published, so it opens read-only. Issue a new revision to change it.'
    if (r.measured) message.value = 'This PDF is measured in Takeoff, so it opens read-only here. Upload a new version to choose what happens to its takeoff.'
    await loadScript(`${r.server}web-apps/apps/api/documents/api.js`).catch(() => {
      throw new Error('The office editor is not available on this site.')
    })
    if (gone) return
    editor = new window.DocsAPI.DocEditor(holder, {
      ...r.config,
      width: '100%',
      height: '100%',
      events: {
        onError: (e) => (error.value = `The office editor reported an error: ${e?.data?.errorDescription || e?.data?.errorCode || ''}`),
      },
    })
  } catch (e) {
    error.value = e.message || 'Could not open the file.'
    emit('unavailable') // no editor here, whatever the reason (no Document Server, or none configured)
  }
})

// Closing the editor ends the session, so the Document Server saves now rather than on its idle timer.
onBeforeUnmount(() => {
  gone = true
  if (editor) editor.destroyEditor()
  editor = null
})
</script>
