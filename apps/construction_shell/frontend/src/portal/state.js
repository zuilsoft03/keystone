// What the portal's bar shows (P2-10): the open project's name and visible tabs, and how many requests wait for the client (P3-79). Project.vue fills it from
// portal_api.project_data; every other page clears it. Not a permission: the server checks every call.
import { reactive, ref } from 'vue'

export const portal = reactive({ project: '', title: '', tabs: [], tab: '', waiting: 0 })

export function clearPortal() {
  Object.assign(portal, { project: '', title: '', tabs: [], tab: '', waiting: 0 })
}

// A phone (the design's PortalMobile): the tabs move to a bottom bar and Discussion shows the list, then a thread.
const query = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(max-width: 767px)') : null
export const isPhone = ref(Boolean(query && query.matches))
if (query) query.addEventListener('change', (e) => (isPhone.value = e.matches))
