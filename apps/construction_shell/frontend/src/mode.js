// The person's view, Simple or Advanced (P3-01, D-154), kept on the server (construction_shell.preferences) and
// arriving in the boot. A view preference only: the server decides every read and write whatever the mode.
import { inject, ref } from 'vue'
import { boot } from './boot.js'
import { call } from './api.js'
import { normal } from './words.js'

const mode = ref(normal(boot.mode))

// A screen asks for the mode through useMode(), so a parent can supply another one: the staff preview of a client's
// portal (P3-05) shows that client's mode, not the viewer's.
export const MODE_KEY = Symbol('cc-view-mode')

export function useMode() {
  return inject(MODE_KEY, mode)
}

export async function setMode(next) {
  const value = normal(next)
  if (value === mode.value) return
  const before = mode.value
  mode.value = value // the screen follows at once
  try {
    await call('construction_shell.preferences.set_mode', { mode: value }, { post: true })
  } catch {
    mode.value = before // not saved: the view shows what the server keeps
  }
}
