<template>
  <div class="flex w-[340px] max-w-full items-center gap-2.5 rounded-5 border border-outline-gray-2 bg-surface-base px-2.5 py-2"
    :data-testid="`${prefix}voice-note`" :data-status="state.status">
    <button type="button" class="grid size-9 flex-none cursor-pointer place-items-center rounded-full border-0 bg-surface-blue-6 text-ink-base hover:bg-surface-blue-7 max-md:size-12"
      :aria-label="buttonLabel" :data-testid="`${prefix}voice-play`" @click="press">
      <span class="size-4 max-md:size-5" :class="icon" aria-hidden="true" />
    </button>
    <div class="min-w-0 flex-1">
      <div v-if="seekable" ref="wave" class="flex h-7 cursor-pointer items-center gap-0.5 rounded-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-blue-5 max-md:h-12"
        role="slider" tabindex="0" :aria-label="w('voice.seek')" aria-valuemin="0" :aria-valuemax="Math.round(total)" :aria-valuenow="Math.round(state.position)"
        :aria-valuetext="w('voice.seek_value', { position: lengthText(state.position), length: lengthText(total) })" :data-testid="`${prefix}voice-wave`"
        @click="seekTo" @keydown="key">
        <span v-for="(b, i) in bars" :key="i" class="flex-1 rounded-[2px]" :class="i < filled ? 'bg-surface-blue-6' : 'bg-surface-gray-4'" :style="{ height: `${b}px` }" />
      </div>
      <div v-else class="flex h-7 items-center gap-0.5" aria-hidden="true" :data-testid="`${prefix}voice-wave`">
        <span v-for="(b, i) in bars" :key="i" class="flex-1 rounded-[2px]" :class="i < filled ? 'bg-surface-blue-6' : 'bg-surface-gray-4'" :style="{ height: `${b}px` }" />
      </div>
      <div class="flex flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-7">
        <span class="whitespace-nowrap tabular-nums" :data-testid="`${prefix}voice-time`">{{ w('voice.position', { position: lengthText(state.position), length: lengthText(total) }) }}</span>
        <span class="ml-auto inline-flex gap-px rounded-4 bg-surface-gray-2 p-px" role="group" :aria-label="w('voice.speed')">
          <button v-for="s in SPEEDS" :key="s" type="button" :aria-pressed="String(state.speed === s)" :aria-label="w('voice.speed_set', { speed: s })"
            class="h-[22px] min-w-7 cursor-pointer rounded-3 border-0 px-1.5 text-xs text-ink-gray-8 max-md:h-12 max-md:min-w-12"
            :class="state.speed === s ? 'bg-surface-base font-semibold text-ink-gray-9 shadow-sm' : 'bg-transparent hover:bg-surface-gray-3'"
            :data-testid="`${prefix}voice-speed-${s}`" @click="model.setSpeed(s)">{{ w('voice.speed_option', { speed: s }) }}</button>
        </span>
      </div>
      <p v-if="state.status === 'error'" class="m-0 mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-red-8" role="status" :data-testid="`${prefix}voice-note-error`">
        <span>{{ w('voice.cannot_play') }}</span>
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useMode } from '../../../mode.js'
import { wordsFor } from '../../words.js'
import { SKIP_SECONDS, SPEEDS, VoicePlayer } from './player.js'
import { lengthText } from './recorder.js'

// One voice note's player (design §3.6; canvas "Message cards": Voice note, and "The composer" frame 5): play and pause,
// the waveform, the length and the speeds 1×, 1.5× and 2×. The length is the server's (or the recording's own), the
// waveform comes with the card. The model (player.js) times every play and seek: a note that will not play ends in an
// error line with Try again on the play button, never a spinner for ever. A wave that can seek is a slider the keyboard
// moves too (arrows, Home, End). Only one note plays at a time.
const props = defineProps({
  src: { type: String, required: true },
  length: { type: Number, default: 0 },
  waveform: { type: Array, default: () => [] },
  seekable: { type: Boolean, default: true },
  portal: Boolean,
  prefix: { type: String, default: '' },
})
const w = wordsFor(useMode(), props.portal)
const BARS = 48
const wave = ref(null)
const model = shallowRef(make())
const state = computed(() => model.value.state)
const total = computed(() => props.length || 0)

function make() {
  return new VoicePlayer({ src: props.src, length: props.length })
}

watch(() => [props.src, props.length], () => {
  model.value.dispose()
  model.value = make()
})
onBeforeUnmount(() => model.value.dispose())

// The wave as BARS bars of 4 to 26 px, each the loudest of its share of the 100 values.
const bars = computed(() => {
  const values = props.waveform.length ? props.waveform : [0]
  return Array.from({ length: BARS }, (_, i) => {
    const from = Math.floor((i * values.length) / BARS)
    const to = Math.max(from + 1, Math.floor(((i + 1) * values.length) / BARS))
    const peak = Math.max(0, ...values.slice(from, to).map((n) => Number(n) || 0))
    return Math.round(4 + (Math.min(100, peak) / 100) * 22)
  })
})
const filled = computed(() => (total.value > 0 ? Math.floor((state.value.position / total.value) * BARS) : 0))

const icon = computed(() => ({ loading: 'lucide-loader-circle animate-spin', playing: 'lucide-pause', error: 'lucide-rotate-ccw' }[state.value.status] || 'lucide-play'))
const buttonLabel = computed(() => {
  if (state.value.status === 'error') return w('voice.try_again')
  if (model.value.busy) return w('voice.pause')
  return w('voice.play', { length: lengthText(total.value) })
})

function press() {
  if (state.value.status === 'error') model.value.retry()
  else model.value.toggle()
}

function seekTo(event) {
  const box = wave.value?.getBoundingClientRect()
  if (!box?.width || !total.value) return
  model.value.seek(((event.clientX - box.left) / box.width) * total.value)
}

function key(event) {
  const at = state.value.position
  const to = { ArrowLeft: at - SKIP_SECONDS, ArrowDown: at - SKIP_SECONDS, ArrowRight: at + SKIP_SECONDS, ArrowUp: at + SKIP_SECONDS, Home: 0, End: total.value }[event.key]
  if (to === undefined) return
  event.preventDefault()
  model.value.seek(to)
}
</script>
