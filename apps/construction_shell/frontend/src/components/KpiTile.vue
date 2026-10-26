<template>
  <div class="cw-card px-4 py-3.5" data-testid="kpi">
    <div class="cw-label">{{ label }}</div>
    <div class="mt-1.5 text-4xl-semibold text-ink-gray-9" data-testid="kpi-value">{{ value }}</div>
    <div v-if="sub" class="mt-0.5 text-xs" :class="subClass || 'text-ink-gray-7'">{{ sub }}</div>
  </div>
</template>

<script setup>
// A stat card of the live design (D-124, version 1791648865-5845).
defineProps({ label: String, value: String, sub: String, subClass: String })
</script>
