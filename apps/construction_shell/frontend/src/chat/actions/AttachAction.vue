<template>
  <span class="relative inline-flex items-center" @keydown.esc.stop="menu = false">
    <input :id="id" ref="device" type="file" class="sr-only" multiple :accept="accept || ACCEPT" :disabled="disabled" :data-testid="`${prefix}attach-input`" @change="pick($event)" />
    <input :id="`${id}-photo`" ref="camera" type="file" class="sr-only" capture="environment" :accept="PHOTO_ACCEPT" :disabled="disabled" @change="pick($event, true)" />
    <button type="button" class="grid size-8 cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-8 hover:bg-surface-gray-3 disabled:cursor-default disabled:opacity-50 max-md:size-12"
      :title="w('attachments.attach')" :aria-label="w('attachments.attach')" :aria-haspopup="options.length > 1 ? 'listbox' : undefined"
      :aria-expanded="options.length > 1 ? String(menu) : undefined" :disabled="disabled" :data-testid="`${prefix}attach`" @click="open">
      <span class="lucide-paperclip size-4 max-md:size-5" aria-hidden="true" />
    </button>
    <!-- The attach menu (canvas "The composer" frames 2 and 7): a list above the box; on a phone, rows of 48 px -->
    <div v-if="menu" class="fixed inset-0 z-30" aria-hidden="true" @click="menu = false" />
    <div v-if="menu" role="listbox" :aria-label="w('attachments.attach')"
      class="absolute bottom-full left-0 z-40 mb-2 w-[280px] rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 shadow-lg max-md:w-[min(320px,calc(100vw-24px))]">
      <button v-for="o in options" :key="o.id" type="button" role="option" aria-selected="false"
        class="flex min-h-9 w-full items-center gap-2.5 rounded-4 border-0 bg-transparent px-2 py-1 text-left hover:bg-surface-gray-2 max-md:min-h-12"
        :data-testid="`${prefix}attach-${o.id}`" @click="choose(o.id)">
        <span class="size-4 flex-none text-ink-gray-7" :class="o.icon" aria-hidden="true" />
        <span class="min-w-0 flex-1">
          <span class="block text-base text-ink-gray-9">{{ o.label }}</span>
          <span v-if="o.hint" class="block text-xs text-ink-gray-7 max-md:hidden">{{ o.hint }}</span>
        </span>
      </button>
    </div>
    <FilePicker v-if="host.files" v-model:open="picking" :thread="thread" :prefix="prefix" @staged="(a) => tray.link(a)" />
    <!-- staff in a Client conversation (P3-80): Ask the client to approve… and New Decision… -->
    <AskFlow v-if="staffWant" :project="host.project" :want="staffWant" @done="staffWant = ''" />
    <!-- the menu's other actions (P3-79: Attach an approval…): each has its own dialog; a pick puts its tag in the box -->
    <component :is="a.component" v-for="a in extras" :key="a.id" :open="asking === a.id" :thread="thread" :portal="portal" :prefix="prefix"
      @update:open="(v) => (asking = v ? a.id : '')" @picked="(card) => compose?.insert(card)" />
  </span>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { useMode } from '../../mode.js'
import { useTouchPhone } from '../../sections/drafts.js'
import { HOST_KEY } from '../host.js'
import FilePicker from '../parts/attachments/FilePicker.vue'
import { ACCEPT, PHOTO_ACCEPT } from '../parts/attachments/tray.js'
import { attachActions } from '../registry.js'
import { COMPOSE_KEY } from '../suggest.js'
import { wordsFor } from '../words.js'
import AskFlow from '../../approvals/staff/AskFlow.vue'
import { staffWords } from '../../approvals/words.js'

// The attach action (design §3.2, §3.3, §13.2 F3; canvas "The composer"): Upload from this device, From project files
// (staff: Attach from Files, Share and send in a Client conversation) and Take photo (a touch device's camera, through
// the file input, which needs no camera permission). With one choice the button opens it at once. Each file joins the
// message box's tray, which stages it on the server; the send claims it. A client sends files while the portal's Files
// section is on (the server's capability, FIT-19).
const props = defineProps({
  accept: { type: String, default: '' },
  disabled: Boolean,
  portal: Boolean,
  prefix: { type: String, default: '' },
  tray: { type: Object, required: true },
  thread: { type: Object, default: null },
})
const host = inject(HOST_KEY)
const w = wordsFor(useMode(), props.portal)
const sw = staffWords(useMode())
const touch = useTouchPhone()
const id = `${props.prefix || 'chat-'}attach-input`
const menu = ref(false)
const picking = ref(false)
const device = ref(null)
const camera = ref(null)
const extras = computed(() => attachActions(host, props.thread))
const asking = ref('')
const staffWant = ref('')
const staffAsk = computed(() => host.viewer === 'staff' && props.thread?.audience === 'Client' && host.approvals && (props.thread.capabilities || []).includes('refs'))
const compose = inject(COMPOSE_KEY, null)
const options = computed(() => [
  ...(touch.value ? [{ id: 'photo', icon: 'lucide-camera', label: w('attachments.take_photo'), hint: w('attachments.take_photo_hint') }] : []),
  { id: 'device', icon: 'lucide-upload', label: w(touch.value ? 'attachments.upload_phone' : 'attachments.upload_device'), hint: w('attachments.upload_hint') },
  ...(host.files ? [{ id: 'files', icon: 'lucide-folder-open', label: w('attachments.from_files'),
    hint: w(props.thread?.audience === 'Client' ? 'attachments.from_files_client' : 'attachments.from_files_team') }] : []),
  ...extras.value.map((a) => ({ id: a.id, icon: a.icon, label: w(a.word), hint: w(a.hint) })),
  ...(staffAsk.value ? [
    { id: 'ask', icon: 'lucide-square-check', label: sw('picker_menu'), hint: sw('picker_menu_hint') },
    { id: 'decision', icon: 'lucide-list-checks', label: sw('decision_menu'), hint: sw('decision_menu_hint') },
  ] : []),
])

function open() {
  if (options.value.length === 1) return choose(options.value[0].id)
  menu.value = !menu.value
}

function choose(option) {
  menu.value = false
  if (option === 'device') device.value?.click()
  else if (option === 'photo') camera.value?.click()
  else if (option === 'files') picking.value = true
  else if (option === 'ask' || option === 'decision') staffWant.value = option
  else asking.value = option
}

function pick(event, photo = false) {
  const files = [...(event.target.files || [])]
  event.target.value = ''
  if (files.length) props.tray.add(files, { shrink: photo || touch.value })
}
</script>
