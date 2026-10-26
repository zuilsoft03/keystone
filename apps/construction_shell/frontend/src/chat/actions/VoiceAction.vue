<template>
  <span v-if="why" class="inline-flex min-h-8 items-center gap-1.5 px-1 text-xs text-ink-gray-7" :data-testid="`${prefix}voice-note-plain`">
    <span class="lucide-mic-off size-4 flex-none" aria-hidden="true" />{{ w(`voice.${why}`) }}
  </span>
  <span v-else class="relative inline-flex items-center">
    <!-- Slid up far enough, the lock shows above the button (canvas frame 5: the lock over the red microphone) -->
    <span v-if="hold" class="absolute bottom-full left-1/2 mb-2 grid h-10 w-8 -translate-x-1/2 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-7" aria-hidden="true">
      <span class="lucide-lock size-4" />
    </span>
    <button ref="button" type="button" class="grid cursor-pointer select-none disabled:cursor-default disabled:opacity-50 place-items-center border-0 [-webkit-touch-callout:none] touch-none"
      :class="recording ? 'size-12 rounded-full bg-surface-red-7 text-ink-base hover:bg-surface-red-8' : 'size-8 rounded-4 bg-transparent text-ink-gray-8 hover:bg-surface-gray-3 max-md:size-12'"
      :title="recording ? w('voice.mic_stop') : w('voice.hint')" :aria-label="recording ? w('voice.mic_stop') : w('voice.mic')"
 :disabled="blocked" :data-testid="`${prefix}voice`"
      @touchstart.prevent @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="lost" @lostpointercapture="lost" @contextmenu.prevent @click="click">
      <span class="lucide-mic size-4 max-md:size-5" aria-hidden="true" />
    </button>
  </span>
</template>

<script setup>
import { computed, inject, onBeforeUnmount } from 'vue'
import { useMode } from '../../mode.js'
import { VOICE_KEY } from '../parts/voice/key.js'
import { TAP_MS } from '../parts/voice/draft.js'
import { wordsFor } from '../words.js'

// The microphone (design §3.6; canvas "The composer": the tools, and frame 5): press and hold to record, slide up to lock,
// slide left to cancel. A tap starts it and a second tap stops it; the keyboard and a screen reader do the same through
// the button's click (Enter or Space). An unlocked hold that is let go sends the note at once; after a tap or a lock the
// note waits for Play, Delete or Send. The panel (VoicePanel) shows the take. Where the page cannot record (plain http,
// no MediaRecorder) the button is replaced by a plain note, as the drawing viewer says it needs HTTPS (D-321).
const props = defineProps({ disabled: Boolean, portal: Boolean, prefix: { type: String, default: '' }, tray: { type: Object, default: null } })
const injected = inject(VOICE_KEY, null)
const draft = computed(() => injected?.value || null)
const w = wordsFor(useMode(), props.portal)
const why = computed(() => (draft.value && draft.value.support !== 'ok' ? draft.value.support : ''))
const recording = computed(() => Boolean(draft.value?.recording))
const hold = computed(() => draft.value?.state.mode === 'hold' && recording.value)
// Files in the tray and a voice note cannot go in one message (the server sends a note on its own): one or the other.
const blocked = computed(() => !draft.value || (!recording.value && (props.disabled || draft.value.hasNote || Boolean(props.tray?.items?.length))))
let origin = null
let pressedAt = 0
let stopOnUp = false
let pointer = -1

function down(event) {
  if (event.button > 0 || blocked.value) return
  pressedAt = performance.now()
  if (draft.value.recording) { // already recording hands-free: this press stops it when it is let go
    stopOnUp = true
    return
  }
  stopOnUp = false
  origin = { x: event.clientX, y: event.clientY }
  pointer = event.pointerId
  try { event.currentTarget.setPointerCapture(event.pointerId) } catch { /* a pointer that is already gone */ }
  draft.value.begin('hold')
}

function move(event) {
  if (!origin || event.pointerId !== pointer) return
  draft.value.gesture(event.clientX - origin.x, event.clientY - origin.y)
}

function up(event) {
  if (stopOnUp) {
    stopOnUp = false
    draft.value.stop()
    return
  }
  if (!origin || event.pointerId !== pointer) return
  origin = null
  const state = draft.value.state
  if (state.mode !== 'hold') return // locked while held: it goes on
  if (performance.now() - pressedAt < TAP_MS && !state.cancelling) draft.value.lock() // a tap starts a hands-free take
  else draft.value.release()
}

// The pointer was taken away (a call, a system gesture, a touch turned into a scroll): the take is kept as a draft.
function lost() {
  if (!origin) return
  origin = null
  if (draft.value.state.mode === 'hold') draft.value.interrupt()
}

// A click with no pointer (detail 0) is the keyboard or a screen reader: it starts and stops.
function click(event) {
  if (event.detail !== 0 || blocked.value) return
  if (draft.value.recording) draft.value.stop()
  else draft.value.begin('free')
}

onBeforeUnmount(() => {
  if (draft.value?.recording) draft.value.interrupt() // leaving the room: what was said is kept
})
</script>
