// P3-52…P3-57 (docs/design/phase-3.3-firm-setup.md §4): what the set-up wizard and its panels share, kept apart from
// the screens so it is tested. The server decides every step's state; this only reads it and words it.
import { onBeforeUnmount, ref } from 'vue'
import { call } from '../../api.js'

export const SETUP = 'construction_core.accounts.setup.'
export const post = (method, args = {}) => call(method, args, { post: true })

// W11 (partner companies) is in the list so a server that shows it later needs no change here; the server's `hidden` hides it.
export const STEPS = [
  { id: 'W1', title: 'Your firm', lead: 'Tell us who you are. Your company name and a privacy contact are required.' },
  { id: 'W2', title: 'Your brand', lead: 'Your logo, colours and font lead on every page. You can keep the standard look and change it later.' },
  { id: 'W3', title: 'Outgoing email', lead: 'The workspace sends invitations and codes by email. We send you a test email to be sure it arrives.' },
  { id: 'W4', title: 'Your own account', lead: 'Administrator is for emergencies. Make the account you will use every day.' },
  { id: 'W5', title: 'Two-step sign-in', lead: 'Choose who must confirm a sign-in with a code from their phone.' },
  { id: 'W6', title: 'Backups', lead: 'Choose how long to keep backups, and make the first one now.' },
  { id: 'W7', title: 'Project defaults', lead: 'Every new project starts with these folders, rates and cost codes.' },
  { id: 'W8', title: 'Your first project', lead: 'Make the first project. You can make more later.' },
  { id: 'W9', title: 'Your team', lead: 'Invite your team by email. Each person gets a link that works for 7 days.' },
  { id: 'W10', title: 'Your client', lead: 'Invite the first client contact to the first project.' },
  { id: 'W11', title: 'Partner companies', lead: '' },
  { id: 'W12', title: 'Finish', lead: 'Check the steps, then finish set-up.' },
]

// The steps whose completion is the screen's own act: the server lets the screen mark only these done (setup.CLIENT_DONE).
export const CLIENT_DONE = ['W2', 'W5', 'W8', 'W10']

export const visibleSteps = (state) => STEPS.filter((s) => !(state?.hidden || []).includes(s.id))
export const stateOf = (state, id) => state?.steps?.[id]?.state || ''
const settled = (state, id) => stateOf(state, id) === 'done' || stateOf(state, id) === 'skipped'

// The first step still open (W12 when all are settled): where the wizard opens.
export function firstOpen(state) {
  const open = visibleSteps(state).find((s) => s.id !== 'W12' && !settled(state, s.id))
  return open ? open.id : 'W12'
}

// The server's own rule, to disable the button early (setup.finish() checks again): W1 done, every other step done or skipped.
export const canFinish = (state) => stateOf(state, 'W1') === 'done'
  && visibleSteps(state).every((s) => s.id === 'W12' || s.id === 'W1' || settled(state, s.id))

export const stateWord = (state, id) => ({ done: 'Done', skipped: 'Skipped' })[stateOf(state, id)] || 'Not done yet'

// Steps "on screen" counted from 1 among the visible ones, for "Step 3 of 11".
export const position = (state, id) => visibleSteps(state).findIndex((s) => s.id === id) + 1

// Cost codes are typed one a line, the code first: "03-100 Concrete".
export function parseCostCodes(text) {
  return String(text || '').split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
    const [code, ...rest] = l.split(/\s+/)
    return { code, name: rest.join(' ') }
  })
}
export const costCodesText = (rows) => (rows || []).map((r) => `${r.code} ${r.name}`.trim()).join('\n')
export const linesOf = (text) => String(text || '').split('\n').map((l) => l.trim()).filter(Boolean)

// One place for a panel's busy flag and messages. The server's message is shown as it is; a secret the panel just
// sent is cut out of it first (T4), even though the server already strips it.
export function useRun() {
  const busy = ref(false)
  const error = ref('')
  const done = ref('')
  let gone = false
  onBeforeUnmount(() => { gone = true })
  async function run(job, message = '', secret = '') {
    busy.value = true
    error.value = ''
    done.value = ''
    try {
      const out = await job()
      if (!gone) done.value = message
      return { out }
    } catch (e) {
      const text = e.message || 'That did not work. Try again.'
      error.value = secret ? text.split(secret).join('') : text
      return null
    } finally {
      busy.value = false
    }
  }
  return { busy, error, done, run, stopped: () => gone }
}

// The firm's projects, oldest first: the first one is "the first project" of W9 and W10.
export const projects = () => call('frappe.client.get_list', { doctype: 'Construction Project', fields: ['name', 'project_name'], limit_page_length: 50, order_by: 'creation asc' })
