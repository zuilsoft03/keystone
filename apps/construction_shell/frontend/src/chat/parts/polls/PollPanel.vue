<template>
  <form class="flex flex-col gap-2 rounded-6 border border-outline-gray-3 bg-surface-base p-3 shadow-sm" :aria-label="w('polls.new')" :data-testid="`${prefix}poll-form`" @submit.prevent="send" @keydown.esc.stop="draft.close()">
    <p class="m-0 text-xs text-ink-gray-7">{{ w('polls.builder_hint') }}</p>
    <label class="text-sm font-medium text-ink-gray-9" :for="`${prefix}poll-question-input`">{{ w('polls.question') }}</label>
    <input :id="`${prefix}poll-question-input`" ref="question" v-model="form.question" type="text" class="form-input w-full text-base max-md:h-12" :maxlength="MAX_QUESTION"
      :placeholder="w('polls.question_ph')" :data-testid="`${prefix}poll-question-input`" />
    <p class="m-0 mt-1 text-sm font-medium text-ink-gray-9">{{ w('polls.options', { min: MIN_OPTIONS, max: MAX_OPTIONS }) }}</p>
    <ul class="m-0 flex list-none flex-col gap-2 p-0">
      <li v-for="(o, i) in form.options" :key="o.id" class="flex items-center gap-2" :data-testid="`${prefix}poll-option-row`">
        <Dropdown v-if="!itemOf(o) && host.files" :options="pictureMenu(o)">
          <button type="button" class="grid size-10 flex-none cursor-pointer place-items-center rounded-3 border border-dashed border-outline-gray-4 bg-transparent text-ink-gray-7 hover:bg-surface-gray-2 max-md:size-12"
            :aria-label="w('polls.add_picture', { n: i + 1 })" :title="w('polls.add_picture', { n: i + 1 })" :data-testid="`${prefix}poll-picture-add`">
            <span class="lucide-image-plus size-4" aria-hidden="true" />
          </button>
        </Dropdown>
        <button v-else-if="!itemOf(o)" type="button" class="grid size-10 flex-none cursor-pointer place-items-center rounded-3 border border-dashed border-outline-gray-4 bg-transparent text-ink-gray-7 hover:bg-surface-gray-2 max-md:size-12"
          :aria-label="w('polls.add_picture', { n: i + 1 })" :title="w('polls.add_picture', { n: i + 1 })" :data-testid="`${prefix}poll-picture-add`" @click="fromDevice(o)">
          <span class="lucide-image-plus size-4" aria-hidden="true" />
        </button>
        <span v-else class="relative grid size-10 flex-none place-items-center overflow-hidden rounded-3 bg-surface-gray-3 max-md:size-12" :data-testid="`${prefix}poll-picture-item`" :data-state="itemOf(o).state"
          :title="itemOf(o).file_name">
          <img v-if="itemOf(o).thumb" :src="itemOf(o).thumb" alt="" class="size-full object-cover" />
          <span v-else class="lucide-image size-4 text-ink-gray-7" aria-hidden="true" />
          <span v-if="['waiting', 'uploading', 'checking'].includes(itemOf(o).state)" class="absolute inset-0 grid place-items-center bg-surface-base opacity-70">
            <span class="lucide-loader-circle size-4 animate-spin text-ink-gray-7" aria-hidden="true" />
          </span>
        </span>
        <label class="sr-only" :for="`${prefix}poll-option-${o.id}`">{{ w('polls.option_n', { n: i + 1 }) }}</label>
        <input :id="`${prefix}poll-option-${o.id}`" v-model="o.text" type="text" class="form-input min-w-0 flex-1 text-base max-md:h-12" :maxlength="MAX_OPTION"
          :placeholder="w('polls.option_ph', { n: i + 1 })" :data-testid="`${prefix}poll-option-input`" />
        <button v-if="itemOf(o)" type="button" class="grid size-8 flex-none cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-7 hover:bg-surface-gray-3 max-md:size-12"
          :aria-label="w('polls.remove_picture', { n: i + 1 })" :title="w('polls.remove_picture', { n: i + 1 })" :data-testid="`${prefix}poll-picture-remove`" @click="draft.clearPicture(o.id)">
          <span class="lucide-image-off size-4" aria-hidden="true" />
        </button>
        <button type="button" class="grid size-8 flex-none cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-7 hover:bg-surface-gray-3 disabled:cursor-default disabled:opacity-50 max-md:size-12"
          :aria-label="w('polls.remove_option', { n: i + 1 })" :title="w('polls.remove_option', { n: i + 1 })" :disabled="!form.canRemove" :data-testid="`${prefix}poll-option-remove`" @click="removeOption(o)">
          <span class="lucide-x size-4" aria-hidden="true" />
        </button>
      </li>
    </ul>
    <input ref="device" type="file" class="sr-only" :accept="PHOTO_ACCEPT" tabindex="-1" aria-hidden="true" :data-testid="`${prefix}poll-picture-input`" @change="picked" />
    <Button class="self-start max-md:!h-12" variant="ghost" icon-left="lucide-plus" :label="w('polls.add_option')" :disabled="!form.canAdd" :data-testid="`${prefix}poll-add-option`" @click="addOption" />
    <div class="flex flex-wrap items-center gap-2">
      <div class="inline-flex rounded-4 bg-surface-gray-2 p-0.5" role="group" :aria-label="w('polls.choices')">
        <button v-for="c in CHOICES" :key="c.id" type="button" :aria-pressed="form.multiple === c.multiple ? 'true' : 'false'" :class="segment(form.multiple === c.multiple)"
          :data-testid="`${prefix}poll-${c.id}`" @click="form.multiple = c.multiple">{{ w(c.word) }}</button>
      </div>
      <div v-if="form.anonymousAllowed" class="inline-flex rounded-4 bg-surface-gray-2 p-0.5" role="group" :aria-label="w('polls.who_sees')">
        <button v-for="c in VOTES" :key="c.id" type="button" :aria-pressed="form.anonymous === c.anonymous ? 'true' : 'false'" :class="segment(form.anonymous === c.anonymous)"
          :data-testid="`${prefix}poll-${c.id}`" @click="form.anonymous = c.anonymous">{{ w(c.word) }}</button>
      </div>
      <label class="inline-flex items-center gap-1.5 text-sm text-ink-gray-8">
        {{ w('polls.close_time') }}
        <input v-model="form.closes" type="datetime-local" class="form-input text-base max-md:h-12" :data-testid="`${prefix}poll-closes-input`" />
      </label>
    </div>
    <p v-if="!form.anonymousAllowed" class="m-0 text-xs text-ink-gray-7" :data-testid="`${prefix}poll-client-note`">{{ w('polls.client_note') }}</p>
    <ul v-if="shown.length" class="m-0 list-none rounded-4 bg-surface-red-1 p-0 px-3 py-2 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}poll-problems`">
      <li v-for="p in shown" :key="p.code + (p.n || '')">{{ w(`polls.problem_${p.code}`, { n: p.n || '', max: MAX_QUESTION }) }}</li>
    </ul>
    <p v-if="state.error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}poll-error`">{{ state.error === 'not_photo' ? w('polls.not_photo') : state.error }}</p>
    <div class="flex justify-end gap-2">
      <Button class="max-md:!h-12" variant="ghost" :label="w('polls.cancel')" :data-testid="`${prefix}poll-cancel`" @click="cancel" />
      <Button class="max-md:!h-12" type="submit" variant="solid" theme="blue" :label="w('polls.send')" :loading="state.sending" :data-testid="`${prefix}poll-send`" />
    </div>
    <FilePicker v-if="host.files" v-model:open="picking" :thread="thread" :prefix="`${prefix}poll-`" @staged="staged" />
  </form>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, ref } from 'vue'
