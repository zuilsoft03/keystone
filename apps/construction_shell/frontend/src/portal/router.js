import { createRouter, createWebHistory } from 'vue-router'
import NotFound from '../pages/NotFound.vue'

// The server's shapes (construction_core/www/ws_portal.py): /portal, /portal/<project>, /portal/<project>/whiteboard/<b>.
// A tab is a query (?tab=files), so the app adds no path the server does not know.
export const routes = [
  { path: '/', name: 'portal-home', component: () => import('./Projects.vue') },
  { path: '/:project', name: 'portal-project', component: () => import('./Project.vue') },
  { path: '/:project/whiteboard/:board', name: 'portal-board', component: () => import('./Board.vue') },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFound },
]

export default createRouter({ history: createWebHistory('/portal/'), routes })
