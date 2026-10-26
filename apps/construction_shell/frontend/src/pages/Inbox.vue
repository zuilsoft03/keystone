<template>
  <InboxView />
</template>

<script setup>
import { provide } from 'vue'
import { HOST_KEY, createHost } from '../chat/host.js'
import InboxView from '../chat/inbox/InboxView.vue'

// P3-74: the staff Discussion inbox page, /workspace/discussion. Only pages make a chat host (F1): this one reads as
// the signed-in staff member; the server answers with their member projects only (§14.6).
provide(HOST_KEY, createHost({ viewer: 'staff' }))
</script>
