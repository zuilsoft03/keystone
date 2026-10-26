<template>
  <!-- P3-34 (D-273, D-274): the renders a manager marked, behind LoginB: one picture, or a slideshow that crossfades every
       7 seconds with a pause button (WCAG 2.2.2) and stays still for reduced motion. A picture that no longer loads (it
       was unmarked) is skipped; when none load, the night-city picture comes back. The caption chip shows only a
       caption the manager typed, as the design's render tag. When none is marked, the firm's default picture (P3-45) is the one picture. -->
  <!-- P3-38 (D-283): on a wide screen the picture fills the right two thirds, centred there, and fades in from the
       left; the left third, where the sign-in card sits, shows the same picture blurred and dark. A phone shows it whole. -->
  <div class="pointer-events-none absolute inset-0 overflow-hidden" data-testid="login-pictures" :data-count="shown.length">
    <img v-if="shown[at]" :key="`back-${shown[at].id}`" :src="src(shown[at])" alt="" aria-hidden="true"
      class="absolute inset-0 hidden size-full scale-110 object-cover blur-2xl brightness-[.45] lg:block" />
    <img v-for="(p, i) in shown" v-show="i === at || i === next" :key="p.id" :src="src(p)" alt="" aria-hidden="true"
      class="lb-photo absolute inset-y-0 right-0 h-full w-full object-cover transition-opacity duration-1000 ease-in-out motion-reduce:transition-none lg:w-2/3"
      :class="i === at ? 'opacity-100' : 'opacity-0'" :loading="i === at ? 'eager' : 'lazy'" data-testid="login-picture"
      @error="drop(p)" />
  </div>
  <div v-if="shown.length && (caption || shown.length > 1)" class="absolute bottom-4 right-4 z-[2] flex items-center gap-2">
    <span v-if="caption" class="inline-flex max-w-[60vw] items-center gap-1.5 truncate rounded-full px-2.5 py-1 text-[11px] backdrop-blur"
      style="border: 1px solid rgba(255, 255, 255, 0.14); background: rgba(8, 16, 28, 0.6); color: rgba(255, 255, 255, 0.88)" data-testid="login-caption">
      <span class="lucide-image size-3 flex-none" aria-hidden="true" />{{ caption }}
    </span>
    <button v-if="shown.length > 1" type="button" class="grid size-7 place-items-center rounded-full backdrop-blur"
      style="border: 1px solid rgba(255, 255, 255, 0.16); background: rgba(8, 16, 28, 0.6); color: rgba(255, 255, 255, 0.9)"
      :aria-label="playing ? 'Pause the slideshow' : 'Play the slideshow'" :aria-pressed="!playing" data-testid="login-slideshow-toggle" @click="toggle">
      <span :class="[playing ? 'lucide-pause' : 'lucide-play', 'size-3.5']" aria-hidden="true" />
    </button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { pictureUrl } from './flow.js'

const props = defineProps({ pictures: { type: Array, default: () => [] } })
const emit = defineEmits(['empty'])
const STEP = 7000
const failed = ref(new Set())
const shown = computed(() => props.pictures.filter((p) => !failed.value.has(p.id)))
const at = ref(0)
const next = computed(() => (shown.value.length > 1 ? (at.value + 1) % shown.value.length : -1))
const caption = computed(() => (shown.value[at.value] && shown.value[at.value].caption) || '')
const reduced = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
const playing = ref(!reduced)
let timer = null

// the firm's default picture (P3-45) is a path on this site, not a marked render
const src = (p) => p.url || pictureUrl(p.id)

function drop(p) {
  failed.value = new Set([...failed.value, p.id])
  if (at.value >= shown.value.length) at.value = 0
  if (!shown.value.length) emit('empty')
}

function toggle() {
  playing.value = !playing.value
}

onMounted(() => {
  timer = setInterval(() => {
    if (playing.value && shown.value.length > 1 && !document.hidden) at.value = (at.value + 1) % shown.value.length
  }, STEP)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<style>
@media (min-width: 1024px) {
  .lb-photo { -webkit-mask-image: linear-gradient(to right, transparent, black 22%); mask-image: linear-gradient(to right, transparent, black 22%); }
}
</style>
