<template>
  <aside ref="panel" :aria-label="w('file_requests.page_heading')" tabindex="-1"
    class="flex min-h-0 min-w-0 flex-col border-outline-gray-2 bg-surface-base md:w-[360px] md:flex-none md:border-l max-md:flex-1"
    data-testid="request-panel" @keydown.esc.stop="close">
    <header class="flex items-center gap-2 py-2.5 pl-4 pr-2 max-md:min-h-14 max-md:pl-1.5">
      <button v-if="phone" type="button" class="grid size-12 flex-none place-items-center rounded-4 text-ink-gray-8 hover:bg-surface-gray-2"
        :aria-label="w('file_requests.back')" data-testid="request-back" @click="close">
        <span class="lucide-chevron-left size-5" aria-hidden="true" />
      </button>
      <h2 ref="heading" tabindex="-1" class="m-0 min-w-0 flex-1 truncate text-base font-semibold text-ink-gray-9 outline-none" data-testid="request-panel-title">{{ w('file_requests.page_heading') }}</h2>
      <Button v-if="!phone" variant="ghost" icon="lucide-x" :aria-label="w('file_requests.panel_close')" data-testid="request-close" @click="close" />
    </header>
    <div class="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
      <RequestPage :request="request" />
    </div>
  </aside>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { wordsFor } from '../../words.js'
import RequestPage from './RequestPage.vue'

// A file request beside its conversation (design §3.10): staff open it from the card's Open request or Send files. The
// same page the client has in the portal (RequestPage), in the thread panel's place: a column on a wide screen, its own
// screen on a phone. Focus moves into it when it opens; Escape, Close or Back closes it.
const props = defineProps({ request: { type: String, required: true }, phone: Boolean })
const emit = defineEmits(['close'])
const w = wordsFor(useMode())
const heading = ref(null)

const close = () => emit('close', props.request)

async function takeFocus() {
  await nextTick()
  heading.value?.focus({ preventScroll: true })
}

onMounted(takeFocus)
watch(() => props.request, takeFocus)
</script>
