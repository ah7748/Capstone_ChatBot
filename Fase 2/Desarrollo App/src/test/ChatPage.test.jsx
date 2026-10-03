import { act, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ChatPage from '../pages/public/ChatPage'
import { fail, json, mockFetch, renderApp } from './utils'

const SESSION = {
  session_id: 's1', session_token: 'tok-123', ws_url: 'ws://test/ws/chat/s1',
  config: { bot_name: 'Asistente Demo', widget_color: '#00a79d',
    welcome_message: '¡Hola! ¿En qué puedo ayudarte?', languages: ['es'] },
}
const routes = (extra = {}) => ({
  'POST /public/chat/demo/sessions': () => json(SESSION, 201), ...extra })
const open = () => renderApp({ '/c/:slug': <ChatPage /> }, '/c/demo')
const input = () => screen.getByPlaceholderText('Escribe tu consulta…')
const say = (user, text) => user.type(input(), `${text}{Enter}`)
const serverEvent = (event, data = {}) =>
  act(() => { WebSocket.instances[0].onmessage({ data: JSON.stringify({ event, data }) }) })
const talkToPerson = () => screen.getByRole('button', { name: /Hablar con una persona/ })

describe('Chat público', () => {
  it('crea la sesión, muestra la bienvenida y abre el WebSocket con el token', async () => {
    const f = mockFetch(routes())
    open()
    expect(await screen.findByText('Asistente Demo')).toBeInTheDocument()
    expect(screen.getByText('¡Hola! ¿En qué puedo ayudarte?')).toBeInTheDocument()
    expect(JSON.parse(f.called('POST /public/chat/demo/sessions')[0].opts.body).lang).toBe('es')
    expect(WebSocket.instances[0].url).toBe('ws://test/ws/chat/s1?token=tok-123')
  })

  it('envía el mensaje con el session token y muestra la respuesta del bot', async () => {
    const f = mockFetch(routes({
      'POST /public/chat/sessions/s1/messages': { message_id: 'm1', escalation: null,
        bot_reply: { message_id: 'b1', content: 'Entra a Salud > Exámenes > Subir archivo.',
          agent_type: 'technical', sources_used: 2 } },
    }))
    const user = userEvent.setup()
    open()
    await screen.findByText('Asistente Demo')
    await say(user, 'No puedo subir mi examen')
    expect(await screen.findByText('Entra a Salud > Exámenes > Subir archivo.')).toBeInTheDocument()
    expect(screen.getByText('No puedo subir mi examen')).toBeInTheDocument()
    const call = f.called('POST /public/chat/sessions/s1/messages')[0]
    expect(call.opts.headers.Authorization).toBe('Bearer tok-123')
    expect(JSON.parse(call.opts.body)).toEqual({ content: 'No puedo subir mi examen' })
  })

  it('muestra el error del backend como línea de sistema', async () => {
    mockFetch(routes({
      'POST /public/chat/sessions/s1/messages':
        fail(400, 'DEEPSEEK_KEY_MISSING', 'La empresa no tiene API key configurada o válida.'),
    }))
    const user = userEvent.setup()
    open()
    await screen.findByText('Asistente Demo')
    await say(user, 'Hola')
    expect(await screen.findByText(/La empresa no tiene API key configurada o válida/)).toBeInTheDocument()
  })

  it('deriva a una persona (en vivo) y oculta el botón', async () => {
    mockFetch(routes({
      'POST /public/chat/sessions/s1/escalate': { mode: 'live', queue_position: 1 } }))
    const user = userEvent.setup()
    open()
    await screen.findByText('Asistente Demo')
    await user.click(talkToPerson())
    expect(await screen.findByText(/posición 1/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Hablar con una persona/ })).not.toBeInTheDocument()
  })

  it('deriva a ticket cuando no hay agentes disponibles', async () => {
    mockFetch(routes({
      'POST /public/chat/sessions/s1/escalate': { mode: 'ticket', ticket_number: 'T-1001' } }))
    const user = userEvent.setup()
    open()
    await screen.findByText('Asistente Demo')
    await user.click(talkToPerson())
    expect(await screen.findByText(/ticket #T-1001/)).toBeInTheDocument()
  })

  it('muestra en tiempo real lo que llega por WebSocket del agente', async () => {
    mockFetch(routes())
    open()
    await screen.findByText('Asistente Demo')
    serverEvent('agent.joined', { agent_name: 'Sofía' })
    expect(await screen.findByText(/Sofía se unió a la conversación/)).toBeInTheDocument()
    serverEvent('message.agent', { content: 'Hola María, reviso tu caso.', agent_name: 'Sofía' })
    expect(await screen.findByText('Hola María, reviso tu caso.')).toBeInTheDocument()
  })

  it('al cerrarse la sesión permite valorar la atención una sola vez', async () => {
    const f = mockFetch(routes({
      'POST /public/chat/sessions/s1/rating': () => json({ saved: true }, 201) }))
    const user = userEvent.setup()
    open()
    await screen.findByText('Asistente Demo')
    serverEvent('session.closed')
    expect(await screen.findByText('¿Cómo estuvo la atención?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '👍' }))
    expect(await screen.findByText(/Gracias por tu valoración/)).toBeInTheDocument()
    expect(JSON.parse(f.called('POST /public/chat/sessions/s1/rating')[0].opts.body))
      .toEqual({ rating: 'up' })
    expect(screen.queryByRole('button', { name: '👍' })).not.toBeInTheDocument()
  })

  it('muestra el error si la empresa no existe', async () => {
    mockFetch({ 'POST /public/chat/demo/sessions':
      fail(404, 'TENANT_NOT_FOUND', 'No existe una empresa con ese slug.') })
    open()
    expect(await screen.findByText(/No existe una empresa con ese slug/)).toBeInTheDocument()
  })
})
