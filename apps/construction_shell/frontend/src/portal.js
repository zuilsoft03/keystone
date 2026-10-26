// The client portal on the shell (P2-06, D-121). construction_core's /portal page has checked the client before this
// loads; every read goes to construction_core.portal_api and discuss.api, which check each call again.
import { createApp } from 'vue'
import { wipeCadWhenIdle } from './cadstore.js'
import { FrappeUI, useColorScheme } from 'frappe-ui'
import 'frappe-ui/style.css'
import './style.css'
import PortalApp from './portal/PortalApp.vue'
import router from './portal/router.js'

// The saved Light/Dark choice (D-126) is applied before the app mounts; the account menu changes it.
useColorScheme()

const app = createApp(PortalApp)
app.use(router)
app.use(FrappeUI)
app.mount('#app')
wipeCadWhenIdle() // P3-48: drawing copies a CAD viewer left in this browser (cadstore.js)
