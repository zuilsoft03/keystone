<template>
  <div class="flex min-w-0 flex-col gap-3" :data-testid="`${prefix}request-page`" :data-status="page?.status">
    <p v-if="missing" class="m-0 text-ink-gray-7" role="alert" :data-testid="`${prefix}request-missing`">{{ w('file_requests.missing') }}</p>
    <p v-else-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}request-load-error`">{{ error }}</p>
    <p v-else-if="!page" class="m-0 text-ink-gray-7">{{ w('core.loading') }}</p>
    <template v-else>
      <div class="flex flex-col gap-1">
        <h2 class="m-0 text-lg font-semibold text-ink-gray-9" :data-testid="`${prefix}request-page-title`">{{ page.title }}</h2>
        <p class="m-0 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm text-ink-gray-7">
          <span v-if="due" :data-testid="`${prefix}request-page-due`">{{ w('file_requests.due', { date: due }) }}</span>
          <strong class="font-semibold text-ink-gray-9" :data-testid="`${prefix}request-page-count`">{{ count }}</strong>
        </p>
        <div class="h-1.5 overflow-hidden rounded-full bg-surface-gray-3" role="progressbar" aria-valuemin="0" :aria-valuemax="bar.total" :aria-valuenow="bar.received" :aria-label="count">
          <span class="block h-full bg-surface-green-7" :style="{ width: `${bar.percent}%` }" />
        </div>
      </div>
      <p v-if="cap" class="m-0 rounded-4 bg-surface-blue-1 px-3 py-2 text-sm text-ink-blue-8" :data-testid="`${prefix}request-cap`">{{ cap }}</p>
      <p v-if="page.status === 'Done'" class="m-0 rounded-4 bg-surface-green-1 px-3 py-2 text-sm text-ink-green-8" :data-testid="`${prefix}request-all-in`">{{ w('file_requests.all_in') }}</p>
      <p v-else-if="page.status === 'Cancelled'" class="m-0 rounded-4 bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8" :data-testid="`${prefix}request-closed`">{{ w('file_requests.closed') }}</p>
      <ul class="m-0 flex list-none flex-col gap-2 p-0" :aria-label="page.title">
        <li v-for="(i, n) in page.items" :key="i.item" class="flex flex-col gap-1.5 rounded-5 border border-outline-gray-2 bg-surface-base p-3"
          :data-testid="`${prefix}request-slot`" :data-item="i.item" :data-state="slotState(i, busyOf(i))">
          <div class="flex items-start gap-2">
            <span class="mt-0.5 grid size-[18px] flex-none place-items-center rounded-full" :class="MARK[stateOf(i)]" aria-hidden="true">
              <span v-if="i.status !== 'Waiting'" class="lucide-check size-3" />
              <span v-else-if="i.reason" class="lucide-rotate-ccw size-3" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="m-0 text-base font-medium text-ink-gray-9">{{ name(i, n) }}</p>
              <p class="m-0 text-xs text-ink-gray-7">{{ w(i.required ? 'file_requests.required' : 'file_requests.optional') }}
                <a v-if="i.example" :href="i.example.url" target="_blank" rel="noopener" class="ml-2 text-ink-blue-8 underline" :data-testid="`${prefix}request-example-link`">{{ w('file_requests.example_link') }}</a>
              </p>
            </div>
            <span class="flex-none text-xs text-ink-gray-7" :data-testid="`${prefix}request-slot-state`">{{ w(`file_requests.state_${stateOf(i)}`) }}</span>
          </div>
          <p v-if="i.reason && i.status === 'Waiting'" class="m-0 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-8" role="status" :data-testid="`${prefix}request-slot-reason`">{{ w('file_requests.again_note', { reason: i.reason }) }}</p>
          <p v-if="i.held?.checking" class="m-0 text-sm text-ink-gray-8" role="status" :data-testid="`${prefix}request-slot-checking`">{{ w('file_requests.checking_note', { file: i.held.file_name }) }}</p>
          <p v-else-if="i.held?.refused" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}request-slot-refused`">{{ w('file_requests.refused_note', { file: i.held.file_name, reason: i.held.refused }) }}</p>
          <p v-else-if="i.held" class="m-0 text-sm text-ink-gray-8" :data-testid="`${prefix}request-slot-sent`">{{ w('file_requests.sent_waiting', { file: i.held.file_name }) }}</p>
          <p v-if="i.file" class="m-0 text-sm text-ink-gray-8"><a :href="i.file.url" target="_blank" rel="noopener" class="text-ink-blue-8 underline" :data-testid="`${prefix}request-slot-file`">{{ w('file_requests.accepted_file', { file: i.file.file_name }) }}</a></p>
          <div v-if="busyOf(i)" class="flex flex-col gap-1" :data-testid="`${prefix}request-slot-uploading`">
            <span class="text-sm text-ink-gray-8">{{ w('file_requests.uploading', { file: busyOf(i).name, percent: Math.round(busyOf(i).progress * 100) }) }}</span>
            <span class="block h-1 overflow-hidden rounded-full bg-surface-gray-3" role="progressbar" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(busyOf(i).progress * 100)">
              <span class="block h-full bg-surface-blue-6" :style="{ width: `${Math.round(busyOf(i).progress * 100)}%` }" />
            </span>
          </div>
          <p v-if="uploads[i.item]?.error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}request-slot-error`">{{ uploads[i.item].error }}</p>
          <div v-if="slotOpen(i, page) && !busyOf(i)" class="flex flex-wrap items-center gap-2">
            <input :ref="(el) => put(i.item, 'file', el)" type="file" class="sr-only" tabindex="-1" aria-hidden="true" :accept="ACCEPT" :data-testid="`${prefix}request-file-input`" @change="picked(i, $event)" />
            <input :ref="(el) => put(i.item, 'photo', el)" type="file" class="sr-only" capture="environment" tabindex="-1" aria-hidden="true" :accept="PHOTO_ACCEPT" :data-testid="`${prefix}request-photo-input`" @change="picked(i, $event, true)" />
            <Button class="min-w-12 max-md:!h-12" variant="solid" theme="blue" size="md" icon-left="lucide-upload" :label="w(i.status === 'Waiting' ? 'file_requests.send_file' : 'file_requests.send_again')"
              :aria-label="`${w(i.status === 'Waiting' ? 'file_requests.send_file' : 'file_requests.send_again')}: ${name(i, n)}`" :data-testid="`${prefix}request-pick`" @click="inputs[`${i.item}:file`]?.click()" />
            <Button v-if="touch" class="min-w-12 max-md:!h-12" variant="subtle" size="md" icon-left="lucide-camera" :label="w('attachments.take_photo')"
              :aria-label="`${w('attachments.take_photo')}: ${name(i, n)}`" :data-testid="`${prefix}request-photo`" @click="inputs[`${i.item}:photo`]?.click()" />
          </div>
        </li>
      </ul>
    </template>
    <p class="sr-only" role="status" :data-testid="`${prefix}request-said`">{{ said }}</p>
  </div>
