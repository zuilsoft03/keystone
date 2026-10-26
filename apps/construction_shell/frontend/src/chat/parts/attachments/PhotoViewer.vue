<template>
  <Teleport to="body">
    <div ref="root" class="fixed inset-0 z-50 flex flex-col bg-surface-gray-8 outline-none dark:bg-surface-base" role="dialog" aria-modal="true"
      :aria-label="w('attachments.photo_viewer')" tabindex="-1" :data-testid="`${prefix}photo-viewer`"
      @keydown.esc.stop.prevent="close" @keydown.left.prevent="step(-1)" @keydown.right.prevent="step(1)">
      <div class="flex min-h-14 items-center gap-2 px-3 text-sm text-ink-gray-2 dark:text-ink-gray-8">
        <span aria-live="off" :data-testid="`${prefix}photo-count`">{{ w('attachments.of', { n: at + 1, count: photos.length }) }}</span>
        <a :href="photo.url" :download="photo.file_name" :class="ROUND" class="ml-auto" :aria-label="w('attachments.download')" :title="w('attachments.download')">
          <span class="lucide-download size-5" aria-hidden="true" />
        </a>
        <button v-if="markable" type="button" :class="ROUND" :disabled="making" :aria-label="w('markup.canvas')" :title="w('markup.canvas')"
          :data-testid="`${prefix}photo-markup`" @click="markUp">
          <span :class="making ? 'lucide-loader-circle animate-spin' : 'lucide-pen-line'" class="size-5" aria-hidden="true" />
        </button>
        <button v-if="editable" type="button" :class="ROUND" :disabled="making" :aria-label="w('markup.edit')" :title="w('markup.edit')"
          :data-testid="`${prefix}photo-edit`" @click="edit">
          <span :class="making ? 'lucide-loader-circle animate-spin' : 'lucide-pen-line'" class="size-5" aria-hidden="true" />
        </button>
        <button ref="closer" type="button" :class="ROUND" :aria-label="w('attachments.close')" :title="w('attachments.close')" :data-testid="`${prefix}photo-close`" @click="close">
          <span class="lucide-x size-5" aria-hidden="true" />
        </button>
      </div>
      <div class="relative flex min-h-0 flex-1 items-center justify-center px-16 pb-2 max-md:px-2"
        @pointerdown="down" @pointerup="up" @pointercancel="start = null">
        <img ref="img" :key="photo.attachment" :src="photo.url" :alt="photo.file_name" class="max-h-full max-w-full select-none object-contain" draggable="false" />
        <button v-if="photos.length > 1" type="button" :class="ROUND" class="absolute left-3 top-1/2 -mt-6 max-md:hidden" :aria-label="w('attachments.previous')"
          :data-testid="`${prefix}photo-previous`" @click="step(-1)">
          <span class="lucide-chevron-left size-6" aria-hidden="true" />
        </button>
        <button v-if="photos.length > 1" type="button" :class="ROUND" class="absolute right-3 top-1/2 -mt-6 max-md:hidden" :aria-label="w('attachments.next')"
          :data-testid="`${prefix}photo-next`" @click="step(1)">
          <span class="lucide-chevron-right size-6" aria-hidden="true" />
        </button>
      </div>
      <p v-if="error" class="m-0 mx-auto mb-2 rounded-4 bg-surface-base px-3 py-1 text-xs text-ink-red-7" role="alert" :data-testid="`${prefix}photo-error`">{{ error }}</p>
      <PictureEditor v-if="editing" :picture="picture" :name="photo.file_name" :thread="conversation" :portal="portal" :prefix="prefix" @cancel="editing = false" @done="marked" />
      <p class="m-0 px-4 pb-4 text-center text-xs text-ink-gray-3 dark:text-ink-gray-7">{{ line }}</p>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMode } from '../../../mode.js'
