<template>
  <!-- P3-77 (approvals design §3.2 item 3): the confirm page of the evidence mailbox, built like the join page (D-196):
       the firm's brand leads and the product is the small credit. The token stays in the link's fragment, which never
       reaches the server; only the button posts it. The button goes once the link has been answered, either way. -->
  <div class="flex min-h-screen justify-center bg-surface-base px-4 py-8" data-testid="mailbox-app">
    <main class="flex w-full max-w-[420px] flex-col gap-6">
      <div class="flex min-w-0" data-testid="mailbox-brand">
        <BrandMark :size="40" />
      </div>

      <div class="flex flex-col gap-3">
        <h1 class="m-0 text-[26px] font-semibold leading-[1.25] text-ink-gray-9">Confirm the evidence mailbox</h1>
        <p id="cc-mailbox-text" role="status" class="m-0 text-[18px] leading-[1.55] text-ink-gray-8" data-testid="mailbox-text">{{ text }}</p>
      </div>

      <button v-if="!answered" type="button" :disabled="busy" data-testid="mailbox-confirm" @click="confirm"
        class="h-14 w-full rounded-5 bg-surface-blue-7 px-4 text-[18px] font-semibold text-white hover:bg-surface-blue-8 disabled:cursor-not-allowed disabled:bg-surface-gray-3 disabled:text-ink-gray-7">Confirm the mailbox</button>

      <footer v-if="boot.credit" class="mt-auto flex justify-center pt-6" data-testid="mailbox-credit">
        <PoweredBy />
      </footer>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { boot } from '../boot.js'
import BrandMark from '../components/BrandMark.vue'
import PoweredBy from '../components/PoweredBy.vue'

const text = ref('This mailbox receives the records of client approvals. Confirm it if you expected this message.')
const busy = ref(false)
const answered = ref(false)

async function confirm() {
  busy.value = true
  const token = new URLSearchParams(window.location.hash.slice(1)).get('k') || ''
  const response = await fetch('/api/method/construction_core.approvals.api.confirm_evidence_mailbox', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' },
    body: JSON.stringify({ token }),
    credentials: 'same-origin',
  }).catch(() => null)
  text.value = response && response.ok
    ? 'The evidence mailbox is confirmed. You can close this page.'
    : 'This link does not work. Ask for a new test message.'
  answered.value = true
}
</script>
