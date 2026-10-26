import { createRouter, createWebHistory } from 'vue-router'
import { knownPath } from './paths.js'
import NotFound from './pages/NotFound.vue'

// The URL is the source of truth (ARCHITECTURE §3.4): /workspace/:project/:section[/:item[/:action]].
export const routes = [
  { path: '/', name: 'projects', component: () => import('./pages/Dashboard.vue') },
  // P3-21 (D-235): System Managers only; the server checks every call. Before /:project, which would take it.
  { path: '/people', name: 'people', component: () => import('./pages/People.vue') },
  // P3-45 (D-300): the owner's Brand page, System Managers only (the server checks every call); before /:project too.
  { path: '/brand', name: 'brand', component: () => import('./pages/Brand.vue') },
  // P3-52 (D-347): the set-up wizard; the server sends a System Manager here until set-up is finished. P3-58: the Company page. Both before /:project.
  { path: '/setup', name: 'setup', component: () => import('./pages/Setup.vue') },
  { path: '/company', name: 'company', component: () => import('./pages/Company.vue') },
  // P3-74 (§14.6): the staff Discussion inbox across their projects; before /:project, as /people is.
  { path: '/discussion', name: 'discussion', component: () => import('./pages/Inbox.vue') },
  {
    path: '/:project',
    component: () => import('./pages/ProjectLayout.vue'),
    children: [
      { path: '', name: 'project', redirect: (to) => ({ name: 'section', params: { ...to.params, section: 'home' } }) },
      { path: ':section/:item?/:action?', name: 'section', component: () => import('./pages/SectionView.vue') },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFound },
]

const router = createRouter({ history: createWebHistory('/workspace/'), routes })

// A path the server would refuse (sections.json) never renders a page in the app either.
router.beforeEach((to) => {
  if (to.name !== 'not-found' && !knownPath('/workspace' + to.path)) {
    return { name: 'not-found', params: { pathMatch: to.path.split('/').filter(Boolean) }, query: to.query, hash: to.hash }
  }
})

export default router
