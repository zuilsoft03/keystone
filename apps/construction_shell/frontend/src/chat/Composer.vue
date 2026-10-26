<template>
  <form :class="editing ? 'mt-1' : 'px-4 pb-3.5 pt-2 max-md:border-t max-md:border-outline-gray-1 max-md:px-2 max-md:pb-2.5'" :data-testid="editing ? `${prefix}form` : undefined" @submit.prevent="submit">
    <!-- P3-68: Make a poll replaces the box while its builder is open (canvas "The composer" frame 6) -->
    <PollPanel v-if="poll?.state.open" :draft="poll" :thread="thread" :portal="portal" :prefix="prefix" @sent="(name) => emit('sent', name)" />
    <div v-else class="relative rounded-6 border bg-surface-base shadow-sm" :class="dragging ? 'border-outline-blue-6' : 'border-outline-gray-3'"
      @paste="paste" @dragover="drag" @dragleave="dragging = false" @drop="drop">
      <TrayList v-if="tray" :tray="tray" :portal="portal" :prefix="prefix" />
      <VoicePanel v-if="voice" :voice="voice" :portal="portal" :prefix="prefix" />
      <p v-if="dragging" class="m-0 px-3 pt-2 text-xs text-ink-blue-7" role="status">{{ w('attachments.dropped_here') }}</p>
      <label class="sr-only" :for="inputId">{{ w('core.message') }}</label>
      <div class="relative">
        <!-- P3-66: a mention or a tag is a chip behind the text (same font and wrapping), so the text stays one plain box -->
        <div ref="mirror" class="pointer-events-none absolute inset-y-0 left-0 overflow-hidden whitespace-pre-wrap break-words px-3 py-2.5 text-base text-transparent" aria-hidden="true"
          :style="{ right: `${gutter}px` }" :data-testid="`${prefix}composer-chips`">
          <template v-for="(p, i) in pieces" :key="i"><span v-if="p.mark" class="rounded-3" :class="p.mark.kind === 'mention' ? 'bg-surface-blue-2' : 'bg-surface-gray-3'" :data-chip="p.mark.kind">{{ p.text }}</span><template v-else>{{ p.text }}</template></template>
        </div>
        <textarea :id="inputId" ref="box" :value="modelValue" rows="1" :maxlength="MAX"
          class="relative block min-h-11 w-full resize-none border-0 bg-transparent px-3 py-2.5 text-base text-ink-gray-9 placeholder-ink-gray-5 focus:ring-0"
          :placeholder="voice?.hasNote ? w('voice.caption') : placeholder" :data-testid="`${prefix}composer`"
          :role="suggestible ? 'combobox' : undefined" :aria-autocomplete="suggestible ? 'list' : undefined" :aria-haspopup="suggestible ? 'listbox' : undefined"
          :aria-expanded="suggestible ? String(suggest.state.open && suggest.state.items.length > 0) : undefined"
          :aria-controls="suggestible && suggest.state.open && suggest.state.items.length ? listId : undefined"
          :aria-activedescendant="suggestible && suggest.state.open && suggest.state.items.length ? `${listId}-${suggest.state.active}` : undefined"
          @input="onInput" @keydown="onKey" @keyup="onKeyup" @click="refresh" @scroll="syncMirror" @blur="suggest.close()" />
      </div>
      <Suggest :state="suggest.state" :list-id="listId" :portal="portal" :prefix="prefix" @pick="pick" />
      <div class="flex items-center gap-1 px-1.5 pb-1.5 pt-1 max-md:flex-wrap">
        <component :is="a.component" v-for="a in actions" :key="a.id" :accept="accept" :disabled="busy || (a.part === 'attachments' && Boolean(voice?.active))" :portal="portal" :prefix="prefix"
          :tray="tray" :thread="thread" />
        <label v-if="alsoRoom" class="ml-1.5 inline-flex cursor-pointer items-center gap-1.5 text-xs text-ink-gray-8" :data-testid="`${prefix}also-room`">
          <input type="checkbox" class="form-checkbox" :checked="also" @change="emit('update:also', $event.target.checked)" />{{ w('core.also_room') }}
        </label>
        <span v-if="!touch && !alsoRoom && !editing" class="ml-2 text-xs text-ink-gray-7 max-md:hidden">{{ w('core.hint') }}</span>
        <Button v-if="editing" class="ml-auto max-md:!h-12 max-md:!min-w-12" variant="ghost" size="md" :label="w('core.cancel')" :data-testid="`${prefix}cancel`" @click="emit('cancel')" />
        <Button :class="editing ? 'max-md:!h-12 max-md:!min-w-12' : 'ml-auto max-md:!h-12 max-md:!min-w-12'" type="submit" variant="solid" theme="blue" size="md" :icon-left="editing ? 'lucide-check' : 'lucide-send'"
          :label="editing ? w('core.edit_save') : w('core.send')" :disabled="!ready" :data-testid="editing ? `${prefix}save` : `${prefix}send`" />
      </div>
    </div>
    <p v-if="audience && !poll?.state.open" class="mb-0 mt-1.5 text-xs text-ink-gray-7" :data-testid="`${prefix}audience`">{{ audience }}</p>
  </form>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, provide, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { useMode } from '../mode.js'
