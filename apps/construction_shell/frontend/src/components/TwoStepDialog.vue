<template>
  <!-- P3-20 (D-190, D-227): two-step sign-in, the person's own choice, from the account menu. Built from the design's
       dialogs and tokens (D-196). The server checks the password and every code. -->
  <Dialog :open="open" title="Two-step sign-in" @update:open="(v) => !v && $emit('close')">
    <div class="flex flex-col gap-3 text-base text-ink-gray-8" data-testid="two-step">
      <p v-if="problem" role="alert" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-ink-gray-9" data-testid="two-step-problem">{{ problem }}</p>

      <p v-if="step === 'loading'" class="m-0">Loading…</p>

      <template v-else-if="step === 'off'">
        <p v-if="required" class="m-0 rounded-4 bg-surface-amber-1 px-3 py-2 text-ink-gray-9" data-testid="two-step-required-note">Your System Manager requires two-step sign-in. Set it up here now; otherwise your next sign-in emails you a setup link.</p>
        <p class="m-0" data-testid="two-step-off">Off. With it on, signing in also asks for a 6-digit code from an authenticator app on your phone (for example Google Authenticator or Microsoft Authenticator), so a stolen password alone cannot get in.</p>
        <form id="two-step-start" class="flex flex-col gap-1.5" @submit.prevent="start">
          <label class="text-xs text-ink-gray-7" for="two-step-password">Your password</label>
          <input id="two-step-password" v-model="password" type="password" autocomplete="current-password" class="form-input w-full" data-testid="two-step-password" />
        </form>
      </template>

      <template v-else-if="step === 'scan'">
        <p class="m-0">Scan this with your authenticator app, then enter the 6-digit code it shows. This works for {{ minutes }} minutes.</p>
        <div class="flex items-center gap-3 rounded-4 border border-outline-gray-1 p-3">
          <img :src="qr" alt="QR code for your authenticator app" class="size-32 flex-none rounded" data-testid="two-step-qr" />
          <p class="m-0 break-all text-sm">Or type this key in the app: <strong class="text-ink-gray-9" data-testid="two-step-key">{{ key }}</strong></p>
        </div>
        <form id="two-step-confirm" class="flex flex-col gap-1.5" @submit.prevent="confirm">
          <span class="text-xs text-ink-gray-7">Code from the app</span>
          <CodeBoxes v-model="code" testid="two-step-code" label="Code from the app" :disabled="busy" @complete="confirm" />
        </form>
      </template>

      <template v-else-if="step === 'on'">
        <p class="m-0" data-testid="two-step-on">On. Signing in asks for the code from your authenticator app.<template v-if="!required"> To turn it off, enter your password and a current code.</template></p>
        <p v-if="required" class="m-0 rounded-4 bg-surface-amber-1 px-3 py-2 text-ink-gray-9" data-testid="two-step-required">Your System Manager requires two-step sign-in for your account, so it stays on.</p>
        <form v-else id="two-step-off" class="flex flex-col gap-3" @submit.prevent="turnOff">
          <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Your password
            <input v-model="password" type="password" autocomplete="current-password" class="form-input w-full" data-testid="two-step-password" />
          </label>
          <div class="flex flex-col gap-1.5">
            <span class="text-xs text-ink-gray-7">Code from the app</span>
            <CodeBoxes v-model="code" testid="two-step-code" label="Code from the app" :disabled="busy" @complete="() => password && turnOff()" />
          </div>
        </form>
        <p class="m-0 text-sm text-ink-gray-7">Lost your phone? Ask a System Manager to switch it off for you.</p>
      </template>

      <p v-else-if="step === 'unavailable'" class="m-0">Two-step sign-in is not available on this site yet. Ask a System Manager.</p>
    </div>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button label="Close" @click="$emit('close')" />
        <Button v-if="step === 'off'" type="submit" form="two-step-start" variant="solid" theme="blue" label="Continue" :disabled="busy || !password" data-testid="two-step-continue" />
        <Button v-else-if="step === 'scan'" type="submit" form="two-step-confirm" variant="solid" theme="blue" label="Turn on" :disabled="busy || !code" data-testid="two-step-turn-on" />
        <Button v-else-if="step === 'on' && !required" type="submit" form="two-step-off" variant="solid" theme="red" label="Turn off" :disabled="busy || !password || !code" data-testid="two-step-turn-off" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { call } from '../api.js'
import CodeBoxes from './CodeBoxes.vue'

const props = defineProps({ open: Boolean })
// Every answer in plain words; a wrong try says how many are left this hour.
const SAYS = {
  wrong_password: 'That password is not right.',
  wrong_code: 'That code is not right. Use the newest code the app shows.',
  required: 'Your System Manager requires two-step sign-in, so it stays on.',
  locked: 'Too many wrong tries. Please try again in an hour.',
  start_again: 'That took too long. Please start again.',
  already_on: 'Two-step sign-in is already on.',
  already_off: 'Two-step sign-in is already off.',
  unavailable: 'Two-step sign-in is not available on this site yet.',
}
function twoStepSays(r) {
  const left = Number.isInteger(r.left) && ['wrong_password', 'wrong_code'].includes(r.state)
    ? ` ${r.left} ${r.left === 1 ? 'try' : 'tries'} left this hour.` : ''
  return (SAYS[r.state] || r.message || 'That did not work.') + left
}
defineEmits(['close'])
const METHOD = 'construction_core.accounts.two_step.'
const step = ref('loading')
const problem = ref('')
const busy = ref(false)
const password = ref('')
const code = ref('')
const qr = ref('')
const key = ref('')
const minutes = ref(10)
const required = ref(false)

async function load() {
  step.value = 'loading'
  problem.value = ''
  password.value = ''
  code.value = ''
  try {
    const s = await call(`${METHOD}status`)
    required.value = !!s.required
    step.value = !s.site_on ? 'unavailable' : s.on ? 'on' : 'off'
  } catch (e) {
    problem.value = e.message || 'That did not work.'
  }
}

async function post(name, args) {
  busy.value = true
  problem.value = ''
  try {
    return await call(`${METHOD}${name}`, args, { post: true })
  } catch (e) {
    return { state: 'error', message: e.message }
  } finally {
    busy.value = false
  }
}

async function start() {
  const r = await post('start', { password: password.value })
  password.value = ''
  if (r.state === 'scan') {
    qr.value = r.qr
    key.value = r.key
    minutes.value = r.minutes
    step.value = 'scan'
  } else problem.value = twoStepSays(r)
}

async function confirm() {
  if (busy.value || code.value.length !== 6) return
  const r = await post('confirm', { code: code.value })
  code.value = ''
  if (r.state === 'on') {
    qr.value = ''
    key.value = '' // the key is never kept once the app has it
    step.value = 'on'
  } else {
    problem.value = twoStepSays(r)
    if (r.state === 'start_again') step.value = 'off'
  }
}

async function turnOff() {
  if (busy.value) return
  const r = await post('turn_off', { password: password.value, code: code.value })
  password.value = ''
  code.value = ''
  if (r.state === 'off') step.value = 'off'
  else problem.value = twoStepSays(r)
}

watch(() => props.open, (v) => v && load(), { immediate: true })
</script>
