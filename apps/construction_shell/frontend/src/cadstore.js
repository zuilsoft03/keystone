// What Open CAD Studio leaves in this site's browser storage (P3-48, audit M1). It runs in a frame on our origin, so it
// shares our storage. On every open and save it keeps a copy of the drawing in the origin-private file system, and it
// keeps the names of recent drawings and open tabs in localStorage (upstream 0e4c4c3: src/io/web_recent.rs,
// web_autosave.rs, web_session.rs, app/config.rs). None of that may outlive the viewer, the user's session or their
// right to the file. So the viewer turns autosave off, and the copies are wiped when a viewer closes, when any of our
// pages starts and before a sign-out. A lock keeps a wipe from running under a viewer open in another tab.
export const CAD_DIRS = ['opencadstudio-recent', 'opencadstudio-autosave']
export const CAD_KEYS = ['opencadstudio.settings', 'opencadstudio.session']
// Autosave off (settings.savetime_min = 0 never fires; read at start, and changed only by Options or SAVETIME in Edit,
// whose snapshots the wipes take). The partial JSON parses: AppConfig and UserSettings are #[serde(default)].
export const CAD_SETTINGS = '{"settings":{"savetime_min":0}}'
export const CAD_LOCK = 'opencadstudio-frame'
export const CAD_PREFIX = '/assets/construction_core/vendor/opencadstudio-'

const storeOf = () => {
  try {
    return globalThis.localStorage
  } catch {
    return null // site data blocked
  }
}

// Removes the copies; true when nothing was left behind.
export async function wipeCad({ nav = globalThis.navigator, store = storeOf(), cacheStore = globalThis.caches, origin = globalThis.location?.origin } = {}) {
  try {
    for (const key of CAD_KEYS) store?.removeItem(key)
  } catch { /* site data blocked */ }
  let clean = true
  // A service worker an older build registered may have cached what the frame fetched: keep only the program's files.
  try {
    for (const name of (await cacheStore?.keys?.()) || []) {
      if (!name.startsWith('ocs-app-')) continue
      const cache = await cacheStore.open(name)
      for (const req of await cache.keys()) {
        const url = new URL(req.url)
        if (url.origin !== origin || !url.pathname.startsWith(CAD_PREFIX)) await cache.delete(req)
      }
    }
  } catch {
    clean = false
  }
  let root
  try {
    root = await nav?.storage?.getDirectory?.()
  } catch {
    return clean // no origin-private file system here: nothing was stored in it
  }
  if (!root) return clean
  for (const name of CAD_DIRS) {
    try {
      await root.removeEntry(name, { recursive: true })
    } catch (e) {
      if (e?.name !== 'NotFoundError') clean = false
    }
  }
  return clean
}

// A wipe that waits for no one: it runs only when no viewer holds the lock in any tab (force: at sign-out).
export function wipeCadWhenIdle({ force = false, ...env } = {}) {
  const nav = env.nav ?? globalThis.navigator
  if (force || !nav?.locks) return wipeCad(env)
  return nav.locks.request(CAD_LOCK, { mode: 'exclusive', ifAvailable: true }, (lock) => (lock ? wipeCad(env) : false)).catch(() => false)
}

// Before the frame loads: autosave off, and no donation prompt (docs/automation/web.md).
export function primeCad(store = storeOf()) {
  try {
    store?.setItem('opencadstudio.settings', CAD_SETTINGS)
    store?.setItem('opencadstudio.automation', '1')
  } catch { /* site data blocked: the program starts with its defaults */ }
}

// Held, shared, for the life of a viewer's frame; resolves with the function that lets it go, which resolves once the
// lock is really free (a wipe asked for at once would otherwise find it still held).
export async function holdCadLock(nav = globalThis.navigator) {
  if (!nav?.locks) return async () => {}
  let release
  let done
  const held = new Promise((resolve) => (release = resolve))
  const ok = await new Promise((granted) => {
    done = nav.locks.request(CAD_LOCK, { mode: 'shared' }, () => {
      granted(true)
      return held
    }).catch(() => granted(false))
  })
  return ok ? () => { release(); return done } : async () => {}
}

// While a viewer runs: its copies go as soon as they are made, unless another tab's viewer holds the lock too (a wipe
// under its open would fail that open). The lock is ours, so this wipes without waiting for it.
export async function wipeCadIfAlone({ nav = globalThis.navigator, ...env } = {}) {
  try {
    const held = (await nav?.locks?.query?.())?.held || []
    if (held.filter((l) => l.name === CAD_LOCK).length > 1) return false
  } catch {
    return false
  }
  return wipeCad({ nav, ...env })
}
