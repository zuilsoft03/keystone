<template>
  <span ref="root" class="relative inline-flex" @keydown.esc="escape">
    <Button v-if="iconOnly" size="sm" variant="ghost" class="max-md:!h-12 max-md:!min-w-12" :icon="icon" :title="label" :aria-label="aria || label" aria-haspopup="menu"
      :aria-expanded="open ? 'true' : 'false'" :data-testid="testid" @click="toggle" @keydown.down.prevent="show" />
    <Button v-else size="sm" variant="ghost" class="max-md:!h-12" :icon-left="icon" :label="label" :aria-label="aria || label" aria-haspopup="menu"
      :aria-expanded="open ? 'true' : 'false'" :data-testid="testid" @click="toggle" @keydown.down.prevent="show" />
    <!-- Fixed, so the list the message sits in (it scrolls) never cuts the menu off; placed under the button, or over it when
         there is no room below -->
    <div v-if="open" ref="menu" role="menu" :aria-label="aria || label" class="fixed z-30 w-56 rounded-5 border border-outline-gray-2 bg-surface-base p-1 shadow-lg"
      :style="{ top: `${at.top}px`, left: `${at.left}px`, visibility: placed ? 'visible' : 'hidden' }" :data-testid="`${testid}-menu`" @keydown="keys">
      <button v-for="(it, i) in items" :key="it.id" ref="rows" type="button" role="menuitem" tabindex="-1"
        class="flex min-h-9 w-full cursor-pointer items-center gap-2 rounded-4 border-0 bg-transparent px-2 text-left text-base text-ink-gray-9 hover:bg-surface-gray-2 focus:bg-surface-gray-2 focus:outline-none max-md:min-h-12"
        :data-testid="`${testid}-${it.id}`" :data-on="it.on ? 'true' : undefined" @click="pick(it)" @mousemove="cursor = i">
        <span v-if="it.glyph" class="w-5 flex-none text-center" aria-hidden="true">{{ it.glyph }}</span>
        <span v-else-if="it.icon" class="size-4 flex-none text-ink-gray-7" :class="it.icon" aria-hidden="true" />
        <span class="min-w-0 flex-1 truncate">{{ it.label }}</span>
      </button>
    </div>
  </span>
</template>

<script setup>
import { nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Button } from 'frappe-ui'

// A small menu button for the message toolbar (React, More). Keys: Down opens it on the first entry; Up, Down, Home and End
// move; Enter or Space picks; Esc closes it and gives the focus back to the button; Tab leaves and closes it. A click
// outside closes it. A scroll of the list behind it moves the menu with its button.
const props = defineProps({
  label: { type: String, required: true },
  aria: { type: String, default: '' },
  icon: { type: String, default: '' },
  iconOnly: Boolean,
  items: { type: Array, required: true }, // [{ id, label, icon?, glyph?, on? }]
  testid: { type: String, default: 'menu' },
  end: { type: Boolean, default: true }, // the menu's right edge lines up with its button's (on a phone, the left edges)
})
const emit = defineEmits(['pick'])
const GAP = 4
const EDGE = 8
const WIDTH = 224 // w-56
const open = ref(false)
const placed = ref(false)
const cursor = ref(0)
const at = reactive({ top: 0, left: 0 })
const root = ref(null)
const menu = ref(null)
const rows = ref([])

function toggle() {
  if (open.value) close(false)
  else show()
}

async function show() {
  open.value = true
  placed.value = false
  cursor.value = 0
  await nextTick()
  place()
  placed.value = true
  await nextTick() // a hidden menu cannot take the focus
  rows.value[0]?.focus({ preventScroll: true })
}

// Under the button, or over it when the bottom of the screen is too near and the top has the room; always inside the screen.
function place() {
  const button = root.value?.querySelector('button')?.getBoundingClientRect()
  const height = menu.value?.offsetHeight || 0
  if (!button) return
  const phone = window.innerWidth < 768
  const left = props.end && !phone ? button.right - WIDTH : button.left
  at.left = Math.max(EDGE, Math.min(left, window.innerWidth - WIDTH - EDGE))
  const below = button.bottom + GAP
  const above = button.top - GAP - height
  at.top = below + height > window.innerHeight - EDGE && above > EDGE ? above : Math.max(EDGE, Math.min(below, window.innerHeight - height - EDGE))
}

function close(back) {
  if (!open.value) return
  open.value = false
  if (back) root.value?.querySelector('button')?.focus()
}

function escape(event) {
  if (!open.value) return // Esc with no menu open belongs to the panel around
  event.stopPropagation()
  close(true)
}

function pick(item) {
  close(true)
  emit('pick', item)
}

function keys(event) {
  const last = props.items.length - 1
  const move = { ArrowDown: cursor.value + 1, ArrowUp: cursor.value - 1, Home: 0, End: last }[event.key]
  if (move !== undefined) {
    event.preventDefault()
    cursor.value = (move + last + 1) % (last + 1)
    rows.value[cursor.value]?.focus({ preventScroll: true })
  } else if (event.key === 'Tab') close(false)
}

function outside(event) {
  if (root.value && !root.value.contains(event.target)) close(false)
}

watch(open, (now) => {
  const act = now ? 'addEventListener' : 'removeEventListener'
  document[act]('pointerdown', outside)
  window[act]('scroll', place, true)
  window[act]('resize', place)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside)
  window.removeEventListener('scroll', place, true)
  window.removeEventListener('resize', place)
})
</script>
