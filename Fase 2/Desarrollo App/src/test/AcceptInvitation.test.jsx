import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AcceptInvitation from '../pages/AcceptInvitation'
import ResetPassword from '../pages/ResetPassword'
import { fail, json, mockFetch, renderApp } from './utils'

const routes = {
  '/accept-invitation': <AcceptInvitation />,
  '/reset-password': <ResetPassword />,
  '/login': <p>PAGINA LOGIN</p>,
}
const open = (path, q = '?token=abc123') => renderApp(routes, `${path}${q}`)
const pwd = () => document.querySelectorAll('input[type="password"]')
const fillBoth = async (user, v) => { await user.type(pwd()[0], v); await user.type(pwd()[1], v) }

describe('Aceptar invitación', () => {
  it('rechaza una contraseña débil sin llamar a la API', async () => {
    const f = mockFetch({})
    const user = userEvent.setup()
    open('/accept-invitation')
    await fillBoth(user, 'corta')
    await user.click(screen.getByRole('button', { name: 'Activar cuenta' }))
    expect(await screen.findByText(/10\+ caracteres/)).toBeInTheDocument()
    expect(f.calls).toHaveLength(0)
  })

  it('activa la cuenta con el token del enlace y va al login', async () => {
    const f = mockFetch({ 'POST /auth/invitations/accept': () => json({ activated: true }) })
    const user = userEvent.setup()
    open('/accept-invitation')
    await fillBoth(user, 'Password123!')
    await user.click(screen.getByRole('button', { name: 'Activar cuenta' }))
    expect(await screen.findByText('PAGINA LOGIN')).toBeInTheDocument()
    expect(JSON.parse(f.called('POST /auth/invitations/accept')[0].opts.body))
      .toMatchObject({ invitation_token: 'abc123', password: 'Password123!' })
  })

  it('muestra el error si la invitación expiró', async () => {
    mockFetch({ 'POST /auth/invitations/accept':
      fail(410, 'INVITE_EXPIRED', 'La invitación expiró; el administrador debe reenviarla.') })
    const user = userEvent.setup()
    open('/accept-invitation')
    await fillBoth(user, 'Password123!')
    await user.click(screen.getByRole('button', { name: 'Activar cuenta' }))
    expect(await screen.findByText(/INVITE_EXPIRED/)).toBeInTheDocument()
  })

  it('abre la pantalla en el idioma indicado en el enlace', async () => {
    mockFetch({})
    const user = userEvent.setup()
    open('/accept-invitation', '?token=abc123&lang=en')
    try {
      expect(await screen.findByRole('button', { name: 'Activate account' })).toBeInTheDocument()
    } finally {
      await user.click(screen.getByRole('button', { name: 'ES' }))
    }
  })
})

describe('Restablecer contraseña', () => {
  it('envía el token y la nueva contraseña, y va al login', async () => {
    const f = mockFetch({ 'POST /auth/password/reset-confirm': () => json({ reset: true }) })
    const user = userEvent.setup()
    open('/reset-password', '?token=rst999')
    await fillBoth(user, 'NuevaClave123')
    await user.click(screen.getByRole('button', { name: 'Restablecer contraseña' }))
    expect(await screen.findByText('PAGINA LOGIN')).toBeInTheDocument()
    expect(JSON.parse(f.called('POST /auth/password/reset-confirm')[0].opts.body))
      .toEqual({ reset_token: 'rst999', new_password: 'NuevaClave123' })
  })

  it('muestra el error si el enlace ya fue usado', async () => {
    mockFetch({ 'POST /auth/password/reset-confirm':
      fail(400, 'RESET_INVALID', 'Token inexistente o ya usado.') })
    const user = userEvent.setup()
    open('/reset-password', '?token=viejo')
    await fillBoth(user, 'NuevaClave123')
    await user.click(screen.getByRole('button', { name: 'Restablecer contraseña' }))
    expect(await screen.findByText(/RESET_INVALID/)).toBeInTheDocument()
  })
})