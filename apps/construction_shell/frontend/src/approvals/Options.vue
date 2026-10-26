<template>
  <div :role="pick ? 'radiogroup' : 'list'" :aria-label="w('options')" class="flex flex-wrap gap-3" data-testid="approval-options">
    <component :is="pick ? 'button' : 'div'" v-for="o in rows" :key="o.key" :type="pick ? 'button' : undefined" :role="pick ? 'radio' : 'listitem'"
      :aria-checked="pick ? String(modelValue === o.key) : undefined"
      class="relative flex min-w-0 flex-[1_1_220px] flex-col overflow-hidden rounded-5 border p-0 text-left"
      :class="[pick ? 'cursor-pointer hover:border-outline-gray-4' : '', modelValue === o.key ? 'border-outline-blue-6 bg-surface-blue-1' : 'border-outline-gray-2 bg-surface-base']"
      data-testid="approval-option" :data-option="o.key" @click="pick && $emit('update:modelValue', o.key)">
      <span v-if="o.picture" class="relative block">
        <Picture :request="request" :file-key="o.picture" :name="nameOf(o.picture)" :alt="o.label" />
        <span v-if="o.recommended" class="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-surface-base px-2 py-0.5 text-xs font-medium text-ink-green-8 shadow-sm" data-testid="approval-recommended">
          <span class="lucide-thumbs-up size-3" aria-hidden="true" />{{ w('recommended') }}
        </span>
      </span>
      <span class="flex min-h-12 items-start gap-2.5 px-3 py-2.5">
        <span v-if="pick" class="mt-0.5 grid size-5 flex-none place-items-center rounded-full border-2" aria-hidden="true"
          :class="modelValue === o.key ? 'border-outline-blue-6' : 'border-outline-gray-4'">
          <span v-if="modelValue === o.key" class="size-2.5 rounded-full bg-surface-blue-6" />
        </span>
        <span class="min-w-0 flex-1">
          <span v-if="o.recommended && !o.picture" class="mb-1 inline-flex items-center gap-1 text-xs font-medium text-ink-green-8" data-testid="approval-recommended">
            <span class="lucide-thumbs-up size-3" aria-hidden="true" />{{ w('recommended') }}
          </span>
          <span class="block text-base font-semibold text-ink-gray-9">{{ pick && modelValue === o.key ? w('approve_option', { label: o.label }) : o.label }}</span>
          <span v-if="o.description" class="block text-xs text-ink-gray-7">{{ o.description }}</span>
          <span class="mt-1.5 flex flex-wrap gap-x-3 text-sm text-ink-gray-9">
            <span>{{ w('cost') }}: <strong class="font-semibold">{{ o.cost }}</strong></span>
            <span>{{ w('time') }}: <strong class="font-semibold">{{ o.time }}</strong></span>
          </span>
        </span>
      </span>
    </component>
  </div>
</template>

<script setup>
import Picture from './Picture.vue'

// A Decision's options (approvals design §3.3, §3.5): each with its picture, its description and what it costs or
// takes; the team's recommended one carries a note. `pick` makes them a radio group for an approver; the read-only
// sheet shows them as a list. The picked one reads "Approve <label>" (design §12, accepted); choosing never answers.
const props = defineProps({
  request: { type: String, required: true },
  rows: { type: Array, required: true }, // optionRows(terms, w)
  files: { type: Array, default: () => [] }, // the request's frozen copies, for each picture's name
  modelValue: { type: String, default: '' },
  pick: Boolean,
  w: { type: Function, required: true },
})
defineEmits(['update:modelValue'])
const nameOf = (key) => props.files.find((f) => f.key === key)?.name || ''
</script>
