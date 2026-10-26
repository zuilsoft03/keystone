<template>
  <!-- P3-24, P3-26 (D-251, D-252, D-264): the sign-in steps every look shares, from the design's LoginA and LoginB (the
       fields keep Frappe's ids, login_email, login_password and old_password, so password managers and earlier checks
       still find them). Nothing here is rendered as HTML. -->
  <div>
    <!-- Sign in, and the wrong password -->
    <form v-if="step === 'signin'" class="flex flex-col gap-5" data-testid="login-signin" @submit.prevent="signIn">
      <div>
        <h1 class="m-0 text-[28px] font-semibold leading-[1.2] text-ink-gray-9">Sign in</h1>
        <p class="mb-0 mt-1.5 text-base leading-[1.5] text-ink-gray-7">{{ client ? 'Sign in to your project portal.' : 'Staff and invited clients sign in here.' }}</p>
      </div>
      <div v-if="wrong" id="lg-error" role="alert" class="flex items-start gap-2.5 rounded-4 border border-outline-red-2 bg-surface-red-1 px-3 py-2.5" data-testid="login-wrong">
        <span class="lucide-circle-alert mt-0.5 size-4 flex-none text-ink-red-8" aria-hidden="true" />
        <div class="min-w-0">
          <div class="text-base font-semibold text-ink-red-8">The email or password is wrong.</div>
          <div class="mt-0.5 text-[13px] leading-[1.45] text-ink-gray-8">Check both and try again. Forgot your password? <button type="button" class="lg-link underline underline-offset-2" @click="go('forgot')">Reset it</button>.</div>
        </div>
      </div>
      <p v-if="problem" role="alert" class="m-0 rounded-4 border border-outline-red-2 bg-surface-red-1 px-3 py-2.5 text-[13px] leading-[1.45] text-ink-gray-9" data-testid="login-problem">{{ problem }}</p>
      <p v-if="notice" role="status" class="m-0 rounded-4 bg-surface-green-1 px-3 py-2.5 text-[13px] leading-[1.45] text-ink-gray-9" data-testid="login-notice">{{ notice }}</p>
      <div class="flex flex-col gap-4">
        <div>
          <label class="mb-1.5 block text-[13px] text-ink-gray-7" for="login_email">Email</label>
          <input id="login_email" v-model="email" class="form-input h-9 w-full" type="email" autocomplete="username" spellcheck="false" placeholder="name@example.com" required
            :aria-describedby="wrong ? 'lg-error' : undefined" data-testid="login-email">
        </div>
        <div>
          <div class="mb-1.5 flex items-baseline justify-between gap-2">
            <label class="text-[13px] text-ink-gray-7" for="login_password">Password</label>
            <button type="button" class="lg-link text-[13px]" data-testid="login-forgot" @click="go('forgot')">Forgot password?</button>
          </div>
          <div class="relative">
            <input id="login_password" v-model="password" class="form-input h-9 w-full pr-10" :type="showPw ? 'text' : 'password'" autocomplete="current-password" required data-testid="login-password">
            <button type="button" class="absolute right-1 top-1 grid size-7 place-items-center rounded-4 text-ink-gray-7 hover:bg-surface-gray-3" :aria-label="showPw ? 'Hide password' : 'Show password'" :aria-pressed="showPw" @click="showPw = !showPw">
              <span :class="[showPw ? 'lucide-eye-off' : 'lucide-eye', 'size-4']" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
      <button type="submit" :class="SOLID" :disabled="busy" data-testid="login-submit">{{ busy ? 'Signing in…' : 'Sign in' }}</button>
      <p v-if="!client" class="m-0 text-[13px] leading-[1.5] text-ink-gray-7">No account? Ask your contact at {{ company || 'the project team' }} to invite you.</p>
    </form>

    <!-- The two-step code -->
    <form v-else-if="step === 'code'" class="flex flex-col gap-5" data-testid="login-code" @submit.prevent="checkCode">
      <div>
        <span class="grid size-10 place-items-center rounded-5 bg-surface-gray-2 text-ink-gray-8"><span class="lucide-smartphone size-5" aria-hidden="true" /></span>
        <h1 class="mb-0 mt-4 text-[28px] font-semibold leading-[1.2] text-ink-gray-9">Enter your code</h1>
        <p class="mb-0 mt-1.5 text-base leading-[1.5] text-ink-gray-7">Open the authenticator app on your phone. Enter the code it shows for {{ company || 'this workspace' }}.</p>
      </div>
      <div class="flex items-center gap-2.5 rounded-5 border border-outline-gray-2 px-2.5 py-2">
        <span class="grid size-8 flex-none place-items-center rounded-full bg-surface-amber-2 text-[13px] font-semibold text-ink-amber-8">{{ initials(email) }}</span>
        <div class="min-w-0 flex-1 truncate text-[13px] text-ink-gray-8">{{ email }}</div>
      </div>
      <p v-if="problem" role="alert" class="m-0 rounded-4 border border-outline-red-2 bg-surface-red-1 px-3 py-2.5 text-[13px] text-ink-gray-9" data-testid="login-problem">{{ problem }}</p>
      <div>
        <span class="mb-1.5 block text-[13px] text-ink-gray-7">6-digit code</span>
        <CodeBoxes v-model="code" testid="login-code-box" label="6-digit code" :disabled="busy" @complete="checkCode" />
        <p class="mb-0 mt-1.5 text-xs text-ink-gray-7">The code changes every 30 seconds.</p>
      </div>
      <button type="submit" :class="SOLID" :disabled="busy || code.length !== 6" data-testid="login-verify">{{ busy ? 'Checking…' : 'Verify and sign in' }}</button>
      <div class="flex flex-col items-center gap-2 text-[13px] text-ink-gray-7">
        <button type="button" class="lg-link" @click="restart">Use a different account</button>
        <span v-if="help">Cannot open the app? Contact <a class="lg-inline" :href="`mailto:${help}`">{{ help }}</a>.</span>
        <span v-else>Cannot open the app? Ask your System Manager to switch it off for you.</span>
      </div>
    </form>

    <!-- Forgot password -->
    <form v-else-if="step === 'forgot'" class="flex flex-col gap-5" data-testid="login-reset" @submit.prevent="sendReset">
      <div><button type="button" class="lg-back" @click="go('signin')"><span class="lucide-arrow-left size-3.5" aria-hidden="true" />Back to sign in</button></div>
      <div>
        <span class="grid size-10 place-items-center rounded-5 bg-surface-gray-2 text-ink-gray-8"><span class="lucide-key-round size-5" aria-hidden="true" /></span>
        <h1 class="mb-0 mt-4 text-[28px] font-semibold leading-[1.2] text-ink-gray-9">Reset your password</h1>
        <p class="mb-0 mt-1.5 text-base leading-[1.5] text-ink-gray-7">Enter the email you use to sign in. We will send you a link to set a new password.</p>
      </div>
      <p v-if="problem" role="alert" class="m-0 rounded-4 border border-outline-red-2 bg-surface-red-1 px-3 py-2.5 text-[13px] text-ink-gray-9" data-testid="login-problem">{{ problem }}</p>
      <div>
        <label class="mb-1.5 block text-[13px] text-ink-gray-7" for="lg-reset-email">Email</label>
        <input id="lg-reset-email" v-model="email" class="form-input h-9 w-full" type="email" autocomplete="username" spellcheck="false" required aria-describedby="lg-reset-hint" data-testid="login-reset-email">
        <p id="lg-reset-hint" class="mb-0 mt-1.5 text-xs leading-[1.45] text-ink-gray-7">{{ client ? 'Use the email that got your project invite.' : 'Clients: use the email that got the project invite.' }}</p>
      </div>
      <button type="submit" :class="SOLID" :disabled="busy" data-testid="login-reset-send">{{ busy ? 'Sending…' : 'Send reset link' }}</button>
    </form>

    <!-- Reset link sent -->
    <div v-else-if="step === 'sent'" class="flex flex-col gap-5" data-testid="login-sent">
      <div>
        <span class="grid size-10 place-items-center rounded-5 bg-surface-green-2 text-ink-green-7"><span class="lucide-mail-check size-5" aria-hidden="true" /></span>
        <h1 class="mb-0 mt-4 text-[28px] font-semibold leading-[1.2] text-ink-gray-9">Check your inbox</h1>
        <p class="mb-0 mt-1.5 text-base leading-[1.5] text-ink-gray-7">If an account uses this email, we sent it a link to set a new password.</p>
        <div class="mt-3 inline-flex items-center gap-2 rounded-4 bg-surface-gray-2 px-2.5 py-1.5 text-[13px] font-semibold text-ink-gray-9"><span class="lucide-mail size-3.5" aria-hidden="true" />{{ email }}</div>
      </div>
      <button type="button" :class="SOLID" data-testid="login-back" @click="go('signin')">Back to sign in</button>
      <div class="rounded-5 border border-outline-gray-1 bg-surface-gray-1 px-3.5 py-3 text-[13px] leading-[1.5] text-ink-gray-8">
        <div>No email? Look in your spam folder.</div>
        <div class="mt-2 flex items-center justify-between gap-3">
          <span class="text-ink-gray-7">{{ again > 0 ? `You can send it again in ${again} s.` : 'You can send it again now.' }}</span>
          <button type="button" class="h-7 rounded-4 border border-outline-gray-2 bg-surface-base px-2 text-base text-ink-gray-8 disabled:cursor-not-allowed disabled:text-ink-gray-4" :disabled="again > 0 || busy" @click="sendReset">Send again</button>
        </div>
      </div>
    </div>

    <!-- Set your password (a reset key), or change it (signed in) -->
    <form v-else-if="step === 'setpw'" class="flex flex-col gap-[18px]" data-testid="login-setpw" @submit.prevent="setPassword">
      <div>
        <h1 class="m-0 text-[28px] font-semibold leading-[1.2] text-ink-gray-9">{{ key ? 'Set your password' : 'Change your password' }}</h1>
        <p class="mb-0 mt-1.5 text-base leading-[1.5] text-ink-gray-8">{{ key ? `Choose a password to sign in to ${company || 'your workspace'}.` : 'Enter your current password, then the new one.' }}</p>
      </div>
      <p v-if="problem" role="alert" class="m-0 rounded-4 border border-outline-red-2 bg-surface-red-1 px-3 py-2.5 text-[13px] text-ink-gray-9" data-testid="login-problem">{{ problem }}</p>
      <div v-if="!key">
        <label class="mb-1.5 block text-[13px] text-ink-gray-7" for="old_password">Current password</label>
        <input id="old_password" v-model="oldPassword" class="form-input h-9 w-full" :type="showPw ? 'text' : 'password'" autocomplete="current-password" required data-testid="login-old">
      </div>
      <div>
        <label class="mb-1.5 block text-[13px] text-ink-gray-7" for="lg-new">New password</label>
        <div class="relative">
          <input id="lg-new" v-model="newPassword" class="form-input h-9 w-full pr-10" :type="showPw ? 'text' : 'password'" autocomplete="new-password" required aria-describedby="lg-strength" data-testid="login-new">
          <button type="button" class="absolute right-1 top-1 grid size-7 place-items-center rounded-4 text-ink-gray-7 hover:bg-surface-gray-3" :aria-label="showPw ? 'Hide passwords' : 'Show passwords'" :aria-pressed="showPw" @click="showPw = !showPw">
            <span :class="[showPw ? 'lucide-eye-off' : 'lucide-eye', 'size-4']" aria-hidden="true" />
          </button>
        </div>
        <div v-if="newPassword && strengthResult && Object.keys(strengthResult).length" class="mt-2.5 flex items-center gap-2.5">
          <div role="meter" aria-label="Password strength" aria-valuemin="0" aria-valuemax="4" :aria-valuenow="strength.score" :aria-valuetext="`${strength.word}, ${strength.score} of 4`" class="grid flex-1 grid-cols-4 gap-1">
            <span v-for="i in 4" :key="i" class="h-1 rounded-sm" :class="i <= strength.score ? (strength.passed ? 'bg-surface-green-7' : 'bg-surface-amber-7') : 'bg-surface-gray-3'" />
          </div>
          <span id="lg-strength" class="text-xs text-ink-gray-7">Strength: <span class="font-semibold text-ink-gray-9" data-testid="login-strength">{{ strength.word }}</span></span>
        </div>
        <p v-if="newPassword && !strength.passed && strength.hint" class="mb-0 mt-1.5 text-xs text-ink-gray-8">{{ strength.hint }}</p>
      </div>
      <div>
        <label class="mb-1.5 block text-[13px] text-ink-gray-7" for="lg-confirm">Confirm new password</label>
        <input id="lg-confirm" v-model="confirmPassword" class="form-input h-9 w-full" :type="showPw ? 'text' : 'password'" autocomplete="new-password" required aria-describedby="lg-match" data-testid="login-confirm">
        <p v-if="confirmPassword" id="lg-match" class="mb-0 mt-1.5 flex items-center gap-1.5 text-xs text-ink-gray-8">
          <span :class="[matches ? 'lucide-check text-ink-green-7' : 'lucide-x text-ink-red-7', 'size-3.5']" aria-hidden="true" />{{ matches ? 'The passwords match.' : 'The passwords do not match yet.' }}
        </p>
      </div>
      <button type="submit" :class="SOLID" :disabled="busy || !matches || !strength.passed" data-testid="login-setpw-submit">{{ busy ? 'Saving…' : key ? 'Set password and sign in' : 'Change password' }}</button>
      <p class="m-0 text-center text-[13px] text-ink-gray-7">{{ key ? 'Already set a password?' : 'Changed your mind?' }} <a class="lg-inline" :href="key ? signInPath(look) : '/'">{{ key ? 'Sign in' : 'Go back' }}</a></p>
    </form>

    <!-- A reset link that no longer works -->
    <div v-else-if="step === 'expired'" class="flex flex-col gap-5" data-testid="login-expired">
      <div>
        <h1 class="m-0 text-[28px] font-semibold leading-[1.2] text-ink-gray-9">This link no longer works</h1>
        <p class="mb-0 mt-1.5 text-base leading-[1.5] text-ink-gray-7">Reset links work once and for a short time. Ask for a new one.</p>
      </div>
      <button type="button" :class="SOLID" @click="go('forgot')">Send me a new link</button>
    </div>
  </div>
</template>

<script setup>
import CodeBoxes from '../components/CodeBoxes.vue'
import { initials } from './flow.js'
import { signInPath } from './useSignIn.js'

const props = defineProps({
  s: { type: Object, required: true },
  look: { type: String, default: 'team' },
  company: { type: String, default: '' },
  help: { type: String, default: '' },
})
const client = props.look === 'client'
const {
  key, step, email, password, showPw, wrong, problem, notice, busy, code, again, oldPassword, newPassword,
  confirmPassword, strengthResult, strength, matches, go, restart, signIn, checkCode, sendReset, setPassword,
} = props.s
const SOLID = 'h-9 w-full rounded-4 bg-surface-blue-6 text-base font-medium text-white hover:bg-surface-blue-7 disabled:cursor-not-allowed disabled:bg-surface-gray-3 disabled:text-ink-gray-6'
</script>
