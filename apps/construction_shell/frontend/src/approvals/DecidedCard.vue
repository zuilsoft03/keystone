<template>
  <article class="flex flex-col gap-1.5 px-4 py-3" data-testid="approval-decided" :data-request="row.name" :data-state="row.state">
    <div class="text-xs text-ink-gray-7">{{ kind }} · <span class="font-medium text-ink-gray-8">{{ row.reference }}</span></div>
    <div class="break-words text-base font-semibold text-ink-gray-9" data-testid="approval-title">{{ row.title }}</div>
    <p class="m-0 flex items-start gap-2 text-sm text-ink-gray-9" data-testid="approval-answer">
      <span class="mt-px grid size-[18px] flex-none place-items-center rounded-full" :class="look[1]" aria-hidden="true"><span :class="look[0]" class="size-3" /></span>
      <span class="min-w-0 flex-1 break-words">{{ lines.text }}</span>
    </p>
    <p v-if="lines.note" class="m-0 break-words text-sm text-ink-gray-8" data-testid="approval-note">{{ lines.note }}</p>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
      <router-link :to="approvalLink(row.name)" class="inline-flex min-h-12 items-center text-sm md:min-h-0" data-testid="approval-open">{{ w('open') }}</router-link>
      <a v-if="row.mine && !preview" :href="`/api/method/construction_core.approvals.receipts.my_copy?request=${encodeURIComponent(row.name)}`" download
        class="inline-flex min-h-12 items-center text-sm md:min-h-0" data-testid="approval-copy">{{ w('copy') }}</a>
      <button v-if="canDispute" type="button" class="inline-flex min-h-12 items-center border-0 bg-transparent p-0 text-sm text-ink-blue-link hover:text-ink-blue-7 md:min-h-0"
        :aria-expanded="String(help)" data-testid="approval-not-me" @click="help = !help">{{ w('not_me') }}</button>
    </div>
    <p v-if="help" class="m-0 rounded-4 bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8" data-testid="approval-not-me-help">{{ w('not_me_help') }}</p>
  </article>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { HOST_KEY } from '../chat/host.js'
import { useMode } from '../mode.js'
import { approvalLink, decidedLines, kindWord } from './terms.js'

// One decided request (PortalApprovals' "Decided", approvals design §3.12): the answer line, "You approved this on 18 Oct.
// The team will confirm it." for the person who gave it, Open, their own copy of the receipt, and "This was not me".
// "This was not me" works from the receipt email's single-use link (§3.7): there is no signed-in way to dispute, so the
// link here says where to find it instead of recording anything.
const props = defineProps({ row: { type: Object, required: true }, w: { type: Function, required: true } })
const preview = Boolean(inject(HOST_KEY, null)?.readOnly) // T31: the staff preview of the portal downloads no one's copy
const mode = useMode()
const help = ref(false)
const kind = computed(() => kindWord(props.row.kind, mode.value))
const lines = computed(() => decidedLines(props.row, props.w))
const canDispute = computed(() => !preview && props.row.mine && props.row.status === 'Approved' && props.row.state === 'approved') // the preview shows no answer-side control
const TONE = { approved: ['lucide-check', 'bg-surface-green-2 text-ink-green-8'], recorded: ['lucide-check', 'bg-surface-green-2 text-ink-green-8'],
  returned: ['lucide-rotate-ccw', 'bg-surface-amber-2 text-ink-amber-8'], disputed: ['lucide-circle-alert', 'bg-surface-red-2 text-ink-red-8'] }
const look = computed(() => TONE[props.row.state] || TONE.approved)
</script>
