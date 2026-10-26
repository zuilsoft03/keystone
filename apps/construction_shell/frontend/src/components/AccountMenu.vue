<template>
  <Popover side="bottom" align="end">
    <template #trigger="{ setOpen, open: isOpen }">
      <button
        type="button"
        :class="client
          ? 'flex items-center gap-1 rounded-full border border-outline-gray-2 bg-surface-base py-0.5 pl-0.5 pr-1 text-ink-gray-7'
          : 'flex size-8 items-center justify-center rounded-4 hover:bg-surface-gray-3'"
        :aria-label="`Account menu for ${name}`"
        aria-haspopup="menu"
        :aria-expanded="isOpen"
        data-testid="account-menu"
        @click="setOpen(!isOpen)"
      >
        <Avatar :image="boot.user_image || undefined" :label="name" :size="client ? 'lg' : 'md'" />
        <span v-if="client" class="lucide-chevron-down size-3.5" aria-hidden="true" />
      </button>
    </template>
    <template #default="{ close }">
      <div role="menu" aria-label="Your account" class="w-[264px] rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 text-base shadow-lg" data-testid="account-panel">
        <div class="flex items-center gap-2.5 px-2 pb-2.5 pt-2">
          <Avatar :image="boot.user_image || undefined" :label="name" size="xl" />
          <div class="min-w-0 flex-1">
            <div class="truncate font-semibold text-ink-gray-9" data-testid="account-name">{{ name }}</div>
            <div class="truncate text-xs text-ink-gray-7" data-testid="account-email">{{ boot.email || boot.user }}</div>
          </div>
          <Badge v-if="client" label="Client" theme="violet" size="sm" data-testid="client-badge" />
          <Badge v-else label="Staff" theme="blue" size="sm" data-testid="staff-badge" />
        </div>
        <div class="mb-1.5 mt-0.5 border-t border-outline-gray-1" />
        <a v-if="!client && boot.desk" :href="boot.desk" role="menuitem" class="flex h-8 items-center gap-2.5 rounded-4 px-2 text-ink-gray-9 no-underline hover:bg-surface-gray-2" data-testid="open-desk">
          <span class="lucide-external-link size-4 text-ink-gray-7" aria-hidden="true" />Open Desk
        </a>
        <div class="flex h-9 items-center gap-2.5 px-2 text-ink-gray-9">
          <span class="lucide-moon size-4 text-ink-gray-7" aria-hidden="true" />Appearance
          <TabButtons class="ml-auto" :options="SCHEMES" :model-value="resolvedColorScheme" aria-label="Theme" data-testid="appearance" @update:model-value="setColorScheme" />
        </div>
        <div class="flex h-9 items-center gap-2.5 px-2 text-ink-gray-9" :title="VIEW_HINT">
          <span class="lucide-sliders-horizontal size-4 text-ink-gray-7" aria-hidden="true" />View
          <TabButtons class="ml-auto" :options="VIEWS" :model-value="mode" aria-label="View" data-testid="view-mode" @update:model-value="setMode" />
        </div>
        <div class="my-1.5 border-t border-outline-gray-1" />
        <!-- P3-21 (D-235): the People page, for System Managers; every call there is checked on the server -->
        <a v-if="!client && boot.system_manager" href="/workspace/people" role="menuitem" class="flex h-8 items-center gap-2.5 rounded-4 px-2 text-ink-gray-9 no-underline hover:bg-surface-gray-2" data-testid="open-people">
          <span class="lucide-users size-4 text-ink-gray-7" aria-hidden="true" />People
        </a>
        <!-- P3-45 (D-300): the Brand page, for System Managers -->
        <a v-if="!client && boot.system_manager" href="/workspace/brand" role="menuitem" class="flex h-8 items-center gap-2.5 rounded-4 px-2 text-ink-gray-9 no-underline hover:bg-surface-gray-2" data-testid="open-brand">
          <span class="lucide-palette size-4 text-ink-gray-7" aria-hidden="true" />Brand
        </a>
        <!-- P3-58: the Company page, for System Managers -->
        <a v-if="!client && boot.system_manager" href="/workspace/company" role="menuitem" class="flex h-8 items-center gap-2.5 rounded-4 px-2 text-ink-gray-9 no-underline hover:bg-surface-gray-2" data-testid="open-company">
          <span class="lucide-building-2 size-4 text-ink-gray-7" aria-hidden="true" />Company
        </a>
        <!-- P3-20 (D-190, D-227): two-step sign-in, each person's own choice -->
        <button type="button" role="menuitem" class="flex h-8 w-full items-center gap-2.5 rounded-4 px-2 text-left text-ink-gray-9 hover:bg-surface-gray-2" data-testid="two-step-open" @click="close?.(); twoStep = true">
          <span class="lucide-shield-check size-4 text-ink-gray-7" aria-hidden="true" />Two-step sign-in
        </button>
        <!-- P3-14 (D-204): Frappe's own page, which asks for the current password -->
        <a href="/update-password" role="menuitem" class="flex h-8 items-center gap-2.5 rounded-4 px-2 text-ink-gray-9 no-underline hover:bg-surface-gray-2" data-testid="change-password">
          <span class="lucide-key-round size-4 text-ink-gray-7" aria-hidden="true" />Change password
        </a>
        <button type="button" role="menuitem" class="flex h-8 w-full items-center gap-2.5 rounded-4 px-2 text-left text-ink-red-7 hover:bg-surface-gray-2" data-testid="sign-out" @click="signOut">
          <span class="lucide-log-out size-4" aria-hidden="true" />Sign out
        </button>
        <div v-if="!client && boot.credit" class="mt-1.5 flex justify-center border-t border-outline-gray-1 pb-1 pt-2.5"><PoweredBy /></div>
      </div>
    </template>
  </Popover>
  <TwoStepDialog :open="twoStep" @close="twoStep = false" />
