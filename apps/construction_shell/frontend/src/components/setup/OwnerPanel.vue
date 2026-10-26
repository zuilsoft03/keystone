<template>
  <!-- P3-54 (W4, T1): the owner's own account, by an invitation of kind Owner. Only Administrator may send it, and only before
       set-up is finished; the server checks both, this only says so in plain words. The step is done when the owner joins. -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-owner" data-testid="owner-panel">
    <h2 id="sec-owner" class="cw-card-title">Your own account</h2>
    <p class="m-0 text-sm text-ink-gray-7">You join through a link in your email, so we know the address is yours. Keep Administrator for emergencies.</p>
    <template v-if="invite">
      <p class="m-0 text-sm text-ink-gray-9" data-testid="owner-open">An invitation went to {{ invite.full_name }} ({{ invite.email }}). Open the email and follow the link. It works until {{ invite.expires }}.</p>
      <Button label="I have joined: check again" class="self-start max-md:!h-12" :disabled="busy" data-testid="owner-refresh" @click="load" />
    </template>
    <p v-else-if="state && !state.owner_invite.allowed" class="m-0 text-sm text-ink-gray-8" data-testid="owner-denied">Only Administrator can invite the owner, and only before set-up is finished. Sign in as Administrator for this step, or skip it.</p>
    <form v-else-if="state" class="flex flex-col gap-3" @submit.prevent="send">
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Your name
        <input v-model="form.full_name" maxlength="140" required class="form-input h-12 w-full md:h-8" data-testid="owner-name" />
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Your work email
        <input v-model="form.email" type="email" required class="form-input h-12 w-full md:h-8" data-testid="owner-email" />
      </label>
      <Button type="submit" variant="solid" theme="blue" label="Send the invitation" class="self-start max-md:!h-12" :loading="busy" :disabled="busy" data-testid="owner-send" />
    </form>
    <p v-if="joined" class="m-0 text-ink-green-7" data-testid="owner-joined">You have joined.</p>
    <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="owner-error">{{ error }}</p>
    <p v-if="done" class="m-0 text-ink-green-7" data-testid="owner-done">{{ done }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Button } from 'frappe-ui'
import { call } from '../../api.js'
import { SETUP, post, stateOf, useRun } from './setup.js'

const emit = defineEmits(['saved'])
const state = ref(null)
const form = reactive({ full_name: '', email: '' })
const { busy, error, done, run } = useRun()
const invite = computed(() => state.value?.owner_invite.open)
const joined = computed(() => stateOf(state.value, 'W4') === 'done')

async function load() {
  const got = await run(() => call(`${SETUP}state`))
  if (!got) return
  state.value = got.out
  if (joined.value) emit('saved')
}
onMounted(load)

async function send() {
  if (!(await run(() => post(`${SETUP}invite_owner`, { ...form }), 'The invitation is sent.'))) return
  try {
    state.value = await call(`${SETUP}state`) // not through load(): run() would wipe the message above
  } catch {
    // the invitation is sent; "check again" reads the state
  }
}
</script>
