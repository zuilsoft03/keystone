<template>
  <!-- P3-20 (D-230, D-231): a 6-digit code in 6 boxes, as on the client join page (D-219): one digit a box, a paste or
       a phone's autofill fills them all, Backspace and the arrows move between them. -->
  <div class="flex justify-between gap-2" :data-testid="testid" @paste.prevent="onPaste($event, 0)">
    <input v-for="(d, i) in boxes" :key="i" :ref="(el) => (els[i] = el)" :value="d" :disabled="disabled"
      class="form-input h-12 w-full min-w-0 rounded-5 border-2 border-outline-gray-4 bg-surface-base p-0 text-center text-2xl font-semibold text-ink-gray-9"
      inputmode="numeric" pattern="[0-9]*" :autocomplete="i === 0 ? 'one-time-code' : 'off'"
      :aria-label="`${label}: digit ${i + 1} of 6`" :data-testid="`${testid}-${i}`"
      @input="onBox($event, i)" @keydown="onKey($event, i)" @paste.stop.prevent="onPaste($event, i)" @focus="$event.target.select()">
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { digitsOf, fillBoxes } from '../join/flow.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  testid: { type: String, default: 'code' },
  label: { type: String, default: 'Code' },
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue', 'complete'])
const boxes = ref(['', '', '', '', '', ''])
const els = []

watch(() => props.modelValue, (v) => {
  if (v === boxes.value.join('')) return
  const digits = digitsOf(v)
  boxes.value = Array.from({ length: 6 }, (_, i) => digits[i] || '')
}, { immediate: true })

function focus(i) {
  nextTick(() => els[i]?.focus())
}

function set(at, text) {
  const out = fillBoxes(boxes.value, at, text)
  boxes.value = out.boxes
  const code = out.boxes.join('')
  emit('update:modelValue', code)
  focus(out.focus)
  if (code.length === 6) emit('complete', code) // the sixth digit sends it, no extra tap
}

function onBox(event, i) {
  const digits = digitsOf(event.target.value)
  event.target.value = boxes.value[i]
  set(i, digits.length > 2 ? digits : digits.slice(-1))
}

function onPaste(event, i) {
  set(i, event.clipboardData?.getData('text') || '')
}

function onKey(event, i) {
  if (event.key === 'Backspace' && !boxes.value[i] && i > 0) {
    event.preventDefault()
    boxes.value = boxes.value.map((d, j) => (j === i - 1 ? '' : d))
    emit('update:modelValue', boxes.value.join(''))
    focus(i - 1)
  } else if (event.key === 'ArrowLeft' && i > 0) focus(i - 1)
  else if (event.key === 'ArrowRight' && i < 5) focus(i + 1)
}

defineExpose({ focus: () => focus(0) })
</script>
