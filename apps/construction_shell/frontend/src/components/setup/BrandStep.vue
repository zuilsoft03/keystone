<template>
  <!-- P3-52 (W2): the Brand page's own form (P3-45), without the page frame. Skip ("Keep" the standard brand) leaves the brand as it is. -->
  <Brand embedded @saved="$emit('saved')" />
</template>

<script setup>
import Brand from '../../pages/Brand.vue'

defineEmits(['saved'])
</script>
