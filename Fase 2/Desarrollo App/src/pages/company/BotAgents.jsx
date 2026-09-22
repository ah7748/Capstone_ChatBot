import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Loading, Modal, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

export default function BotAgents() {
  const { t } = useI18n()
  const toast = useToast()
  const [agents, setAgents] = useState(null)
  const [preview, setPreview] = useState(null) // {agent_type, message, result}

  const load = () => api('/company/bot-agents').then(d => setAgents(d.agents)).catch(e => toast(errText(e)))
  useEffect(() => { load() }, [])

  async function save(agent) {
    try {
      await api(`/company/bot-agents/${agent.agent_type}`, { method: 'PATCH', body: {
        display_name: agent.display_name, topics: agent.topics,
        system_prompt: agent.system_prompt, enabled: agent.enabled } })
      toast('Agente guardado')
      load()
    } catch (e) { toast(errText(e)) }
  }

  async function runPreview() {
    setPreview(p => ({ ...p, result: 'loading' }))
    try {
      const r = await api(`/company/bot-agents/${preview.agent_type}/preview`, {
        method: 'POST', body: { message: preview.message } })
      setPreview(p => ({ ...p, result: r }))
    } catch (e) { setPreview(p => ({ ...p, result: { error: errText(e) } })) }
  }

  if (!agents) return <Loading t={t} />
  const set = (i, k) => e => setAgents(a => a.map((x, j) => j === i
    ? { ...x, [k]: e.target?.type === 'checkbox' ? e.target.checked : e.target.value } : x))

  return (
    <>
      <div className="page-head"><h1>{t('Agentes del bot')}</h1>
        <div className="sub">El clasificador de intención decide cuál responde cada consulta;
          cada agente usa solo los documentos de su tipo.</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {agents.map((a, i) => (
          <div className="panel" key={a.agent_type}>
            <div className="panel-head">
              <h3>{a.agent_type === 'technical' ? '🛠️ Agente de soporte técnico' : '💼 Agente de soporte comercial'}</h3>
              <div className="spacer" />
              <Badge kind={a.enabled ? 'ok' : 'off'}>{a.enabled ? 'Activo' : 'Inactivo'}</Badge>
            </div>
            <div className="panel-body">
              <div className="field"><label>Nombre visible</label>
                <input value={a.display_name} onChange={set(i, 'display_name')} /></div>
              <div className="field"><label>Atiende consultas sobre</label>
                <input value={a.topics || ''} onChange={set(i, 'topics')} /></div>
              <div className="field"><label>Instrucciones (prompt del agente)</label>
                <textarea rows={3} value={a.system_prompt || ''} onChange={set(i, 'system_prompt')} /></div>
              <div className="field" style={{ fontSize: 12.5, color: 'var(--muted)' }}>
                Últimos 7 días: {a.metrics_7d.conversations} conversaciones ·
                {' '}{a.metrics_7d.resolved_pct}% resueltas
              </div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <button className="btn btn-primary" onClick={() => save(a)}>{t('Guardar')}</button>
                <button className="btn btn-ghost" onClick={() =>
                  setPreview({ agent_type: a.agent_type, message: '', result: null })}>
                  Probar en vista previa</button>
                {a.agent_type === 'commercial' && (
                  <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
                    <input type="checkbox" checked={a.enabled} onChange={set(i, 'enabled')} />
                    Activo
                  </label>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {preview && (
        <Modal title={`Vista previa · ${preview.agent_type === 'technical' ? '🛠️ Técnico' : '💼 Comercial'}`}
          width={640} onClose={() => setPreview(null)}
          footer={<button className="btn btn-soft" onClick={() => setPreview(null)}>{t('Cerrar')}</button>}>
          <div className="field">
            <div style={{ display: 'flex', gap: 8 }}>
              <input style={{ flex: 1 }} placeholder={t('Escribe tu consulta…')}
                value={preview.message}
                onChange={e => setPreview(p => ({ ...p, message: e.target.value }))}
                onKeyDown={e => e.key === 'Enter' && runPreview()} />
              <button className="btn btn-primary" onClick={runPreview}>{t('Enviar')}</button>
            </div>
          </div>
          {preview.result === 'loading' && <Loading t={t} />}
          {preview.result?.error && <div className="login-error">{preview.result.error}</div>}
          {preview.result?.answer && (
            <>
              <div className="msg bot" style={{ float: 'none', maxWidth: 'none' }}>{preview.result.answer}</div>
              <div style={{ fontSize: 12, color: 'var(--muted)', clear: 'both' }}>
                Fuentes: {preview.result.sources.map(s => s.document).join(' · ') || '—'}
                {' '}· {preview.result.tokens_used} tokens · {preview.result.latency_ms} ms
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  )
}
