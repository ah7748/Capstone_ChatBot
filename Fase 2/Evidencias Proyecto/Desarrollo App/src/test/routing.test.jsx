import { render, waitFor } from '@testing-library/react'
import App from '../App'
import { fail, mockFetch } from './utils'

const go = path => window.history.pushState({}, '', path)
const dashboard = {
  kpis: { conversations: 0, bot_resolved_pct: 0, pending_tickets: 0, pending_unassigned: 0,
    escalations: 0, tokens: 0, token_limit_pct: 0 },
  top_topics: [], period: '7d',
}
const me = role => ({ id: 'u1', name: 'Max', email: 'max@test.com', role, tenant_id: 't1',
  tenant_name: 'WellQ', lang: 'es', permissions: [] })

describe('Rutas protegidas por rol', () => {
  it('sin sesión, una ruta protegida redirige a /login', async () => {
    mockFetch({})
    go('/company/documents')
    render(<App />)
    await waitFor(() => expect(window.location.pathname).toBe('/login'))
  })

  it('un company_admin que entra a /platform es devuelto a /company', async () => {
    localStorage.setItem('access_token', 'acc')
    mockFetch({ 'GET /auth/me': me('company_admin'), 'GET /company/dashboard': dashboard })
    go('/platform')
    render(<App />)
    await waitFor(() => expect(window.location.pathname).toBe('/company'))
  })

  it('con un token inválido se limpia la sesión y se va a /login', async () => {
    localStorage.setItem('access_token', 'basura')
    mockFetch({ 'GET /auth/me': fail(401, 'AUTH_TOKEN_INVALID', 'El token es inválido.') })
    go('/console')
    render(<App />)
    await waitFor(() => expect(window.location.pathname).toBe('/login'))
    expect(localStorage.getItem('access_token')).toBeNull()
  })
})
