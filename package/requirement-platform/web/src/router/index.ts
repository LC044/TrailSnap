import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

export type AppTab = 'public' | 'dashboard' | 'submit' | 'mine' | 'admin' | 'versions' | 'usage' | 'integrations' | 'ai-settings' | 'users'

// App.vue still owns the shell while pages are migrated one at a time. Route
// records are authoritative for URLs and browser history during that migration.
const RouteTarget = { render: () => null }
const tabRoutes: Array<[AppTab, string]> = [
  ['public', '/'],
  ['dashboard', '/dashboard'],
  ['submit', '/requirements/new'],
  ['mine', '/requirements/mine'],
  ['admin', '/admin/requirements'],
  ['versions', '/versions'],
  ['usage', '/usage'],
  ['integrations', '/settings/integrations'],
  ['ai-settings', '/settings/ai'],
  ['users', '/settings/users'],
]

const routes: RouteRecordRaw[] = [
  ...tabRoutes.map(([name, path]) => ({ path, name, component: RouteTarget, meta: { tab: name } })),
  { path: '/requirements/REQ-:number(\\d+)', name: 'requirement-detail', component: RouteTarget, meta: { tab: 'public' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({ history: createWebHistory(), routes })