import { focusComposer } from '../../../sections/drafts.js'
import { HOST_KEY, ROOM_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { jpegOf, sceneOf } from '../markup/board.js'
import { buttonOf } from '../markup/editor.js'
import PictureEditor from '../markup/PictureEditor.vue'
import { takenValues } from './cards.js'

// The photo viewer (canvas "Message cards": Swipe viewer): the original picture, "2 of 7", the arrows and a swipe
// on a phone, Escape or Close to leave, Download. The original is read through its own address, which the reader
// may open (the card was drawn only because they can). P3-70: staff in Advanced mode also get "Mark up on a Canvas", which
// puts the picture on a new team-only board; the board posts the marked-up picture back to the conversation. A client and staff in
// Simple mode get "Mark up" instead (the small editor); its picture joins the message tray. The staff preview of the portal gets neither,
// nor does a reader who may not send files in that conversation.
// `thread`, `capabilities`: the conversation and what it offers, where the part is outside its room (the details panel); inside it the room says.
const props = defineProps({
  photos: { type: Array, required: true }, start: { type: Number, default: 0 }, portal: Boolean, prefix: { type: String, default: '' },
  thread: { type: String, default: '' }, capabilities: { type: Array, default: null },
})
const emit = defineEmits(['close'])
const mode = useMode()
const w = wordsFor(mode, props.portal)
const host = inject(HOST_KEY, null)
const room = inject(ROOM_KEY, null)
const router = useRouter()
const ROUND = 'grid size-12 flex-none place-items-center rounded-full border-0 bg-surface-gray-7 text-ink-base no-underline hover:bg-surface-gray-6 dark:bg-surface-gray-3 dark:text-ink-gray-9 dark:hover:bg-surface-gray-4'
const at = ref(Math.min(Math.max(props.start, 0), props.photos.length - 1))
const photo = computed(() => props.photos[at.value])
const root = ref(null)
const closer = ref(null)
const img = ref(null)
const making = ref(false)
const error = ref('')
const conversation = computed(() => props.thread || room?.thread?.name || '')
const kind = computed(() => (conversation.value ? buttonOf(host, mode.value, { capabilities: props.capabilities ?? room?.thread?.capabilities }) : null))
const markable = computed(() => kind.value === 'canvas')
const editable = computed(() => kind.value === 'editor')
const editing = ref(false)
const picture = ref(null)
let start = null
let before = null

const line = computed(() => {
  const values = takenValues([photo.value])
  const parts = [photo.value.file_name, values.taken ? w('attachments.taken_sent', values) : w('attachments.sent_at', values)]
  if (props.photos.length > 1) parts.push(w('attachments.swipe'))
  return parts.join(' · ')
})

function step(by) {
  const n = props.photos.length
  at.value = (at.value + by + n) % n
}

function down(e) {
  start = { x: e.clientX, y: e.clientY }
}

function up(e) {
  if (!start) return
  const dx = e.clientX - start.x
  const dy = e.clientY - start.y
  start = null
  if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) step(dx < 0 ? 1 : -1)
}

function close() {
  emit('close')
}

async function markUp() {
  making.value = true
  error.value = ''
  const { file_name: name } = photo.value
  try {
    const { dataURL, width, height } = await jpegOf(img.value)
    const board = await host.markup(w('markup.board_title', { name: name.replace(/\.\w+$/, '') }), sceneOf(dataURL, width, height, Date.now()))
    router.push({ name: 'section', params: { project: host.project, section: 'whiteboards', item: board }, query: { post: conversation.value } })
  } catch (e) {
    error.value = e?.message || w('markup.failed')
  } finally {
    making.value = false
  }
}

async function edit() {
  making.value = true
  error.value = ''
  try {
    picture.value = await jpegOf(img.value)
    editing.value = true
  } catch {
    error.value = w('markup.edit_failed')
  } finally {
    making.value = false
  }
}

// The editor has put the picture in the tray: the viewer closes and the message box is next, for a note and Send.
async function marked() {
  emit('close')
  await nextTick() // the viewer has gone, with its own return of focus
  focusComposer(document.querySelector(`[data-testid="${props.prefix}composer"]`), { force: true })
}

onMounted(async () => {
  before = document.activeElement
  await nextTick()
  closer.value?.focus()
})
onUnmounted(() => before?.focus?.())
</script>
