<template>
  <span :class="ICONS[section] || ICONS.files" class="size-[18px] flex-none" aria-hidden="true" />
</template>

<script setup>
// The rail's icons: Lucide, as the design system says (D-125), through frappe-ui's Lucide utilities. They follow the
// live design's rail (D-124, version 1791648865-5845).
const ICONS = {
  home: 'lucide-house',
  discuss: 'lucide-message-circle',
  files: 'lucide-folder',
  documents: 'lucide-file-text',
  rfi: 'lucide-circle-help',
  submittals: 'lucide-square-check',
  variations: 'lucide-arrow-left-right',
  whiteboards: 'lucide-pen-line',
  takeoff: 'lucide-layers',
  boq: 'lucide-table',
  settings: 'lucide-sliders-horizontal',
}
defineProps({ section: { type: String, required: true } })
</script>
