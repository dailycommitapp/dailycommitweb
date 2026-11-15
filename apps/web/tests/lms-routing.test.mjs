import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import { NextRequest } from 'next/server'
import proxy from '../proxy'

const originalFetch = globalThis.fetch
const request = (path, cookie = '') => new NextRequest(`http://localhost:3000${path}`, {
  headers: { host: 'localhost:3000', ...(cookie ? { cookie } : {}) },
})
beforeEach(() => {
  globalThis.fetch = async () => Response.json({ multi_org_enabled: false, default_org_slug: 'default', mode: 'oss', tenancy: 'single', frontend_domain: 'localhost:3000', top_domain: 'localhost' })
})
afterEach(() => { globalThis.fetch = originalFetch })
describe('Public landing and LMS routing', () => {
  test('root serves marketing outside the organization layouts', async () => {
    const response = await proxy(request('/'))
    expect(new URL(response.headers.get('x-middleware-rewrite')).pathname).toBe('/welcome')
    expect(response.headers.get('x-middleware-request-x-dailycommit-public-org')).toBe('default')
  })
  test('single-organization post-login destination goes to courses', async () => {
    const response = await proxy(request('/home'))
    expect(new URL(response.headers.get('location')).pathname).toBe('/courses')
  })
  test('a stale session marker does not bounce login back into the LMS', async () => {
    const response = await proxy(request('/login?next=%2Fcourses', 'LH_session=1'))
    expect(new URL(response.headers.get('x-middleware-rewrite')).pathname).toBe('/auth/login')
    expect(response.headers.get('location')).toBeNull()
  })
  test('protected routes retain the original path and query for returning after login', async () => {
    const response = await proxy(request('/courses?search=java'))
    expect(new URL(response.headers.get('x-middleware-rewrite')).pathname).toBe('/orgs/default/courses')
    expect(response.headers.get('x-middleware-request-x-dailycommit-return-to')).toBe('/courses?search=java')
  })
})
