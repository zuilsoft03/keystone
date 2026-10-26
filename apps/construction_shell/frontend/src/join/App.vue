<template>
  <!-- P3-17, P3-18 (D-214, D-219): one step per screen, large text and controls, built from the design's login
       column and tokens (D-196). Nothing here is rendered as HTML. -->
  <div class="flex min-h-screen justify-center bg-surface-base px-4 py-8" data-testid="join-app">
    <main class="flex w-full max-w-[420px] flex-col gap-6">
      <div class="flex min-w-0" data-testid="join-brand">
        <BrandMark :size="40" :company-name="company" />
      </div>

      <p v-if="label" class="m-0 text-lg font-semibold text-ink-gray-8" data-testid="join-step">{{ label }}</p>

      <div v-if="problem" role="alert" class="flex items-start gap-3 rounded-4 border-2 border-outline-red-2 bg-surface-red-1 px-4 py-3" data-testid="join-problem">
        <span class="lucide-circle-alert mt-1 size-5 flex-none text-ink-red-8" aria-hidden="true" />
        <p class="m-0 text-[18px] leading-[1.5] text-ink-gray-9">{{ problem }}</p>
      </div>

      <section v-if="step === 'loading'" aria-busy="true" class="text-[18px] text-ink-gray-8">Loading…</section>

      <section v-else-if="step === 'dead'" data-testid="join-dead" class="flex flex-col gap-3">
        <h1 :class="H1">This link no longer works</h1>
        <p :class="P">Ask the person who sent it for a new one.</p>
      </section>

      <section v-else-if="step === 'welcome'" data-testid="join-welcome" class="flex flex-col gap-6">
        <div class="flex flex-col gap-3">
          <h1 :class="H1">Welcome</h1>
          <p :class="P">{{ company || 'The project team' }} has invited you to {{ team ? 'join the team online' : 'follow your project online' }}.<template v-if="inviter"> Invited by {{ inviter }}.</template> It takes about 3 minutes.</p>
          <p v-if="kind === 'bound'" :class="P">We'll email a 6-digit code to <strong class="text-ink-gray-9">{{ masked }}</strong> to make sure it's you.</p>
        </div>
        <button v-if="kind === 'bound'" type="button" :class="BUTTON" :disabled="busy" data-testid="join-send" @click="sendCode()">{{ busy ? 'Sending…' : 'Send me a code' }}</button>
        <button v-else type="button" :class="BUTTON" data-testid="join-start" @click="start">Start</button>
      </section>

      <section v-else-if="step === 'email'" data-testid="join-email" class="flex flex-col gap-6">
        <div class="flex flex-col gap-3">
          <h1 :class="H1">Your email address</h1>
          <p :class="P">We'll send a code here to check it's yours.</p>
        </div>
        <form class="flex flex-col gap-5" @submit.prevent="sendCode(email)">
          <div>
            <label :class="LABEL" for="join-email-input">Email address</label>
            <input id="join-email-input" v-model="email" :class="INPUT" type="email" inputmode="email" autocomplete="email" maxlength="140" required data-testid="join-email-input">
            <p :class="HELP">Example: maria.santos@example.com</p>
          </div>
          <button type="submit" :class="BUTTON" :disabled="busy || !email.trim()" data-testid="join-send">{{ busy ? 'Sending…' : 'Send me a code' }}</button>
        </form>
      </section>

      <section v-else-if="step === 'code'" data-testid="join-code" class="flex flex-col gap-6">
        <div class="flex flex-col gap-3">
          <h1 :class="H1">Enter the 6-digit code</h1>
          <p :class="P">We emailed it to <strong class="text-ink-gray-9">{{ masked }}</strong>. Check your inbox, and your spam folder too. The code works for 15 minutes.</p>
        </div>
        <form class="flex flex-col gap-5" @submit.prevent="checkCode">
          <fieldset class="m-0 border-0 p-0">
            <legend :class="LABEL">Code</legend>
            <div class="flex justify-between gap-2" data-testid="join-code-input" @paste.prevent="onPaste($event, 0)">
              <input v-for="(d, i) in boxes" :key="i" :ref="(el) => (boxEls[i] = el)" :value="d"
                class="form-input h-16 w-full min-w-0 rounded-5 border-2 border-outline-gray-4 bg-surface-base p-0 text-center text-[28px] font-semibold text-ink-gray-9"
                inputmode="numeric" pattern="[0-9]*" :autocomplete="i === 0 ? 'one-time-code' : 'off'"
                :aria-label="`Digit ${i + 1} of 6`" :data-testid="`join-code-${i}`"
                @input="onBox($event, i)" @keydown="onKey($event, i)" @paste.stop.prevent="onPaste($event, i)" @focus="$event.target.select()">
            </div>
            <p :class="HELP">Tip: you can paste the whole code into the first box.</p>
          </fieldset>
          <button type="submit" :class="BUTTON" :disabled="busy || code.length !== 6" data-testid="join-check">{{ busy ? 'Checking…' : 'Continue' }}</button>
        </form>
        <button type="button" class="self-start py-2 text-[18px] text-ink-blue-link underline underline-offset-4 disabled:text-ink-gray-6 disabled:no-underline" :disabled="resendIn > 0 || busy" data-testid="join-resend" @click="resend">
          {{ resendIn > 0 ? `Send a new code in ${resendIn} seconds` : 'Send a new code' }}
        </button>
      </section>

      <section v-else-if="step === 'details'" data-testid="join-details" class="flex flex-col gap-6">
        <div class="flex flex-col gap-3">
          <h1 :class="H1">About you</h1>
          <p :class="P">{{ team ? 'The name your colleagues see.' : 'So the project team knows who you are.' }}</p>
        </div>
        <form class="flex flex-col gap-5" @submit.prevent="afterDetails">
          <div>
            <label :class="LABEL" for="join-name">Your full name</label>
            <input id="join-name" v-model="fullName" :class="INPUT" autocomplete="name" maxlength="140" required data-testid="join-name">
            <p :class="HELP">Example: Maria Santos</p>
          </div>
          <div v-if="!team">
            <label :class="LABEL" for="join-mobile">{{ kind === 'open' ? 'Mobile number' : 'Mobile number (optional)' }}</label>
            <input id="join-mobile" v-model="mobile" :class="INPUT" type="tel" inputmode="tel" autocomplete="tel" maxlength="24" :required="kind === 'open'" data-testid="join-mobile">
            <p :class="HELP">So the team can call you about site visits. Example: 0917 123 4567</p>
          </div>
          <div v-if="!team">
            <label :class="LABEL" for="join-company">Company or business name (optional)</label>
            <input id="join-company" v-model="companyName" :class="INPUT" autocomplete="organization" maxlength="140" data-testid="join-company">
          </div>
          <button type="submit" :class="BUTTON" :disabled="!fullName.trim() || (kind === 'open' && !mobile.trim())" data-testid="join-details-next">Continue</button>
        </form>
      </section>

      <section v-else-if="step === 'password'" data-testid="join-password" class="flex flex-col gap-6">
        <div class="flex flex-col gap-3">
          <h1 :class="H1">{{ kind === 'approved' ? `Welcome${name ? ', ' + name : ''}` : 'Choose a password' }}</h1>
          <p v-if="kind === 'approved'" :class="P">The project team approved you. Choose a password to finish.</p>
          <p :class="P">{{ team ? `Use at least ${minPassword} characters. A short sentence you'll remember works well. Don't use your name.` : `Use at least ${minPassword} letters or numbers. Two or three words you'll remember work well.` }}</p>
        </div>
        <p v-if="inApp" class="m-0 rounded-4 bg-surface-gray-2 px-4 py-3 text-lg leading-[1.5] text-ink-gray-9" data-testid="join-in-app">
          You're in a chat app's browser. If you can, open this page in your phone's own browser, so your phone can save the password.
        </p>
        <form class="flex flex-col gap-5" @submit.prevent="afterPassword">
          <div>
            <label :class="LABEL" for="join-pass">Password</label>
            <div class="flex gap-2">
              <input id="join-pass" v-model="password" :class="INPUT" class="min-w-0 flex-1" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" maxlength="256" data-testid="join-pass">
              <button type="button" class="h-14 flex-none rounded-5 border-2 border-outline-gray-3 bg-surface-base px-4 text-lg font-semibold text-ink-gray-9" :aria-pressed="showPassword" data-testid="join-show" @click="showPassword = !showPassword">{{ showPassword ? 'Hide' : 'Show' }}</button>
            </div>
            <p :class="HELP">{{ password.length >= minPassword ? 'Good length.' : `${minPassword - password.length} more to go.` }}</p>
          </div>
          <button type="submit" :class="BUTTON" :disabled="busy || password.length < minPassword" data-testid="join-pass-next">{{ kind === 'approved' || team ? (busy ? 'Finishing…' : 'Finish') : 'Continue' }}</button>
        </form>
      </section>

      <section v-else-if="step === 'privacy'" data-testid="join-privacy" class="flex flex-col gap-6">
        <div class="flex flex-col gap-3">
          <h1 :class="H1">Your privacy</h1>
          <p class="m-0 text-[18px] leading-[1.6] text-ink-gray-9" data-testid="join-consent-text">{{ consent }}</p>
        </div>
        <label class="flex cursor-pointer items-center gap-3 rounded-5 border-2 border-outline-gray-3 px-4 py-4 text-[18px] font-semibold text-ink-gray-9">
          <input v-model="agreed" type="checkbox" class="form-checkbox size-6 flex-none rounded-2" data-testid="join-agree">
          I agree
        </label>
        <button type="button" :class="BUTTON" :disabled="busy || !agreed" data-testid="join-finish" @click="finish">{{ busy ? 'Sending…' : kind === 'open' ? 'Send to the project team' : 'Join the project' }}</button>
      </section>

      <section v-else-if="step === 'waiting'" data-testid="join-waiting" class="flex flex-col gap-3">
        <h1 :class="H1">Thank you</h1>
        <p :class="P">The project team will check your details. When they approve you, we'll email <strong class="text-ink-gray-9">{{ masked || 'you' }}</strong> a link to finish.</p>
        <p :class="P">You can close this page now.</p>
      </section>

      <section v-else-if="step === 'done'" data-testid="join-done" class="flex flex-col gap-6">
        <div class="flex flex-col gap-3">
          <h1 :class="H1">You're all set</h1>
          <p :class="P">{{ existing ? 'The project is added to your account. Sign in with your email and your usual password.' : 'Sign in with your email and the password you chose.' }}</p>
        </div>
        <button type="button" :class="BUTTON" data-testid="join-signin" @click="signIn">Sign in</button>
      </section>

      <footer v-if="boot.credit" class="mt-auto flex justify-center pt-6" data-testid="join-credit">
        <PoweredBy />
      </footer>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { MIN_PASSWORD, MIN_TEAM_PASSWORD, PROOF_KEY, REQUEST_KEY, consentText, digitsOf, fillBoxes, forget, inAppBrowser, post, readToken,
  recall, remember, say, stepLabel, stepOf } from './flow.js'
