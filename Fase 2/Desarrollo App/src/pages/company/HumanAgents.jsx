import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, CHAT_TYPE_BADGE, Loading, Modal, STATUS_BADGE, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

const EMPTY = { name: '', email: '', escalation_type: 'technical', channel: 'web' }

export default function HumanAgents() {
  const { t } = useI18n()
  const toast = useToast()
  const [data, setData] = useState(null)
  const [editing, setEditing] = useState(null) // {form, agent_id|null}
  const [busy, setBusy] = useState(false)

  const load = () => api('/company/human-agents?page_size=100').then(setData).catch(e => toast(errText(e)))
  useEffect(() => { load() }, [])

  async function save() {
    setBusy(true)
    try {
      if (editing.agent_id) {
        await api(`/company/human-agents/${editing.agent_id}`, { method: 'PATCH', body: editing.form })
        toast('Agente actualizado')
      } else {
        await api('/company/human-agents', { method: 'POST', body: editing.form })
        toast('Agente creado: recibirá la invitación por email')
      }
      setEditing(null); load()
    } catch (e) { toast(errText(e)) } finally { setBusy(false) }
  }

  async function remove(a) {
    if (!confirm(`¿Eliminar a ${a.name}? Sus conversaciones activas se reasignarán.`)) return
    try {
      const r = await api(`/company/human-agents/${a.agent_id}?confirm=true`, { method: 'DELETE' })
      toast(`Agente eliminado · reasignadas ${r.reassigned.live} en vivo y ${r.reassigned.tickets} tickets`)
      load()
    } catch (e) { toast(errText(e)) }
  }

  if (!data) return <Loading t={t} />
  const set = k => e => setEditing(ed => ({ ...ed, form: { ...ed.form, [k]: e.target.value } }))
  return (
    <>
      <div className="page-head">
        <h1>{t('Agentes humanos')}</h1>
        <div className="spacer" />
        <button className="btn btn-primary" onClick={() => setEditing({ form: EMPTY, agent_id: null })}>
          + {t('Nuevo agente humano')}</button>
        <div className="sub">Personas que reciben las conversaciones derivadas por el bot.
          Cada empresa administra los suyos.</div>
      </div>
      <div className="panel">
        <table>
          <thead><tr>
            <th>Agente</th><th>{t('Recibe derivaciones de')}</th><th>{t('Canal')}</th>
            <th>{t('Estado')}</th><th>Carga</th><th>{t('Acciones')}</th>
          </tr></thead>
          <tbody>
            {data.items.map(a => {
              const [ck, cl] = CHAT_TYPE_BADGE[a.escalation_type] || ['off', a.escalation_type]
              const [sk, sl] = STATUS_BADGE[a.status] || ['off', a.status]
              return (
                <tr key={a.agent_id}>
                  <td><b>{a.name}</b><br />
                    <span style={{ color: 'var(--muted)', fontSize: 12 }}>{a.email}</span></td>
                  <td><Badge kind={ck}>{cl}</Badge></td>
                  <td>💻 Chat web</td>
                  <td><Badge kind={sk}>{sl}</Badge></td>
                  <td>{a.live_count} en vivo · {a.open_tickets} tickets</td>
                  <td style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-soft btn-sm" onClick={() => setEditing({
                      agent_id: a.agent_id,
                      form: { name: a.name, email: a.email, escalation_type: a.escalation_type,
                        channel: a.channel } })}>{t('Editar')}</button>
                    <button className="btn btn-soft btn-sm" onClick={() => remove(a)}>{t('Eliminar')}</button>
                  </td>
                </tr>
              )
            })}
            {data.items.length === 0 && (
              <tr><td colSpan={6} style={{ color: 'var(--muted)' }}>Sin agentes humanos aún.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal title={editing.agent_id ? 'Editar agente humano' : t('Nuevo agente humano')}
          onClose={() => setEditing(null)} footer={<>
            <button className="btn btn-soft" onClick={() => setEditing(null)}>{t('Cancelar')}</button>
            <button className="btn btn-primary" disabled={busy} onClick={save}>{t('Guardar')}</button>
          </>}>
          <div className="field"><label>Nombre completo</label>
            <input value={editing.form.name} onChange={set('name')} /></div>
          <div className="field"><label>Email</label>
            <input type="email" value={editing.form.email} onChange={set('email')} />
            <div className="hint">Recibirá una invitación para acceder a la consola de agente.</div></div>
          <div className="field"><label>{t('Recibe derivaciones de')}</label>
            <select value={editing.form.escalation_type} onChange={set('escalation_type')}>
              <option value="technical">🛠️ Agente de soporte técnico</option>
              <option value="commercial">💼 Agente de soporte comercial</option>
              <option value="both">🛠️💼 Ambos</option>
            </select></div>
          <div className="field"><label>Canal de derivación</label>
            <select value={editing.form.channel} onChange={set('channel')}>
              <option value="web">💻 Chat web</option>
            </select>
            <div className="hint">WhatsApp: próximamente.</div></div>
        </Modal>
      )}
    </>
  )
}
