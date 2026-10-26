<template>
  <canvas ref="pad" class="block h-[150px] w-full min-w-[300px] cursor-crosshair touch-none rounded-t-5" role="img" :aria-label="label" data-testid="approval-draw"
    @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @lostpointercapture="up" />
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { paint } from './flow.js'

// The draw box (design §3.5 item 4; N4, N12): at least 300 by 120 pixels, white paper with dark ink in both themes, and
// touch-action none so a finger draws instead of scrolling the page. The strokes live in the flow's state as fractions
// of the box; the box draws them again whenever its size changes (a rotation, a resize) or they are cleared.
const props = defineProps({
  strokes: { type: Array, required: true }, // the flow's own array: drawing adds to it, Clear empties it
  label: { type: String, default: '' },
})
const emit = defineEmits(['ratio']) // the box's width over its height: the flow exports the picture in the same shape (B6)
const pad = ref(null)
let line = null

// Sized by layout (clientWidth), not by the on-screen rectangle, which a dialog's opening scale shrinks for a moment.
function redraw() {
  const c = pad.value
  if (!c) return
  const dpr = window.devicePixelRatio || 1
  c.width = Math.round(c.clientWidth * dpr)
  c.height = Math.round(c.clientHeight * dpr)
  const ctx = c.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  paint(ctx, props.strokes, c.clientWidth, c.clientHeight)
  if (c.clientWidth && c.clientHeight) emit('ratio', c.clientWidth / c.clientHeight)
}
// a pointer as fractions of the box as shown (the rectangle includes any scale, so the fraction is right either way)
function at(e) {
  const r = pad.value.getBoundingClientRect()
  return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]
}
const ink = (strokes) => paint(pad.value.getContext('2d'), strokes, pad.value.clientWidth, pad.value.clientHeight, false)
function down(e) {
  e.preventDefault()
  pad.value.setPointerCapture?.(e.pointerId)
  line = [at(e)]
  props.strokes.push(line)
  ink([line])
}
function move(e) {
  if (!line) return
  const point = at(e)
  ink([[line[line.length - 1], point]]) // only the new piece
  line.push(point)
}
const up = () => { line = null }

let watcher = null
onMounted(() => {
  redraw()
  if (typeof ResizeObserver !== 'undefined') (watcher = new ResizeObserver(redraw)).observe(pad.value)
})
onUnmounted(() => watcher?.disconnect())
watch(() => props.strokes.length, (n, was) => n < was && redraw()) // Clear
</script>
