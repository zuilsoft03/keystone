<template>
  <Dialog v-model:open="shown" :title="w('core.history_title')" :options="{ size: 'lg' }">
      <div :data-testid="`${prefix}history`">
        <p v-if="loading" class="m-0 text-sm text-ink-gray-7" role="status">{{ w('core.loading') }}</p>
        <p v-else-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert">{{ error }}</p>
        <p v-else-if="!versions.length" class="m-0 text-sm text-ink-gray-7">{{ w('core.history_empty') }}</p>
        <ol v-else class="m-0 flex max-h-[60vh] list-none flex-col gap-2 overflow-y-auto p-0">
          <li v-for="(v, i) in versions" :key="i" class="rounded-4 border border-outline-gray-2 px-3 py-2" :data-testid="`${prefix}history-version`">
            <p class="m-0 whitespace-pre-wrap break-words text-base text-ink-gray-9">{{ v.text || w('core.history_blank') }}</p>
            <p class="m-0 mt-1 text-xs text-ink-gray-7">{{ w('core.history_line', { when: stamp(v.replaced), who: v.by || w('core.history_someone') }) }}</p>
          </li>
        </ol>
      </div>
  </Dialog>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { Dialog } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { stampTime } from '../../../sections/util.js'
import { HOST_KEY } from '../../host.js'
import { plain } from '../../tokens.js'
import { wordsFor } from '../../words.js'
import { versionsOf } from './edit.js'

// The earlier texts of an edited message (design §3.8, staff only), newest first. The server sends the raw tokens; they are
// worded here ("@Someone", "#Item"), never shown as tokens. A reader who may not see history never reaches this: `can` has no
// history for them.
const props = defineProps({ open: Boolean, message: { type: Object, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['update:open'])
const host = inject(HOST_KEY)
const w = wordsFor(useMode(), props.portal)
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const versions = ref([])
const loading = ref(false)
const error = ref('')
const stamp = (value) => stampTime(value)

watch(() => props.open, async (open) => {
  if (!open) return
  loading.value = true
  error.value = ''
  versions.value = []
  try {
    versions.value = versionsOf(await host.read('history', { message: props.message.name }), (t) => plain(t, w))
  } catch (e) {
    error.value = e.message || ''
  } finally {
    loading.value = false
  }
}, { immediate: true }) // the dialog is mounted already open
</script>
