<template>
  <!-- P3-78 (approvals design §3.7, M11), drawn to the canvas "Dispute page" in P3-79 (ApprovalDecidePhone): the firm's brand
       leads on a card and the product is the small credit, as the mailbox's confirm page. The token stays in the link's
       fragment; the page posts it to read what was answered (nothing is recorded) and, on the button, to dispute it once. -->
  <div class="flex min-h-screen justify-center bg-surface-gray-1 px-4 py-6 max-md:px-3.5" data-testid="dispute-app">
    <main class="flex w-full max-w-[420px] flex-col gap-3.5">
      <h1 class="m-0 text-lg-semibold text-ink-gray-9" data-testid="dispute-title">Was this you?</h1>

      <div class="flex flex-col gap-3.5 rounded-6 border border-outline-gray-2 bg-surface-base p-[22px] max-md:p-4">
        <div class="flex min-w-0" data-testid="dispute-brand">
          <BrandMark :size="30" />
        </div>

        <h2 class="m-0 text-lg-semibold text-ink-gray-9" data-testid="dispute-heading">{{ heading }}</h2>
        <p role="status" class="m-0 break-words rounded-4 bg-surface-gray-1 px-3 py-2.5 text-base text-ink-gray-9" data-testid="dispute-text">{{ page.summary || 'Checking the link…' }}</p>
        <p v-if="page.next" class="m-0 text-base text-ink-gray-8" data-testid="dispute-next">{{ page.next }}</p>

        <button v-if="page.phase === 'ready'" type="button" :disabled="page.busy" data-testid="dispute-confirm" @click="confirm"
          class="h-12 w-full rounded-5 bg-surface-blue-7 px-4 text-base font-semibold text-white hover:bg-surface-blue-8 disabled:cursor-not-allowed disabled:bg-surface-gray-3 disabled:text-ink-gray-7">Yes, this was not me</button>

        <footer v-if="boot.credit" class="flex justify-center border-t border-outline-gray-1 pt-3.5" data-testid="dispute-credit">
          <PoweredBy />
        </footer>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { boot } from '../boot.js'
import BrandMark from '../components/BrandMark.vue'
import PoweredBy from '../components/PoweredBy.vue'
import { createPage, tokenOf } from './page.js'

const { page, load, confirm } = createPage({ token: tokenOf(window.location.hash), csrf: window.csrf_token || '' })
// "Did you not approve this?" in the frame; an answer may also be a return, so the page asks about the answer.
const heading = computed(() => ({ done: 'Thank you', broken: 'This link does not work' })[page.phase] || 'Did you not give this answer?')
onMounted(load)
</script>
