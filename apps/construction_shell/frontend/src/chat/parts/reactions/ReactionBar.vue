<template>
  <div v-if="list.length" aria-live="off" class="mt-1.5 flex flex-wrap gap-1.5" role="group" :aria-label="w('reactions.label')" :data-testid="`${prefix}reactions`">
    <button v-for="p in list" :key="p.key" type="button" :aria-pressed="p.mine ? 'true' : 'false'" :aria-label="p.label" :title="p.names.join(', ') || undefined"
      class="inline-flex min-h-7 cursor-pointer items-center gap-1.5 rounded-full border px-2 py-0.5 text-sm text-ink-gray-8 disabled:cursor-default max-md:min-h-12 max-md:px-3"
      :class="p.mine ? 'border-outline-blue-6 bg-surface-blue-2 text-ink-blue-8' : 'border-outline-gray-2 bg-surface-base hover:bg-surface-gray-2'"
      :disabled="!host.act || busy" :data-testid="`${prefix}reaction`" :data-reaction="p.key" :data-mine="p.mine ? 'true' : undefined" @click="toggle(p)">
      <span aria-hidden="true">{{ p.glyph }}</span>
      <span class="font-medium" aria-live="off">{{ p.count }}</span>
    </button>
  </div>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { useMode } from '../../../mode.js'
import { HOST_KEY, ROOM_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { pills, said } from './summary.js'

// The reactions under a message (design §3.8, canvas: the hover toolbar's React button; the pills are built from its
// tokens, D-196): each is a toggle with its count and who reacted. A pill the reader made is drawn filled and says so by
// aria-pressed. The server's answer carries the new counts, so the pill changes at once and the room says it once, politely.
const props = defineProps({ items: { type: [Array, Object], default: () => [] }, message: { type: Object, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const host = inject(HOST_KEY)
const room = inject(ROOM_KEY, null)
const w = wordsFor(useMode(), props.portal)
const busy = ref(false)
const list = computed(() => pills(props.items, w))

async function toggle(p) {
  if (busy.value || !host.act) return
  busy.value = true
  try {
    room?.merge(await host.act('reactions', 'react', { message: props.message.name, reaction: p.key, on: p.mine ? 0 : 1 }))
    room?.say(said(p.key, !p.mine, w))
  } catch (e) {
    room?.fail(e.message)
  } finally {
    busy.value = false
  }
}
</script>
