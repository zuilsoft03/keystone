<template>
  <header class="flex min-h-[52px] flex-wrap items-center gap-3 border-b border-outline-gray-2 bg-surface-base px-3">
    <router-link :to="{ name: 'projects' }" class="flex min-w-0 items-center text-ink-gray-9 no-underline" data-testid="brand">
      <BrandMark />
    </router-link>
    <GlobalSearch />
    <div class="ml-auto flex items-center gap-1">
      <InboxButton />
      <NotificationBell />
      <AccountMenu />
    </div>
  </header>
</template>

<script setup>
import AccountMenu from './AccountMenu.vue'
import BrandMark from './BrandMark.vue'
import GlobalSearch from './GlobalSearch.vue'
import InboxButton from '../chat/inbox/InboxButton.vue'
import NotificationBell from './NotificationBell.vue'

// The live design's 52px top bar (D-124, version 1791790116-f48d), with its search (P3-08, Ctrl K), the Discussion
// inbox (P3-74) and the bell before the account menu (P3-06). "Help and shortcuts" has no data behind it yet and is not
// drawn (D-058). The brand is BrandMark's (P3-44, D-299): the mark, the product name, a divider and the company in small capitals.
</script>
