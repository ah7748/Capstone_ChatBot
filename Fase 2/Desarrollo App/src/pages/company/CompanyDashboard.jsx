import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, CHAT_TYPE_BADGE, Kpi, Loading, Modal, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

const METRIC_TITLES = {
  conversations: 'Conversaciones', resolved: 'Resueltas por el bot',
  pending_tickets: 'Tickets pendientes', escalations: 'Derivadas a agente',
}

export default function CompanyDashboard() {
  const { t } = useI18n()
  const toast = useToast()
  const [data, setData] = useState(null)
  const [metric, setMetric] = useState(null)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    api('/company/dashboard?period=7d').then(setData).catch(e => toast(errText(e)))
  }, [])

  useEffect(() => {
    if (!metric) { setDetail(null); return }
    api(`/company/dashboard/detail?metric=${metric}&page_size=50`)
      .then(setDetail).catch(e => toast(errText(e)))
  }, [metric])

  if (!data) return <Loading t={t} />
  const k = data.kpis
  return (
    <>
      <div className="page-head"><h1>{t('Dashboard')}</h1>
        <div className="sub">Actividad del chatbot de soporte de tu empresa (últimos 7 días).</div>
      </div>
      <div className="cards-row">
        <Kpi label={t('Conversaciones')} value={k.conversations} more={t('Ver detalle →')}
          onClick={() => setMetric('conversations')} />
        <Kpi label={t('Resueltas por el bot')} value={`${k.bot_resolved_pct}%`} more={t('Ver detalle →')}
          onClick={() => setMetric('resolved')} />
        <Kpi label={t('Tickets pendientes')} value={k.pending_tickets}
          extra={`${k.pending_unassigned} sin asignar`} more={t('Ver detalle →')}
          onClick={() => setMetric('pending_tickets')} />
        <Kpi label={t('Derivadas a agente')} value={k.escalations} more={t('Ver detalle →')}
          onClick={() => setMetric('escalations')} />
        <Kpi label={t('Tokens consumidos')} value={k.tokens.toLocaleString()}
          extra={`${k.token_limit_pct}% del límite`} />
      </div>
      {data.top_topics.length > 0 && (
        <div className="panel">
          <div className="panel-head"><h3>Temas más consultados</h3></div>
          <table>
            <thead><tr><th>#</th><th>Tema</th><th>Consultas</th></tr></thead>
            <tbody>{data.top_topics.map((row, i) => (
              <tr key={i}><td>{i + 1}</td><td>{row.topic}</td><td>{row.count}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {metric && (
        <Modal title={t(METRIC_TITLES[metric])} width={820} onClose={() => setMetric(null)}
          footer={<button className="btn btn-soft" onClick={() => setMetric(null)}>{t('Cerrar')}</button>}>
          {!detail ? <Loading t={t} /> : (
            <table>
              <thead>{metric === 'pending_tickets' ? (
                <tr><th>Ticket</th><th>{t('Usuario')}</th><th>Tema</th><th>Tipo</th>
                  <th>Asignado</th><th>Desde</th></tr>
              ) : (
                <tr><th>{t('Usuario')}</th><th>{t('Canal')}</th><th>Tipo</th><th>Fecha</th>
                  <th>{metric === 'escalations' ? t('Motivo') : t('Estado')}</th>
                  {metric === 'resolved' && <th>Valoración</th>}</tr>
              )}</thead>
              <tbody>
                {detail.items.map(row => {
                  const [ck, cl] = CHAT_TYPE_BADGE[row.chat_type] || ['off', row.chat_type]
                  return metric === 'pending_tickets' ? (
                    <tr key={row.ticket_id}>
                      <td><b>#{row.number}</b></td><td>{row.user_name || '—'}</td>
                      <td>{row.topic || '—'}</td><td><Badge kind={ck}>{cl}</Badge></td>
                      <td>{row.assigned_to || <Badge kind="danger">Sin asignar</Badge>}</td>
                      <td>{new Date(row.waiting_since).toLocaleString()}</td>
                    </tr>
                  ) : (
                    <tr key={row.conversation_id}>
                      <td>{row.user_name || '—'}</td>
                      <td><Badge kind="navy">{row.channel}</Badge></td>
                      <td><Badge kind={ck}>{cl}</Badge></td>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td>{metric === 'escalations' ? (row.escalation_reason || '—') : row.status}</td>
                      {metric === 'resolved' && <td>{row.rating === 'up' ? '👍' : row.rating === 'down' ? '👎' : '—'}</td>}
                    </tr>
                  )
                })}
                {detail.items.length === 0 && (
                  <tr><td colSpan={6} style={{ color: 'var(--muted)' }}>Sin registros en el período.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </Modal>
      )}
    </>
  )
}