import BrandMark from '../components/BrandMark.vue'
import PoweredBy from '../components/PoweredBy.vue'

const H1 = 'cw-brand-font m-0 text-[26px] font-semibold leading-[1.25] text-ink-gray-9'
const P = 'm-0 text-[18px] leading-[1.55] text-ink-gray-8'
const LABEL = 'mb-2 block p-0 text-lg font-semibold text-ink-gray-9'
const HELP = 'mt-2 mb-0 text-lg leading-[1.45] text-ink-gray-8'
const INPUT = 'form-input h-14 w-full rounded-5 border-2 border-outline-gray-4 bg-surface-base px-4 text-[18px] text-ink-gray-9'
const BUTTON = 'h-14 w-full rounded-5 bg-surface-blue-7 px-4 text-[18px] font-semibold text-white hover:bg-surface-blue-8 disabled:cursor-not-allowed disabled:bg-surface-gray-3 disabled:text-ink-gray-7'

const store = window.sessionStorage
const boot = window.cc_boot || {}
const token = readToken(window.location, store, window.history)
const step = ref('loading')
const kind = ref('')
const problem = ref('')
const busy = ref(false)
const company = ref(boot.company || '')
const inviter = ref('')
const masked = ref('')
const name = ref('')
const email = ref('')
const request = ref(recall(store, REQUEST_KEY))
const proof = ref(recall(store, PROOF_KEY))
const boxes = ref(['', '', '', '', '', ''])
const boxEls = []
const fullName = ref('')
const mobile = ref('')
const companyName = ref('')
const password = ref('')
const showPassword = ref(false)
const agreed = ref(false)
const existing = ref(false)
const login = ref('/login')
const resendIn = ref(0)
const consent = ref('')
const inApp = inAppBrowser(navigator.userAgent)
const code = computed(() => boxes.value.join(''))
const team = ref(false) // a team invitation (D-235): the name and a password, under the site's policy
const minPassword = computed(() => (team.value ? MIN_TEAM_PASSWORD : MIN_PASSWORD))
const label = computed(() => stepLabel(kind.value, existing.value, step.value, team.value))
let timer = null

