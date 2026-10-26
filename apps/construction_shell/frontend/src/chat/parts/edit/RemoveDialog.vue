<template>
  <Dialog v-model:open="shown" :title="w('core.remove_title')" :options="{ size: 'sm' }">
      <div class="flex flex-col gap-2" :data-testid="`${prefix}remove-confirm`">
        <p class="m-0 text-base text-ink-gray-9">{{ w('core.remove_body') }}</p>
        <p class="m-0 rounded-4 border border-outline-gray-2 px-3 py-2 text-sm text-ink-gray-8 line-clamp-3 whitespace-pre-wrap">{{ preview }}</p>
        <p v-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert">{{ error }}</p>
      </div>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button class="max-md:!h-12" :label="w('core.cancel')" :disabled="busy" :data-testid="`${prefix}remove-cancel`" @click="shown = false" />
        <Button class="max-md:!h-12" variant="solid" theme="red" :label="w('core.remove_yes')" :loading="busy" :data-testid="`${prefix}remove-yes`" @click="remove" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { HOST_KEY, ROOM_KEY } from '../../host.js'
import { readable } from '../../tokens.js'
import { wordsFor } from '../../words.js'

// "Remove this message?" (design §3.8, QH-K): asks once, says what stays (a placeholder, "Message removed") and that it cannot
// be undone. The server moves the words to a store only System Managers read and puts the message's files in the bin.
const props = defineProps({ open: Boolean, message: { type: Object, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['update:open', 'done'])
const host = inject(HOST_KEY)
const room = inject(ROOM_KEY, null)
const w = wordsFor(useMode(), props.portal)
const busy = ref(false)
const error = ref('')
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const preview = computed(() => readable(props.message.text, props.message.parts, w) || w(`kind.${props.message.kind}`))

async function remove() {
  busy.value = true
  error.value = ''
  try {
    room?.merge(await host.remove(props.message.name))
    room?.say(w('core.said_removed'))
    shown.value = false
    emit('done')
  } catch (e) {
    error.value = e.message || ''
  } finally {
    busy.value = false
  }
}

watch(() => props.open, (open) => { if (open) error.value = '' })
</script>
