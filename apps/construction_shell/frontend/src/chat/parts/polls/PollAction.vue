<template>
  <button type="button" class="grid size-8 cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-8 hover:bg-surface-gray-3 disabled:cursor-default disabled:opacity-50 max-md:size-12"
    :class="open ? 'bg-surface-gray-3' : ''" :title="w('polls.tool')" :aria-label="w('polls.tool')" :aria-expanded="open ? 'true' : 'false'" :disabled="disabled || !draft"
    :data-testid="`${prefix}poll-tool`" @pointerdown.prevent @click="draft.toggle()">
    <span class="lucide-chart-bar-big size-4 max-md:size-5" aria-hidden="true" />
  </button>
</template>

<script setup>
import { computed, inject } from 'vue'
import { useMode } from '../../../mode.js'
import { wordsFor } from '../../words.js'
import { POLL_KEY } from './key.js'

// The Make a poll button (design §3.7; canvas "The composer": the tools). It opens the builder in place of the box; the
// builder (PollPanel) is the message box's. Staff only: the thread offers the polls part to staff in an open thread.
const props = defineProps({ disabled: Boolean, portal: Boolean, prefix: { type: String, default: '' } })
const injected = inject(POLL_KEY, null)
const draft = computed(() => injected?.value || null)
const open = computed(() => Boolean(draft.value?.state.open))
const w = wordsFor(useMode(), props.portal)
</script>
