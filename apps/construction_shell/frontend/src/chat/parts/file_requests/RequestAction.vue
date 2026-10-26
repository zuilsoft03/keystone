<template>
  <span class="inline-flex">
    <button type="button" class="grid size-8 cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-8 hover:bg-surface-gray-3 disabled:cursor-default disabled:opacity-50 max-md:size-12"
      :class="open ? 'bg-surface-gray-3' : ''" :title="w('file_requests.tool')" :aria-label="w('file_requests.tool')" aria-haspopup="dialog" :disabled="disabled || !thread"
      :data-testid="`${prefix}request-tool`" @pointerdown.prevent @click="open = true">
      <span class="lucide-arrow-up-to-line size-4 max-md:size-5" aria-hidden="true" />
    </button>
    <RequestBuilder v-if="open" v-model:open="open" :form="form" :thread="thread" :prefix="prefix" @sent="sent" />
  </span>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { useMode } from '../../../mode.js'
import { HOST_KEY, ROOM_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import RequestBuilder from './RequestBuilder.vue'
import { requestFormOf } from './form.js'

// The Request files button (design §3.10; canvas "The composer": the tools). It opens the builder in a dialog (the poll's
// builder replaces the box; a checklist is too long for it). Staff only: the thread offers the file_requests part to staff in
// an open thread. The form is the page's, one for each conversation, so closing the dialog keeps what was typed.
defineOptions({ inheritAttrs: false }) // the box hands every action its tray, accept and so on; this one needs only the thread
const props = defineProps({ disabled: Boolean, portal: Boolean, prefix: { type: String, default: '' }, thread: { type: Object, default: null } })
const host = inject(HOST_KEY)
const room = inject(ROOM_KEY, null)
const w = wordsFor(useMode(), props.portal)
const open = ref(false)
const form = computed(() => requestFormOf(`${host.viewer}:${props.thread?.name}`))

// The request is in the conversation as soon as the server has it; the room's live read would bring it too.
async function sent(name) {
  try {
    room?.merge(await host.read('message', { name }))
  } catch { /* the live event reads it */ }
}
</script>
