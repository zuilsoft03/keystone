<template>
  <Avatar shape="square" :theme="themeOf(name)" :label="label || name" :size="SIZES[size] || 'sm'" class="font-semibold" aria-hidden="true">
    <template v-if="status === 'Open'" #indicator><span class="size-2 rounded-full bg-surface-green-6" title="Active" /></template>
  </Avatar>
</template>

<script setup>
import { Avatar } from 'frappe-ui'
import { themeOf } from '../frame.js'

// A project's badge as the live design draws it (D-124, version 1791648865-5845): a square frappe-ui Avatar in a
// design-system theme, with a green dot for an active project where the caller passes its status.
const SIZES = { sm: 'sm', md: 'lg', lg: 'xl' }
defineProps({
  name: { type: String, required: true },
  label: { type: String, default: '' },
  size: { type: String, default: 'sm' },
  status: { type: String, default: '' },
})
</script>