import { composerKey, fitComposer, focusComposer, isTouchPhone, useTouchPhone } from '../sections/drafts.js'
import Suggest from './Suggest.vue'
import { HOST_KEY } from './host.js'
import TrayList from './parts/attachments/TrayList.vue'
import { POLL_KEY } from './parts/polls/key.js'
import PollPanel from './parts/polls/PollPanel.vue'
import { VOICE_KEY } from './parts/voice/key.js'
import VoicePanel from './parts/voice/VoicePanel.vue'
import { COMPOSE_KEY, insertPick, useSuggest } from './suggest.js'
import { addMark, refMark, spans } from './tokens.js'
import { wordsFor } from './words.js'

// The message box (design §13.2 F3, canvas "The composer"): the text, the actions the thread offers, the hint, Send and
// the audience line under the box. The room owns the thread, the draft, the send and its id; this box owns the Enter key
// (Enter sends, Shift+Enter is a new line, a touch phone sends only with its button, P3-61). P3-66: "@" and "#" open the
// list of people and the picker of files and records while the thread offers those parts; the box keeps Enter, Tab, the
// arrows and Escape for the open list. A pick puts its label in the text and a mark in `marks`; the send turns the labels
// into tokens (tokens.js build).
const MAX = 5000
const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  audience: { type: String, default: '' },
  actions: { type: Array, default: () => [] },
  accept: { type: String, default: '' },
  busy: Boolean,
  portal: Boolean,
  tray: { type: Object, default: null }, // P3-65: the files this message will carry (parts/attachments/tray.js)
  voice: { type: Object, default: null }, // P3-67: the voice note this message will carry (parts/voice/draft.js); null where the thread has no voice
  thread: { type: Object, default: null }, // the conversation's row, for its actions (Share and send in a Client one)
  prefix: { type: String, default: '' },
  alsoRoom: Boolean, // a thread's box: offer "Also send to room" (off by default, §14.1)
  also: Boolean,
  marks: { type: Array, default: () => [] }, // P3-66: the people and items picked into this text (tokens.js)
  poll: { type: Object, default: null }, // P3-68: the poll this conversation's box is making (parts/polls/draft.js); null where the thread has no polls
  editing: Boolean, // P3-68: the box of an edit: Save and Cancel, no hint, Esc cancels; the parent decides when Save is ready (`saveable`)
  saveable: Boolean,
})
const emit = defineEmits(['update:modelValue', 'update:also', 'update:marks', 'send', 'typing', 'sent', 'cancel'])
const w = wordsFor(useMode(), props.portal)
const touch = useTouchPhone()
const box = ref(null)
const inputId = `${props.prefix || 'chat-'}message`
const listId = `${inputId}-suggest`
const host = inject(HOST_KEY, null)
const mode = useMode()
const mirror = ref(null)
const gutter = ref(0)

// P3-66: the lists the thread offers, by the box's actions (capabilities and the viewer's rights decide the actions).
const chars = computed(() => `${props.actions.some((a) => a.part === 'mentions') ? '@' : ''}${props.actions.some((a) => a.part === 'refs') ? '#' : ''}`)
const suggestible = computed(() => chars.value.length > 0)
const suggest = useSuggest(() => ({ host, thread: props.thread?.name, mode: mode.value, chars: chars.value }))
const pieces = computed(() => {
  const text = props.modelValue
  const out = []
  let at = 0
  for (const { start, end, mark } of spans(text, props.marks)) {
    if (start > at) out.push({ text: text.slice(at, start) })
    out.push({ text: text.slice(start, end), mark })
    at = end
  }
  if (at < text.length) out.push({ text: text.slice(at) })
  return out
})

provide(VOICE_KEY, computed(() => props.voice)) // a ref: the room can change under the box
provide(POLL_KEY, computed(() => props.poll))

provide(COMPOSE_KEY, {
  has: (char) => chars.value.includes(char),
  // "Attach an approval…" (P3-79): the picked request joins the text as a tag at the caret, as a # pick does, without the list.
  insert(card) {
    const el = box.value
    if (!el || !chars.value.includes('#')) return
    const text = props.modelValue
    const caret = el.selectionStart ?? text.length
    const added = addMark(props.marks, refMark(card))
    const lead = caret && !/\s$/.test(text.slice(0, caret)) ? ' ' : ''
    const next = insertPick(text, { start: caret }, caret, lead + added.label)
    emit('update:marks', added.marks)
    emit('update:modelValue', next.text)
    nextTick(() => {
      el.focus({ preventScroll: true })
      el.setSelectionRange(next.caret, next.caret)
    })
  },
  // The tool buttons: put the trigger where the caret is (after a space), which opens its list.
  begin(char) {
    const el = box.value
    if (!el || !chars.value.includes(char)) return
    const text = props.modelValue
    if (suggest.state.open && suggest.state.char === char) { // a second press ends it, and takes back a trigger with nothing typed after it
      const { start, query } = suggest.state
      suggest.close()
      if (!query && text[start] === char) {
        emit('update:modelValue', text.slice(0, start) + text.slice(start + 1))
        nextTick(() => el.setSelectionRange(start, start))
      }
      return
    }
    const caret = el.selectionStart ?? text.length
    const before = text.slice(0, caret)
    const head = `${before}${before && !/\s$/.test(before) ? ' ' : ''}${char}`
    emit('update:modelValue', `${head}${text.slice(caret)}`)
    nextTick(() => {
      el.focus({ preventScroll: true })
      el.setSelectionRange(head.length, head.length)
      refresh()
    })
  },
})