</template>

<script setup>
import { computed, inject, onUnmounted, reactive, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { onEvent } from '../../../realtime.js'
import { useTouchPhone } from '../../../sections/drafts.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { captureTime } from '../attachments/exif.js'
import { shrinkImage } from '../attachments/shrink.js'
import { ACCEPT, PHOTO_ACCEPT } from '../attachments/tray.js'
import { CHANGED_EVENT } from '../../live.js'
import { capWord, dayText, itemName, progressOf, scanning, slotOpen, slotState, stateOf } from './view.js'

// The request page (design §3.10; no canvas frame, drawn from the card and the portal's Files tab, D-196), one component for the
// portal ("Files we asked for", Requests.vue) and for staff in the workspace (a panel beside the conversation): the request's
// title, due date and count, then one slot for each file. A slot shows what was asked, an example, its state and, when the
// team asked again, the reason; the person asked picks a file or, on a phone, takes a photo. Every upload goes through the
// server's checks and waits for staff; a large file is scanned after the request, so the page reads again until it is
// done. A client asked sees how many more files can go today (D-182). The server decides every right again.
const props = defineProps({ request: { type: String, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['loaded', 'missing'])
const host = inject(HOST_KEY)
const w = wordsFor(useMode(), props.portal)
const touch = useTouchPhone()
const MARK = { received: 'bg-surface-green-2 text-ink-green-8', accepted: 'bg-surface-green-2 text-ink-green-8', again: 'bg-surface-amber-2 text-ink-amber-8', waiting: 'bg-surface-gray-2 text-ink-gray-6' }
const page = ref(null)
const missing = ref(false)
const error = ref('')
const said = ref('')
const uploads = reactive({}) // item -> { name, progress, error }
const inputs = {}
let asked = 0
let timer = null
const bar = computed(() => progressOf(page.value))
const due = computed(() => dayText(page.value?.due_on))
const count = computed(() => w(bar.value.total === 1 ? 'file_requests.progress_one' : 'file_requests.progress', { received: bar.value.received, total: bar.value.total }))
const cap = computed(() => {
  const line = capWord(page.value?.files_left_today)
  return line ? w(line.key, line.values) : ''
})
const name = (item, n) => itemName({ ...item, n: n + 1 }, w)
const busyOf = (item) => (uploads[item.item] && !uploads[item.item].error ? uploads[item.item] : null)
const put = (item, kind, el) => { inputs[`${item}:${kind}`] = el }

async function load() {
  const ask = ++asked
  clearTimeout(timer)
  try {
    const answer = await host.read('page', { request: props.request })
    if (ask !== asked) return
    page.value = answer
    missing.value = false
    error.value = ''
    emit('loaded', answer)
  } catch (e) {
    if (ask !== asked) return
    if (e.type === 'DoesNotExistError') {
      missing.value = true
      emit('missing')
    } else error.value = e.message || ''
  }
  if (ask === asked && scanning(page.value)) timer = setTimeout(load, 3000) // a large file is scanned after its request
}

async function picked(item, event, photo = false) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || busyOf(item)) return
  uploads[item.item] = { name: file.name, progress: 0, error: '' }
  try {
    const takenOn = await captureTime(file) // read before the shrink drops the EXIF
    const sent = photo && touch.value ? await shrinkImage(file) : file
    const job = host.requestUpload(item.item, sent, { takenOn, onProgress: (p) => { if (uploads[item.item]) uploads[item.item].progress = p } })
    page.value = await job.done
    delete uploads[item.item]
    said.value = ''
    said.value = w('file_requests.sent_waiting', { file: file.name })
    emit('loaded', page.value)
    if (scanning(page.value)) timer = setTimeout(load, 3000)
  } catch (e) {
    uploads[item.item] = { name: file.name, progress: 0, error: e.message || w('file_requests.upload_failed') }
  }
}

watch(() => props.request, load, { immediate: true })
// The team accepted a file, asked again or cancelled: the card's message changed, so this page reads again.
const off = onEvent(CHANGED_EVENT, (d) => d && page.value && d.message === page.value.message && load())
onUnmounted(() => {
  off()
  clearTimeout(timer)
  asked += 1
})
</script>
