import { createContext, useContext, useEffect, useState } from 'react'
import { api, clearTokens, getTokens, setTokens } from '../api/client'

const AuthCtx = createContext(null)

// El login es único: el backend devuelve el rol y App.jsx monta la interfaz correspondiente.
export const HOME_BY_ROLE = {
  platform_admin: '/platform',
  company_admin: '/company',
  human_agent: '/console',
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(true)

  useEffect(() => {
    (async () => {
      if (getTokens().access) {
        try { setUser(await api('/auth/me')) } catch { clearTokens() }
      }
      setBooting(false)
    })()
  }, [])

  async function login(email, password) {
    const data = await api('/auth/login', { method: 'POST', body: { email, password } })
    setTokens(data)
    const me = await api('/auth/me')
    setUser(me)
    return me
  }

  async function logout() {
    const { refresh } = getTokens()
    try { await api('/auth/logout', { method: 'POST', body: { refresh_token: refresh } }) }
    catch { /* la sesión local se cierra igual */ }
    clearTokens()
    setUser(null)
  }

  return (
    <AuthCtx.Provider value={{ user, booting, login, logout }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)
