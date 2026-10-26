<template>
  <Dialog v-model:open="shown" size="xl" :title="w('attachments.picker_title')">
      <div v-if="!asking" class="flex flex-col gap-2.5" :data-testid="`${prefix}picker`">
        <div class="flex flex-wrap items-center gap-2">
          <label class="sr-only" :for="`${prefix}picker-folder`">{{ w('attachments.picker_folder') }}</label>
          <select :id="`${prefix}picker-folder`" v-model="folder" class="form-select h-8 min-w-0 flex-1 text-base max-md:h-12" :data-testid="`${prefix}picker-folder`">
            <option value="">{{ w('attachments.picker_recent') }}</option>
            <option v-for="f in folders" :key="f.folder" :value="f.folder">{{ f.path || f.label }}</option>
          </select>
          <label class="sr-only" :for="`${prefix}picker-search`">{{ w('attachments.picker_search') }}</label>
          <input :id="`${prefix}picker-search`" v-model="search" type="search" class="form-input h-8 min-w-0 flex-1 text-base max-md:h-12"
            :placeholder="w('attachments.picker_search')" :data-testid="`${prefix}picker-search`" />
        </div>
        <p v-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert">{{ error }}</p>
        <p v-if="!loading && !shownFiles.length" class="m-0 py-3 text-sm text-ink-gray-7">{{ w('attachments.picker_empty') }}</p>
        <ul class="m-0 flex max-h-[360px] list-none flex-col overflow-y-auto p-0" role="listbox" :aria-label="w('attachments.picker_title')">
          <li v-for="f in shownFiles" :key="f.name">
            <button type="button" role="option" aria-selected="false"
              class="flex min-h-10 w-full items-center gap-2.5 rounded-4 border-0 bg-transparent px-2 text-left hover:bg-surface-gray-2 max-md:min-h-12"
              :aria-label="w('attachments.picker_pick', { name: f.file_name })" :data-testid="`${prefix}picker-file`" @click="choose(f)">
              <Badge class="min-w-10 flex-none justify-center" size="sm" :theme="extTheme(fileExt(f.file_name))" :label="fileExt(f.file_name) || w('attachments.file')" />
              <span class="min-w-0 flex-1 truncate text-base text-ink-gray-9">{{ f.file_name }}</span>
              <span v-if="f.rev" class="flex-none text-xs text-ink-gray-7">{{ w('attachments.rev', { rev: f.rev }) }}</span>
              <span class="w-16 flex-none text-right text-xs text-ink-gray-7 max-sm:hidden">{{ formatSize(f.file_size) }}</span>
            </button>
          </li>
        </ul>
      </div>
      <!-- Share and send (D-367, D-390): a client gets a checked copy, never the team's own file -->
      <div v-else class="flex flex-col gap-2" :data-testid="`${prefix}share-confirm`">
        <p class="m-0 text-base font-medium text-ink-gray-9">{{ w('attachments.share_question') }}</p>
        <p class="m-0 flex items-center gap-2 rounded-4 border border-outline-gray-2 px-3 py-2 text-base text-ink-gray-9">
          <Badge size="sm" :theme="extTheme(fileExt(asking.file_name))" :label="fileExt(asking.file_name) || w('attachments.file')" />
          <span class="min-w-0 truncate">{{ asking.file_name }}</span>
        </p>
        <p class="m-0 text-sm text-ink-gray-7">{{ w('attachments.share_note') }}</p>
        <p v-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert">{{ error }}</p>
      </div>
    <template v-if="asking" #actions>
      <div class="flex justify-end gap-2">
        <Button :label="w('attachments.cancel')" :disabled="busy" @click="asking = null" />
        <Button variant="solid" theme="blue" :label="w('attachments.share_send')" :loading="busy" :data-testid="`${prefix}share-send`" @click="attach(asking)" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { Badge, Button, Dialog } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { extTheme, fileExt, formatSize } from '../../../sections/util.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'

// "From project files" (design §3.2, staff only): the project's newest files or one folder's, searched by name. In the
// Team room the file is linked, never copied or shared; in a Client conversation "Share and send" asks first and sends
// a checked copy (scan, signature, structure, image clean), the team's file unchanged. The server refuses earlier
// versions, files in the bin and other projects' files whatever this list shows.
// pickOnly (P3-71, a file request's example): hand back the chosen file row and stage nothing, which asks no "Share and send".
const props = defineProps({ open: Boolean, thread: { type: Object, default: null }, prefix: { type: String, default: '' }, pickOnly: Boolean })
const emit = defineEmits(['update:open', 'staged', 'picked'])
const host = inject(HOST_KEY)
const w = wordsFor(useMode())
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const folders = ref([])
const folder = ref('')
const files = ref([])
const search = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const asking = ref(null)
const shownFiles = computed(() => {
  const q = search.value.trim().toLowerCase()
  return files.value.filter((f) => !f.is_folder && (!q || f.file_name.toLowerCase().includes(q)))
})

async function list() {
  if (!host.files) return
  loading.value = true
  error.value = ''
  try {
    files.value = folder.value ? await host.files('list', { folder: folder.value }) : await host.files('view', { view: 'recent' })
  } catch (e) {
    files.value = []
    error.value = e.message || ''
  } finally {
    loading.value = false
  }
}

function choose(f) {
  if (props.pickOnly) {
    emit('picked', f)
    shown.value = false
  } else if (props.thread?.audience === 'Client') asking.value = f
  else attach(f)
}

async function attach(f) {
  busy.value = true
  error.value = ''
  try {
    const answer = await host.act('attachments', 'attach', { thread: props.thread.name, file: f.name })
    emit('staged', answer)
    asking.value = null
    shown.value = false
  } catch (e) {
    error.value = e.message || ''
  } finally {
    busy.value = false
  }
}

watch(() => props.open, async (open) => {
  if (!open) return
  asking.value = null
  search.value = ''
  if (!folders.value.length && host.files) folders.value = (await host.files('tree').catch(() => [])).filter((f) => f.path)
  list()
})
watch(folder, list)
</script>
