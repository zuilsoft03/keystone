<template>
  <!-- P3-19 (D-196): a new invitation link, shown once. Copy, the phone's own share sheet, chat apps (the message
       encoded as one parameter), a QR code as an image. Built from the design's Settings card and tokens. -->
  <div class="flex flex-col gap-3" data-testid="share-panel">
    <p class="m-0 text-sm text-ink-gray-8">This link is shown once. Copy or share it now; you can make a new one later.</p>
    <div class="flex gap-2">
      <input :value="share.link" readonly class="form-input min-w-0 flex-1 text-sm" aria-label="Invitation link" data-testid="share-link" @focus="$event.target.select()" />
      <Button variant="solid" theme="blue" :label="copied ? 'Copied' : 'Copy'" icon-left="lucide-copy" data-testid="share-copy" @click="copy" />
    </div>
    <div class="flex flex-wrap gap-2">
      <Button v-if="canShare" variant="outline" label="Share…" icon-left="lucide-share-2" data-testid="share-native" @click="nativeShare" />
      <a v-for="app in apps" :key="app.key" :href="app.href" target="_blank" rel="noopener noreferrer"
        class="inline-flex h-7 items-center gap-1.5 rounded border border-outline-gray-2 px-2.5 text-base text-ink-gray-8 hover:bg-surface-gray-2"
        :data-testid="`share-${app.key}`">{{ app.label }}</a>
    </div>
    <div class="flex items-center gap-3 rounded-4 border border-outline-gray-1 p-3">
      <img :src="share.qr" alt="QR code of the invitation link" class="size-28 flex-none rounded" data-testid="share-qr" />
      <p class="m-0 text-sm text-ink-gray-8">Show this on your phone; the person scans it with their camera.</p>
    </div>
    <p v-if="share.bound" class="m-0 text-sm text-ink-gray-8" data-testid="share-mail">
      {{ share.emailed ? `Emailed to ${email}. The link in that email opens without a code.` : `Not emailed to ${email}.` }}
      This copied link asks for a code sent to their email.
    </p>
    <p v-else class="m-0 text-sm text-ink-gray-8">Anyone with this link can ask to join for 3 days. Each person proves their email, then waits for a manager to approve them.</p>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Button } from 'frappe-ui'
import { shareLinks } from '../invites.js'

const props = defineProps({ share: Object, email: String, company: String })
const copied = ref(false)
const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'
const links = computed(() => shareLinks(props.share.link, props.company))
const apps = computed(() => [
  { key: 'whatsapp', label: 'WhatsApp', href: links.value.whatsapp },
  { key: 'viber', label: 'Viber', href: links.value.viber },
  { key: 'messenger', label: 'Messenger', href: links.value.messenger },
])

async function copy() {
  try {
    await navigator.clipboard.writeText(props.share.link)
    copied.value = true
  } catch {
    copied.value = false // no clipboard here: the field is selected for a manual copy
  }
}

async function nativeShare() {
  try {
    await navigator.share({ title: 'Your project invitation', text: links.value.text })
  } catch {
    // cancelled
  }
}
</script>
