import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { I18nProvider } from '../context/I18nContext'
import { ThemeProvider } from '../context/ThemeContext'
import { ToastProvider } from '../components/ui'

export const json = (body, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' } })

/** Handler de error con el formato de la API: { error: { code, message } } */
export const fail = (status, code, message = 'error') => () =>
  json({ error: { code, message } }, status)

/**
 * Sustituye fetch. routes: { 'METHOD /ruta': objeto | (opts) => objeto | Response }
 * Usa objetos planos o funciones (un Response estático solo se puede leer una vez).
 * Devuelve el mock con .calls y .called('METHOD /ruta').
 */
export function mockFetch(routes) {
  const calls = []
  const fn = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase()
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0]
    const key = `${method} ${path}`
    calls.push({ key, url: String(url), opts })
    const handler = routes[key]
    if (!handler) return json({ error: { code: 'NOT_MOCKED', message: key } }, 404)
    const res = typeof handler === 'function' ? await handler(opts) : handler
    return res instanceof Response ? res : json(res)
  })
  vi.stubGlobal('fetch', fn)
  fn.calls = calls
  fn.called = (key) => calls.filter(c => c.key === key)
  return fn
}

/** Renderiza con todos los providers. routes: { '/ruta': <Elemento /> } */
export function renderApp(routes, route = '/') {
  return render(
    <I18nProvider>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <MemoryRouter initialEntries={[route]}>
              <Routes>
                {Object.entries(routes).map(([path, el]) => (
                  <Route key={path} path={path} element={el} />
                ))}
              </Routes>
            </MemoryRouter>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </I18nProvider>,
  )
}
