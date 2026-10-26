<template>
  <Dialog v-model:open="asking" :title="w('refs.discuss_title')" :options="{ size: 'sm' }">
    <div class="flex flex-col gap-2" role="radiogroup" :aria-label="w('refs.discuss_title')" data-testid="discuss-this-rooms">
      <button v-for="r in rooms" :key="r.room" type="button" role="radio" :aria-checked="choice === r.room ? 'true' : 'false'"
        class="flex min-h-12 w-full cursor-pointer items-center gap-3 rounded-5 border px-3 py-2 text-left"
        :class="choice === r.room ? 'border-outline-gray-4 bg-surface-gray-2' : 'border-outline-gray-2 bg-surface-base hover:border-outline-gray-3'"
        :data-testid="`discuss-this-${r.room === 'Internal' ? 'team' : 'client'}`" @click="choice = r.room">
        <span class="grid size-4 flex-none place-items-center rounded-full border" :class="choice === r.room ? 'border-outline-gray-8' : 'border-outline-gray-3'" aria-hidden="true">
          <span v-if="choice === r.room" class="size-2 rounded-full bg-surface-gray-8" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-base text-ink-gray-9">{{ w(r.room === 'Internal' ? 'refs.room_team' : 'refs.room_client') }}</span>
          <span class="block text-xs text-ink-gray-7">{{ w(r.room === 'Internal' ? 'refs.discuss_team_hint' : 'refs.discuss_client_hint') }}</span>
        </span>
      </button>
    </div>
    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button class="max-md:!h-12" :label="w('refs.discuss_cancel')" @click="close" />
        <Button class="max-md:!h-12" variant="solid" theme="blue" :label="w('refs.discuss_this')" :loading="busy" data-testid="discuss-this-confirm" @click="go(choice)" />
      </div>
    </template>
  </Dialog>
  <p v-if="error" class="fixed left-1/2 top-16 z-50 m-0 -translate-x-1/2 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="discuss-this-error">{{ error }}</p>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, Dialog } from 'frappe-ui'
import { wordsFor } from '../chat/words.js'
import { discussRooms, discussThis, threadRoute } from '../discussThis.js'
import { useMode } from '../mode.js'

// "Discuss this" on a file's menu and on a record's page (design §3.5, D-413, D-418): when the Team room is the only
// place, the item's thread opens at once; when the client may read the item too, the person chooses Team or Client first
// (Team is chosen already). The thread opens in the project's Discussion. The server decides the rooms; a refusal is
// shown as its own words.
const props = defineProps({ project: { type: String, required: true } })
const router = useRouter()
const w = wordsFor(useMode())
const asking = ref(false)
const busy = ref(false)
const error = ref('')
const rooms = ref([])
const choice = ref('Internal')
let item = null

async function start(doctype, name) {
  error.value = ''
  item = { doctype, name }
  try {
    rooms.value = await discussRooms(doctype, name)
    if (!rooms.value.length) throw new Error(w('refs.discuss_error'))
    choice.value = 'Internal'
    if (rooms.value.length === 1) return await go(rooms.value[0].room)
    asking.value = true
  } catch (e) {
    fail(e)
  }
}

async function go(room) {
  if (!item) return
  busy.value = true
  error.value = ''
  try {
    const answer = await discussThis(item.doctype, item.name, room)
    asking.value = false
    await router.push(threadRoute(props.project, answer))
  } catch (e) {
    asking.value = false
    fail(e)
  } finally {
    busy.value = false
  }
}

function fail(e) {
  error.value = e?.message || w('refs.discuss_error')
  setTimeout(() => (error.value = ''), 6000)
}

defineExpose({ start })
</script>
