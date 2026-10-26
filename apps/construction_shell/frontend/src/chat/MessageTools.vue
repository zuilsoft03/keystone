<template>
  <div class="absolute -top-3 right-3 hidden gap-0.5 rounded-4 border border-outline-gray-2 bg-surface-base p-0.5 shadow-sm group-focus-within:flex group-hover:flex max-md:static max-md:flex max-md:w-full max-md:flex-wrap max-md:border-0 max-md:p-0 max-md:pl-12 max-md:shadow-none"
    :data-testid="`${prefix}message-tools`">
    <Button v-if="canReply" size="sm" variant="ghost" class="max-md:!h-12" icon-left="lucide-message-square-reply" :label="w('core.reply_in_thread')" data-testid="reply-in-thread" @click="emit('thread')" />
    <Button v-if="canTeam" size="sm" variant="ghost" class="max-md:!h-12" icon-left="lucide-users" :label="w('core.discuss_team')" data-testid="discuss-with-team" @click="emit('team')" />
    <MenuButton v-if="reactions.length" icon="lucide-smile-plus" :label="w('reactions.react')" :aria="w('reactions.add')" icon-only :items="reactions" testid="react" @pick="(it) => emit('react', it)" />
    <Button v-for="a in direct" :key="a.id" size="sm" variant="ghost" class="max-md:!h-12" :label="word(a)" :data-testid="a.id" @click="emit('action', a)" />
    <MenuButton v-if="more.length" icon="lucide-ellipsis" :label="w('core.more')" icon-only :items="more" testid="more" @pick="(it) => emit('action', it.action)" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import { useMode } from '../mode.js'
import MenuButton from './MenuButton.vue'
import { wordsFor } from './words.js'

// The toolbar that shows on a message when it is hovered or focused, and always on a phone (design §13.2 F4; canvas "Discussion":
// Reply in thread, React, Discuss with team, More). Pin stays a button of its own; the author's and manager's actions
// (Edit, History, Agreed, Remove) are in More. React offers the reactions this reader may use. The registry decides what is
// offered (`actions`, from the message's `can`); this only draws it.
const props = defineProps({
  actions: { type: Array, default: () => [] },
  reactions: { type: Array, default: () => [] }, // [{ id, label, glyph, on }], empty when the thread offers none
  canReply: Boolean,
  canTeam: Boolean,
  message: { type: Object, required: true },
  portal: Boolean,
  prefix: { type: String, default: '' },
})
const emit = defineEmits(['thread', 'team', 'action', 'react'])
const w = wordsFor(useMode(), props.portal)
const word = (a) => w(typeof a.word === 'function' ? a.word(props.message) : a.word)
const direct = computed(() => props.actions.filter((a) => !a.menu))
const more = computed(() => props.actions.filter((a) => a.menu).map((a) => ({ id: a.id, label: word(a), icon: a.icon, action: a })))
</script>
