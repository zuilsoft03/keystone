<template>
  <button type="button" :aria-pressed="modelValue ? 'true' : 'false'"
    class="flex min-h-9 w-full cursor-pointer items-center gap-2 rounded-4 border border-outline-gray-2 px-2.5 py-1 text-left text-sm max-md:min-h-12"
    :class="modelValue ? 'bg-surface-blue-1 text-ink-blue-8' : 'bg-surface-base text-ink-gray-8 hover:bg-surface-gray-2'"
    :data-testid="`${prefix}mentions-filter`" @click="emit('update:modelValue', !modelValue)">
    <span class="lucide-at-sign size-4 flex-none" aria-hidden="true" />
    <span class="min-w-0 flex-1 truncate">{{ w('inbox.mentions') }}</span>
    <Badge v-if="count" size="sm" theme="blue" variant="solid" :label="String(count)" :aria-label="w('inbox.mention_aria')" :data-testid="`${prefix}mentions-count`" />
  </button>
</template>

<script setup>
import { Badge } from 'frappe-ui'
import { useMode } from '../mode.js'
import { wordsFor } from './words.js'

// The Mentions filter of the thread list (P3-66, design §3.4, §14.6; the inbox's "Mentions me" on the room's own threads):
// it keeps the threads where someone mentioned the reader and has not been read yet. The count is those threads.
const props = defineProps({ modelValue: Boolean, count: { type: Number, default: 0 }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])
const w = wordsFor(useMode(), props.portal)
</script>
