<template>
  <!-- P3-26, P3-34 (D-264, D-265, D-273): the design's LoginB frame for clients at /portal/login, read live (canvas
       1791955581-f999): the sign-in card over the render, the brand above it, a note strip below it, and the theme switch.
       The render is a manager's marked pictures (Pictures), else the night-city picture; the card follows the theme. -->
  <div class="relative min-h-screen overflow-hidden" style="background: oklch(0.14 0.02 255)" data-testid="login-app" data-look="client">
    <Pictures v-if="pictures.length" :pictures="pictures" @empty="pictures = []" />
    <img v-else :src="city" alt="" aria-hidden="true" class="pointer-events-none absolute inset-0 size-full object-cover" data-testid="login-city" />
    <!-- A phone keeps the design's full shading, so white text stays readable over a bright photo; a wide screen with a
         photo shades only the card's side and the foot (P3-38, D-283). -->
    <div aria-hidden="true" class="pointer-events-none absolute inset-0" :class="pictures.length ? 'lg:hidden' : ''" :style="{ background: SHADE }" />
    <div v-if="pictures.length" aria-hidden="true" class="pointer-events-none absolute inset-0 hidden lg:block" :style="{ background: SHADE_PHOTO }" />

    <!-- P3-38 (D-283): on a wide screen the card sits in the middle of the page's first third -->
    <main class="lb-edge relative z-[1] flex min-h-screen flex-col justify-center pb-[88px] pt-14">
      <div class="w-full max-w-[400px]">
        <div class="mb-5" data-testid="login-brand">
          <BrandMark on-dark :size="40" />
        </div>

        <section aria-label="Sign in" class="overflow-hidden rounded-7 border border-outline-gray-2 bg-surface-elevation-1" style="box-shadow: var(--elevation-xl), 0 32px 80px -24px rgba(0, 0, 0, 0.7)">
          <div class="px-7 pb-6 pt-7 max-sm:px-5">
            <Steps :s="s" look="client" :company="company" :help="help" />
          </div>
          <div v-if="foot" class="flex items-start gap-2 border-t border-outline-gray-2 bg-surface-gray-1 px-7 py-3 text-[13px] leading-[1.4] text-ink-gray-7 max-sm:px-5" data-testid="login-foot">
            <span class="lucide-info mt-px size-4 flex-none" aria-hidden="true" />{{ foot }}
          </div>
        </section>
      </div>
    </main>

    <div role="group" aria-label="Color theme" class="lb-on-dark absolute right-4 top-4 z-[2] flex gap-0.5 rounded-full p-[3px] backdrop-blur" style="border: 1px solid rgba(255, 255, 255, 0.16); background: rgba(8, 16, 28, 0.55)">
      <button v-for="t in THEMES" :key="t.value" type="button" class="grid size-7 place-items-center rounded-full" :aria-label="t.label" :aria-pressed="t.dark === dark"
        :style="t.dark === dark ? { background: 'rgba(255, 255, 255, 0.92)', color: 'oklch(0.2 0.03 255)' } : { color: 'rgba(255, 255, 255, 0.88)' }" @click="setColorScheme(t.value)">
        <span :class="[t.icon, 'size-4']" aria-hidden="true" />
      </button>
    </div>

    <footer class="lb-on-dark lb-edge absolute inset-x-0 bottom-0 z-[1] pb-[18px] text-xs" :style="{ color: 'rgba(255, 255, 255, 0.82)' }">
      © {{ year }} {{ brand.name }}<template v-if="help"> · Help: <a class="text-white underline underline-offset-2" :href="`mailto:${help}`">{{ help }}</a></template>
      <div class="mt-1.5"><PoweredBy on-dark /></div>
    </footer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useColorScheme } from 'frappe-ui'
import BrandMark, { brandOf } from '../components/BrandMark.vue'
import PoweredBy from '../components/PoweredBy.vue'
import Pictures from './Pictures.vue'
import { bootLook } from '../brand.js'
import Steps from './Steps.vue'
import city from './city.svg'

const props = defineProps({
  s: { type: Object, required: true },
  company: { type: String, default: '' },
  help: { type: String, default: '' },
})
// P3-34 (D-273): the renders a manager marked, from the boot; none marked, the night-city picture.
const marked = Array.isArray((window.cc_boot || {}).pictures) ? window.cc_boot.pictures.slice(0, 12) : []
// no render marked: the firm's default sign-in picture (P3-45), else the night-city picture
const fallback = bootLook(window.cc_boot).picture
const pictures = ref(marked.length || !fallback ? marked : [{ id: 'default', url: fallback, caption: '' }])
// The design's shading, which keeps the card's side of the picture dark enough for white text.
const SHADE = 'linear-gradient(90deg, rgba(5,10,20,0.92) 0%, rgba(5,10,20,0.84) 34%, rgba(5,10,20,0.5) 56%, rgba(5,10,20,0.18) 74%, rgba(5,10,20,0.1) 100%), linear-gradient(0deg, rgba(5,10,20,0.9) 0%, rgba(5,10,20,0) 20%), linear-gradient(180deg, rgba(5,10,20,0.55) 0%, rgba(5,10,20,0) 22%)'
// Over a manager's photo, which fills the right two thirds on a wide screen, only the card's side and the foot are shaded.
const SHADE_PHOTO = 'linear-gradient(90deg, rgba(5,10,20,0.55) 0%, rgba(5,10,20,0.3) 30%, rgba(5,10,20,0) 42%), linear-gradient(0deg, rgba(5,10,20,0.85) 0%, rgba(5,10,20,0) 18%), linear-gradient(180deg, rgba(5,10,20,0.45) 0%, rgba(5,10,20,0) 18%)'
const THEMES = [
  { value: 'light', dark: false, label: 'Light theme', icon: 'lucide-sun' },
  { value: 'dark', dark: true, label: 'Dark theme', icon: 'lucide-moon' },
]
// The note strip under the card, as the design words it for each step (the steps carry the rest).
const FOOT = {
  signin: 'New client? Your project team sends you an invite by email.',
  setpw: 'After this step, you go to your project portal.',
}
const foot = computed(() => (props.s.step.value === 'setpw' && !props.s.key ? '' : FOOT[props.s.step.value] || ''))
const brand = brandOf(window.cc_boot)
const year = new Date().getFullYear()
const { resolvedColorScheme, setColorScheme } = useColorScheme()
const dark = computed(() => resolvedColorScheme.value === 'dark')
</script>

<style>
.lb-on-dark :focus-visible { outline: 2px solid white; outline-offset: 1px; }
/* The card's left edge: the design's, then from 1024 px the middle of the first third (P3-38, D-283). The card is
   400 px wide, so it is centred in a third of the width, never closer than 24 px to the edge. */
.lb-edge { padding-left: max(16px, calc(50% - 360px)); padding-right: 16px; }
@media (min-width: 1024px) { .lb-edge { padding-left: max(24px, calc((100% / 3 - 400px) / 2)); } }
</style>
