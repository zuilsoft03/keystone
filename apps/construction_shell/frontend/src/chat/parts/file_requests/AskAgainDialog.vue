<template>
  <Dialog v-model:open="shown" :title="w('file_requests.ask_title')" :options="{ size: 'sm' }">
    <form class="flex flex-col gap-2" :data-testid="`${prefix}ask-form`" @submit.prevent="send">
      <p class="m-0 text-sm text-ink-gray-8">{{ w('file_requests.ask_body') }}</p>
      <p class="m-0 text-sm font-medium text-ink-gray-9">{{ name }}</p>
      <label class="text-sm font-medium text-ink-gray-9" :for="`${prefix}ask-reason`">{{ w('file_requests.ask_label') }}</label>
      <textarea :id="`${prefix}ask-reason`" ref="box" v-model="reason" rows="3" :maxlength="MAX_REASON" class="form-textarea w-full text-base"
        :placeholder="w('file_requests.ask_ph')" :data-testid="`${prefix}ask-reason`" />
      <p v-if="problem" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" :data-testid="`${prefix}ask-problem`">{{ problem }}</p>
    </form>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button class="max-md:!h-12" :label="w('file_requests.cancel_builder')" :disabled="busy" :data-testid="`${prefix}ask-cancel`" @click="shown = false" />
        <Button class="max-md:!h-12" variant="solid" theme="blue" :label="w('file_requests.ask_again')" :loading="busy" :data-testid="`${prefix}ask-send`" @click="send" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, inject, nextTick, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { MAX_REASON } from './view.js'

// "Ask again" (design §3.10): staff say why a file is asked for again; the held file is deleted for real, the slot opens
// and the person is told the reason. A small dialog, drawn from the remove dialog (the canvas has no frame for it, D-196).
const props = defineProps({ open: Boolean, item: { type: Object, required: true }, name: { type: String, default: '' }, prefix: { type: String, default: '' } })
const emit = defineEmits(['update:open', 'done'])
const host = inject(HOST_KEY)
const w = wordsFor(useMode())
const reason = ref('')
const busy = ref(false)
const problem = ref('')
const box = ref(null)
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })

async function send() {
  if (busy.value) return
  const why = reason.value.trim()
  problem.value = why ? '' : w('file_requests.ask_problem')
  if (!why) return
  busy.value = true
  try {
    await host.act('file_requests', 'ask_again', { item: props.item.item, reason: why })
    reason.value = ''
    emit('done')
  } catch (e) {
    problem.value = e.message || ''
  } finally {
    busy.value = false
  }
}

watch(() => props.open, async (open) => {
  if (!open) return
  problem.value = ''
  await nextTick()
  box.value?.focus()
})
</script>