</template>

<script setup>
import { computed, ref } from 'vue'
import { wipeCadWhenIdle } from '../cadstore.js'
import { Avatar, Badge, Popover, TabButtons, useColorScheme } from 'frappe-ui'
import { boot } from '../boot.js'
import { call } from '../api.js'
import { setMode, useMode } from '../mode.js'
import { clearAllDrafts, draftStorage } from '../sections/drafts.js'
import PoweredBy from './PoweredBy.vue'
import TwoStepDialog from './TwoStepDialog.vue'

// The account menu (P2-08, D-126), drawn as the live design's portal header has it; staff get the same menu from the
// design's avatar button, with Open Desk. Light/Dark is frappe-ui's own switch: it sets data-theme on <html> and
// remembers the choice in this browser (localStorage "theme").
const { client } = defineProps({ client: { type: Boolean, default: false } })
const SCHEMES = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]
const { resolvedColorScheme, setColorScheme } = useColorScheme()
// Simple or Advanced (D-154), the same row as Appearance. Kept on the server, so it follows the person to any device.
const VIEWS = [
  { value: 'simple', label: 'Simple' },
  { value: 'advanced', label: 'Advanced' },
]
const VIEW_HINT = 'Simple shows the main screens in plain words. Advanced shows every section with industry terms.'
const mode = useMode()
const name = computed(() => boot.full_name || boot.user || '')
const twoStep = ref(false)

async function signOut() {
  clearAllDrafts(draftStorage()) // P3-61: unsent chat drafts go with the session
  try {
    // P3-48: drawing copies a CAD viewer left in this browser go before the session does (cadstore.js); a viewer open
    // in another tab closes first
    try { new BroadcastChannel('cc-session').postMessage('signout') } catch { /* no BroadcastChannel */ }
    await Promise.race([wipeCadWhenIdle({ force: true }), new Promise((resolve) => setTimeout(resolve, 2000))])
    await call('logout', {}, { post: true })
  } finally {
    window.location.href = client ? '/portal/login' : '/login' // each group's own sign-in (D-265)
  }
}
</script>
