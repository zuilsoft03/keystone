// The sign-in page's state and actions (P3-24, P3-26; D-251, D-252, D-265), shared by every look: each action is one
// of Frappe's own calls, and the looks only present it. Kept apart from the screens so LoginA and LoginB behave alike.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { LOGIN, RESET, STRENGTH, UPDATE, nextPlace, post, serverMessage, signInResult, strengthOf } from './flow.js'

export function useSignIn(boot) {
  const params = new URLSearchParams(window.location.search)
  const key = params.get('key') || ''

  const step = ref('signin')
  const email = ref(boot.email || '')
  const password = ref('')
  const showPw = ref(false)
  const wrong = ref(false)
  const problem = ref('')
  const notice = ref('')
  const busy = ref(false)
  const code = ref('')
  const tmpId = ref('')
  const again = ref(0)
  const oldPassword = ref('')
  const newPassword = ref('')
  const confirmPassword = ref('')
  const strengthResult = ref(null)
  const strength = computed(() => strengthOf(strengthResult.value))
  const matches = computed(() => !!newPassword.value && newPassword.value === confirmPassword.value)
  let timer = null
  let strengthTimer = null

  function go(next) {
    problem.value = ''
    wrong.value = false
    step.value = next
  }

  function restart() {
    password.value = ''
    code.value = ''
    tmpId.value = ''
    go('signin')
  }

  function arrive(data) {
    window.location.href = nextPlace(data, window.location.search)
  }

  async function signIn() {
    busy.value = true
    problem.value = ''
    notice.value = ''
    wrong.value = false
    const out = signInResult(await post(LOGIN, { usr: email.value.trim(), pwd: password.value }))
    busy.value = false
    if (out.kind === 'done') return arrive(out.data)
    if (out.kind === 'code') {
      tmpId.value = out.tmpId
      code.value = ''
      password.value = '' // the server keeps it for the code step; the page does not
      return go('code')
    }
    if (out.kind === 'wrong') wrong.value = true
    else problem.value = out.kind === 'offline' ? 'We could not reach the server. Check your connection.' : out.text
  }

  async function checkCode() {
    if (busy.value || code.value.length !== 6) return
    busy.value = true
    problem.value = ''
    const out = signInResult(await post(LOGIN, { otp: code.value, tmp_id: tmpId.value }))
    busy.value = false
    if (out.kind === 'done') return arrive(out.data)
    code.value = ''
    if (out.kind === 'wrong' || /expired/i.test(out.text || '')) {
      problem.value = /expired/i.test(out.text || '') ? 'That took too long. Please sign in again.' : 'That code is not right. Use the newest code the app shows.'
      if (/expired/i.test(out.text || '')) restart()
    } else problem.value = out.text || 'That did not work.'
  }

  function countdown(seconds) {
    again.value = seconds
    clearInterval(timer)
    timer = setInterval(() => {
      again.value = Math.max(0, again.value - 1)
      if (!again.value) clearInterval(timer)
    }, 1000)
  }

  async function sendReset() {
    if (!email.value.trim()) return
    busy.value = true
    problem.value = ''
    const { status, data } = await post(RESET, { user: email.value.trim() })
    busy.value = false
    if (status === 429) {
      problem.value = 'Too many reset requests. Please try again in an hour.'
      if (step.value !== 'forgot') step.value = 'forgot'
      return
    }
    if (status === 0) {
      problem.value = 'We could not reach the server. Check your connection.'
      return
    }
    void data // Frappe answers the same for every address (it never says whether one exists)
    step.value = 'sent'
    countdown(60)
  }

  watch(newPassword, (value) => {
    clearTimeout(strengthTimer)
    if (!value) {
      strengthResult.value = null
      return
    }
    strengthTimer = setTimeout(async () => {
      const { data } = await post(STRENGTH, { new_password: value }, window.csrf_token || '')
      if (value === newPassword.value) strengthResult.value = data.message || { score: 0, feedback: { password_policy_validation_passed: !data.message } }
    }, 250)
  })

  async function setPassword() {
    busy.value = true
    problem.value = ''
    const body = { new_password: newPassword.value, logout_all_sessions: 1, ...(key ? { key } : { old_password: oldPassword.value }) }
    const { status, data } = await post(UPDATE, body, window.csrf_token || '')
    busy.value = false
    if (status === 410) return go('expired') // Frappe's answer for a used, expired or unknown key; a policy refusal is not
    if (status !== 200) {
      problem.value = serverMessage(data) || 'The password could not be saved.'
      return
    }
    const where = typeof data.message === 'string' ? data.message : '/'
    if (where === '/login') {
      // Two-step sign-in is on: Frappe asks for a normal sign-in with the code, on this look's own sign-in page.
      newPassword.value = confirmPassword.value = ''
      window.history.replaceState(null, '', signInPath(boot.look))
      notice.value = 'Your password is set. Sign in with it now.'
      return go('signin')
    }
    window.location.href = nextPlace({ home_page: where }, '')
  }

  onMounted(() => {
    if (boot.view === 'password') step.value = key || boot.signed_in ? 'setpw' : 'expired'
    if (key && boot.view === 'password') window.history.replaceState(null, '', '/update-password') // the key leaves the address bar
  })
  onBeforeUnmount(() => {
    clearInterval(timer)
    clearTimeout(strengthTimer)
  })

  return {
    key, step, email, password, showPw, wrong, problem, notice, busy, code, again, oldPassword, newPassword,
    confirmPassword, strengthResult, strength, matches, go, restart, signIn, checkCode, sendReset, setPassword,
  }
}

// Each group's own sign-in page (D-265).
export function signInPath(look) {
  return look === 'client' ? '/portal/login' : '/login'
}
