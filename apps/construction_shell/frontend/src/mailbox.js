// The evidence mailbox's confirm page (P3-77, approvals design §3.2 item 3). construction_core's /evidence-mailbox page
// serves no data; the button posts the link's token to construction_core.approvals.api.confirm_evidence_mailbox.
import { createApp } from 'vue'
import { wipeCadWhenIdle } from './cadstore.js'
import { FrappeUI, useColorScheme } from 'frappe-ui'
import 'frappe-ui/style.css'
import './style.css'
import MailboxApp from './mailbox/App.vue'

useColorScheme() // the viewer's saved Light/Dark choice, as on the join page (D-126)

createApp(MailboxApp).use(FrappeUI).mount('#app')
wipeCadWhenIdle() // P3-48: drawing copies a CAD viewer left in this browser (cadstore.js)
