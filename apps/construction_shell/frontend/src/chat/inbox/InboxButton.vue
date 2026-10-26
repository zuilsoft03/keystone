<template>
  <router-link :to="{ name: 'discussion' }" class="relative flex size-8 items-center justify-center rounded-4 no-underline"
    :class="here ? 'bg-surface-blue-1 text-ink-blue-8' : 'text-ink-gray-7 hover:bg-surface-gray-3'"
    :aria-label="count ? w('inbox.nav', { count }) : w('inbox.nav_plain')" :title="w('inbox.nav_plain')"
    :aria-current="here ? 'page' : undefined" data-testid="inbox-button">
    <span class="lucide-message-circle size-4" aria-hidden="true" />
    <span v-if="count > 0" class="pointer-events-none absolute right-px top-px flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-surface-blue-6 px-[3px] text-[9px] font-semibold leading-none text-ink-base"
      aria-hidden="true" data-testid="inbox-count">{{ count > 99 ? '99+' : count }}</span>
  </router-link>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useMode } from '../../mode.js'
import { inboxUnreadTotal } from '../../store.js'
import { wordsFor } from '../words.js'

// The top bar's way to the Discussion inbox (canvas frame 4: beside the bell, with the count of rooms with something
// new). The count is the frame's (api.projects), kept current by the live page hosts (store.js inboxUnread, P3-74
// round 3); this button makes no host and reads nothing itself (F1).
const route = useRoute()
const w = wordsFor(useMode())
const here = computed(() => route.name === 'discussion')
const count = computed(() => inboxUnreadTotal())
</script>
