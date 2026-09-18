import { createContext, useContext, useState } from 'react'

// Diccionario de interfaz (ES base → EN, PT), heredado del wireframe v5.
const D = {
  'Módulo de administración': ['Administration module', 'Módulo de administração'],
  'Iniciar sesión': ['Sign in', 'Entrar'],
  'Correo electrónico': ['Email', 'E-mail'],
  'Contraseña': ['Password', 'Senha'],
  'Entrar': ['Sign in', 'Entrar'],
  'Cerrar sesión': ['Log out', 'Sair'],
  'Dashboard global': ['Global dashboard', 'Painel global'],
  'Empresas cliente': ['Client companies', 'Empresas clientes'],
  'Agentes de soporte': ['Support agents', 'Agentes de suporte'],
  'Configuración': ['Settings', 'Configuração'],
  'Dashboard': ['Dashboard', 'Painel'],
  'Documentos del cliente': ['Client documents', 'Documentos do cliente'],
  'Agentes del bot': ['Bot agents', 'Agentes do bot'],
  'Agentes humanos': ['Human agents', 'Agentes humanos'],
  'Canales del chat': ['Chat channels', 'Canais do chat'],
  'Consola de agente': ['Agent console', 'Console do agente'],
  'Conversaciones': ['Conversations', 'Conversas'],
  'Resueltas por el bot': ['Resolved by the bot', 'Resolvidas pelo bot'],
  'Tickets pendientes': ['Pending tickets', 'Tickets pendentes'],
  'Derivadas a agente': ['Escalated to agents', 'Encaminhadas a agente'],
  'Tokens consumidos': ['Tokens used', 'Tokens consumidos'],
  'Ver detalle →': ['View detail →', 'Ver detalhe →'],
  'Documentos': ['Documents', 'Documentos'],
  'Preguntas frecuentes': ['FAQs', 'Perguntas frequentes'],
  'Sitio web': ['Website', 'Site'],
  'Todos': ['All', 'Todos'],
  'Chat técnico': ['Technical chat', 'Chat técnico'],
  'Chat comercial': ['Commercial chat', 'Chat comercial'],
  'Subir documento': ['Upload document', 'Enviar documento'],
  'Escanear sitio del cliente': ['Scan client website', 'Escanear site do cliente'],
  'Agregar sugerencias': ['Add suggestions', 'Adicionar sugestões'],
  'Exportar:': ['Export:', 'Exportar:'],
  'Añadir': ['Add', 'Adicionar'],
  'Añadir todas': ['Add all', 'Adicionar todas'],
  'Ver': ['View', 'Ver'],
  'Editar': ['Edit', 'Editar'],
  'Eliminar': ['Delete', 'Excluir'],
  'Guardar': ['Save', 'Salvar'],
  'Cancelar': ['Cancel', 'Cancelar'],
  'Cerrar': ['Close', 'Fechar'],
  'Gestionar': ['Manage', 'Gerenciar'],
  'Nueva empresa': ['New company', 'Nova empresa'],
  'Nuevo agente humano': ['New human agent', 'Novo agente humano'],
  'Recibe derivaciones de': ['Receives escalations from', 'Recebe encaminhamentos de'],
  'Canal': ['Channel', 'Canal'],
  'Estado': ['Status', 'Status'],
  'Acciones': ['Actions', 'Ações'],
  'En vivo': ['Live', 'Ao vivo'],
  'Tomar conversación': ['Take conversation', 'Assumir conversa'],
  'Devolver al bot': ['Return to bot', 'Devolver ao bot'],
  'Resolver': ['Resolve', 'Resolver'],
  'Enviar': ['Send', 'Enviar'],
  'Respuestas sugeridas (IA)': ['Suggested replies (AI)', 'Respostas sugeridas (IA)'],
  'Usar respuesta': ['Use reply', 'Usar resposta'],
  'Usuario': ['User', 'Usuário'],
  'Motivo': ['Reason', 'Motivo'],
  'Consumo de tokens': ['Token usage', 'Consumo de tokens'],
  'Datos de la empresa': ['Company details', 'Dados da empresa'],
  'Bots por canal en uso': ['Bots in use by channel', 'Bots em uso por canal'],
  'Solo lectura': ['Read-only', 'Somente leitura'],
  'Cargando…': ['Loading…', 'Carregando…'],
  'Hoy': ['Today', 'Hoje'],
  'Últimos 7 días': ['Last 7 days', 'Últimos 7 dias'],
  'Últimos 30 días': ['Last 30 days', 'Últimos 30 dias'],
  'Mes anterior': ['Previous month', 'Mês anterior'],
  'Últimos 3 meses': ['Last 3 months', 'Últimos 3 meses'],
  'Año': ['Year', 'Ano'],
  'Escribe tu consulta…': ['Type your question…', 'Escreva sua dúvida…'],
  'Hablar con una persona': ['Talk to a person', 'Falar com uma pessoa'],
}

export const PERIOD_OPTIONS = [
  ['7d', 'Últimos 7 días'], ['today', 'Hoy'], ['prev_month', 'Mes anterior'],
  ['30d', 'Últimos 30 días'], ['3m', 'Últimos 3 meses'], ['year', 'Año'],
]

const I18nCtx = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem('lang') || 'es')
  const t = (key) => {
    if (lang === 'es') return key
    const entry = D[key]
    return entry ? entry[lang === 'en' ? 0 : 1] : key
  }
  const change = (l) => { setLang(l); localStorage.setItem('lang', l) }
  return <I18nCtx.Provider value={{ lang, setLang: change, t }}>{children}</I18nCtx.Provider>
}

export const useI18n = () => useContext(I18nCtx)
