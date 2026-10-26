<template>
  <div class="flex flex-wrap items-end gap-3">
    <div class="min-w-0 flex-[1_1_320px]">
      <div class="text-xs text-ink-gray-7" data-testid="page-crumb"><slot name="crumb">{{ crumb }}</slot></div>
      <div class="mt-1 flex flex-wrap items-baseline gap-2.5">
        <h1 class="m-0 text-3xl-semibold text-ink-gray-9" data-testid="section-title"><slot name="title">{{ title }}</slot></h1>
        <span v-if="meta || $slots.meta" class="text-sm text-ink-gray-7"><slot name="meta">{{ meta }}</slot></span>
      </div>
    </div>
    <div v-if="$slots.default" class="flex flex-wrap items-center gap-2"><slot /></div>
  </div>
</template>

<script setup>
// The in-page header of the live design (D-124, version 1791648865-5845): a small breadcrumb, the title in
// text-3xl-semibold with a muted line beside it, and the actions on the right. frappe-ui's PageHeader belongs to its
// DesktopShell, which this layout does not use (design system README, D-125).
defineProps({ crumb: { type: String, default: '' }, title: { type: String, default: '' }, meta: { type: String, default: '' } })
</script>
