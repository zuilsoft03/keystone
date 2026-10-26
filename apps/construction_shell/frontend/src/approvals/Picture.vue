<template>
  <span class="relative block overflow-hidden bg-surface-gray-2" :class="box" data-testid="approval-picture">
    <img v-if="ready" :src="book.src(id)" :alt="alt" class="size-full object-cover" loading="lazy" @error="failed = true" />
    <span v-else class="grid size-full place-items-center text-ink-gray-5" aria-hidden="true"><span :class="icon" class="size-6" /></span>
  </span>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { previewable } from '../previews.js'
import { book } from './pictures.js'

// A frozen copy's picture (approvals design §4.3): the "approval copy" preview of the request's own frozen file, through
// the request's read rule. Never the file endpoint: opening that writes an "opened" event into the evidence chain, which
// only the person's own Open does. One book (pictures.js) serves every picture; a picture not made yet is asked again
// a few times by the book, and the icon stays until it is ready.
const props = defineProps({
  request: { type: String, required: true },
  fileKey: { type: String, required: true },
  name: { type: String, default: '' }, // the frozen file's name: the preview only reads types the renderer knows
  alt: { type: String, default: '' },
  box: { type: String, default: 'h-[120px] w-full' },
  icon: { type: String, default: 'lucide-image' },
})
const id = computed(() => `${props.request}:${props.fileKey}`)
const failed = ref(false)
const ready = computed(() => !failed.value && book.of(id.value)?.state === 'ready')
onMounted(() => previewable(props.name) && book.want([{ id: id.value }]))
</script>
