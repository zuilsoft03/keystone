<template>
  <!-- P3-44 (D-402, D-404, R-30): the small credit that names the product once a firm's name leads. It shows at the foot of
       the sign-in and join pages, in the portal's footer and in the staff account menu. The server's flag (the boot's
       credit) decides, and it follows the firm's name alone: no setting hides it. The mark is the one asset
       (public/logo.svg), its dark tone on a ground that is always dark. -->
  <span v-if="shown.credit" class="inline-flex items-center gap-1.5 text-[11px] leading-none" :class="onDark ? 'text-white/70' : 'text-ink-gray-7'" data-testid="powered-by">
    <span>Powered by{{ ' ' }}</span>
    <img v-if="!onDark" :src="LOGO" alt="" class="size-3.5 flex-none dark:hidden" data-testid="powered-by-logo">
    <img :src="`${LOGO}#dark`" alt="" class="size-3.5 flex-none" :class="onDark ? '' : 'hidden dark:block'" data-testid="powered-by-logo-dark">
    <span class="font-semibold">{{ shown.product }}</span>
  </span>
</template>

<script setup>
import { boot } from '../boot.js'
import { LOGO, brandOf } from './BrandMark.vue'

defineProps({
  // A ground that is dark in both themes (the team sign-in panel, the client sign-in picture).
  onDark: { type: Boolean, default: false },
})
const shown = brandOf(boot)
</script>
