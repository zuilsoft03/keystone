<template>
  <aside ref="panel" :aria-label="w('core.thread_label')" tabindex="-1"
    class="flex min-h-0 min-w-0 flex-col border-outline-gray-2 bg-surface-base md:w-[360px] md:flex-none md:border-l max-md:flex-1"
    :data-testid="`${prefix}thread-panel`" @keydown.esc.stop="close" @focusin="emit('focus')">
    <header class="flex items-center gap-2 py-2.5 pl-4 pr-2 max-md:min-h-14 max-md:pl-1.5">
      <button v-if="phone" type="button" class="grid size-12 flex-none place-items-center rounded-4 text-ink-gray-8 hover:bg-surface-gray-2"
        :aria-label="w('core.back_thread')" :data-testid="`${prefix}thread-back`" @click="close">
        <span class="lucide-chevron-left size-5" aria-hidden="true" />
      </button>
      <div class="min-w-0 flex-1">
        <h2 ref="heading" tabindex="-1" class="m-0 truncate text-base font-semibold text-ink-gray-9 outline-none" :data-testid="`${prefix}thread-title`">{{ threadTitle(thread, w) }}</h2>
        <p class="m-0 truncate text-xs text-ink-gray-7">{{ w('core.thread_in', { room: roomTitle }) }} · {{ repliesWord }}</p>
      </div>
      <Button v-if="!phone" variant="ghost" icon="lucide-x" :aria-label="w('core.close_thread')" :data-testid="`${prefix}thread-close`" @click="close" />
    </header>
    <div role="tablist" class="flex gap-1 border-b border-outline-gray-2 px-2">
      <button v-for="t in TABS" :key="t" type="button" role="tab" :aria-selected="tab === t"
        class="-mb-px h-9 border-b-2 px-2.5 text-sm" :class="tab === t ? 'border-outline-gray-8 font-medium text-ink-gray-9' : 'border-transparent text-ink-gray-7 hover:text-ink-gray-8'"
        :data-testid="`${prefix}thread-tab-${t}`" @click="tab = t">{{ w(`core.tab_${t}`) }}</button>
    </div>
    <ChatRoom v-show="tab === 'thread'" ref="room" bare in-thread :room="thread.name" :audience="thread.audience" :title="threadTitle(thread, w)"
      :root="thread.root || ''" :replies="Number(thread.replies) || 0" :placeholder="w('core.reply_placeholder')" :audience-line="audienceLine"
      :accept="accept" :portal="portal" :prefix="prefix" :live="live" :thread-rows="threadRows" :team-room="teamRoom"
      @team="(m) => emit('team', m)" />
    <ThreadDetails v-if="tab === 'details'" :thread="thread" :root="room?.rootMessage" :messages="room?.state.messages || []" :portal="portal" :prefix="prefix" />
    <p v-if="!portal && thread.audience === 'Client'" class="m-0 border-t border-outline-gray-1 px-4 py-2 text-xs text-ink-gray-7" data-testid="thread-clients-see">
      {{ w('core.thread_clients') }}
    </p>
  </aside>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { useMode } from '../mode.js'
import ChatRoom from './ChatRoom.vue'
import ThreadDetails from './ThreadDetails.vue'
import { threadTitle } from './threads.js'
import { wordsFor } from './words.js'

// The thread beside its room on a wide screen, and its own screen on a phone (P3-64, R-32; canvas frames 1 and 2):
// the root message, the replies and a message box with "Also send to room"; a Details tab with the working parts
// (the root, the files in the conversation, the people). Focus moves into it when it opens; Escape, Close or Back
// closes it and the page returns the focus to the root's reply line.
const TABS = ['thread', 'details']
const props = defineProps({
  thread: { type: Object, required: true }, // a thread row (discuss.api.threads)
  roomTitle: { type: String, default: '' },
  audienceLine: { type: String, default: '' },
  accept: { type: String, default: '' },
  portal: Boolean,
  prefix: { type: String, default: '' },
  phone: Boolean,
  live: { type: Boolean, default: true },
  threadRows: { type: Array, default: () => [] },
  teamRoom: { type: String, default: '' },
})
const emit = defineEmits(['close', 'focus', 'team'])
const w = wordsFor(useMode(), props.portal)
const tab = ref('thread')
const heading = ref(null)
const room = ref(null)
const repliesWord = computed(() => {
  const n = Number(props.thread.replies) || 0
  return n === 1 ? w('core.replies_one') : w('core.replies', { count: n })
})

function close() {
  emit('close', props.thread)
}

async function takeFocus() {
  tab.value = 'thread'
  await nextTick()
  heading.value?.focus({ preventScroll: true })
}

onMounted(takeFocus)
watch(() => props.thread.name, takeFocus)
</script>
