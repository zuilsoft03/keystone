<template>
  <!-- P3-24 (D-250, D-251): the design's LoginA frame for the team at /login: the brand panel beside the form. -->
  <div class="flex min-h-screen flex-wrap bg-surface-base" data-testid="login-app" data-look="team">
    <section aria-label="About this workspace" class="relative flex min-h-[560px] flex-[55_1_550px] flex-col overflow-hidden px-14 pb-[52px] pt-10 text-white max-sm:min-h-[560px] max-sm:px-14"
      :style="{ background: `var(--brand-panel, ${dark ? 'oklch(0.165 0 0)' : 'oklch(0.205 0 0)'})`, boxShadow: dark ? 'inset -1px 0 0 rgba(255,255,255,0.08)' : 'none' }">
      <svg aria-hidden="true" viewBox="0 0 792 960" preserveAspectRatio="xMaxYMin slice" class="absolute inset-0 size-full">
        <defs>
          <pattern id="lg-tiles" width="34" height="34" patternUnits="userSpaceOnUse"><rect x="3" y="3" width="28" height="28" rx="7" style="fill: oklch(0.439 0 0)" /></pattern>
          <radialGradient id="lg-fade" gradientUnits="userSpaceOnUse" cx="640" cy="230" r="680">
            <stop offset="0" style="stop-color: white; stop-opacity: 0.78" /><stop offset="0.36" style="stop-color: white; stop-opacity: 0.3" /><stop offset="0.7" style="stop-color: white; stop-opacity: 0" />
          </radialGradient>
          <mask id="lg-mask"><rect width="792" height="960" fill="url(#lg-fade)" /></mask>
          <radialGradient id="lg-glow" gradientUnits="userSpaceOnUse" cx="612" cy="204" r="300">
            <stop offset="0" style="stop-color: var(--surface-blue-6); stop-opacity: 0.26" /><stop offset="1" style="stop-color: var(--surface-blue-6); stop-opacity: 0" />
          </radialGradient>
        </defs>
        <rect width="792" height="960" fill="url(#lg-glow)" />
        <rect width="792" height="960" fill="url(#lg-tiles)" mask="url(#lg-mask)" />
        <rect class="lg-tile" x="717" y="105" width="28" height="28" rx="7" style="fill: var(--surface-blue-6); animation-delay: 0.35s" />
        <rect class="lg-tile" x="479" y="275" width="28" height="28" rx="7" style="fill: var(--surface-green-6, var(--surface-blue-6)); animation-delay: 0.6s" />
        <rect class="lg-tile" x="683" y="309" width="28" height="28" rx="7" style="fill: var(--surface-amber-6, var(--surface-blue-6)); animation-delay: 0.85s" />
        <rect class="lg-tile" x="547" y="411" width="28" height="28" rx="7" opacity="0.55" style="fill: var(--surface-blue-6); animation-delay: 1.1s" />
        <g class="lg-tile" style="animation-delay: 0.1s">
          <image v-if="!brand.firm" :href="APP_ICON" x="581" y="173" width="62" height="62" />
          <template v-else>
            <rect x="581" y="173" width="62" height="62" rx="12" style="fill: var(--surface-blue-6)" />
            <text x="612" y="215" text-anchor="middle" font-size="30" font-weight="600" fill="white">{{ initial }}</text>
          </template>
        </g>
      </svg>
      <div class="relative" data-testid="login-brand">
        <BrandMark on-dark :size="40" />
      </div>
      <div class="relative mt-auto max-w-[400px]">
        <div class="text-[11px] font-semibold uppercase tracking-[0.08em] text-white/80" data-testid="login-kicker">{{ brand.name }}</div>
        <p class="cw-brand-font mb-0 mt-2.5 text-[26px] font-semibold leading-[1.25] text-white">The project workspace for {{ company ? `the ${company}` : 'the' }} team and its clients.</p>
        <ul class="mb-0 mt-6 flex list-none flex-wrap gap-2 p-0">
          <li v-for="c in CHIPS" :key="c.text" class="inline-flex min-h-[30px] items-center gap-2 rounded-full py-1 pl-2.5 pr-3 text-[13px] text-white/90 backdrop-blur" style="background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.14)">
            <span :class="[c.icon, 'size-3.5 flex-none']" aria-hidden="true" />{{ c.text }}
          </li>
        </ul>
      </div>
    </section>

    <main class="relative flex min-w-0 flex-[45_1_450px] flex-col bg-surface-base px-10 py-6 max-sm:px-10">
      <div class="flex justify-end">
        <div class="cw-tabbuttons" role="group" aria-label="Theme">
          <button type="button" class="cw-tabbutton" :aria-pressed="!dark" @click="setColorScheme('light')"><span class="lucide-sun size-3.5" aria-hidden="true" />Light</button>
          <button type="button" class="cw-tabbutton" :aria-pressed="dark" @click="setColorScheme('dark')"><span class="lucide-moon size-3.5" aria-hidden="true" />Dark</button>
        </div>
      </div>

      <div class="flex flex-1 items-center justify-center py-8">
        <div class="w-full max-w-[380px]">
          <Steps :s="s" look="team" :company="company" :help="help" />
        </div>
      </div>

      <footer class="flex flex-col items-center gap-2 text-xs text-ink-gray-7">
        <span>© {{ year }} {{ brand.name }}<template v-if="help"> · Help: <a class="lg-inline" :href="`mailto:${help}`">{{ help }}</a></template></span>
        <PoweredBy />
      </footer>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useColorScheme } from 'frappe-ui'
import BrandMark, { APP_ICON, brandOf, initialOf } from '../components/BrandMark.vue'
import PoweredBy from '../components/PoweredBy.vue'
import Steps from './Steps.vue'

defineProps({
  s: { type: Object, required: true },
  company: { type: String, default: '' },
  help: { type: String, default: '' },
})
const CHIPS = [
  { icon: 'lucide-layout-grid text-ink-blue-3', text: 'Projects, files and approvals in one place' },
  { icon: 'lucide-users text-ink-green-3', text: 'Clients see only what the team shares' },
  { icon: 'lucide-server text-ink-amber-3', text: 'Runs on our own server' },
]
const brand = brandOf(window.cc_boot)
const initial = initialOf(brand.name)
const year = new Date().getFullYear()
const { resolvedColorScheme, setColorScheme } = useColorScheme()
const dark = computed(() => resolvedColorScheme.value === 'dark')
</script>
