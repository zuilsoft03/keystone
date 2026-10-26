<template>
  <div v-if="tray.items.length || tray.state.error" class="flex flex-col gap-1.5 px-2.5 pt-2.5" :data-testid="`${prefix}tray`">
    <ul class="m-0 flex list-none flex-wrap gap-2 p-0">
      <li v-for="item in tray.items" :key="item.key"
        class="relative flex w-[210px] max-w-full items-center gap-2 rounded-4 border border-outline-gray-2 bg-surface-base py-1.5 pl-1.5 pr-7 max-md:pr-12"
        :data-testid="`${prefix}tray-item`" :data-state="item.state">
        <span v-if="item.thumb" class="size-9 flex-none overflow-hidden rounded-3 bg-surface-gray-2">
          <img :src="item.thumb" alt="" class="size-full object-cover" />
        </span>
        <span v-else class="grid size-9 flex-none place-items-center rounded-3 bg-surface-gray-2">
          <Badge size="sm" :theme="extTheme(fileExt(item.file_name))" :label="fileExt(item.file_name) || w('attachments.file')" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate text-[13px] text-ink-gray-9">{{ item.file_name }}</span>
          <span v-if="item.state === 'ready'" class="mt-1 block text-[11px] text-ink-green-8">{{ w('attachments.ready') }}</span>
          <span v-else-if="item.state === 'checking'" class="mt-1 flex items-center gap-1 text-[11px] text-ink-gray-7" :data-testid="`${prefix}tray-checking`">
            <span class="lucide-loader-circle size-3 flex-none motion-safe:animate-spin" aria-hidden="true" />{{ w('attachments.checking') }}
          </span>
          <span v-else-if="item.state === 'refused'" class="mt-1 block text-[11px] leading-snug text-ink-red-7" :title="refusedText(item)" :data-testid="`${prefix}tray-refused`">
            {{ refusedText(item) }}
          </span>
          <span v-else-if="item.state === 'failed'" class="mt-1 flex items-center gap-1.5 text-[11px] text-ink-red-7" role="alert">
            <span class="min-w-0 truncate" :title="item.error">{{ item.error || w('attachments.not_added') }}</span>
            <button v-if="item.file" type="button" class="flex-none rounded-3 border-0 bg-transparent px-1 text-[11px] font-medium text-ink-blue-7 underline max-md:min-h-12"
              :data-testid="`${prefix}tray-retry`" @click="tray.retry(item.key)">{{ w('core.retry') }}</button>
          </span>
          <span v-else class="mt-1.5 block h-1 overflow-hidden rounded-full bg-surface-gray-3" role="progressbar" aria-valuemin="0" aria-valuemax="100"
            :aria-valuenow="Math.round(item.progress * 100)" :aria-label="w('attachments.uploading', { percent: Math.round(item.progress * 100) })">
            <span class="block h-full bg-surface-blue-6" :style="{ width: `${Math.round(item.progress * 100)}%` }" />
          </span>
        </span>
        <button type="button" class="absolute right-0.5 top-1 grid size-6 place-items-center rounded-3 border-0 bg-transparent text-ink-gray-7 hover:bg-surface-gray-2 max-md:right-0 max-md:top-0 max-md:size-12"
          :aria-label="w('attachments.remove', { name: item.file_name })" :data-testid="`${prefix}tray-remove`" @click="tray.remove(item.key)">
          <span class="lucide-x size-3.5" aria-hidden="true" />
        </button>
      </li>
    </ul>
    <p v-if="tray.state.error" class="m-0 text-xs text-ink-red-7" role="alert" :data-testid="`${prefix}tray-error`">{{ errorText }}</p>
    <!-- Why Send is off (P3-75): one line, announced politely when it changes -->
    <p v-if="tray.blocked" class="m-0 text-xs" :class="tray.refused ? 'text-ink-red-7' : 'text-ink-gray-8'" role="status" :data-testid="`${prefix}tray-blocked`">{{ tray.refused ? w('attachments.blocked_line') : w('attachments.checking_line') }}</p>
    <label v-if="touch && hasPhoto" class="inline-flex min-h-12 cursor-pointer items-center gap-2 self-start text-xs text-ink-gray-8 md:min-h-0" :data-testid="`${prefix}original`">
      <input v-model="tray.state.original" type="checkbox" class="form-checkbox" />{{ w('attachments.original') }}
    </label>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { useTouchPhone } from '../../../sections/drafts.js'
import { extTheme, fileExt } from '../../../sections/util.js'
import { wordsFor } from '../../words.js'
import { REFUSALS } from './tray.js'

// The files a message will carry, inside the message box (canvas "The composer" frame 2): a thumbnail or the type,
// the name, Ready or the upload's progress, and Remove. "Send original quality" keeps a phone's photos full size (L-11).
const props = defineProps({ tray: { type: Object, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const w = wordsFor(useMode(), props.portal)
const touch = useTouchPhone()
const hasPhoto = computed(() => props.tray.items.some((i) => i.kind === 'photo' && i.file))
// A refused large file: the server's reason in words (threat, could not be checked, not stored), else the general line.
const refusedText = (item) => w(REFUSALS.includes(item.reason) ? `attachments.${item.reason === 'gone' ? 'check_gone' : `refused_${item.reason}`}` : 'attachments.refused')
const errorText = computed(() => (props.tray.state.error === 'too_many' ? w('attachments.too_many', { max: props.tray.state.max }) : props.tray.state.error))
</script>
