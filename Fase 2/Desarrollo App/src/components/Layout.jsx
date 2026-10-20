import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../context/I18nContext'
import { useTheme } from '../context/ThemeContext'

export function Topbar({ onMenu }) {
  const { user, logout } = useAuth()
  const { lang, setLang, t } = useI18n()
  const { dark, toggle } = useTheme()
  const nav = useNavigate()
  return (
    <div className="topbar">
      {onMenu && (
        <button className="menu-btn" onClick={onMenu} aria-label="Menu">☰</button>
      )}
      <span className="logo-fallback">allo<span>x</span>entric</span>
      <div className="product-name">
        <b>Chatbot de Soporte Genérico</b>{t('Módulo de administración')}
      </div>
      <div className="lang-switch">
        {['es', 'en', 'pt'].map(l => (
          <button key={l} className={`lang-btn ${lang === l ? 'active' : ''}`}
            onClick={() => setLang(l)}>{l.toUpperCase()}</button>
        ))}
      </div>
      <button className="theme-toggle" onClick={toggle}>
        {dark ? '☀️' : '🌙'}
      </button>
      {user && (
        <div className="user-chip">
          <span>👤 {user.name}{user.tenant_name ? ` · ${user.tenant_name}` : ''}</span>
          <button className="btn btn-sm" onClick={async () => { await logout(); nav('/login') }}>
            {t('Cerrar sesión')}
          </button>
        </div>
      )}
    </div>
  )
}

export function Shell({ menu, children }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()

  // al cambiar de página, el menú se cierra solo
  useEffect(() => { setOpen(false) }, [pathname])

  return (
    <>
      <Topbar onMenu={() => setOpen(o => !o)} />
      <div className="app">
        {open && <div className="side-backdrop" onClick={() => setOpen(false)} />}
        <aside className={`sidebar ${open ? 'open' : ''}`}>
          {menu.map(section => (
            <div key={section.title}>
              <div className="side-title">{t(section.title)}</div>
              {section.items.map(([to, icon, label]) => (
                <NavLink key={to} to={to} end className={({ isActive }) =>
                  `side-link ${isActive ? 'active' : ''}`}>
                  <span>{icon}</span>{t(label)}
                </NavLink>
              ))}
            </div>
          ))}
        </aside>
        <main className="main">{children}</main>
      </div>
    </>
  )
}