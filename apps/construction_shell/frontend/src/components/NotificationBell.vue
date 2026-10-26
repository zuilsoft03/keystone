<template>
  <Popover side="bottom" align="end">
    <template #trigger="{ setOpen, open: isOpen }">
      <button
        type="button"
        class="relative flex size-8 items-center justify-center rounded-4 text-ink-gray-7 hover:bg-surface-gray-3"
        :aria-label="bellLabel(bell.unread, bell.more)"
        aria-haspopup="dialog"
        :aria-expanded="isOpen"
        data-testid="notification-bell"
        @click="setOpen(!isOpen)"
      >
        <span class="lucide-bell size-4" aria-hidden="true" />
        <span
          v-if="bell.unread > 0"
          class="pointer-events-none absolute right-px top-px flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-surface-red-7 px-[3px] text-[9px] font-semibold leading-none text-ink-base"
          aria-hidden="true"
          data-testid="notification-count"
        >{{ badgeText(bell.unread, bell.more) }}</span>
      </button>
    </template>
    <template #default="{ close }">
      <div role="dialog" aria-label="Notifications" class="w-[min(360px,calc(100vw-24px))] rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 text-base shadow-lg" data-testid="notification-panel">
        <div class="flex min-h-8 items-center justify-between gap-2 px-2 pb-1">
          <span class="font-semibold text-ink-gray-9">Notifications</span>
          <Button v-if="bell.unread > 0" variant="ghost" size="sm" label="Mark all as read" data-testid="mark-all-read" @click="markAll" />
        </div>
        <p v-if="bell.error" role="alert" class="px-2.5 py-2 text-xs text-ink-red-7">{{ bell.error }}</p>
        <ul v-if="bell.items.length" class="max-h-[min(420px,70vh)] overflow-y-auto">
          <li v-for="n in bell.items" :key="n.name">
            <button
              type="button"
              class="flex w-full items-start gap-2.5 rounded-4 px-2.5 py-2 text-left hover:bg-surface-gray-2"
              data-testid="notification-row"
              :data-read="n.read ? 1 : 0"
              @click="go(n, close)"
            >
              <Avatar :image="n.actor.image || undefined" :label="n.actor.name" size="md" />
              <span class="min-w-0 flex-1">
                <span class="block text-ink-gray-9" :class="{ 'font-medium': !n.read }"><span v-if="!n.read" class="sr-only">Unread: </span>{{ n.text }}</span>
                <span class="mt-0.5 block text-[11px] text-ink-gray-6">{{ clockTime(n.when) }}</span>
              </span>
              <span v-if="!n.read" class="mt-1.5 size-2 flex-none rounded-full bg-surface-blue-6" aria-hidden="true" />
            </button>
          </li>
        </ul>
        <p v-else-if="bell.loaded && !bell.error" class="px-2.5 py-2 text-xs text-ink-gray-6">No notifications yet.</p>
      </div>
    </template>
  </Popover>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { Avatar, Button, Popover } from 'frappe-ui'
import { badgeText, bell, bellLabel, markAll, markRead } from '../notifications.js'
import { clockTime } from '../sections/util.js'

// The staff bell (P3-06), the live design's top-bar button with its red count (D-124). The design draws no panel, so
// the panel follows the account menu and the project switcher (D-058, D-125). Every text is the server's, shown as
// text only: never as markup.
const router = useRouter()

// The mark is saved before the record opens: opening a conversation marks its notices read too, and two requests
// that write the same notices at once would make the later one fail (MariaDB 1020, as D-177 measured).
function go(n, close) {
  close()
  const marking = markRead(n)
  if (n.route) marking.finally(() => router.push({ name: 'section', params: n.route, query: n.query || {} }))
  else if (n.href?.startsWith('/desk/')) marking.finally(() => window.location.assign(n.href))
}
</script>
