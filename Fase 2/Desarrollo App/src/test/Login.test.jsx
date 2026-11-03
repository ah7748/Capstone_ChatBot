import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Login from '../pages/Login'
import { fail, mockFetch, renderApp } from './utils'

const pages = {
  '/login': <Login />,
  '/platform': <p>HOME platform</p>,
  '/company': <p>HOME company</p>,
  '/console': <p>HOME console</p>,
}
const me = role => ({ id: 'u1', name: 'Usuario Test', email: 'u@test.com', role,
  tenant_id: null, lang: 'es', tenant_name: null, permissions: [] })

async function fill(user, email, pass, emailPh = 'tu@empresa.com') {
  await user.type(screen.getByPlaceholderText(emailPh), email)
  await user.type(screen.getByPlaceholderText('••••••••••'), pass)
}

describe('Login', () => {
  it.each([
    ['platform_admin', 'HOME platform'],
    ['company_admin', 'HOME company'],
    ['human_agent', 'HOME console'],
  ])('un %s es llevado a su interfaz', async (role, home) => {
    const f = mockFetch({
      'POST /auth/login': { access_token: 'acc', refresh_token: 'ref', expires_in: 1800, user: me(role) },
      'GET /auth/me': me(role),
    })
    const user = userEvent.setup()
    renderApp(pages, '/login')
    await fill(user, 'u@test.com', 'Password123!')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText(home)).toBeInTheDocument()
    expect(localStorage.getItem('access_token')).toBe('acc')
    expect(JSON.parse(f.called('POST /auth/login')[0].opts.body))
      .toEqual({ email: 'u@test.com', password: 'Password123!' })
  })

  it('con credenciales incorrectas muestra el error y no guarda sesión', async () => {
    mockFetch({ 'POST /auth/login':
      fail(401, 'AUTH_INVALID_CREDENTIALS', 'Email o contraseña incorrectos.') })
    const user = userEvent.setup()
    renderApp(pages, '/login')
    await fill(user, 'u@test.com', 'malamala1')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText(/Email o contraseña incorrectos/)).toBeInTheDocument()
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(screen.queryByText(/HOME/)).not.toBeInTheDocument()
  })

  it('el error se muestra traducido al cambiar de idioma en el login', async () => {
    mockFetch({ 'POST /auth/login':
      fail(401, 'AUTH_INVALID_CREDENTIALS', 'Email o contraseña incorrectos.') })
    const user = userEvent.setup()
    renderApp(pages, '/login')
    try {
      await user.click(screen.getByRole('button', { name: 'EN' }))
      await fill(user, 'u@test.com', 'malamala1', 'you@company.com')
      await user.click(screen.getByRole('button', { name: 'Sign in' }))
      expect(await screen.findByText(/Incorrect email or password/)).toBeInTheDocument()
    } finally {
      await user.click(screen.getByRole('button', { name: 'ES' }))
    }
  })
})