function dead(result) {
  if (['invalid', 'too_many_codes', 'full'].includes(result.state)) {
    forget(store)
    step.value = 'dead'
    problem.value = result.state === 'invalid' ? '' : say(result)
    return true
  }
  return false
}

function countdown(seconds) {
  resendIn.value = seconds
  clearInterval(timer)
  timer = setInterval(() => {
    resendIn.value = Math.max(0, resendIn.value - 1)
    if (!resendIn.value) clearInterval(timer)
  }, 1000)
}

function focusBox(i) {
  nextTick(() => boxEls[i]?.focus())
}

function setBoxes(at, text) {
  const out = fillBoxes(boxes.value, at, text)
  boxes.value = out.boxes
  focusBox(out.focus)
  if (code.value.length === 6 && !busy.value) checkCode() // the last digit sends it: no extra tap
}

function onBox(event, i) {
  const typed = event.target.value
  event.target.value = boxes.value[i] // the box shows only what the code holds
  const digits = digitsOf(typed)
  setBoxes(i, digits.length > 2 ? digits : digits.slice(-1)) // a phone's autofill brings the whole code at once
}

function onPaste(event, i) {
  setBoxes(i, event.clipboardData?.getData('text') || '')
}

function onKey(event, i) {
  if (event.key === 'Backspace' && !boxes.value[i] && i > 0) {
    event.preventDefault()
    boxes.value = boxes.value.map((d, j) => (j === i - 1 ? '' : d))
    focusBox(i - 1)
  } else if (event.key === 'ArrowLeft' && i > 0) focusBox(i - 1)
  else if (event.key === 'ArrowRight' && i < 5) focusBox(i + 1)
}

