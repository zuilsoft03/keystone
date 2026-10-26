<template>
  <!-- P3-44 (D-298, D-401…D-404, R-30; docs/design/brand.md): who leads where users look. Until a firm's name is set
       (cc_company_name, D-210) Keystone leads: mark B and the wordmark, with no credit line. Once it is set the firm's
       name leads, on its logo (P3-45) or, until it has one, a tile with its initial (D-403), and Keystone shows only as
       the small "Powered by" credit (PoweredBy.vue). The mark is the one asset (public/logo.svg): its light tone, and in
       the dark theme or on a ground that is always dark (onDark) its dark tone, so no colour of the brand is written in
       this file. -->
  <span class="inline-flex min-w-0 items-center gap-3" :data-leads="firm ? 'firm' : 'product'" data-testid="brand-mark">
    <template v-if="firm">
      <img v-if="logo" :src="logo" :alt="name" class="flex-none object-contain" :style="logoBox" data-testid="brand-firm-logo">
      <span v-else class="grid flex-none place-items-center rounded-4 bg-surface-blue-6 font-semibold text-white" :style="tile" aria-hidden="true" data-testid="brand-initial">{{ initial }}</span>
      <span class="cw-brand-font min-w-0 truncate font-semibold leading-tight" :class="[big ? 'text-[20px]' : 'text-[17px]', onDark ? 'text-white' : 'text-ink-gray-9']" data-testid="brand-name">{{ name }}</span>
    </template>
    <template v-else>
      <img v-if="!onDark" :src="LIGHT" alt="" class="flex-none dark:hidden" :style="box" data-testid="brand-logo">
      <img :src="DARK" alt="" class="flex-none" :class="onDark ? '' : 'hidden dark:block'" :style="box" data-testid="brand-logo-dark">
      <span class="cw-wordmark whitespace-nowrap" :class="[big ? 'text-[20px]' : 'text-[18px]', onDark ? 'text-white' : 'text-ink-gray-9']" data-testid="brand-name">{{ name }}</span>
    </template>
  </span>
</template>

<script>
import { boot } from '../boot.js'
import { applyLook, looksOf, pathOf } from '../brand.js'

// Every app entry (workspace, portal, sign-in, join) draws a BrandMark, so the firm's colours and heading font are set once
// here, from the boot, before the first paint (P3-45, D-300). A boot without a brand leaves the design system's.
const look = looksOf(boot.brand)
if (typeof document !== 'undefined') applyLook(look)

// The only place the product's default name is written in the app (with the credit's, which reads the same function): a
// page whose boot has no product_name (the shell's presenters always send one) still shows it. P3-45's Brand page
// replaces the server's default, never this fallback.
export const FALLBACK_PRODUCT = 'Keystone'

// The brand's files, served from the shell's public folder (the mark in both tones, and the app icon: the dark tone on Ink).
export const LOGO = '/assets/construction_shell/logo.svg'
export const APP_ICON = '/assets/construction_shell/icon-192.png'

/**
 * What a page shows as its brand, from its boot payload: the product's name, the company's ("" until it is set), the name
 * that leads (the server's brand_name, else the company's, else the product's), whether a firm leads, and whether the
 * "Powered by" credit shows (the server's flag: it follows the firm's name and nothing a firm can set turns it off).
 */
export function brandOf(source) {
  const named = (value) => (typeof value === 'string' ? value.trim() : '')
  const product = named(source?.product_name) || FALLBACK_PRODUCT
  const company = named(source?.company)
  return { product, company, name: named(source?.brand_name) || company || product, firm: company !== '', credit: source?.credit === true }
}

/** The letter on the tile that stands in for a firm's logo: its first character, capitalised. */
export function initialOf(name) {
  return Array.from(typeof name === 'string' ? name.trim() : '')[0]?.toUpperCase() || ''
}
</script>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // A ground that is dark in both themes (the team sign-in panel, the client sign-in picture): the dark tone, white text.
  onDark: { type: Boolean, default: false },
  // The mark's or tile's side in px: 32 in the bar, larger where the brand leads a page.
  size: { type: Number, default: 32 },
  // The join page learns the company from its link, so it may pass a newer one than the boot's.
  companyName: { type: String, default: '' },
  // The firm's logo (P3-45): null reads the boot's; the Brand page's preview passes the draft's ("" draws the tile).
  logoUrl: { type: String, default: null },
  // The Brand page's preview draws the draft alone: what the page itself was booted with does not lead.
  preview: { type: Boolean, default: false },
})

const LIGHT = LOGO
const DARK = `${LOGO}#dark`
const shown = brandOf(boot)
const override = computed(() => props.companyName.trim())
const firm = computed(() => override.value !== '' || (!props.preview && shown.firm))
const name = computed(() => override.value || (props.preview ? shown.product : shown.name))
const logo = computed(() => (props.logoUrl === null ? look.logo : pathOf(props.logoUrl)))
const initial = computed(() => initialOf(name.value))
const big = computed(() => props.size >= 40)
const box = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }))
const logoBox = computed(() => ({ height: `${props.size}px`, maxWidth: `${props.size * 4}px` }))
const tile = computed(() => ({ ...box.value, fontSize: `${Math.round(props.size * 0.5)}px` }))
</script>
