<template>
  <button type="button" class="grid size-8 cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-8 hover:bg-surface-gray-3 max-md:size-12"
    :title="w('refs.tag')" :aria-label="w('refs.tag')" aria-haspopup="listbox" :disabled="disabled" :data-testid="`${prefix}tag`" @pointerdown.prevent @click="compose.begin('#')">
    <span class="lucide-hash size-4 max-md:size-5" aria-hidden="true" />
  </button>
</template>

<script setup>
import { inject } from 'vue'
import { useMode } from '../../mode.js'
import { COMPOSE_KEY } from '../suggest.js'
import { wordsFor } from '../words.js'

// The Tag a file or record button (design §3.5, canvas "The composer"): puts "#" in the box where the caret is, which
// opens the picker. Typing "#" does the same.
const props = defineProps({ disabled: Boolean, portal: Boolean, prefix: { type: String, default: '' } })
const compose = inject(COMPOSE_KEY)
const w = wordsFor(useMode(), props.portal)
</script>
