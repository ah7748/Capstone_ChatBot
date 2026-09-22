// Cliente HTTP: Bearer JWT + renovación automática con el refresh token (rotación).
const BASE = import.meta.env.VITE_API_URL || ''

let refreshing = null

export function getTokens() {
  return {
    access: localStorage.getItem('access_token'),
    refresh: localStorage.getItem('refresh_token'),
  }
}

export function setTokens({ access_token, refresh_token }) {
  if (access_token) localStorage.setItem('access_token', access_token)
  if (refresh_token) localStorage.setItem('refresh_token', refresh_token)
}

export function clearTokens() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export class ApiError extends Error {
  constructor(status, code, message, detail) {
    super(message)
    this.status = status
    this.code = code
    this.detail = detail
  }
}

async function parseError(res) {
  let body = null
  try { body = await res.json() } catch { /* vacío */ }
  const e = body?.error || {}
  return new ApiError(res.status, e.code || 'HTTP_' + res.status,
    e.message || res.statusText, e.detail)
}

async function doRefresh() {
  const { refresh } = getTokens()
  if (!refresh) throw new ApiError(401, 'AUTH_REFRESH_INVALID', 'Sesión expirada')
  const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!res.ok) { clearTokens(); throw await parseError(res) }
  const data = await res.json()
  setTokens(data)
  return data.access_token
}

/**
 * api('/company/faqs', {method, body, form, token, raw})
 *  - body: objeto JSON · form: FormData · token: sobrescribe el Bearer (session token del chat)
 *  - raw: true devuelve la Response (para descargas)
 */
export async function api(path, opts = {}) {
  const { method = 'GET', body, form, token, raw = false, _retried = false } = opts
  const headers = {}
  const auth = token || getTokens().access
  if (auth) headers.Authorization = `Bearer ${auth}`
  let payload
  if (form) payload = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`${BASE}/api/v1${path}`, { method, headers, body: payload })
  if (res.status === 401 && !token && !_retried) {
    const err = await res.clone().json().catch(() => null)
    if (err?.error?.code === 'AUTH_TOKEN_EXPIRED') {
      refreshing = refreshing || doRefresh().finally(() => { refreshing = null })
      await refreshing
      return api(path, { ...opts, _retried: true })
    }
  }
  if (!res.ok) throw await parseError(res)
  if (raw) return res
  if (res.status === 204) return null
  return res.json()
}

export function wsUrl(path) {
  const base = BASE || window.location.origin
  return base.replace(/^http/, 'ws') + path
}