import { Button, Dropdown } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import FilePicker from '../attachments/FilePicker.vue'
import { PHOTO_ACCEPT } from '../attachments/tray.js'
import { MAX_OPTION, MAX_OPTIONS, MAX_QUESTION, MIN_OPTIONS } from './form.js'

// The poll builder (design §3.7; canvas "The composer" frame 6, Poll builder): a question, 2 to 10 options each with an
// optional picture, one choice or several, named or anonymous (a Team conversation only), and a close time. It replaces the
// box while it is open; Cancel lets everything go. A picture comes from this device or, for staff, the project's files (in
// a Client conversation as a checked copy, "Share and send"). Problems show after the first Send. Esc closes the form and
// keeps it.
const props = defineProps({ draft: { type: Object, required: true }, thread: { type: Object, default: null }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['sent'])
const host = inject(HOST_KEY)
const w = wordsFor(useMode(), props.portal)
const CHOICES = [{ id: 'one', word: 'polls.one_choice_btn', multiple: false }, { id: 'several', word: 'polls.several_btn', multiple: true }]
const VOTES = [{ id: 'named', word: 'polls.named_btn', anonymous: false }, { id: 'anonymous', word: 'polls.anonymous_btn', anonymous: true }]
const question = ref(null)
const device = ref(null)
const picking = ref(false)
const state = props.draft.state
const form = computed(() => props.draft.form)
const shown = computed(() => (state.tried ? props.draft.problems() : []))
let target = null

const itemOf = (o) => props.draft.itemOf(o)
const segment = (on) => ['h-7 cursor-pointer rounded-3 border-0 px-3 text-sm max-md:h-12', on ? 'bg-surface-base font-medium text-ink-gray-9 shadow-sm' : 'bg-transparent text-ink-gray-7']

function pictureMenu(o) {
  return [
    { label: w('polls.picture_device'), icon: 'lucide-upload', onClick: () => fromDevice(o) },
    { label: w('polls.picture_files'), icon: 'lucide-folder-open', onClick: () => { target = o.id; picking.value = true } },
  ]
}

function fromDevice(o) {
  target = o.id
  device.value?.click()
}

function picked(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file && target !== null) props.draft.pick(target, file)
}

function staged(answer) {
  if (target !== null) props.draft.link(target, answer)
}

async function addOption() {
  const o = form.value.add()
  await nextTick()
  if (o) document.getElementById(`${props.prefix}poll-option-${o.id}`)?.focus()
}

function removeOption(o) {
  props.draft.clearPicture(o.id)
  form.value.remove(o.id)
}

function cancel() {
  props.draft.cancel()
}

async function send() {
  const name = await props.draft.send()
  if (name) emit('sent', name)
}

onMounted(() => question.value?.focus())
</script>
