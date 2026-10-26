<template>
  <div class="flex min-h-full flex-col bg-surface-gray-1" :class="phoneNav ? 'pb-14' : ''" data-testid="portal-app">
    <header class="border-b border-outline-gray-2" :class="panel ? 'cw-panel-bar' : 'bg-surface-base'" data-testid="portal-header">
      <div class="mx-auto flex min-h-[52px] max-w-[1120px] flex-wrap items-center gap-4 px-5">
        <router-link :to="portal.project ? { name: 'portal-project', params: { project: portal.project } } : { name: 'portal-home' }"
          class="flex min-w-0 items-center gap-3 text-ink-gray-9 no-underline max-sm:flex-1" data-testid="brand">
          <BrandMark />
          <template v-if="portal.project">
            <span class="h-[22px] flex-none border-l border-outline-gray-3 max-sm:hidden" aria-hidden="true" data-testid="portal-divider" />
            <span class="min-w-0 truncate text-base font-semibold max-sm:hidden" :class="'cw-brand-font'" data-testid="portal-project-name">{{ portal.title }}</span>
          </template>
        </router-link>
        <nav v-if="portal.tabs.length && !isPhone" aria-label="Portal sections" class="flex flex-wrap self-stretch" data-testid="portal-tabs">
          <router-link v-for="t in portal.tabs" :key="t.key" :to="tabLink(t.key)"
            class="flex h-[52px] items-center gap-1.5 border-b-2 px-3 text-base no-underline"
            :class="portal.tab === t.key ? 'border-outline-blue-6 font-semibold text-ink-blue-8' : 'border-transparent text-ink-gray-8 hover:text-ink-gray-9'"
            :aria-current="portal.tab === t.key ? 'page' : undefined" data-testid="portal-tab" :data-tab="t.key">{{ t.label }}<Badge
              v-if="t.key === 'discuss' && unread" variant="solid" theme="blue" size="sm" :label="String(unread)" :aria-label="unreadWord" data-testid="portal-tab-unread" /><Badge
              v-if="t.key === 'approvals' && portal.waiting" variant="solid" theme="blue" size="sm" :label="String(portal.waiting)" :aria-label="waitingWord" data-testid="portal-tab-waiting" /></router-link>
        </nav>
        <div class="ml-auto flex items-center gap-2.5">
          <span class="hidden text-sm text-ink-gray-7 sm:inline" data-testid="portal-user">{{ boot.full_name }}</span>
          <AccountMenu client />
        </div>
      </div>
    </header>
    <router-view />
    <footer v-if="boot.credit" class="mt-auto flex justify-center px-5 pb-6 pt-8" data-testid="portal-footer">
      <PoweredBy />
    </footer>
    <nav v-if="phoneNav" aria-label="Portal" class="fixed inset-x-0 bottom-0 z-10 grid h-14 border-t border-outline-gray-1 bg-surface-base"
      :style="{ gridTemplateColumns: `repeat(${portal.tabs.length}, minmax(0, 1fr))` }" data-testid="portal-nav">
      <router-link v-for="t in portal.tabs" :key="t.key" :to="tabLink(t.key)"
        class="flex flex-col items-center justify-center gap-0.5 text-[11px] no-underline"
        :class="portal.tab === t.key ? 'font-semibold text-ink-blue-8' : 'text-ink-gray-7'"
        :aria-current="portal.tab === t.key ? 'page' : undefined" data-testid="portal-nav-item" :data-tab="t.key">
        <span class="relative"><span :class="t.icon" class="block size-6" aria-hidden="true" /><span v-if="t.key === 'discuss' && unread"
          class="absolute -right-1.5 -top-1 min-w-4 rounded-full bg-surface-blue-6 px-1 text-center text-[10px] font-semibold leading-4 text-ink-base"
          :aria-label="unreadWord" data-testid="portal-nav-unread">{{ unread }}</span><span v-if="t.key === 'approvals' && portal.waiting"
          class="absolute -right-1.5 -top-1 min-w-4 rounded-full bg-surface-blue-6 px-1 text-center text-[10px] font-semibold leading-4 text-ink-base"
          :aria-label="waitingWord" data-testid="portal-nav-waiting">{{ portal.waiting }}</span></span>{{ t.label }}
      </router-link>
    </nav>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { boot } from '../boot.js'
import { chatUnreadOf } from '../store.js'
import { chatWord } from '../chat/words.js'
import { approvalWord } from '../approvals/words.js'
import { useMode } from '../mode.js'
import AccountMenu from '../components/AccountMenu.vue'
import BrandMark from '../components/BrandMark.vue'
import PoweredBy from '../components/PoweredBy.vue'
import { bootLook } from '../brand.js'
import { isPhone, portal } from './state.js'

// The portal's one 52px bar from the live design (D-124, version 1791648865-5845; D-127): the brand (P3-44, D-401: the
// firm's name leads, the product's until a firm is set), the project (not on a phone: its page shows it), its four tabs with a
// 2px blue underline, and the client's account menu; the credit is the footer. On a phone the tabs are a bottom bar of
// 56px items.
// P3-45: the firm's panel colour paints the header (a dark ground: its ink tokens turn white inside it)
const panel = !!bootLook(boot).panel
const phoneNav = computed(() => isPhone.value && portal.tabs.length > 0)
// P3-64: the Discussion tab shows the client's unread messages in their room (the store, kept by Project.vue's host).
const mode = useMode()
const unread = computed(() => (portal.project ? chatUnreadOf(portal.project) : 0))
const unreadWord = computed(() => chatWord('core.unread', { mode: mode.value, portal: true, values: { count: unread.value } }))
// P3-79 (design §3.12): the Approvals tab's badge counts the requests waiting for this client (Project.vue fills it).
const waitingWord = computed(() => approvalWord('badge_aria', { mode: mode.value, values: { count: portal.waiting } }))
const tabLink = (key) => ({ name: 'portal-project', params: { project: portal.project }, query: key === 'home' ? {} : { tab: key } })
</script>
