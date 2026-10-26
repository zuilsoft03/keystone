<template>
  <div class="mt-2" :data-testid="`${prefix}voice-card`">
    <NotePlayer v-if="card" :src="card.url" :length="card.length" :waveform="card.waveform" :portal="portal" :prefix="prefix" />
    <p v-else class="m-0 text-sm text-ink-gray-7" data-testid="voice-fallback">{{ w('kind.Voice') }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useMode } from '../../../mode.js'
import { wordsFor } from '../../words.js'
import NotePlayer from './NotePlayer.vue'

// The voice part's card (design §3.6, canvas "Message cards": Voice note): the player for the note the server read and
// served. `items` is the part's value: { attachment, url, type, codec, length, waveform, size, sent_on }. A note with no
// address (an unreadable file) is named by its kind, never a player that cannot play.
const props = defineProps({ items: { type: [Array, Object], default: () => ({}) }, message: Object, portal: Boolean, prefix: { type: String, default: '' } })
const w = wordsFor(useMode(), props.portal)
const card = computed(() => {
  const v = Array.isArray(props.items) ? props.items[0] : props.items
  return v && typeof v.url === 'string' && v.url ? { url: v.url, length: Number(v.length) || 0, waveform: Array.isArray(v.waveform) ? v.waveform : [] } : null
})
</script>
