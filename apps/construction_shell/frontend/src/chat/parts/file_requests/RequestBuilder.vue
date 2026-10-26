<template>
  <Dialog v-model:open="shown" :title="w('file_requests.new')" :options="{ size: 'xl' }">
    <form class="flex max-h-[70vh] flex-col gap-2 overflow-y-auto pr-1" :aria-label="w('file_requests.new')" :data-testid="`${prefix}request-form`" @submit.prevent="send">
      <p class="m-0 text-xs text-ink-gray-7">{{ w('file_requests.builder_hint') }}</p>
      <div v-if="templates.length" class="flex flex-wrap items-center gap-2">
        <label class="text-sm font-medium text-ink-gray-9" :for="`${prefix}request-template`">{{ w('file_requests.template_label') }}</label>
        <select :id="`${prefix}request-template`" v-model="template" class="form-select min-w-0 flex-1 text-base max-md:h-12" :data-testid="`${prefix}request-template`" @change="useTemplate">
          <option value="">{{ w('file_requests.template_pick') }}</option>
          <option v-for="t in templates" :key="t.name" :value="t.name">{{ t.title }}</option>
        </select>
      </div>
      <label class="text-sm font-medium text-ink-gray-9" :for="`${prefix}request-title-input`">{{ w('file_requests.title_label') }}</label>
      <input :id="`${prefix}request-title-input`" ref="titleBox" v-model="form.title" type="text" class="form-input w-full text-base max-md:h-12" :maxlength="MAX_TITLE"
        :placeholder="w('file_requests.title_ph')" :data-testid="`${prefix}request-title-input`" />
      <label class="text-sm font-medium text-ink-gray-9" :for="`${prefix}request-note-input`">{{ w('file_requests.message_label') }}</label>
      <input :id="`${prefix}request-note-input`" v-model="form.note" type="text" class="form-input w-full text-base max-md:h-12" maxlength="500"
        :placeholder="w('file_requests.message_ph')" :data-testid="`${prefix}request-note-input`" />
      <p class="m-0 mt-1 text-sm font-medium text-ink-gray-9">{{ w('file_requests.items_label', { max: MAX_ITEMS }) }}</p>
      <ul class="m-0 flex list-none flex-col gap-2 p-0">
        <li v-for="(it, n) in form.items" :key="it.id" class="flex flex-col gap-1.5 rounded-4 border border-outline-gray-2 p-2" :data-testid="`${prefix}request-item-row`">
          <div class="flex items-center gap-2">
            <label class="sr-only" :for="`${prefix}request-item-${it.id}`">{{ w('file_requests.item_n', { n: n + 1 }) }}</label>
            <input :id="`${prefix}request-item-${it.id}`" v-model="it.description" type="text" class="form-input min-w-0 flex-1 text-base max-md:h-12" :maxlength="MAX_DESCRIPTION"
              :placeholder="w('file_requests.item_ph')" :data-testid="`${prefix}request-item-input`" />
            <button type="button" class="grid size-8 flex-none cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-7 hover:bg-surface-gray-3 disabled:cursor-default disabled:opacity-50 max-md:size-12"
              :aria-label="w('file_requests.remove_item', { n: n + 1 })" :title="w('file_requests.remove_item', { n: n + 1 })" :disabled="!form.canRemove" :data-testid="`${prefix}request-item-remove`" @click="form.remove(it.id)">
              <span class="lucide-x size-4" aria-hidden="true" />
            </button>
          </div>
          <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
            <label class="inline-flex min-h-8 items-center gap-1.5 text-sm text-ink-gray-8 max-md:min-h-12">
              <input v-model="it.required" type="checkbox" class="form-checkbox" :data-testid="`${prefix}request-item-required`" />{{ w('file_requests.item_required') }}
            </label>
            <span v-if="it.example" class="inline-flex min-w-0 max-w-full items-center gap-1 rounded-4 bg-surface-gray-2 py-0.5 pl-2 pr-0.5 text-xs text-ink-gray-8" :data-testid="`${prefix}request-example`">
              <span class="truncate">{{ w('file_requests.example_is', { name: it.example.file_name }) }}</span>
              <button type="button" class="grid size-6 flex-none cursor-pointer place-items-center rounded-3 border-0 bg-transparent text-ink-gray-7 hover:bg-surface-gray-3 max-md:size-12"
                :aria-label="w('file_requests.example_remove', { n: n + 1 })" @click="form.setExample(it.id, null)"><span class="lucide-x size-3.5" aria-hidden="true" /></button>
            </span>
            <Button v-else-if="host.files" size="sm" variant="ghost" icon-left="lucide-paperclip" class="max-md:!h-12" :label="w('file_requests.example_add')"
              :data-testid="`${prefix}request-example-add`" @click="pickFor(it.id)" />
          </div>
        </li>
      </ul>
      <Button class="self-start max-md:!h-12" variant="ghost" icon-left="lucide-plus" :label="w('file_requests.add_item')" :disabled="!form.canAdd" :data-testid="`${prefix}request-add-item`" @click="addItem" />
      <label class="text-sm font-medium text-ink-gray-9" :for="`${prefix}request-due-input`">{{ w('file_requests.due_label') }}</label>
      <input :id="`${prefix}request-due-input`" v-model="form.due" type="date" :min="first" :max="last" class="form-input w-full text-base sm:w-56 max-md:h-12" :data-testid="`${prefix}request-due-input`" />
      <p class="m-0 text-xs text-ink-gray-7">{{ w('file_requests.due_hint') }}</p>
      <fieldset class="m-0 flex min-w-0 flex-col gap-0.5 border-0 p-0">
        <legend class="mb-1 p-0 text-sm font-medium text-ink-gray-9">{{ w('file_requests.people_label') }}</legend>
        <p v-if="loading" class="m-0 text-sm text-ink-gray-7" role="status">{{ w('core.loading') }}</p>
        <p v-else-if="!people.length" class="m-0 text-sm text-ink-gray-7" :data-testid="`${prefix}request-no-people`">{{ w('file_requests.people_none') }}</p>
        <label v-for="p in people" :key="p.user" class="inline-flex min-h-8 items-center gap-2 text-base text-ink-gray-9 max-md:min-h-12">
          <input type="checkbox" class="form-checkbox" :checked="form.recipients.includes(p.user)" :data-testid="`${prefix}request-person`" :data-user="p.user"
            @change="form.toggle(p.user, $event.target.checked)" />{{ p.name }}
        </label>
      </fieldset>
      <ul v-if="shown_problems.length" class="m-0 list-none rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}request-problems`">
        <li v-for="p in shown_problems" :key="p.code + (p.n || '')">{{ w(`file_requests.problem_${p.code}`, { n: p.n || '', max: p.code === 'title_long' ? MAX_TITLE : MAX_DESCRIPTION, days: MAX_DUE_DAYS }) }}</li>
      </ul>
      <p v-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}request-error`">{{ error }}</p>
      <p v-if="saved" class="m-0 text-sm text-ink-green-8" role="status" :data-testid="`${prefix}request-saved`">{{ saved }}</p>
      <FilePicker v-if="host.files" v-model:open="picking" pick-only :thread="thread" :prefix="`${prefix}request-`" @picked="picked" />
    </form>
    <template #actions>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <Button v-if="host.templates" class="mr-auto max-md:!h-12" variant="ghost" :label="w('file_requests.template_save')" :loading="saving" :data-testid="`${prefix}request-save-template`" @click="saveTemplate" />
        <Button class="max-md:!h-12" :label="w('file_requests.cancel_builder')" :disabled="sending" :data-testid="`${prefix}request-cancel-build`" @click="cancel" />
        <Button class="max-md:!h-12" variant="solid" theme="blue" :label="w('file_requests.send')" :loading="sending" :data-testid="`${prefix}request-send-form`" @click="send" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, ref } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { boot } from '../../../boot.js'
import { useMode } from '../../../mode.js'
import { HOST_KEY } from '../../host.js'
import { newClientId } from '../../unsent.js'
import { wordsFor } from '../../words.js'
import FilePicker from '../attachments/FilePicker.vue'
import { askable, dateValue } from './form.js'
import { MAX_DESCRIPTION, MAX_DUE_DAYS, MAX_ITEMS, MAX_TITLE } from './view.js'

// The file request builder (design §3.10; no canvas frame, drawn from the poll builder, the composer and the picker, D-196):
// a title, an optional note above the card, 1 to 20 files each with Required and an example from the project's files, a due
// date (left empty: the server's 5 working days), and the people asked: the conversation's people, all ticked in a Client
// conversation. "Use a template" fills the checklist; "Save as template" keeps it. It sends as a message of its own with the
// title as its words. Problems show after the first Send; the server checks everything again.
const props = defineProps({ open: Boolean, form: { type: Object, required: true }, thread: { type: Object, required: true }, prefix: { type: String, default: '' } })
const emit = defineEmits(['update:open', 'sent'])
const host = inject(HOST_KEY)
const w = wordsFor(useMode())
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const people = ref([])
const templates = ref([])
const template = ref('')
const loading = ref(true)
const sending = ref(false)
const saving = ref(false)
const tried = ref(false)
const error = ref('')
const saved = ref('')
const picking = ref(false)
const titleBox = ref(null)
const now = new Date()
const first = dateValue(now)
const last = dateValue(new Date(now.getFullYear(), now.getMonth(), now.getDate() + MAX_DUE_DAYS))
const problems = computed(() => props.form.problems())
const shown_problems = computed(() => (tried.value ? problems.value : []))
let target = null

async function loadPeople() {
  try {
    const answer = await host.read('people', { thread: props.thread.name })
    people.value = askable(answer?.people, props.thread.audience, boot.user)
    // A Client conversation asks its client contacts by default; a team conversation, nobody until chosen.
    if (props.thread.audience === 'Client' && !props.form.recipients.length) props.form.recipients = people.value.map((p) => p.user)
  } catch (e) {
    error.value = e.message || ''
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  try {
    templates.value = host.templates ? (await host.templates.list()) || [] : []
  } catch {
    templates.value = [] // the list is a convenience; the form works without it
  }
}

function useTemplate(event) {
  const picked = templates.value.find((t) => t.name === event.target.value)
  if (picked) props.form.useTemplate(picked)
  template.value = ''
}

async function saveTemplate() {
  tried.value = true
  saved.value = ''
  error.value = ''
  if (saving.value || props.form.checklistProblems().length) return
  saving.value = true
  try {
    await host.templates.save(props.form.title.trim(), props.form.templateItems())
    saved.value = w('file_requests.template_saved')
    await loadTemplates()
  } catch (e) {
    error.value = e.message || ''
  } finally {
    saving.value = false
  }
}

function pickFor(id) {
  target = id
  picking.value = true
}

function picked(file) {
  if (target !== null) props.form.setExample(target, file)
}

async function addItem() {
  const it = props.form.add()
  await nextTick()
  if (it) document.getElementById(`${props.prefix}request-item-${it.id}`)?.focus()
}

function cancel() {
  props.form.reset()
  tried.value = false
  shown.value = false
}

async function send() {
  tried.value = true
  error.value = ''
  saved.value = ''
  if (sending.value || problems.value.length) return
  sending.value = true
  try {
    const { text, parts } = props.form.payload()
    const name = await host.send({ thread: props.thread.name, text, client_id: newClientId(), parts })
    props.form.reset()
    shown.value = false
    emit('sent', name)
  } catch (e) {
    error.value = e.message || w('core.not_sent')
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  loadPeople()
  loadTemplates()
  await nextTick()
  titleBox.value?.focus()
})
</script>
