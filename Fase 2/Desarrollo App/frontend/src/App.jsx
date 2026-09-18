import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Shell } from './components/Layout'
import { AuthProvider, HOME_BY_ROLE, useAuth } from './context/AuthContext'
import { I18nProvider } from './context/I18nContext'
import { ThemeProvider } from './context/ThemeContext'
import { ToastProvider } from './components/ui'

import Login from './pages/Login'
import PlatformDashboard from './pages/platform/PlatformDashboard'
import Tenants from './pages/platform/Tenants'
import PlatformAgents from './pages/platform/PlatformAgents'
import PlatformSettings from './pages/platform/PlatformSettings'
import CompanyDashboard from './pages/company/CompanyDashboard'
import Documents from './pages/company/Documents'
import BotAgents from './pages/company/BotAgents'
import HumanAgents from './pages/company/HumanAgents'
import Channels from './pages/company/Channels'
import CompanySettings from './pages/company/CompanySettings'
import Console from './pages/agent/Console'
import ChatPage from './pages/public/ChatPage'

const PLATFORM_MENU = [{ title: 'Alloxentric · Plataforma', items: [
  ['/platform', '📊', 'Dashboard global'],
  ['/platform/tenants', '🏷️', 'Empresas cliente'],
  ['/platform/agents', '🎧', 'Agentes de soporte'],
  ['/platform/settings', '⚙️', 'Configuración'],
] }]

const COMPANY_MENU = [{ title: 'Empresa', items: [
  ['/company', '📊', 'Dashboard'],
  ['/company/documents', '📁', 'Documentos del cliente'],
  ['/company/bot-agents', '🤖', 'Agentes del bot'],
  ['/company/human-agents', '🧑‍💼', 'Agentes humanos'],
  ['/company/channels', '🔗', 'Canales del chat'],
  ['/company/settings', '⚙️', 'Configuración'],
] }]

/** Protege una sección por rol. El login es único: aquí solo se controla el acceso. */
function RequireRole({ role, children }) {
  const { user, booting } = useAuth()
  const location = useLocation()
  if (booting) return <div className="center" style={{ minHeight: '100vh' }}>…</div>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  if (user.role !== role) return <Navigate to={HOME_BY_ROLE[user.role] || '/login'} replace />
  return children
}

function HomeRedirect() {
  const { user, booting } = useAuth()
  if (booting) return <div className="center" style={{ minHeight: '100vh' }}>…</div>
  return <Navigate to={user ? HOME_BY_ROLE[user.role] : '/login'} replace />
}

export default function App() {
  return (
    <I18nProvider>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<HomeRedirect />} />
                <Route path="/login" element={<Login />} />
                {/* Chat público del usuario final (sin login) */}
                <Route path="/c/:slug" element={<ChatPage />} />

                {/* Admin de plataforma */}
                <Route path="/platform" element={<RequireRole role="platform_admin">
                  <Shell menu={PLATFORM_MENU}><PlatformDashboard /></Shell></RequireRole>} />
                <Route path="/platform/tenants" element={<RequireRole role="platform_admin">
                  <Shell menu={PLATFORM_MENU}><Tenants /></Shell></RequireRole>} />
                <Route path="/platform/agents" element={<RequireRole role="platform_admin">
                  <Shell menu={PLATFORM_MENU}><PlatformAgents /></Shell></RequireRole>} />
                <Route path="/platform/settings" element={<RequireRole role="platform_admin">
                  <Shell menu={PLATFORM_MENU}><PlatformSettings /></Shell></RequireRole>} />

                {/* Admin de empresa */}
                <Route path="/company" element={<RequireRole role="company_admin">
                  <Shell menu={COMPANY_MENU}><CompanyDashboard /></Shell></RequireRole>} />
                <Route path="/company/documents" element={<RequireRole role="company_admin">
                  <Shell menu={COMPANY_MENU}><Documents /></Shell></RequireRole>} />
                <Route path="/company/bot-agents" element={<RequireRole role="company_admin">
                  <Shell menu={COMPANY_MENU}><BotAgents /></Shell></RequireRole>} />
                <Route path="/company/human-agents" element={<RequireRole role="company_admin">
                  <Shell menu={COMPANY_MENU}><HumanAgents /></Shell></RequireRole>} />
                <Route path="/company/channels" element={<RequireRole role="company_admin">
                  <Shell menu={COMPANY_MENU}><Channels /></Shell></RequireRole>} />
                <Route path="/company/settings" element={<RequireRole role="company_admin">
                  <Shell menu={COMPANY_MENU}><CompanySettings /></Shell></RequireRole>} />

                {/* Consola de agente humano */}
                <Route path="/console" element={<RequireRole role="human_agent">
                  <Console /></RequireRole>} />

                <Route path="*" element={<HomeRedirect />} />
              </Routes>
            </BrowserRouter>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </I18nProvider>
  )
}
