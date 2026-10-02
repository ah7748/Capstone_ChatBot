import { ApiError, api, getTokens, setTokens, wsUrl } from '../api/client'
import { fail, json, mockFetch } from './utils'

const expired = () => json({ error: { code: 'AUTH_TOKEN_EXPIRED', message: 'expiró' } }, 401)

describe('api client', () => {
  it('envía Bearer y Accept-Language', async () => {
    setTokens({ access_token: 'abc', refresh_token: 'r' })
    localStorage.setItem('lang', 'pt')
    const f = mockFetch({ 'GET /auth/me': { id: 1 } })
    await expect(api('/auth/me')).resolves.toEqual({ id: 1 })
    const { headers } = f.calls[0].opts
    expect(headers.Authorization).toBe('Bearer abc')
    expect(headers['Accept-Language']).toBe('pt')
  })

  it('lanza ApiError con status, code y message de la API', async () => {
    mockFetch({ 'GET /x': fail(409, 'DOCUMENT_DUPLICATE', 'Ya existe un documento idéntico.') })
    const err = await api('/x').catch(e => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 409, code: 'DOCUMENT_DUPLICATE' })
    expect(err.message).toBe('Ya existe un documento idéntico.')
  })

  it('ante AUTH_TOKEN_EXPIRED renueva el token y reintenta una vez', async () => {
    setTokens({ access_token: 'old', refresh_token: 'r1' })
    let n = 0
    const f = mockFetch({
      'GET /company/dashboard': () => (++n === 1 ? expired() : json({ ok: true })),
      'POST /auth/refresh': { access_token: 'new', refresh_token: 'r2', expires_in: 1800 },
    })
    await expect(api('/company/dashboard')).resolves.toEqual({ ok: true })
    expect(getTokens()).toEqual({ access: 'new', refresh: 'r2' })
    expect(JSON.parse(f.called('POST /auth/refresh')[0].opts.body)).toEqual({ refresh_token: 'r1' })
    const retry = f.called('GET /company/dashboard')[1]
    expect(retry.opts.headers.Authorization).toBe('Bearer new')
  })

  it('si la renovación falla, limpia la sesión y propaga el error', async () => {
    setTokens({ access_token: 'old', refresh_token: 'r1' })
    mockFetch({
      'GET /a': expired,
      'POST /auth/refresh': fail(401, 'AUTH_REFRESH_REUSED', 'Reutilización detectada'),
    })
    const err = await api('/a').catch(e => e)
    expect(err.code).toBe('AUTH_REFRESH_REUSED')
    expect(getTokens()).toEqual({ access: null, refresh: null })
  })

  it('varias peticiones expiradas a la vez comparten una sola renovación', async () => {
    setTokens({ access_token: 'old', refresh_token: 'r1' })
    const ok = (o) => (o.headers.Authorization === 'Bearer new' ? { ok: true } : expired())
    const f = mockFetch({
      'GET /a': ok,
      'GET /b': ok,
      'POST /auth/refresh': async () => {
        await new Promise(r => setTimeout(r, 20))
        return { access_token: 'new', refresh_token: 'r2' }
      },
    })
    await Promise.all([api('/a'), api('/b')])
    expect(f.called('POST /auth/refresh')).toHaveLength(1)
  })

  it('devuelve null en respuestas 204', async () => {
    mockFetch({ 'DELETE /x': () => json(null, 204) })
    await expect(api('/x', { method: 'DELETE' })).resolves.toBeNull()
  })

  it('wsUrl convierte http(s) en ws(s)', () => {
    expect(wsUrl('/ws/agent?token=t')).toMatch(/^ws:\/\/.+\/ws\/agent\?token=t$/)
  })
})
