<template>
  <div class="mt-1 flex flex-col gap-1.5">
    <template v-for="(item, i) in list" :key="i">
      <!-- P3-69: a design event is one quiet line with the record's title in it; the System message's author did it -->
      <EventCard v-if="isEvent(item)" :item="item" :portal="portal" :prefix="prefix" :actor="message?.author?.name || ''" :time="time" :datetime="message?.creation" />
      <div v-else role="note" class="flex items-start gap-2 rounded-4 bg-surface-gray-2 px-2.5 py-1.5 text-[13px] text-ink-gray-8" data-testid="pointer">
        <span :class="item.type === 'message' ? 'lucide-quote' : 'lucide-messages-square'" class="mt-0.5 size-4 flex-none text-ink-gray-6" aria-hidden="true" />
        <span class="min-w-0 flex-1 whitespace-pre-wrap break-words">{{ lineOf(item) }}</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useMode } from '../../mode.js'
import { plain } from '../tokens.js'
import { wordsFor } from '../words.js'
import EventCard from './events/EventCard.vue'
import { isEvent } from './events/view.js'

// The pointer part (D-418): what a System card points at, drawn per reader at read time: a thread (its title, or
// "Conversation" when the reader cannot read its record), or a message (a mirrored reply, or the client message a Team
// thread is about), or a design event (P3-69: EventCard). The server leaves out anything the reader cannot read.
const props = defineProps({ items: { type: [Array, Object], default: () => [] }, message: Object, portal: Boolean, prefix: { type: String, default: '' }, time: { type: String, default: '' } })
const w = wordsFor(useMode(), props.portal)
const list = computed(() => (Array.isArray(props.items) ? props.items : [props.items]).filter(Boolean))

function lineOf(item) {
  if (item.type === 'thread') return w('pointer.thread', { title: plain(item.title, w) })
  // A photo or file with no caption is named by its kind (P3-65), never left as "wrote:" with nothing after it.
  if (item.type === 'message') return w('pointer.message', { author: item.author?.name || '', text: plain(item.text, w) || (item.kind ? w(`kind.${item.kind}`) : '') })
  return w('core.unknown_part')
}
</script>