function onInput(event) {
  emit('update:modelValue', event.target.value)
  if (!props.editing) emit('typing')
  if (suggestible.value) suggest.update(event.target.value, event.target.selectionStart, props.marks)
  syncMirror()
}

// The caret moved by a click or an arrow key: the list follows what is before it.
function refresh() {
  const el = box.value
  if (el && suggestible.value) suggest.update(el.value, el.selectionStart, props.marks)
}

function onKeyup(event) {
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) refresh()
}

// The keys of an open list come before the Enter-to-send rule: Enter picks, it does not send.
function listKey(event) {
  if (!suggest.state.open || event.isComposing) return false
  const move = { ArrowDown: 1, ArrowUp: -1 }[event.key]
  if (move) suggest.move(move)
  else if ((event.key === 'Enter' || event.key === 'Tab') && suggest.current() && !event.shiftKey) pick(suggest.current())
  else if (event.key === 'Escape') {
    suggest.dismiss()
    event.stopPropagation() // closes the list only, not the thread panel around it
  } else return false
  event.preventDefault()
  return true
}

// Backspace right after a chip takes the whole chip, so a name is never left half deleted.
function chipKey(event) {
  const el = box.value
  if (event.key !== 'Backspace' || !el || el.selectionStart !== el.selectionEnd) return false
  const hit = spans(props.modelValue, props.marks).find((s) => s.end === el.selectionStart)
  if (!hit) return false
  event.preventDefault()
  emit('update:modelValue', props.modelValue.slice(0, hit.start) + props.modelValue.slice(hit.end))
  nextTick(() => el.setSelectionRange(hit.start, hit.start))
  return true
}

function onKey(event) {
  if (listKey(event) || chipKey(event)) return
  if (props.editing && event.key === 'Escape') { // Esc ends an edit, and only that (not the panel around it)
    event.stopPropagation()
    emit('cancel')
    return
  }
  if (composerKey(event, { touch: isTouchPhone() }) !== 'send') return
  event.preventDefault()
  submit()
}

function pick(option) {
  const el = box.value
  const done = suggest.pick(option, props.modelValue, el.selectionStart, props.marks)
  if (!done) return
  emit('update:marks', done.marks)
  emit('update:modelValue', done.text)
  nextTick(() => {
    el.focus({ preventScroll: true })
    el.setSelectionRange(done.caret, done.caret)
  })
}

// The chips sit behind the text: they scroll with it and keep its width when the box shows a scroll bar.
function syncMirror() {
  const el = box.value
  if (!el || !mirror.value) return
  gutter.value = el.offsetWidth - el.clientWidth
  mirror.value.scrollTop = el.scrollTop
}

// A message has text, or ready files and nothing still uploading (P3-65): a file's name is never sent as its text.
// A file being checked or refused keeps Send off (P3-75), and TrayList says why.
// P3-67: a voice note is a message by itself (its caption is the text): Send waits while it records or goes to the server.
const ready = computed(() => props.editing ? props.saveable && !props.busy : !props.busy && !props.tray?.busy && !props.tray?.blocked && !props.voice?.busy
  && Boolean(props.modelValue.trim() || props.tray?.ids().length || props.voice?.payload()))
const canAttach = computed(() => Boolean(props.tray) && !props.voice?.active && props.actions.some((a) => a.part === 'attachments'))
const dragging = ref(false)

function submit() {
  if (!ready.value) return
  emit('send')
}

// Paste and drag-and-drop add files where the thread offers attach (§3.2).
function paste(event) {
  const files = [...(event.clipboardData?.files || [])]
  if (!canAttach.value || !files.length) return
  event.preventDefault()
  props.tray.add(files, { shrink: isTouchPhone() })
}

function drag(event) {
  if (!canAttach.value || ![...(event.dataTransfer?.types || [])].includes('Files')) return
  event.preventDefault()
  dragging.value = true
}

function drop(event) {
  dragging.value = false
  const files = [...(event.dataTransfer?.files || [])]
  if (!canAttach.value || !files.length) return
  event.preventDefault()
  props.tray.add(files)
}

watch(() => props.modelValue, () => nextTick(() => { fitComposer(box.value); syncMirror() }))
watch(box, (el) => { fitComposer(el); syncMirror() })
onMounted(syncMirror)
defineExpose({ focus: (opts) => focusComposer(box.value, opts) })
</script>
