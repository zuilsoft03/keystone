<template>
  <Dialog :open="true" size="xl" :show-close-button="false" @update:open="(v) => !v && $emit('close')">
    <template #title>
      <div class="pr-10 max-md:pr-14">
        <div class="text-2xl-semibold leading-6 text-ink-gray-8" data-testid="approval-sheet-title">{{ head.title }}</div>
        <div v-if="head.subtitle" class="mt-1 text-xs font-normal text-ink-gray-7" data-testid="approval-sheet-subtitle">{{ head.subtitle }}</div>
      </div>
    </template>
    <!-- B9: the frame's Close at the head's right, 48 px on a phone. It sits outside the title (so the dialog's name stays the
         title) and is placed against the dialog itself, which is the nearest positioned box. -->
    <Button variant="ghost" icon="lucide-x" :aria-label="w('close')" class="absolute right-3 top-3 max-md:!size-12" data-testid="approval-sheet-close" @click="$emit('close')" />
    <p v-if="error && !sheet" class="m-0 text-sm text-ink-red-7" role="alert" data-testid="approval-sheet-error">{{ error }}</p>
    <p v-else-if="!sheet" class="m-0 text-sm text-ink-gray-7">{{ w('loading') }}</p>
    <SheetView v-else v-model:option="option" v-model:step="step" :sheet="shown" :w="w" :can-message="canMessage" @close="$emit('close')" @message="$emit('message')">
      <template #notice>
        <p v-if="error" role="alert" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2.5 text-base text-ink-red-8" data-testid="approval-sheet-error">{{ error }}</p>
        <p v-if="answer.notice" role="status" class="m-0 rounded-4 bg-surface-green-1 px-3 py-2.5 text-base text-ink-green-8" data-testid="approval-notice">{{ answer.notice }}</p>
      </template>
      <template v-if="!preview" #flow="p">
        <AnswerFlow :sheet="p.sheet" :option="p.option" :step="p.step" :state="answer" :w="w" :can-message="canMessage"
          @step="p.setStep" @close="$emit('close')" @message="$emit('message')" @reload="load" />
      </template>
    </SheetView>
  </Dialog>
</template>

<script setup>
import { computed, inject, onUnmounted, reactive, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { useMode } from '../mode.js'
import { HOST_KEY } from '../chat/host.js'
import { onEvent } from '../realtime.js'
import AnswerFlow from './AnswerFlow.vue'
import SheetView from './SheetView.vue'
import { answerFor, keepDraft, useSheet } from './flow.js'
import { sheetHead } from './terms.js'
import { approvalWords } from './words.js'

// The approval sheet for one request (approvals design §3.5; ApprovalDecide): reads approvals.answer.sheet as the client
// may, and draws it in a dialog (SheetView) with the answering flow in its #flow place (AnswerFlow) and notes in #notice.
// On a phone the dialog is as wide as the screen and every target is 48 px; the actions scroll with the terms (the
// frame's page with Back and sticky actions is not built). A `cc_approval_changed` event for this request reads the
// sheet again and replaces it in place; the flow's state (`answer`) is this sheet's, so a typed name, a drawing or a
// reason stays, and a failed reload keeps the sheet on screen.
//   Closing (the X, a tap outside, Escape, Back) keeps the typed name, the drawing and the reason (flow.keepDraft); the
//   password is never kept.
//   The picked option (v-model:option) and the step (v-model:step) live here; the page's address opens a sheet with
//   them (?tab=approvals&request=<name>&option=<key>&step=review|return, terms.approvalLink).
const props = defineProps({
  request: { type: String, required: true },
  option: { type: String, default: '' }, // a Decision's option picked on the card
  step: { type: String, default: '' },
  canMessage: Boolean,
})
defineEmits(['close', 'message'])
const mode = useMode()
const w = approvalWords(mode)
// T31 (design §6): the staff preview of the portal (ClientView) provides a read-only chat host. There the sheet is shown as a
// reader's: it never says the viewer can answer, mounts no answering flow (so no agree, password or decide call can be made),
// and ignores the step in the address. This holds whatever the server sends.
const preview = Boolean(inject(HOST_KEY, null)?.readOnly)
const { sheet, error, load } = useSheet(() => props.request, w)
const shown = computed(() => (preview && sheet.value ? { ...sheet.value, can_answer: false } : sheet.value))
const answer = reactive(answerFor(props.request)) // a sheet closed with a draft gets it back when it opens again (B9)
const option = ref(preview ? '' : props.option)
const step = ref(preview ? '' : props.step)
const head = computed(() => (sheet.value ? sheetHead(sheet.value, w, mode.value) : { title: '', subtitle: '' }))

watch(() => props.request, load, { immediate: true })
const off = preview ? () => {} : onEvent('cc_approval_changed', (m) => m?.request === props.request && load()) // the preview takes no live events
onUnmounted(() => {
  off()
  keepDraft(props.request, answer)
})
</script>
