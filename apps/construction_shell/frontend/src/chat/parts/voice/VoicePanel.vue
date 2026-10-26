<template>
  <div v-if="voice" :class="voice.active || s.error ? 'px-3 pt-2' : ''" :data-testid="`${prefix}voice-panel`" :data-phase="s.phase" :data-mode="s.mode">
    <!-- Recording (canvas "The composer" frame 5): a red dot, the time, the level meter and what the gesture does -->
    <template v-if="voice.recording">
      <div class="flex items-center gap-3 rounded-6 border p-3" :class="s.cancelling ? 'border-outline-red-3 bg-surface-red-1' : 'border-outline-red-3 bg-surface-base'" :data-testid="`${prefix}voice-recording`">
        <span class="size-2.5 flex-none animate-pulse rounded-full bg-surface-red-7" aria-hidden="true" />
        <strong class="text-base tabular-nums text-ink-gray-9" :data-testid="`${prefix}voice-timer`">{{ lengthText(s.seconds) }}</strong>
        <span class="flex h-6 min-w-0 flex-1 items-center gap-0.5 overflow-hidden" aria-hidden="true" :data-testid="`${prefix}voice-meter`">
          <span v-for="(b, i) in s.bars" :key="i" class="w-[3px] flex-none rounded-[2px] bg-surface-red-5" :style="{ height: `${Math.round(4 + b * 16)}px` }" />
        </span>
        <span v-if="s.mode === 'hold'" class="flex-none text-xs" :class="s.cancelling ? 'font-semibold text-ink-red-8' : 'text-ink-gray-7'">
          {{ s.cancelling ? w('voice.release_cancel') : w('voice.slide_cancel') }}
        </span>
        <template v-else>
          <button type="button" class="grid size-10 flex-none cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-8 hover:bg-surface-gray-3 max-md:size-12"
            :title="w('voice.delete')" :aria-label="w('voice.delete')" :data-testid="`${prefix}voice-delete`" @click="voice.discard()">
            <span class="lucide-trash-2 size-4 max-md:size-5" aria-hidden="true" />
          </button>
          <Button variant="solid" theme="blue" size="md" icon-left="lucide-square" :label="w('voice.stop')" class="flex-none max-md:!h-12" :data-testid="`${prefix}voice-stop`" @click="voice.stop()" />
        </template>
      </div>
      <p class="m-0 mt-1 text-xs text-ink-gray-7">{{ s.mode === 'hold' ? w('voice.slide_lock') : w('voice.locked') }}</p>
    </template>
    <!-- Review: the note plays before it is sent; Delete takes it out; the box's Send sends it with the caption -->
    <template v-else-if="voice.hasNote">
      <div class="flex items-center gap-2" :data-testid="`${prefix}voice-review`">
        <NotePlayer :key="s.note.url" :src="s.note.url" :length="s.note.seconds" :waveform="s.note.waveform" :seekable="false" :portal="portal" :prefix="`${prefix}review-`" />
        <button type="button" class="grid size-10 flex-none cursor-pointer place-items-center rounded-4 border-0 bg-transparent text-ink-gray-8 hover:bg-surface-gray-3 max-md:size-12"
          :title="w('voice.delete')" :aria-label="w('voice.delete')" :data-testid="`${prefix}voice-delete`" @click="voice.discard()">
          <span class="lucide-trash-2 size-4 max-md:size-5" aria-hidden="true" />
        </button>
      </div>
      <p v-if="s.upload === 'uploading'" class="m-0 mt-1 text-xs text-ink-gray-7" :data-testid="`${prefix}voice-saving`">{{ w('voice.saving', { percent: Math.round(s.progress * 100) }) }}</p>
      <p v-else-if="s.upload === 'failed'" class="m-0 mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-red-8" :data-testid="`${prefix}voice-failed`">
        <span>{{ errorText }}</span>
        <Button size="sm" variant="outline" class="max-md:!h-12 max-md:!px-4" :label="w('voice.try_again')" :data-testid="`${prefix}voice-retry`" @click="voice.retryUpload()" />
      </p>
      <p v-else class="m-0 mt-1 text-xs text-ink-gray-7">{{ w('voice.review_hint') }}</p>
      <p v-if="s.notice" class="m-0 mt-1 text-xs text-ink-gray-8" :data-testid="`${prefix}voice-notice`">{{ w(`voice.${s.notice}`) }}</p>
    </template>
    <p v-else-if="s.error" class="m-0 text-sm text-ink-red-8" :data-testid="`${prefix}voice-problem`">{{ errorText }}</p>
    <!-- Said once, politely, when the state changes (never the ticking timer) -->
    <p class="sr-only" role="status" :data-testid="`${prefix}voice-status`">{{ said }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { wordsFor } from '../../words.js'
import NotePlayer from './NotePlayer.vue'
import { lengthText } from './recorder.js'

// The voice part's panel in the message box (design §3.6; canvas "The composer" frame 5), drawn above the text like the
// attach tray: the take in progress, then the note to review. Press and hold shows what sliding does; a tap or a lock shows
// Delete and Stop. The words and the polite status line come from the draft's state.
const props = defineProps({ voice: { type: Object, default: null }, portal: Boolean, prefix: { type: String, default: '' } })
const w = wordsFor(useMode(), props.portal)
const s = computed(() => props.voice.state)
const KNOWN = ['denied', 'no_mic', 'failed', 'unsupported', 'insecure', 'too_short', 'upload_failed']
// A code of ours is a word of the glossary; anything else is the server's own sentence about the note.
const errorText = computed(() => (KNOWN.includes(s.value.error) ? w(`voice.${s.value.error}`) : s.value.error))
const said = computed(() => (s.value.announce ? w(`voice.${s.value.announce.key}`, s.value.announce.values) : ''))
</script>
