import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, CHAT_TYPE_BADGE, Loading, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

const PRESENCE = { available: ['ok', 'Disponible'], busy: ['warn', 'Ocupado'], offline: ['off', 'Desconectado'] }

/** Vista consolidada de solo lectura: cada empresa administra sus propios agentes. */
export default function PlatformAgents() {
  const { t } = useI18n()
  const toast = useToast()
  const [data, setData] = useState(null)

  useEffect(() => {
    api('/platform/human-agents?page_size=100').then(setData).catch(e => toast(errText(e)))
  }, [])

  if (!data) return <Loading t={t} />
  return (
    <>
      <div className="page-head">
        <h1>{t('Agentes de soporte')}</h1>
        <Badge kind="navy">{t('Solo lectura')}</Badge>
        <div className="sub">Vista consolidada; cada empresa crea, modifica y elimina los suyos.</div>
      </div>
      <div className="panel">
        <table>
          <thead><tr>
            <th>Agente</th><th>Empresa</th><th>{t('Recibe derivaciones de')}</th>
            <th>{t('Canal')}</th><th>{t('Estado')}</th><th>{t('En vivo')}</th><th>Tickets</th>
          </tr></thead>
          <tbody>
            {data.items.map(a => {
              const [tk, tl] = CHAT_TYPE_BADGE[a.escalation_type] || ['off', a.escalation_type]
              const [pk, pl] = PRESENCE[a.presence] || ['off', a.presence]
              return (
                <tr key={a.agent_id}>
                  <td><b>{a.name}</b><br />
                    <span style={{ color: 'var(--muted)', fontSize: 12 }}>{a.email}</span></td>
                  <td>{a.tenant_name}</td>
                  <td><Badge kind={tk}>{tl}</Badge></td>
                  <td>💻 Chat web</td>
                  <td><Badge kind={pk}>{pl}</Badge></td>
                  <td>{a.live_count}</td>
                  <td>{a.open_tickets}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