function resend() {
  if (kind.value === 'open' && !email.value.trim()) step.value = 'email' // after a reload: the address again
  else sendCode(email.value)
}

function start() {
  problem.value = ''
  step.value = kind.value === 'open' ? 'email' : 'details'
}

async function sendCode(address) {
  busy.value = true
  problem.value = ''
  const r = await post('send_code', kind.value === 'open' ? { token, email: address } : { token })
  busy.value = false
  if (dead(r)) return
  if (r.request) {
    request.value = r.request
    remember(store, REQUEST_KEY, r.request)
  }
  if (r.masked) masked.value = r.masked
  if (r.state === 'sent') {
    if (!r.request) request.value = null
    step.value = 'code'
    boxes.value = ['', '', '', '', '', '']
    countdown(60)
    focusBox(0)
  } else {
    problem.value = say(r)
    if (r.state === 'wait') {
      countdown(r.seconds)
      step.value = 'code'
    }
  }
}

async function checkCode() {
  if (!request.value) { // an address that already asked gets no code: the team will write to it (D-222)
    problem.value = 'That code is not right. If you have already asked to join, the project team will email you.'
    boxes.value = ['', '', '', '', '', '']
    return
  }
  busy.value = true
  problem.value = ''
  const r = await post('check_code', { token, request_id: request.value, code: code.value })
  busy.value = false
  if (dead(r)) return
  if (r.state === 'verified') {
    proof.value = r.proof
    remember(store, PROOF_KEY, r.proof)
    existing.value = !!r.existing
    fullName.value = fullName.value || r.name || ''
    step.value = 'details'
  } else {
    problem.value = say(r)
    boxes.value = ['', '', '', '', '', '']
    focusBox(0)
  }
}

function afterDetails() {
  problem.value = ''
  step.value = team.value ? 'password' : existing.value || kind.value === 'open' ? 'privacy' : 'password'
}

function afterPassword() {
  problem.value = ''
  if (kind.value === 'approved' || team.value) finish()
  else step.value = 'privacy'
}

async function finish() {
  busy.value = true
  problem.value = ''
  const r = await post('finish', { token, proof: proof.value, full_name: fullName.value, mobile_no: mobile.value,
    company_name: companyName.value, new_password: existing.value ? '' : password.value, consent: agreed.value ? 1 : 0 })
  busy.value = false
  if (dead(r)) return
  if (r.state === 'waiting') {
    remember(store, PROOF_KEY, null) // spent; the request stays so a reload shows this screen
    step.value = 'waiting'
    return
  }
  if (r.state === 'done') {
    forget(store)
    existing.value = !!r.existing
    login.value = r.login || '/login'
    step.value = 'done'
    return
  }
  problem.value = say(r)
  if (r.state === 'weak') step.value = 'password'
  else if (r.state === 'verify_again') {
    remember(store, PROOF_KEY, null)
    step.value = kind.value === 'open' ? 'email' : 'welcome'
  } else if (['name_needed', 'mobile_invalid', 'mobile_needed'].includes(r.state)) step.value = 'details'
}

onMounted(async () => {
  if (!token) {
    step.value = 'dead'
    return
  }
  const r = await post('look', { token, request_id: request.value, proof: proof.value })
  if (r.state === 'signed_in') {
    step.value = 'dead'
    problem.value = say(r)
    return
  }
  if (dead(r) || r.state !== 'ready') {
    if (r.state !== 'invalid') problem.value = say(r)
    return
  }
  kind.value = r.kind
  team.value = !!r.team
  company.value = r.company || company.value
  inviter.value = r.inviter || ''
  masked.value = r.masked || ''
  name.value = r.name || ''
  fullName.value = r.name || ''
  existing.value = !!r.existing
  consent.value = consentText(company.value, boot.privacy_email)
  if (r.request) request.value = r.request
  // An emailed link opens on the welcome screen; its Start goes straight to the details (D-219).
  step.value = r.kind === 'mailed' && !proof.value && step.value === 'loading' ? 'welcome' : stepOf(r.stage)
  if (r.stage === 'code') countdown(0)
  if (r.kind === 'approved' && r.existing) finish() // an existing client has nothing left to choose
})

function signIn() {
  window.location.href = login.value
}

onBeforeUnmount(() => clearInterval(timer))
</script>
